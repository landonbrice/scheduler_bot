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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .briefing import generate_briefing
from .config import load_settings
from .tasks_store import TasksStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def _open_dashboard_markup(miniapp_url: str) -> InlineKeyboardMarkup | None:
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("📱 Open Dashboard", web_app=WebAppInfo(url=miniapp_url))]])


async def _send_briefing(app: Application, chat_id: str, miniapp_url: str) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    text = generate_briefing(store.list(), today=date.today())
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
    text = generate_briefing(store.list(), today=date.today())
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )


def _build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
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
