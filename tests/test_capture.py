from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from backend.capture import CaptureDeps, CaptureOutcome, process_note
from backend.classifier import ClassifyResult, SuggestedTask
from backend.pending_queue import PendingQueue
from backend.tasks_store import TasksStore
from backend.undo_buffer import UndoBuffer
from backend.capture import process_think, process_return, process_recall


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


class FakeMemoryWithSearch:
    def __init__(self, search_results: list[dict] | None = None, store_ok: bool = True):
        self.search_results = search_results or []
        self.store_ok = store_ok
        self.stored: list[tuple[str, str | None]] = []
        self.searched: list[tuple[str, int]] = []

    async def store(self, content: str, project: str | None) -> bool:
        if not self.store_ok:
            return False
        self.stored.append((content, project))
        return True

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        self.searched.append((query, limit))
        return self.search_results


def _deps_with_search(tmp_path, mem: FakeMemoryWithSearch):
    from backend.capture import CaptureDeps
    from backend.pending_queue import PendingQueue
    from backend.tasks_store import TasksStore
    from backend.undo_buffer import UndoBuffer
    return CaptureDeps(
        tasks=TasksStore(tmp_path / "tasks.json"),
        undo=UndoBuffer(ttl_seconds=60),
        pending=PendingQueue(tmp_path / "pending.jsonl"),
        memory_store=mem.store,
        classifier=lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no classifier for non-/note")),
        today_fn=lambda: date(2026, 4, 16),
        resurface_path=tmp_path / "resurface.jsonl",
    ), mem


@pytest.mark.asyncio
async def test_think_stores_and_returns_related(tmp_path):
    mem = FakeMemoryWithSearch(search_results=[{"text": "earlier thought about pricing"}])
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_think("pricing thoughts part 2", deps=deps, memory_search=mem.search)
    assert outcome.kind == "thought_saved"
    assert outcome.recall_hits == [{"text": "earlier thought about pricing"}]
    assert any(c.startswith("[THINKING]") for c, _ in mem.stored)


