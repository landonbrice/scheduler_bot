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

from .classifier import ClassifyResult, SuggestedTask, classify as real_classify
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

    # Step 1: always write raw note to Membase (or queue it).
    project = None  # we fill this in below after classification; queue entry is re-written if classification refines it
    queued = await _store_or_queue(deps, f"[NOTE] {text}", project)

    # Step 2: classify.
    result: ClassifyResult = deps.classifier(text, today)

    if result.tags:
        project = _pick_project(result.tags)

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
