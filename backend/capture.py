"""Capture orchestrator.

Owns the branching logic for /note, /think, /return, /recall. Written with
dependency injection (CaptureDeps) so tests supply fakes for the tasks
store, Membase, the classifier, and the clock.
"""
from __future__ import annotations
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Literal

from .classifier import ClassifyResult, SuggestedTask
from .pending_queue import PendingQueue
from .tasks_store import Task, TasksStore
from .undo_buffer import UndoBuffer

log = logging.getLogger(__name__)

HIGH_CONFIDENCE = 0.75
DEFAULT_TASK_DUE_OFFSET_DAYS = 7
DEFAULT_RESURFACE_OFFSET_DAYS = 3

MemoryStore = Callable[[str, str | None], Awaitable[bool]]
Classifier = Callable[..., ClassifyResult]  # matches classify(text, today, **kw)


@dataclass
class CaptureDeps:
    tasks: TasksStore
    undo: UndoBuffer
    pending: PendingQueue
    memory_store: MemoryStore
    classifier: Classifier
    today_fn: Callable[[], date]
    resurface_path: Any = None  # pathlib.Path, set by caller; optional in tests


@dataclass(frozen=True)
class CaptureOutcome:
    kind: Literal[
        "task_created", "needs_confirmation",
        "thought_saved", "resurface_saved",
        "recall_results", "usage",
    ]
    task: Task | None = None
    suggested_task: SuggestedTask | None = None
    tags: list[str] = field(default_factory=list)
    trigger_date: str | None = None
    defaulted_due: bool = False
    membase_queued: bool = False
    recall_hits: list[dict] = field(default_factory=list)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _task_id_from(category: str, name: str, existing: set[str]) -> str:
    base = f"{_slug(category)[:8] or 'task'}-{_slug(name)[:16] or uuid.uuid4().hex[:6]}"
    task_id = base
    i = 2
    while task_id in existing:
        task_id = f"{base}-{i}"
        i += 1
    return task_id


async def _store_or_queue(deps: CaptureDeps, content: str, project: str | None) -> bool:
    """Try to write to Membase; on failure append to the pending queue.
    Returns True if queued locally, False if delivered to Membase."""
    ok = await deps.memory_store(content, project)
    if ok:
        return False
    deps.pending.append({"content": content, "project": project})
    return True


def _pick_project(tags: list[str]) -> str | None:
    """Pick a single 'project' label for Membase from the classifier's tags."""
    for t in tags:
        if t in ("corpfin", "scs", "apes", "e4e", "baseball", "recruiting", "projects", "life"):
            return t
    return tags[0] if tags else None


async def process_note(text: str, chat_id: int, message_id: int, deps: CaptureDeps) -> CaptureOutcome:
    text = text.strip()
    if not text:
        return CaptureOutcome(kind="usage")

    today = deps.today_fn()

    # Step 1: classify (fail-soft — returns _AMBIGUOUS on any error).
    result: ClassifyResult = deps.classifier(text, today)

    # Step 2: pick project label from tags, then write raw note to Membase (or queue it).
    project = _pick_project(result.tags) if result.tags else None
    queued = await _store_or_queue(deps, f"[NOTE] {text}", project)

    # Step 3: branch.
    if result.kind == "thought":
        return CaptureOutcome(kind="thought_saved", tags=result.tags, membase_queued=queued)

    if result.kind == "resurface":
        trigger = (today + timedelta(days=DEFAULT_RESURFACE_OFFSET_DAYS)).isoformat()
        write_resurface(deps, text=text, trigger_date=trigger, trigger_raw=None)
        return CaptureOutcome(kind="resurface_saved", trigger_date=trigger, tags=result.tags, membase_queued=queued)

    if result.kind == "ambiguous" or (result.kind == "task" and result.confidence < HIGH_CONFIDENCE):
        return CaptureOutcome(
            kind="needs_confirmation",
            suggested_task=result.suggested_task,
            tags=result.tags,
            membase_queued=queued,
        )

    # result.kind == "task" and confidence >= HIGH_CONFIDENCE
    suggested = result.suggested_task
    if suggested is None:
        # Classifier said "task" but gave no details. Treat as needs_confirmation.
        return CaptureOutcome(kind="needs_confirmation", tags=result.tags, membase_queued=queued)

    due = suggested.due
    defaulted = False
    if not due:
        due = (today + timedelta(days=DEFAULT_TASK_DUE_OFFSET_DAYS)).isoformat()
        defaulted = True

    existing = {t.id for t in deps.tasks.list()}
    task_id = _task_id_from(suggested.category, suggested.name, existing)
    task = Task(
        id=task_id,
        course=suggested.category,
        name=suggested.name,
        due=due,
        type=suggested.type,
        weight=suggested.weight or "",
        done=False,
        notes=None,
    )
    deps.tasks.add(task)
    deps.undo.register(chat_id=chat_id, message_id=message_id, task_id=task_id)
    return CaptureOutcome(
        kind="task_created",
        task=task,
        tags=result.tags,
        defaulted_due=defaulted,
        membase_queued=queued,
    )


