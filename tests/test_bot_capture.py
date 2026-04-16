from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import pytest
from backend.bot import cmd_note, cmd_think, cmd_return, cmd_recall, cmd_help
from backend.classifier import ClassifyResult, SuggestedTask


@dataclass
class _FakeMessage:
    text: str
    chat_id: int
    message_id: int
    replies: list = None

    def __post_init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


@dataclass
class _FakeUpdate:
    message: _FakeMessage

    @property
    def effective_chat(self):
        class _C:
            id = self.message.chat_id
        return _C()


class _FakeContext:
    def __init__(self, args: list[str]):
        self.args = args
        self.bot_data: dict = {}


def _build_context_with_deps(tmp_path: Path, classifier, search_results=None) -> _FakeContext:
    """Populate bot_data with a CaptureDeps the handlers expect."""
    from backend.capture import CaptureDeps
    from backend.pending_queue import PendingQueue
    from backend.tasks_store import TasksStore
    from backend.undo_buffer import UndoBuffer

    class _Mem:
        def __init__(self, results):
            self.results = results or []
            self.stored = []

        async def store(self, content, project):
            self.stored.append((content, project))
            return True

        async def search(self, query, limit=10):
            return self.results

    mem = _Mem(search_results)
    deps = CaptureDeps(
        tasks=TasksStore(tmp_path / "tasks.json"),
        undo=UndoBuffer(60),
        pending=PendingQueue(tmp_path / "pending.jsonl"),
        memory_store=mem.store,
        classifier=classifier,
        today_fn=lambda: date(2026, 4, 16),
        resurface_path=tmp_path / "resurface.jsonl",
    )
    ctx = _FakeContext(args=[])
    ctx.bot_data["deps"] = deps
    ctx.bot_data["memory_search"] = mem.search
    return ctx, mem


@pytest.mark.asyncio
async def test_cmd_note_high_confidence_creates_task(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.9,
            suggested_task=SuggestedTask("corpfin", "Pset 4", "2026-04-24", "pset", "15%"),
            tags=["corpfin"],
        )
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    ctx.args = ["pset", "4", "due", "friday", "15%"]
    msg = _FakeMessage(text="/note pset 4 due friday 15%", chat_id=1, message_id=10)
    update = _FakeUpdate(message=msg)
    await cmd_note(update, ctx)
    assert msg.replies
    assert "✅" in msg.replies[0][0] or "Task created" in msg.replies[0][0]


@pytest.mark.asyncio
async def test_cmd_note_low_confidence_sends_buttons(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.4,
            suggested_task=SuggestedTask("life", "call mom", None, "admin", None),
            tags=["life"],
        )
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    ctx.args = ["call", "mom"]
    msg = _FakeMessage(text="/note call mom", chat_id=1, message_id=10)
    await cmd_note(_FakeUpdate(message=msg), ctx)
    assert msg.replies
    reply_kwargs = msg.replies[0][1]
    assert "reply_markup" in reply_kwargs


@pytest.mark.asyncio
async def test_cmd_note_empty_shows_usage(tmp_path):
    def cls(*a, **kw):
        raise AssertionError("classifier should not run")
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    ctx.args = []
    msg = _FakeMessage(text="/note", chat_id=1, message_id=10)
    await cmd_note(_FakeUpdate(message=msg), ctx)
    assert any("give me" in r[0].lower() or "usage" in r[0].lower() for r in msg.replies)


@pytest.mark.asyncio
async def test_cmd_think_returns_save_and_related(tmp_path):
    def cls(*a, **kw):
        raise AssertionError("no classifier for /think")
    ctx, mem = _build_context_with_deps(tmp_path, cls, search_results=[{"text": "earlier thought"}])
    ctx.args = ["pricing", "idea"]
    msg = _FakeMessage(text="/think pricing idea", chat_id=1, message_id=10)
    await cmd_think(_FakeUpdate(message=msg), ctx)
    assert any("earlier thought" in r[0] or "Saved" in r[0] for r in msg.replies)


@pytest.mark.asyncio
async def test_cmd_return_saves_with_trigger(tmp_path):
    def cls(*a, **kw):
        raise AssertionError("no classifier for /return")
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    ctx.args = ["review", "later"]
    msg = _FakeMessage(text="/return review later", chat_id=1, message_id=10)
    await cmd_return(_FakeUpdate(message=msg), ctx)
    assert any("resurface" in r[0].lower() or "2026-04-17" in r[0] for r in msg.replies)


@pytest.mark.asyncio
async def test_cmd_recall_returns_hits(tmp_path):
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None, search_results=[{"text": "pricing a"}, {"text": "pricing b"}])
    ctx.args = ["pricing"]
    msg = _FakeMessage(text="/recall pricing", chat_id=1, message_id=10)
    await cmd_recall(_FakeUpdate(message=msg), ctx)
    assert any("pricing a" in r[0] for r in msg.replies)


@pytest.mark.asyncio
async def test_cmd_help_lists_all_new_commands(tmp_path):
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    msg = _FakeMessage(text="/help", chat_id=1, message_id=10)
    await cmd_help(_FakeUpdate(message=msg), ctx)
    reply = msg.replies[0][0]
    for cmd in ["/note", "/think", "/return", "/recall", "/briefing", "/help"]:
        assert cmd in reply