@pytest.mark.asyncio
async def test_think_empty_returns_usage(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_think("", deps=deps, memory_search=mem.search)
    assert outcome.kind == "usage"


@pytest.mark.asyncio
async def test_return_bare_uses_tomorrow(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_return("read that article", deps=deps)
    assert outcome.kind == "resurface_saved"
    assert outcome.trigger_date == "2026-04-17"
    import json
    lines = (tmp_path / "resurface.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["text"] == "read that article"
    assert entry["trigger_date"] == "2026-04-17"


@pytest.mark.asyncio
async def test_return_in_n_days(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_return("review plan | in 3 days", deps=deps)
    assert outcome.trigger_date == "2026-04-19"


@pytest.mark.asyncio
async def test_return_next_weekday(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    # 2026-04-16 is a Thursday. 'next monday' → 2026-04-20.
    outcome = await process_return("check pricing ideas | next monday", deps=deps)
    assert outcome.trigger_date == "2026-04-20"


@pytest.mark.asyncio
async def test_return_unparseable_trigger(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_return("review later | sometime soonish", deps=deps)
    assert outcome.kind == "resurface_saved"
    assert outcome.trigger_date is None


@pytest.mark.asyncio
async def test_recall_returns_hits(tmp_path):
    mem = FakeMemoryWithSearch(search_results=[{"text": "a"}, {"text": "b"}, {"text": "c"}])
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_recall("pricing", deps=deps, memory_search=mem.search)
    assert outcome.kind == "recall_results"
    assert len(outcome.recall_hits) == 3
    assert mem.searched == [("pricing", 5)]


@pytest.mark.asyncio
async def test_recall_empty_query_returns_usage(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_recall("", deps=deps, memory_search=mem.search)
    assert outcome.kind == "usage"


@pytest.mark.asyncio
async def test_confirm_create_task_whitespace_raw_text_uses_fallback(tmp_path):
    from backend.capture import confirm_create_task
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await confirm_create_task(
        suggested=None, raw_text="   ",
        chat_id=1, message_id=10, deps=deps,
    )
    assert outcome.kind == "task_created"
    assert outcome.task.name == "captured note"


@pytest.mark.asyncio
async def test_think_propagates_membase_queued(tmp_path):
    mem = FakeMemoryWithSearch(store_ok=False)
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_think("thought", deps=deps, memory_search=mem.search)
    assert outcome.membase_queued is True


@pytest.mark.asyncio
async def test_return_propagates_membase_queued(tmp_path):
    mem = FakeMemoryWithSearch(store_ok=False)
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_return("later thing", deps=deps)
    assert outcome.membase_queued is True


@pytest.mark.asyncio
async def test_return_tomorrow_keyword(tmp_path):
    mem = FakeMemoryWithSearch()
    deps, _ = _deps_with_search(tmp_path, mem)
    outcome = await process_return("read article | tomorrow", deps=deps)
    assert outcome.trigger_date == "2026-04-17"


# --- R2: CaptureResult shape tests ---

from backend.capture import CaptureResult
from datetime import date as _date


def test_capture_result_dataclass_shape():
    r = CaptureResult(
        classification="task",
        confidence=0.9,
        created_task_id="corpfin-pset-4",
        undo_token="1-10",
        memory_stored=True,
        classifier_offline=False,
        suggested_category="corpfin",
        suggested_due=_date(2026, 4, 24),
        raw_text="pset 4 due friday",
    )
    assert r.classification == "task"
    assert r.created_task_id == "corpfin-pset-4"
    assert r.suggested_due == _date(2026, 4, 24)


from backend.capture import process_note_v2


@pytest.mark.asyncio
async def test_v2_high_confidence_task_returns_task_result(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.9,
            suggested_task=SuggestedTask("corpfin", "Pset 4", "2026-04-24", "pset", "15%"),
            tags=["corpfin"],
        )
    deps, mem = _deps(tmp_path, cls)
    result = await process_note_v2("pset 4 due friday 15%", chat_id=1, message_id=10, deps=deps)
    assert result.classification == "task"
    assert result.created_task_id is not None
    assert result.undo_token == "1-10"
    assert result.memory_stored is True
    assert result.classifier_offline is False
    assert result.suggested_due == _date(2026, 4, 24)
    assert result.suggested_category == "corpfin"


@pytest.mark.asyncio
async def test_v2_low_confidence_task_returns_ambiguous(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(
            kind="task", confidence=0.4,
            suggested_task=SuggestedTask("life", "call mom", None, "admin", None),
            tags=["life"],
        )
    deps, mem = _deps(tmp_path, cls)
    result = await process_note_v2("call mom", chat_id=1, message_id=10, deps=deps)
    assert result.classification == "ambiguous"
    assert result.created_task_id is None
    assert result.suggested_category == "life"


@pytest.mark.asyncio
async def test_v2_thought_saves(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="thought", confidence=0.9, suggested_task=None, tags=["projects"])
    deps, mem = _deps(tmp_path, cls)
    result = await process_note_v2("the api should be per-team", chat_id=1, message_id=10, deps=deps)
    assert result.classification == "thought"
    assert result.memory_stored is True


@pytest.mark.asyncio
async def test_v2_resurface_saves(tmp_path):
    def cls(text, today, **_):
        return ClassifyResult(kind="resurface", confidence=0.8, suggested_task=None, tags=[])
    store = TasksStore(tmp_path / "tasks.json")
    queue = PendingQueue(tmp_path / "pending.jsonl")
    buf = UndoBuffer(ttl_seconds=60)
    mem = FakeMemory()
    deps = CaptureDeps(
        tasks=store, undo=buf, pending=queue,
        memory_store=mem.store, classifier=cls,
        today_fn=lambda: date(2026, 4, 16),
        resurface_path=tmp_path / "resurface.jsonl",
    )
    result = await process_note_v2(
        "remind me to read this article later",
        chat_id=1, message_id=10, deps=deps,
    )
    assert result.classification == "resurface"


@pytest.mark.asyncio
async def test_v2_empty_text_returns_ambiguous(tmp_path):
    def cls(text, today, **_):
        raise AssertionError("classifier should not be called on empty text")
    deps, mem = _deps(tmp_path, cls)
    result = await process_note_v2("", chat_id=1, message_id=10, deps=deps)
    assert result.classification == "ambiguous"
    assert result.raw_text == ""
