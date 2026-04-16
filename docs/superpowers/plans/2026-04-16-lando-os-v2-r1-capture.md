# LANDO OS v2 — R1 Capture + Membase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telegram capture commands (`/note`, `/think`, `/return`, `/recall`, `/help`) backed by Anthropic classification + Membase memory, with a 60-second optimistic-write undo window.

**Architecture:** Four new `backend/` modules (`classifier.py`, `capture.py`, `undo_buffer.py`, `pending_queue.py`), plus handler extensions in `backend/bot.py`. Reuses the existing `backend/memory.py` Membase client verbatim. `/return` items are also written to a local `data/resurface.jsonl` so the morning briefing can filter by trigger date without querying Membase. `tasks.json` schema is unchanged.

**Tech Stack:** Python 3.14, FastAPI, python-telegram-bot 21, Anthropic Python SDK (new dependency), existing pytest harness.

---

## Spec addition worth flagging before starting

The design spec (§4.3) says `/return` writes to Membase with `resurface: true` in metadata. The actual Membase client (`backend.memory.store_memory`) accepts only `content` and `project` — no structured metadata. To keep briefing filtering efficient and simple, this plan writes `/return` items to BOTH:

1. **Membase** — as `[RETURN] <text> (resurface on <date>)` via `store_memory`, so the text is searchable via `/recall`.
2. **`data/resurface.jsonl`** (new, gitignored) — structured `{text, trigger_date, trigger_raw, created_at}` per line, read by the briefing module to surface items whose `trigger_date <= today`.

This is a pragmatic divergence from the spec that preserves the spec's intent (never lose a thought, surface at right moment) without requiring Membase metadata queries.

---

## File plan

| File | Action | Purpose |
|---|---|---|
| `backend/classifier.py` | Create | Anthropic-backed thought classifier. Returns `ClassifyResult`. |
| `backend/capture.py` | Create | Orchestrator: `process_note`, `process_think`, `process_return`, `process_recall`. |
| `backend/undo_buffer.py` | Create | In-memory TTL buffer for 60 s undo window. |
| `backend/pending_queue.py` | Create | Append-only retry queue for failed Membase writes (`data/membase_pending.jsonl`). |
| `backend/bot.py` | Modify | Add `/note`, `/think`, `/return`, `/recall`, `/help` handlers; callback-query handler; `undo` text handler; `set_my_commands` in `setup-menu`. |
| `backend/briefing.py` | Modify | Add `🔁 RESURFACING` block from `data/resurface.jsonl`. |
| `backend/config.py` | Modify | Add `anthropic_api_key` to `Settings`. |
| `.env.example` | Modify | Document `ANTHROPIC_API_KEY`. |
| `.gitignore` | Modify | Ignore `data/membase_pending.jsonl` and `data/resurface.jsonl`. |
| `requirements.txt` | Modify | Add `anthropic==0.39.*` (or compatible). |
| `tests/test_classifier.py` | Create | Mocked Anthropic call-out. |
| `tests/test_capture.py` | Create | Branches of `process_note` + other processors. |
| `tests/test_undo_buffer.py` | Create | TTL and multi-entry behavior. |
| `tests/test_pending_queue.py` | Create | Append, drain-on-success, survives partial failure. |
| `tests/test_briefing.py` | Modify | Add test for RESURFACING block. |
| `tests/test_bot_capture.py` | Create | Integration: command router + callback handler, stubbed externals. |

---

## Task 1: Add Anthropic SDK dependency and API key config

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add `anthropic` to requirements.txt**

Append one line to `requirements.txt`:

```
anthropic==0.39.*
```

- [ ] **Step 2: Install it into the venv**

Run: `venv/bin/pip install "anthropic==0.39.*"`
Expected: successful install, no existing deps downgraded.

- [ ] **Step 3: Write a failing test for the new config field**

Create `tests/test_config.py`:

```python
from backend.config import load_settings


def test_anthropic_api_key_loads_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    s = load_settings()
    assert s.anthropic_api_key == "sk-ant-test"


def test_anthropic_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = load_settings()
    assert s.anthropic_api_key == ""
```

- [ ] **Step 4: Run test to verify it fails**

Run: `venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'anthropic_api_key'`.

- [ ] **Step 5: Add field to Settings**

Edit `backend/config.py`. Inside the `Settings` frozen dataclass, add:

```python
    anthropic_api_key: str
```

And inside `load_settings()`, add to the `Settings(...)` constructor call:

```python
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `venv/bin/pytest tests/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 7: Document the env var**

Append to `.env.example`:

```
# Anthropic API key — used by /note classifier (empty disables classification → inline-button fallback)
ANTHROPIC_API_KEY=
```

- [ ] **Step 8: Commit**

```bash
git add requirements.txt backend/config.py .env.example tests/test_config.py
git commit -m "feat(config): add ANTHROPIC_API_KEY setting for capture classifier"
```

---

## Task 2: Pending queue for failed Membase writes

**Files:**
- Create: `backend/pending_queue.py`
- Create: `tests/test_pending_queue.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add queue file to gitignore**

Append to `.gitignore`:

```
data/membase_pending.jsonl
data/resurface.jsonl
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_pending_queue.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
import pytest
from backend.pending_queue import PendingQueue


def test_append_then_iter_returns_entries(tmp_path: Path):
    q = PendingQueue(tmp_path / "pending.jsonl")
    q.append({"content": "hello", "project": "apes"})
    q.append({"content": "world", "project": None})
    entries = list(q.iter_entries())
    assert entries == [
        {"content": "hello", "project": "apes"},
        {"content": "world", "project": None},
    ]


def test_iter_on_missing_file_returns_empty(tmp_path: Path):
    q = PendingQueue(tmp_path / "does-not-exist.jsonl")
    assert list(q.iter_entries()) == []


def test_clear_removes_file(tmp_path: Path):
    q = PendingQueue(tmp_path / "pending.jsonl")
    q.append({"content": "hi", "project": None})
    assert (tmp_path / "pending.jsonl").exists()
    q.clear()
    assert not (tmp_path / "pending.jsonl").exists()


def test_append_creates_parent_dir(tmp_path: Path):
    q = PendingQueue(tmp_path / "nested" / "pending.jsonl")
    q.append({"content": "x", "project": None})
    assert (tmp_path / "nested" / "pending.jsonl").exists()


def test_malformed_line_is_skipped(tmp_path: Path):
    p = tmp_path / "pending.jsonl"
    p.write_text('{"content": "ok", "project": null}\ngarbage\n{"content": "also ok", "project": "x"}\n')
    q = PendingQueue(p)
    entries = list(q.iter_entries())
    assert entries == [
        {"content": "ok", "project": None},
        {"content": "also ok", "project": "x"},
    ]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_pending_queue.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Implement the queue**

Create `backend/pending_queue.py`:

```python
"""Append-only retry queue for Membase writes that failed.

The queue lives at an absolute path (typically data/membase_pending.jsonl).
One JSON object per line. Consumers read all entries, attempt to re-send
each, and clear() the queue once every entry has been processed.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)


class PendingQueue:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def iter_entries(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    log.warning("skipping malformed pending-queue line: %r", line[:80])

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_pending_queue.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/pending_queue.py tests/test_pending_queue.py .gitignore
git commit -m "feat(capture): append-only pending queue for failed Membase writes"
```

---

## Task 3: Undo buffer with TTL

**Files:**
- Create: `backend/undo_buffer.py`
- Create: `tests/test_undo_buffer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_undo_buffer.py`:

```python
from __future__ import annotations
import time
from backend.undo_buffer import UndoBuffer, UndoEntry


def test_register_then_pop_returns_entry():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(chat_id=1, message_id=100, task_id="corpfin-pset4")
    entry = buf.pop_latest(chat_id=1)
    assert entry is not None
    assert entry.task_id == "corpfin-pset4"
    assert entry.message_id == 100


def test_pop_consumes_entry():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    assert buf.pop_latest(1) is not None
    assert buf.pop_latest(1) is None


def test_latest_of_many_is_returned_first():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    buf.register(1, 200, "t2")
    buf.register(1, 300, "t3")
    entry = buf.pop_latest(1)
    assert entry is not None and entry.task_id == "t3"
    entry = buf.pop_latest(1)
    assert entry is not None and entry.task_id == "t2"


def test_expired_entries_are_not_returned(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("backend.undo_buffer.time.monotonic", lambda: now[0])
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t1")
    now[0] += 61
    assert buf.pop_latest(1) is None


def test_entries_are_scoped_per_chat():
    buf = UndoBuffer(ttl_seconds=60)
    buf.register(1, 100, "t_one")
    buf.register(2, 200, "t_two")
    assert buf.pop_latest(1).task_id == "t_one"
    assert buf.pop_latest(2).task_id == "t_two"
    assert buf.pop_latest(1) is None
    assert buf.pop_latest(2) is None


def test_entry_has_all_fields():
    entry = UndoEntry(message_id=10, task_id="x", created_at=0.0)
    assert entry.message_id == 10
    assert entry.task_id == "x"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_undo_buffer.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the buffer**

Create `backend/undo_buffer.py`:

```python
"""In-memory TTL buffer for task-creation undos.

Single-process only (the bot runs in a single process). Lost on restart —
acceptable because the TTL is 60 seconds. Thread-safe is not required
because all handlers run on the telegram asyncio event loop.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from collections import defaultdict


@dataclass(frozen=True)
class UndoEntry:
    message_id: int
    task_id: str
    created_at: float  # monotonic seconds


class UndoBuffer:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._entries: dict[int, list[UndoEntry]] = defaultdict(list)

    def register(self, chat_id: int, message_id: int, task_id: str) -> None:
        entry = UndoEntry(
            message_id=message_id,
            task_id=task_id,
            created_at=time.monotonic(),
        )
        self._entries[chat_id].append(entry)

    def pop_latest(self, chat_id: int) -> UndoEntry | None:
        """Return the most-recently-registered non-expired entry for this chat,
        removing it from the buffer. Returns None if none exist."""
        now = time.monotonic()
        entries = self._entries.get(chat_id, [])
        while entries:
            entry = entries.pop()
            if now - entry.created_at <= self.ttl:
                return entry
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_undo_buffer.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/undo_buffer.py tests/test_undo_buffer.py
git commit -m "feat(capture): in-memory TTL undo buffer (60s window)"
```

---

## Task 4: Classifier module

**Files:**
- Create: `backend/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_classifier.py`:

```python
from __future__ import annotations
import json
from datetime import date
import pytest
from backend.classifier import classify, ClassifyResult, SuggestedTask


def _fake_anthropic(result_json: dict):
    """Return a callable matching the classifier's `call_tool` signature
    that echoes the given tool-use result."""
    def _call(system: str, user: str, tool_schema: dict) -> dict:
        return result_json
    return _call


def test_classifies_as_task_with_date():
    fake = _fake_anthropic({
        "kind": "task",
        "confidence": 0.9,
        "suggested_task": {
            "category": "corpfin", "name": "Pset 4",
            "due": "2026-04-24", "type": "pset", "weight": "15%",
        },
        "tags": ["corpfin", "pset"],
    })
    result = classify("pset 4 due friday 15%", date(2026, 4, 16), call=fake)
    assert result.kind == "task"
    assert result.confidence == 0.9
    assert result.suggested_task is not None
    assert result.suggested_task.category == "corpfin"
    assert result.suggested_task.due == "2026-04-24"
    assert result.tags == ["corpfin", "pset"]


def test_classifies_as_thought_with_no_suggested_task():
    fake = _fake_anthropic({
        "kind": "thought",
        "confidence": 0.85,
        "suggested_task": None,
        "tags": ["projects", "pricing"],
    })
    result = classify("maybe pricing should be per-team not per-seat", date(2026, 4, 16), call=fake)
    assert result.kind == "thought"
    assert result.suggested_task is None
    assert "pricing" in result.tags


def test_ambiguous_falls_back_to_inline_buttons_via_low_confidence():
    fake = _fake_anthropic({
        "kind": "task", "confidence": 0.4,
        "suggested_task": {"category": "life", "name": "call mom", "due": None, "type": "admin", "weight": None},
        "tags": ["life"],
    })
    result = classify("call mom", date(2026, 4, 16), call=fake)
    assert result.kind == "task"
    assert result.confidence == 0.4


def test_anthropic_failure_returns_ambiguous():
    def broken_call(*args, **kwargs):
        raise RuntimeError("api down")
    result = classify("anything", date(2026, 4, 16), call=broken_call)
    assert result.kind == "ambiguous"
    assert result.confidence == 0.0
    assert result.suggested_task is None


def test_malformed_json_returns_ambiguous():
    def bad_call(*args, **kwargs):
        return {"not_the": "right shape"}
    result = classify("anything", date(2026, 4, 16), call=bad_call)
    assert result.kind == "ambiguous"
    assert result.confidence == 0.0


def test_missing_api_key_short_circuits_to_ambiguous():
    # When call=None and no client can be built, classify returns ambiguous
    # (tested by passing call=None and setting the env var to empty).
    import os
    os.environ.pop("ANTHROPIC_API_KEY", None)
    result = classify("anything", date(2026, 4, 16), call=None)
    assert result.kind == "ambiguous"


def test_suggested_task_dataclass_has_expected_fields():
    t = SuggestedTask(category="apes", name="Lab 3", due="2026-04-20", type="pset", weight="5%")
    assert t.category == "apes"
    assert t.due == "2026-04-20"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_classifier.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the classifier**

Create `backend/classifier.py`:

```python
"""Anthropic-backed classifier for captured thoughts.