MemorySearch = Callable[[str, int], Awaitable[list[dict]]]


async def process_think(text: str, *, deps: CaptureDeps, memory_search: MemorySearch) -> CaptureOutcome:
    text = text.strip()
    if not text:
        return CaptureOutcome(kind="usage")
    queued = await _store_or_queue(deps, f"[THINKING] {text}", None)
    try:
        hits = await memory_search(text, 3)
    except Exception:
        log.warning("memory_search failed on /think", exc_info=True)
        hits = []
    return CaptureOutcome(kind="thought_saved", recall_hits=hits, membase_queued=queued)


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _parse_return_trigger(raw: str, today: date) -> tuple[str | None, str | None]:
    """Return (trigger_date_iso_or_None, trigger_raw_or_None).

    If no `|` is present, default trigger = tomorrow.
    `| in N days` → today + N.
    `| next <weekday>` → next occurrence of that weekday strictly after today.
    Anything else → (None, raw_trigger_string).
    """
    if "|" not in raw:
        return (today + timedelta(days=1)).isoformat(), None

    _, trigger = raw.split("|", 1)
    trigger = trigger.strip().lower()

    if trigger == "tomorrow":
        return (today + timedelta(days=1)).isoformat(), None

    m = re.match(r"in\s+(\d+)\s+days?", trigger)
    if m:
        return (today + timedelta(days=int(m.group(1)))).isoformat(), None

    m = re.match(r"next\s+(\w+)", trigger)
    if m and m.group(1) in _WEEKDAYS:
        target_idx = _WEEKDAYS.index(m.group(1))
        today_idx = today.weekday()
        delta = (target_idx - today_idx) % 7
        if delta == 0:
            delta = 7
        return (today + timedelta(days=delta)).isoformat(), None

    return None, trigger


def _text_before_pipe(raw: str) -> str:
    return raw.split("|", 1)[0].strip() if "|" in raw else raw.strip()


async def process_return(raw: str, *, deps: CaptureDeps) -> CaptureOutcome:
    raw = raw.strip()
    if not raw:
        return CaptureOutcome(kind="usage")
    today = deps.today_fn()
    trigger_date, trigger_raw = _parse_return_trigger(raw, today)
    text = _text_before_pipe(raw)
    annotation = f" (resurface on {trigger_date})" if trigger_date else " (no auto-trigger)"
    queued = await _store_or_queue(deps, f"[RETURN] {text}{annotation}", None)
    write_resurface(deps, text=text, trigger_date=trigger_date, trigger_raw=trigger_raw)
    return CaptureOutcome(kind="resurface_saved", trigger_date=trigger_date, membase_queued=queued)


async def process_recall(query: str, *, deps: CaptureDeps, memory_search: MemorySearch) -> CaptureOutcome:
    query = query.strip()
    if not query:
        return CaptureOutcome(kind="usage")
    try:
        hits = await memory_search(query, 5)
    except Exception:
        log.warning("memory_search failed on /recall", exc_info=True)
        hits = []
    return CaptureOutcome(kind="recall_results", recall_hits=hits)


async def confirm_create_task(
    suggested: SuggestedTask | None,
    *,
    raw_text: str,
    chat_id: int,
    message_id: int,
    deps: CaptureDeps,
) -> CaptureOutcome:
    """Invoked when the user taps [✅ Create task] on the inline keyboard.

    If `suggested` is None (classifier produced no suggestion), build a minimal
    task from the raw note text.
    """
    today = deps.today_fn()
    if suggested is None:
        suggested = SuggestedTask(
            category="life",
            name=raw_text.strip()[:80] or "captured note",
            due=(today + timedelta(days=DEFAULT_TASK_DUE_OFFSET_DAYS)).isoformat(),
            type="admin",
            weight=None,
        )
    due = suggested.due or (today + timedelta(days=DEFAULT_TASK_DUE_OFFSET_DAYS)).isoformat()
    defaulted = suggested.due is None

    existing = {t.id for t in deps.tasks.list()}
    task_id = _task_id_from(suggested.category, suggested.name, existing)
    task = Task(
        id=task_id, course=suggested.category, name=suggested.name,
        due=due, type=suggested.type, weight=suggested.weight or "",
        done=False, notes=None,
    )
    deps.tasks.add(task)
    deps.undo.register(chat_id=chat_id, message_id=message_id, task_id=task_id)
    return CaptureOutcome(kind="task_created", task=task, defaulted_due=defaulted)


def write_resurface(deps: CaptureDeps, *, text: str, trigger_date: str | None, trigger_raw: str | None) -> None:
    """Append a structured resurface record to data/resurface.jsonl."""
    if deps.resurface_path is None:
        return
    import json
    from datetime import datetime, timezone
    entry = {
        "text": text,
        "trigger_date": trigger_date,
        "trigger_raw": trigger_raw,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    deps.resurface_path.parent.mkdir(parents=True, exist_ok=True)
    with deps.resurface_path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
