"""Telegram bot entrypoint. Modes: bot | send | setup-menu.

  python -m backend.bot bot          # long-running polling bot
  python -m backend.bot send         # one-shot daily briefing (cron)
  python -m backend.bot setup-menu   # set chat menu button to open the miniapp
"""
from __future__ import annotations
import asyncio
import logging
import sys
from datetime import date

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters,
)

from pathlib import Path

from .briefing import generate_briefing
from .capture import (
    CaptureDeps, CaptureOutcome,
    process_note, process_think, process_return, process_recall,
    confirm_create_task, write_resurface,
)
from .classifier import classify as default_classify, SuggestedTask
from .config import load_settings
from .memory import store_memory, search_memory
from .pending_queue import PendingQueue
from .tasks_store import TasksStore
from .undo_buffer import UndoBuffer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def _build_capture_deps(settings) -> CaptureDeps:
    data_dir = Path(settings.tasks_path).parent
    return CaptureDeps(
        tasks=TasksStore(settings.tasks_path),
        undo=UndoBuffer(ttl_seconds=60),
        pending=PendingQueue(data_dir / "membase_pending.jsonl"),
        memory_store=store_memory,
        classifier=default_classify,
        today_fn=lambda: date.today(),
        resurface_path=data_dir / "resurface.jsonl",
    )


HELP_TEXT = (
    "*Commands*\n"
    "/briefing — today's schedule + due items\n"
    "/note <text> — capture; I classify\n"
    "/think <text> — save as thought, surface related\n"
    "/return <text> [| in N days | next monday] — resurface later\n"
    "/recall <query> — search your captured notes\n"
    "/add <course> | <name> | <YYYY-MM-DD> — structured task\n"
    "/done <id>, /undo <id> — mark / unmark task\n"
    "/help — this message"
)


def _open_dashboard_markup(miniapp_url: str) -> InlineKeyboardMarkup | None:
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("📱 Open Dashboard", web_app=WebAppInfo(url=miniapp_url))]])


async def _send_briefing(app: Application, chat_id: str, miniapp_url: str) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    await app.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(miniapp_url),
    )


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    await update.message.reply_text(
        "Academic Scheduler ready. Use /briefing for today's plan or tap the menu to open the dashboard.",
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )


async def cmd_briefing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )


def _confirmation_markup(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Create task", callback_data=f"capt:create:{pending_id}"),
            InlineKeyboardButton("💭 Thought", callback_data=f"capt:thought:{pending_id}"),
            InlineKeyboardButton("🔁 Later", callback_data=f"capt:later:{pending_id}"),
        ],
    ])


def _format_task_reply(outcome: CaptureOutcome) -> str:
    t = outcome.task
    parts = [f"✅ Task created: `{t.id}` — {t.name}", f"due {t.due}"]
    if t.weight:
        parts.append(t.weight)
    parts.append(f"type {t.type}")
    flag = " ⚠️ no due date found; defaulted" if outcome.defaulted_due else ""
    return ". ".join(parts) + "." + flag + '\nReply "undo" within 60s to revert.'


def _format_thought_reply(outcome: CaptureOutcome) -> str:
    lines = ["💭 Saved."]
    if outcome.tags:
        lines[0] += f" Tagged: [{', '.join(outcome.tags)}]"
    for hit in outcome.recall_hits[:3]:
        snippet = (hit.get("text") or hit.get("content") or "").strip()[:120]
        if snippet:
            lines.append(f"  · {snippet}")
    if outcome.membase_queued:
        lines.append("  (Membase unavailable — queued locally.)")
    return "\n".join(lines)


def _format_resurface_reply(outcome: CaptureOutcome) -> str:
    if outcome.trigger_date:
        return f"🔁 Will resurface on {outcome.trigger_date}."
    return "🔁 Saved. (Trigger not auto-parsed — find this with /recall later.)"


def _format_recall_reply(outcome: CaptureOutcome) -> str:
    if not outcome.recall_hits:
        return "No matching notes found."
    lines = ["*Recall:*"]
    for hit in outcome.recall_hits:
        snippet = (hit.get("text") or hit.get("content") or "").strip()[:140]
        if snippet:
            lines.append(f"  · {snippet}")
    return "\n".join(lines)


def _format_needs_confirmation(outcome: CaptureOutcome, raw_text: str) -> str:
    suggested = outcome.suggested_task
    head = "I think this is a task, but I'm not sure. Pick one:"
    if suggested:
        return f"{head}\n→ would create: `{suggested.category}` · {suggested.name} · due {suggested.due or '(default +7d)'} · type {suggested.type}"
    return f"{head}\n→ raw: {raw_text[:120]}"