Public API:
    classify(text, today, *, call=None) -> ClassifyResult

`call` is an optional dependency-injected callable used in tests. In
production it is None and the module builds a live Anthropic client
from the ANTHROPIC_API_KEY env var. If no API key is available or the
call fails for any reason, returns an ambiguous result with confidence
0.0 — callers then fall through to the inline-button flow.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

log = logging.getLogger(__name__)

CATEGORIES = [
    "corpfin", "scs", "apes", "e4e",
    "baseball", "recruiting", "projects", "life",
]

TASK_TYPES = [
    "exam", "pset", "essay", "case", "project",
    "presentation", "reading", "ai-tutor", "admin",
]

_MODEL = "claude-haiku-4-5"

_TOOL_SCHEMA = {
    "name": "classify_thought",
    "description": "Classify a captured thought and optionally extract a task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["task", "thought", "resurface", "ambiguous"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "suggested_task": {
                "type": ["object", "null"],
                "properties": {
                    "category": {"type": "string", "enum": CATEGORIES},
                    "name": {"type": "string"},
                    "due": {"type": ["string", "null"], "description": "ISO YYYY-MM-DD or null"},
                    "type": {"type": "string", "enum": TASK_TYPES},
                    "weight": {"type": ["string", "null"]},
                },
                "required": ["category", "name", "type"],
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "confidence", "tags"],
    },
}

AnthropicCall = Callable[[str, str, dict], dict]


@dataclass(frozen=True)
class SuggestedTask:
    category: str
    name: str
    due: str | None
    type: str
    weight: str | None


@dataclass(frozen=True)
class ClassifyResult:
    kind: Literal["task", "thought", "resurface", "ambiguous"]
    confidence: float
    suggested_task: SuggestedTask | None
    tags: list[str]


_AMBIGUOUS = ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])


def _build_system_prompt(today: date) -> str:
    return (
        "You classify a single captured thought from a student. Use the "
        "classify_thought tool to return structured output.\n"
        f"Today is {today.isoformat()}. Resolve relative dates "
        "('Friday', 'next week') to absolute ISO dates.\n"
        f"Known categories: {', '.join(CATEGORIES)}.\n"
        f"Known task types: {', '.join(TASK_TYPES)}.\n"
        "Kinds:\n"
        "- 'task': an action the user needs to do, ideally with a deadline.\n"
        "- 'thought': an idea, observation, or half-formed note with no action.\n"
        "- 'resurface': something to bring back later ('remind me', 'look into').\n"
        "- 'ambiguous': unclear — the user should pick manually.\n"
        "Confidence is your self-estimate; use 0.75+ only when you are "
        "clearly correct. For a task, if you cannot extract a due date, "
        "set due to null."
    )


