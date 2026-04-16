from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from backend.capture import CaptureDeps, CaptureOutcome, process_note
from backend.classifier import ClassifyResult, SuggestedTask
from backend.pending_queue import PendingQueue
from backend.tasks_store import TasksStore
from backend.undo_buffer import UndoBuffer


class FakeMemory:
    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.stored: list[tuple[str, str | None]] = []

    async def store(self, content: str, project: str | None) -> bool:
        if not self.succeed:
            return False
        self.stored.append((content, project))
        return True


def _deps(tmp_path: Path, classifier, memory_succeeds: bool = True) -> tuple[CaptureDeps, FakeMemory]:
    store = TasksStore(tmp_path / "tasks.json")
    queue = PendingQueue(tmp_path / "pending.jsonl")
    buf = UndoBuffer(ttl_seconds=60)
    mem = FakeMemory(succeed=memory_succeeds)
    return CaptureDeps(
        tasks=store, undo=buf, pending=queue,
        memory_store=mem.store,
        classifier=classifier,
        today_fn=lambda: date(2026, 4, 16),
    ), mem


@pytest.mark.asyncio
async def test_high_confidence_task_writes_immediately(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.9,
            suggested_task=SuggestedTask("corpfin", "Pset 4", "2026-04-24", "pset", "15%"),
            tags=["corpfin"],
        )
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("pset 4 due friday 15%", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "task_created"
    assert outcome.task is not None
    assert outcome.task.name == "Pset 4"
    assert outcome.task.due == "2026-04-24"
    # Task written to tasks.json
    assert any(t.name == "Pset 4" for t in deps.tasks.list())
    # Membase write happened
    assert mem.stored and mem.stored[0][0].startswith("[NOTE]")
    # Membase write uses the project derived from classifier tags
    assert mem.stored[0][1] == "corpfin"
    # Undo entry registered
    entry = deps.undo.pop_latest(chat_id=1)
    assert entry is not None and entry.task_id == outcome.task.id


@pytest.mark.asyncio
async def test_low_confidence_task_returns_buttons_no_write(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.4,
            suggested_task=SuggestedTask("life", "call mom", None, "admin", None),
            tags=["life"],
        )
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("call mom", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "needs_confirmation"
    assert outcome.suggested_task is not None
    assert outcome.suggested_task.name == "call mom"
    # No task written
    assert deps.tasks.list() == []


@pytest.mark.asyncio
async def test_ambiguous_returns_buttons(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("hmm", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "needs_confirmation"
    assert outcome.suggested_task is None


@pytest.mark.asyncio
async def test_thought_just_saves(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="thought", confidence=0.9, suggested_task=None, tags=["projects"])
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("the api should be per-team", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "thought_saved"
    assert outcome.tags == ["projects"]
    assert deps.tasks.list() == []
    # Membase write uses the project derived from classifier tags
    assert mem.stored[0][1] == "projects"


@pytest.mark.asyncio
async def test_resurface_saves_with_default_trigger(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="resurface", confidence=0.8, suggested_task=None, tags=[])
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("remind me to read this article later", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "resurface_saved"
    # Default trigger is 3 days from today
    assert outcome.trigger_date == "2026-04-19"


@pytest.mark.asyncio
async def test_task_without_due_defaults_to_today_plus_7(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.9,
            suggested_task=SuggestedTask("projects", "ship landing page", None, "admin", None),
            tags=["projects"],
        )
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("ship landing page soon", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "task_created"
    assert outcome.task.due == "2026-04-23"
    assert outcome.defaulted_due is True


@pytest.mark.asyncio
async def test_membase_failure_appends_to_pending(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="thought", confidence=0.9, suggested_task=None, tags=[])
    deps, mem = _deps(tmp_path, cls, memory_succeeds=False)
    outcome = await process_note("a thought", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "thought_saved"
    assert outcome.membase_queued is True
    entries = list(deps.pending.iter_entries())
    assert len(entries) == 1
    assert entries[0]["content"].startswith("[NOTE]")


@pytest.mark.asyncio
async def test_empty_text_returns_usage(tmp_path):
    def cls(text, today, **_):
        raise AssertionError("classifier should not be called on empty text")
    deps, mem = _deps(tmp_path, cls)
    outcome = await process_note("", chat_id=1, message_id=10, deps=deps)
    assert outcome.kind == "usage"
    assert deps.tasks.list() == []