async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps: CaptureDeps = context.bot_data["deps"]
    msg = update.message
    text = " ".join(context.args) if context.args else ""
    outcome = await process_note(text, chat_id=msg.chat_id, message_id=msg.message_id, deps=deps)

    if outcome.kind == "usage":
        await msg.reply_text("Give me something to capture. Usage: /note <text>")
        return
    if outcome.kind == "task_created":
        await msg.reply_text(_format_task_reply(outcome), parse_mode=ParseMode.MARKDOWN)
        return
    if outcome.kind == "thought_saved":
        await msg.reply_text(_format_thought_reply(outcome))
        return
    if outcome.kind == "resurface_saved":
        await msg.reply_text(_format_resurface_reply(outcome))
        return
    if outcome.kind == "needs_confirmation":
        # Stash the suggested task + raw text under a short pending_id keyed on chat/msg.
        pending_id = f"{msg.chat_id}-{msg.message_id}"
        context.bot_data.setdefault("pending", {})[pending_id] = {
            "raw_text": text,
            "suggested_task": outcome.suggested_task,
        }
        await msg.reply_text(
            _format_needs_confirmation(outcome, text),
            reply_markup=_confirmation_markup(pending_id),
        )
        return


async def cmd_think(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps: CaptureDeps = context.bot_data["deps"]
    memory_search = context.bot_data["memory_search"]
    msg = update.message
    text = " ".join(context.args) if context.args else ""
    outcome = await process_think(text, deps=deps, memory_search=memory_search)
    if outcome.kind == "usage":
        await msg.reply_text("Usage: /think <thought>")
        return
    await msg.reply_text(_format_thought_reply(outcome))


async def cmd_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps: CaptureDeps = context.bot_data["deps"]
    msg = update.message
    text = " ".join(context.args) if context.args else ""
    outcome = await process_return(text, deps=deps)
    if outcome.kind == "usage":
        await msg.reply_text("Usage: /return <text> [| in N days | next monday]")
        return
    await msg.reply_text(_format_resurface_reply(outcome))


async def cmd_recall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps: CaptureDeps = context.bot_data["deps"]
    memory_search = context.bot_data["memory_search"]
    msg = update.message
    query = " ".join(context.args) if context.args else ""
    outcome = await process_recall(query, deps=deps, memory_search=memory_search)
    if outcome.kind == "usage":
        await msg.reply_text("Usage: /recall <query>")
        return
    await msg.reply_text(_format_recall_reply(outcome), parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


def _build_app(token: str) -> Application:
    settings = load_settings()
    app = Application.builder().token(token).build()

    # Stash shared capture dependencies in bot_data so handlers can pull them.
    app.bot_data["deps"] = _build_capture_deps(settings)
    app.bot_data["memory_search"] = search_memory

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("think", cmd_think))
    app.add_handler(CommandHandler("return", cmd_return))
    app.add_handler(CommandHandler("recall", cmd_recall))
    app.add_handler(CommandHandler("help", cmd_help))
    return app


async def run_setup_menu() -> None:
    settings = load_settings()
    if not settings.miniapp_url:
        log.error("MINIAPP_URL is empty; set it in .env or via refresh_tunnel.sh first")
        sys.exit(2)
    app = _build_app(settings.telegram_bot_token)
    async with app:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Dashboard", web_app=WebAppInfo(url=settings.miniapp_url)),
        )
    log.info("Menu button set → %s", settings.miniapp_url)


async def run_send() -> None:
    settings = load_settings()
    if not settings.telegram_chat_id:
        log.error("TELEGRAM_CHAT_ID missing"); sys.exit(2)
    app = _build_app(settings.telegram_bot_token)
    async with app:
        await _send_briefing(app, settings.telegram_chat_id, settings.miniapp_url)
    log.info("Briefing sent.")


def run_bot() -> None:
    settings = load_settings()
    app = _build_app(settings.telegram_bot_token)
    log.info("Polling bot started. miniapp_url=%s", settings.miniapp_url or "(not set)")
    # Python 3.14 removed asyncio.get_event_loop()'s implicit-create behavior that
    # python-telegram-bot 21 relies on. Provide a loop explicitly.
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    if mode == "bot":
        run_bot()
    elif mode == "send":
        asyncio.run(run_send())
    elif mode == "setup-menu":
        asyncio.run(run_setup_menu())
    else:
        print(f"unknown mode: {mode}. use: bot | send | setup-menu"); sys.exit(2)


if __name__ == "__main__":
    main()