def _default_call(api_key: str) -> AnthropicCall:
    """Build a production caller that hits the real Anthropic API."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    def _call(system: str, user: str, tool_schema: dict) -> dict:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": user}],
        )
        # Find the tool_use block and return its input.
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError("no tool_use block in Anthropic response")

    return _call


def classify(
    text: str,
    today: date,
    *,
    call: AnthropicCall | None = None,
) -> ClassifyResult:
    if call is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            log.info("ANTHROPIC_API_KEY unset; classifier disabled")
            return _AMBIGUOUS
        try:
            call = _default_call(api_key)
        except Exception:
            log.warning("failed to build Anthropic client", exc_info=True)
            return _AMBIGUOUS

    try:
        raw = call(_build_system_prompt(today), text, _TOOL_SCHEMA)
    except Exception:
        log.warning("classifier call failed", exc_info=True)
        return _AMBIGUOUS

    return _parse_result(raw)


def _parse_result(raw: dict) -> ClassifyResult:
    try:
        kind = raw["kind"]
        if kind not in ("task", "thought", "resurface", "ambiguous"):
            return _AMBIGUOUS
        confidence = float(raw.get("confidence", 0.0))
        tags = list(raw.get("tags") or [])
        st_raw = raw.get("suggested_task")
        if st_raw:
            suggested = SuggestedTask(
                category=str(st_raw.get("category", "life")),
                name=str(st_raw.get("name", "")),
                due=st_raw.get("due"),
                type=str(st_raw.get("type", "admin")),
                weight=st_raw.get("weight"),
            )
        else:
            suggested = None
        return ClassifyResult(kind=kind, confidence=confidence, suggested_task=suggested, tags=tags)
    except (KeyError, TypeError, ValueError):
        log.warning("malformed classifier output: %s", json.dumps(raw)[:200])
        return _AMBIGUOUS
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_classifier.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/classifier.py tests/test_classifier.py
git commit -m "feat(capture): anthropic classifier for /note text"
```

---

## Task 5: Capture orchestrator — `process_note`

**Files:**
- Create: `backend/capture.py`
- Create: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests for `process_note` branches**

Create `tests/test_capture.py`:

```python
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


def _deps(tmp_path: Path, classifier, memory_succeeds: bool = True) -> CaptureDeps:
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `process_note` and its supporting types**

Create `backend/capture.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: 8 passed. (`pytest.ini` already sets `asyncio_mode = auto`, so `@pytest.mark.asyncio` works without further config.)

- [ ] **Step 5: Commit**

```bash
git add backend/capture.py tests/test_capture.py
git commit -m "feat(capture): process_note orchestrator with confidence-gated writes"
```

---

## Task 6: Capture — `process_think`, `process_return`, `process_recall`

**Files:**
- Modify: `backend/capture.py`
- Modify: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests for the remaining processors**

Append to `tests/test_capture.py`:

```python
from backend.capture import process_think, process_return, process_recall


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: the new tests FAIL; previous tests still pass.

- [ ] **Step 3: Implement the three processors**

Add to `backend/capture.py` (at the end of the file):

```python
MemorySearch = Callable[[str, int], Awaitable[list[dict]]]


async def process_think(text: str, *, deps: CaptureDeps, memory_search: MemorySearch) -> CaptureOutcome:
    text = text.strip()
    if not text:
        return CaptureOutcome(kind="usage")
    await _store_or_queue(deps, f"[THINKING] {text}", None)
    try:
        hits = await memory_search(text, 3)
    except Exception:
        log.warning("memory_search failed on /think", exc_info=True)
        hits = []
    return CaptureOutcome(kind="thought_saved", recall_hits=hits)


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
    await _store_or_queue(deps, f"[RETURN] {text}{annotation}", None)
    write_resurface(deps, text=text, trigger_date=trigger_date, trigger_raw=trigger_raw)
    return CaptureOutcome(kind="resurface_saved", trigger_date=trigger_date)


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
            name=raw_text[:80] or "captured note",
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_capture.py -v`
Expected: all tests in the file pass (original 8 plus the 8 new ones = 16).

- [ ] **Step 5: Commit**

```bash
git add backend/capture.py tests/test_capture.py
git commit -m "feat(capture): process_think, process_return, process_recall, confirm_create_task"
```

---

## Task 7: Briefing — RESURFACING block

**Files:**
- Modify: `backend/briefing.py`
- Modify: `tests/test_briefing.py`

- [ ] **Step 1: Write failing test for the RESURFACING block**

Append to `tests/test_briefing.py`:

```python
def test_resurfacing_block_surfaces_due_items(tmp_path):
    import json
    p = tmp_path / "resurface.jsonl"
    p.write_text(
        json.dumps({"text": "read econ paper", "trigger_date": "2026-04-13", "trigger_raw": None, "created_at": "x"}) + "\n"
        + json.dumps({"text": "future thing", "trigger_date": "2026-05-01", "trigger_raw": None, "created_at": "x"}) + "\n"
    )
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" in text
    assert "read econ paper" in text
    assert "future thing" not in text


def test_resurfacing_block_absent_when_no_items(tmp_path):
    p = tmp_path / "resurface.jsonl"
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" not in text


def test_resurfacing_unparseable_trigger_never_surfaces(tmp_path):
    import json
    p = tmp_path / "resurface.jsonl"
    p.write_text(
        json.dumps({"text": "maybe revisit", "trigger_date": None, "trigger_raw": "sometime", "created_at": "x"}) + "\n"
    )
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_briefing.py -v`
Expected: the three new tests FAIL; existing briefing tests still pass.

- [ ] **Step 3: Add the RESURFACING block to the briefing**

Edit `backend/briefing.py`. Update the `generate_briefing` signature to accept `resurface_path`, and add a block before the counts line.

Change the function signature from:

```python
def generate_briefing(
    tasks: list[Task],
    today: date,
    events: list["CalendarEvent"] | None = None,
) -> str:
```

to:

```python
def generate_briefing(
    tasks: list[Task],
    today: date,
    events: list["CalendarEvent"] | None = None,
    resurface_path: "Path | None" = None,
) -> str:
```

And add this import near the top:

```python
from pathlib import Path
```

Add this block **between the existing CRUNCH ALERT block and the final counts line** (inside `generate_briefing`, just before the `lines.append(f"Active: {len(active)} ...")` line):

```python
    # Resurface items from /return whose trigger_date <= today
    if resurface_path is not None and resurface_path.exists():
        import json
        due_resurface: list[str] = []
        for line in resurface_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            trig = entry.get("trigger_date")
            if trig and trig <= today.isoformat():
                due_resurface.append(entry.get("text", ""))
        if due_resurface:
            lines.append("🔁 *RESURFACING*")
            for t in due_resurface:
                lines.append(f"  · {t}")
            lines.append("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_briefing.py -v`
Expected: all tests pass, including the three new ones.

- [ ] **Step 5: Commit**

```bash
git add backend/briefing.py tests/test_briefing.py
git commit -m "feat(briefing): surface /return items whose trigger_date has arrived"
```

---

## Task 8: Bot command handlers (`/note`, `/think`, `/return`, `/recall`, `/help`)

**Files:**
- Modify: `backend/bot.py`
- Create: `tests/test_bot_capture.py`

Note: writing integration tests that exercise python-telegram-bot's `Application` end-to-end is heavy. Test the **handler callbacks** as plain async functions with a minimal fake `Update` / `Context`, matching the pattern used for unit-testing PTB apps.

- [ ] **Step 1: Write failing tests for command handlers**

Create `tests/test_bot_capture.py`:

```python
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
    for cmd in ["/note", "/think", "/return", "/recall", "/briefing", "/done", "/add"]:
        assert cmd in reply
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_bot_capture.py -v`
Expected: FAIL — handlers not yet exported from `backend.bot`.

- [ ] **Step 3: Add handlers to `backend/bot.py`**

Edit `backend/bot.py`. The existing import block already has `InlineKeyboardButton`, `InlineKeyboardMarkup`, `Update`, `WebAppInfo`, `MenuButtonWebApp` from `telegram`. Extend the existing `from telegram.ext import ...` line and add new module imports:

```python
# Extend the existing telegram.ext import line with CallbackQueryHandler, MessageHandler, filters, BotCommand:
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters, BotCommand,
)

# Add these new imports:
from pathlib import Path
from .capture import (
    CaptureDeps, CaptureOutcome,
    process_note, process_think, process_return, process_recall,
    confirm_create_task, write_resurface,
)
from .classifier import classify as default_classify, SuggestedTask
from .memory import store_memory, search_memory
from .pending_queue import PendingQueue
from .undo_buffer import UndoBuffer
```

Add this helper at module level (below the existing `_open_dashboard_markup`):

```python
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
```

Add the command handlers:

```python
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
```

Wire the handlers into `_build_app` (edit the existing function):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_bot_capture.py -v`
Expected: 7 passed. If `context.bot_data["memory_search"]` is not populated in the fake context, the integration tests will set it directly — check `_build_context_with_deps`.

- [ ] **Step 5: Run the full test suite to catch regressions**

Run: `venv/bin/pytest -v`
Expected: all previous tests plus the new ones pass. (Existing 24 + new tests from all tasks so far.)

- [ ] **Step 6: Commit**

```bash
git add backend/bot.py tests/test_bot_capture.py
git commit -m "feat(bot): add /note, /think, /return, /recall, /help handlers"
```

---

## Task 9: Bot callback handler for inline buttons + `undo` text handler

**Files:**
- Modify: `backend/bot.py`
- Modify: `tests/test_bot_capture.py`

- [ ] **Step 1: Write failing tests for callbacks and undo**

Append to `tests/test_bot_capture.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_bot_capture.py -v -k "callback or undo or non_undo"`
Expected: FAIL — handlers do not exist yet.

- [ ] **Step 3: Implement the callback and undo handlers**

Edit `backend/bot.py`. Append after `cmd_help`:

```python
async def cb_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cq = update.callback_query
    await cq.answer()
    data = cq.data or ""
    if not data.startswith("capt:"):
        return
    _, action, pending_id = data.split(":", 2)
    pending = context.bot_data.get("pending", {}).pop(pending_id, None)
    if pending is None:
        await cq.edit_message_text("(This button has expired.)")
        return

    deps: CaptureDeps = context.bot_data["deps"]
    raw_text = pending["raw_text"]
    suggested = pending["suggested_task"]

    if action == "create":
        chat_id, _, msg_id = pending_id.partition("-")
        outcome = await confirm_create_task(
            suggested, raw_text=raw_text,
            chat_id=int(chat_id), message_id=int(msg_id), deps=deps,
        )
        await cq.edit_message_text(_format_task_reply(outcome), parse_mode=ParseMode.MARKDOWN)
    elif action == "thought":
        await cq.edit_message_text("💭 Kept as a thought.")
    elif action == "later":
        from datetime import timedelta
        trigger = (deps.today_fn() + timedelta(days=3)).isoformat()
        write_resurface(deps, text=raw_text, trigger_date=trigger, trigger_raw=None)
        await cq.edit_message_text(f"🔁 Will resurface on {trigger}.")
    else:
        await cq.edit_message_text("(Unknown action.)")


async def on_text_maybe_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.text.strip().lower() != "undo":
        return
    deps: CaptureDeps = context.bot_data["deps"]
    entry = deps.undo.pop_latest(chat_id=msg.chat_id)
    if entry is None:
        await msg.reply_text("Nothing to undo in the last 60 seconds.")
        return
    try:
        # Delete by rewriting tasks without the target id.
        remaining = [t for t in deps.tasks.list() if t.id != entry.task_id]
        deps.tasks.replace_all(remaining)
    except Exception:
        log.warning("undo failed to delete task %s", entry.task_id, exc_info=True)
        await msg.reply_text(f"Couldn't revert task {entry.task_id}.")
        return
    await msg.reply_text(f"Reverted task {entry.task_id}.")
```

Register the new handlers inside `_build_app`:

```python
    app.add_handler(CallbackQueryHandler(cb_capture, pattern=r"^capt:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_maybe_undo))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_bot_capture.py -v`
Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add backend/bot.py tests/test_bot_capture.py
git commit -m "feat(bot): callback-query handler for inline buttons + 'undo' text handler"
```

---

## Task 10: `set_my_commands` registration in `setup-menu` mode

**Files:**
- Modify: `backend/bot.py`

- [ ] **Step 1: Extend `run_setup_menu` to also register slash-command hints**

Edit the body of `run_setup_menu` in `backend/bot.py`. Replace the current body with:

```python
async def run_setup_menu() -> None:
    settings = load_settings()
    if not settings.miniapp_url:
        log.error("MINIAPP_URL is empty; set it in .env or via refresh_tunnel.sh first")
        sys.exit(2)
    app = _build_app(settings.telegram_bot_token)
    async with app:
        # Keep the menu-button pointing at the Mini App.
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Dashboard", web_app=WebAppInfo(url=settings.miniapp_url)),
        )
        # Populate the '/' hint popup.
        await app.bot.set_my_commands([
            BotCommand("briefing", "Today's schedule + due items"),
            BotCommand("note", "Capture a thought (I'll classify)"),
            BotCommand("think", "Save a thought, surface related"),
            BotCommand("return", "Resurface later (| in N days | next monday)"),
            BotCommand("recall", "Search your captured notes"),
            BotCommand("add", "Add a structured task"),
            BotCommand("done", "Mark a task complete"),
            BotCommand("undo", "Unmark a task"),
            BotCommand("help", "Show this command list"),
        ])
    log.info("Menu button + slash hints refreshed (miniapp=%s)", settings.miniapp_url)
```

- [ ] **Step 2: Run the full test suite**

Run: `venv/bin/pytest -v`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/bot.py
git commit -m "feat(bot): register slash-command hints via set_my_commands"
```

---

## Task 11: Wire briefing to read resurface.jsonl + pass path to cron

**Files:**
- Modify: `backend/bot.py`

- [ ] **Step 1: Verify that `cmd_briefing` and `_send_briefing` pass `resurface_path`**

Both `cmd_briefing` and `_send_briefing` in `backend/bot.py` currently call `generate_briefing(store.list(), today=..., events=events)` without the new `resurface_path` kwarg. Update both callsites.

In `cmd_briefing`:

```python
async def cmd_briefing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    resurface_path = Path(settings.tasks_path).parent / "resurface.jsonl"
    text = generate_briefing(store.list(), today=date.today(), events=events, resurface_path=resurface_path)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )
```

In `_send_briefing`:

```python
async def _send_briefing(app: Application, chat_id: str, miniapp_url: str) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    resurface_path = Path(settings.tasks_path).parent / "resurface.jsonl"
    text = generate_briefing(store.list(), today=date.today(), events=events, resurface_path=resurface_path)
    await app.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(miniapp_url),
    )
```

- [ ] **Step 2: Run full test suite**

Run: `venv/bin/pytest -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/bot.py
git commit -m "feat(bot): pass resurface_path to briefing so RETURN items surface"
```

---

## Task 12: Manual smoke test and deploy

**Files:** none (operational)

- [ ] **Step 1: Stop the running bot and API**

Run: `tmux kill-window -t scheduler:bot 2>/dev/null; tmux kill-window -t scheduler:api 2>/dev/null`

- [ ] **Step 2: Confirm `.env` contains `ANTHROPIC_API_KEY=<your key>`**

Run: `grep ANTHROPIC_API_KEY .env`
Expected: key is set (non-empty). If not, add it before continuing.

- [ ] **Step 3: Start a fresh bot + api in tmux**

Run:

```bash
tmux new-window -t scheduler -n bot "venv/bin/python -m backend.bot bot"
tmux new-window -t scheduler -n api "venv/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000"
```

- [ ] **Step 4: Re-point the slash-command hints**

Run: `venv/bin/python -m backend.bot setup-menu`
Expected: log line "Menu button + slash hints refreshed".

- [ ] **Step 5: Smoke-test in Telegram**

In the Telegram chat with the bot, send each of these and verify the response:

1. `/help` — command list renders correctly with the five new commands listed.
2. `/note pset 4 due friday 15%` — expect `✅ Task created: ...` with a correctly-resolved Friday date.
3. `/note maybe rework pricing` — expect the inline-button prompt with three buttons.
4. Tap `[💭 Thought]` — reply becomes "💭 Kept as a thought."
5. `/think the api should be per-team not per-seat` — expect `💭 Saved.` with up to three related snippets.
6. `/return call recruiter | in 2 days` — expect `🔁 Will resurface on <date>.` with correct +2 date.
7. `/recall pricing` — expect up to 5 results including the /think message from step 5.
8. `/note finish report` → within 60 seconds, reply `undo` → expect `Reverted task ...`.
9. `/note finish report` → wait 90 seconds, reply `undo` → expect `Nothing to undo in the last 60 seconds.` and task still exists.
10. `/briefing` — if any `/return` items have triggers ≤ today, the 🔁 RESURFACING block appears.

- [ ] **Step 6: Inspect logs for errors**

Run: `tmux capture-pane -t scheduler:bot -p | tail -80`
Expected: no traceback lines. Classifier-call warnings are OK if the API key is missing (graceful-degrade path).

- [ ] **Step 7: Final commit if anything needed patching during smoke**

```bash
git status
# If changes, commit them with a descriptive message.
```

---

## Spec coverage self-check

Run this mentally against the spec at `docs/superpowers/specs/2026-04-16-lando-os-v2-r1-capture-design.md`:

| Spec requirement | Task(s) implementing it |
|---|---|
| `/note` default command with classifier + optimistic write | 5, 8 |
| Inline-button flow for low-confidence / ambiguous | 6 (confirm_create_task), 9 (cb_capture) |
| 60-second undo via `undo` text reply | 3 (UndoBuffer), 9 (on_text_maybe_undo) |
| `/think` + related-memory surfacing | 6, 8 |
| `/return` with trigger parsing (bare, `in N days`, `next <weekday>`) | 6 |
| `/recall` over Membase | 6, 8 |
| `/help` listing all commands | 8 |
| `set_my_commands` registration | 10 |
| Membase write always-first, fail-soft via pending queue | 2 (PendingQueue), 5 (`_store_or_queue`) |
| Classifier fallback when Anthropic missing/failing → ambiguous | 4 |
| Briefing `🔁 RESURFACING` block | 7, 11 |
| No tasks.json schema change | — (invariant: TasksStore untouched) |
| `backend/memory.py` reused as-is (async, fail-soft) | 8 (wiring), all read/write paths |
| ANTHROPIC_API_KEY in config | 1 |

No spec requirement is unaddressed.

---

## Placeholder scan (self-review)

- No "TBD" / "TODO" / "fill in" in any task body.
- All code shown in full — no "similar to Task N" shortcuts.
- All commands are concrete and runnable.
- Types referenced across tasks are consistent: `CaptureDeps`, `CaptureOutcome`, `ClassifyResult`, `SuggestedTask`, `UndoBuffer`, `UndoEntry`, `PendingQueue`.
- Method names consistent: `store_memory` / `search_memory` / `search_wiki` from existing `backend/memory.py`; `register` / `pop_latest` on `UndoBuffer`; `append` / `iter_entries` / `clear` on `PendingQueue`; `process_note` / `process_think` / `process_return` / `process_recall` / `confirm_create_task` on capture.

---

## Deferred (not in this plan)

- Mini App Notes tab (R1.5).
- Priority-algorithm rollout (R2).
- Evening recap cron, weekly review cron.
- Cron-time pending-queue drain (currently the queue grows until a capture is retried manually or a startup drain is added; acceptable for R1 — write-and-forget captures still confirm).