@pytest.mark.asyncio
async def test_cmd_note_markdown_chars_in_task_name_are_escaped(tmp_path):
    """Real user notes contain _, *, [ — Telegram Markdown must not blow up."""
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.9,
            suggested_task=SuggestedTask("projects", "refactor call_site[x]", "2026-04-24", "admin", "5%"),
            tags=["projects"],
        )
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    ctx.args = ["refactor", "call_site[x]"]
    msg = _FakeMessage(text="/note refactor call_site[x]", chat_id=1, message_id=10)
    await cmd_note(_FakeUpdate(message=msg), ctx)
    reply = msg.replies[0][0]
    # Escaped form uses backslashes before _ and [ (version=1 escapes _ and [ but not ])
    assert "call\\_site\\[x" in reply


@pytest.mark.asyncio
async def test_cmd_help_does_not_claim_add_done_undo_exist_as_bot_commands(tmp_path):
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    msg = _FakeMessage(text="/help", chat_id=1, message_id=10)
    await cmd_help(_FakeUpdate(message=msg), ctx)
    reply = msg.replies[0][0]
    # These are Mini App–only operations, not bot commands. Help should not
    # present them as bot commands (would mislead users who try /done and
    # get silent "unknown command").
    assert "/done" not in reply.split("Mini App")[0]  # should not appear before the Mini App note


@dataclass
class _FakeCallbackQuery:
    data: str
    message: _FakeMessage
    from_user_id: int = 1
    answers: list = None
    edited: list = None

    def __post_init__(self):
        self.answers = []
        self.edited = []

    async def answer(self, text=None, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, **kwargs):
        self.edited.append(text)


@dataclass
class _CallbackUpdate:
    callback_query: _FakeCallbackQuery

    @property
    def effective_chat(self):
        class _C:
            id = 1
        return _C()


@pytest.mark.asyncio
async def test_callback_create_task_creates_task(tmp_path):
    from backend.bot import cb_capture
    def cls(*a, **kw):
        raise AssertionError("no classifier during callback")
    ctx, _ = _build_context_with_deps(tmp_path, cls)
    pending_id = "1-10"
    ctx.bot_data.setdefault("pending", {})[pending_id] = {
        "raw_text": "call mom",
        "suggested_task": SuggestedTask("life", "call mom", None, "admin", None),
    }
    msg = _FakeMessage(text="buttons", chat_id=1, message_id=11)
    cq = _FakeCallbackQuery(data=f"capt:create:{pending_id}", message=msg)
    await cb_capture(_CallbackUpdate(callback_query=cq), ctx)
    tasks = ctx.bot_data["deps"].tasks.list()
    assert any(t.name == "call mom" for t in tasks)
    assert cq.edited and "Task created" in cq.edited[0]


@pytest.mark.asyncio
async def test_callback_thought_does_not_create_task(tmp_path):
    from backend.bot import cb_capture
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    pending_id = "1-10"
    ctx.bot_data.setdefault("pending", {})[pending_id] = {
        "raw_text": "idea x", "suggested_task": None,
    }
    msg = _FakeMessage(text="buttons", chat_id=1, message_id=11)
    cq = _FakeCallbackQuery(data=f"capt:thought:{pending_id}", message=msg)
    await cb_capture(_CallbackUpdate(callback_query=cq), ctx)
    assert ctx.bot_data["deps"].tasks.list() == []
    assert cq.edited and "thought" in cq.edited[0].lower()


@pytest.mark.asyncio
async def test_undo_within_window_deletes_task(tmp_path):
    from backend.bot import on_text_maybe_undo
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    deps = ctx.bot_data["deps"]
    # Seed a task + undo entry
    from backend.tasks_store import Task
    t = Task(id="x-1", course="life", name="n", due="2026-04-20", type="admin", weight="", done=False)
    deps.tasks.add(t)
    deps.undo.register(chat_id=1, message_id=100, task_id="x-1")

    msg = _FakeMessage(text="undo", chat_id=1, message_id=200)
    await on_text_maybe_undo(_FakeUpdate(message=msg), ctx)
    assert deps.tasks.list() == []
    assert any("Reverted" in r[0] for r in msg.replies)


@pytest.mark.asyncio
async def test_undo_without_pending_is_noop(tmp_path):
    from backend.bot import on_text_maybe_undo
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    msg = _FakeMessage(text="undo", chat_id=1, message_id=200)
    await on_text_maybe_undo(_FakeUpdate(message=msg), ctx)
    # No reply is fine (not-our-message style), OR an explicit "nothing to undo".
    # We assert no crash and no task changes.
    assert ctx.bot_data["deps"].tasks.list() == []


@pytest.mark.asyncio
async def test_non_undo_text_is_ignored(tmp_path):
    from backend.bot import on_text_maybe_undo
    ctx, _ = _build_context_with_deps(tmp_path, lambda *a, **kw: None)
    msg = _FakeMessage(text="hello there", chat_id=1, message_id=200)
    await on_text_maybe_undo(_FakeUpdate(message=msg), ctx)
    # Silent: no reply, no crash.
    assert msg.replies == []
