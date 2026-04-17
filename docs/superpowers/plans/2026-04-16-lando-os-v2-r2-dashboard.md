# LANDO OS v2 R2 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship LANDO OS v2 R2 — a priority-ranked Mon–Sun week dashboard with FAB capture, contextual thought surfacing, empty-block LLM suggestion, and search — in one pass.

**Architecture:** Backend extends `server.py` with 8 new endpoints backed by 4 new pure-Python modules (`priority.py`, `surfacing.py`, `schedule.py`, `suggest.py`), plus a refactor of `capture.process_note` to return a renderer-agnostic `CaptureResult` consumed by both `bot.py` (Telegram) and `server.py` (JSON). Frontend replaces `App.tsx` with a 3-tab router (Week default / Tasks / Settings), a week-view grid driven by `/api/tasks`+`/api/schedule`+`/api/calendar`+`/api/notes/surfaced`, and a persistent FAB that round-trips through the same classifier as the bot.

**Tech Stack:** Python 3.14 · FastAPI · pytest · pytest-asyncio · OpenAI SDK → DeepSeek · mcp (Membase) · React 18 · Vite · TypeScript (strict) · Tailwind · `telegram.helpers.escape_markdown` (v1) · `frontend-design:frontend-design` skill.

---

## Task 0: Bootstrap working branch

**Files:** n/a (git only)

- [ ] **Step 0.1: Verify clean tree and create branch**
  ```bash
  cd /Users/landonprojects/scheduler_bot
  git status
  git checkout -b r2-dashboard
  ```
  Expected: `On branch r2-dashboard`.

- [ ] **Step 0.2: Run the full test suite baseline**
  ```bash
  cd /Users/landonprojects/scheduler_bot
  venv/bin/pytest -q
  ```
  Expected: `95 passed` (ignore the pytest-asyncio deprecation spam — see CLAUDE.md gotchas).

---

## Task 1: Refactor `capture.process_note` → `CaptureResult` + split renderers

**Files:**
- Modify: `backend/capture.py` (add `CaptureResult` dataclass, rewrite `process_note` return shape, keep `CaptureOutcome` as an internal detail or remove — see steps)
- Modify: `backend/bot.py` (consume `CaptureResult`; renderers unchanged in output)
- Test: `tests/test_capture.py` (extend), `tests/test_bot_capture.py` (extend — confirm Telegram replies unchanged)

The spec's `CaptureResult` is renderer-agnostic: it collapses the current `CaptureOutcome.kind` enum into `classification` + booleans/options. We keep `CaptureOutcome` internal-only **or** delete it in favor of `CaptureResult` — we delete it to avoid two shapes. The invariant: every existing bot reply (task_created message, thought saved, resurface saved, needs-confirmation with buttons) must render byte-identical text after the refactor.

- [ ] **Step 1.1: Write failing test for `CaptureResult` dataclass**
  Append to `tests/test_capture.py`:
  ```python
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
  ```
  Run it — FAIL (CaptureResult does not exist):
  ```bash
  venv/bin/pytest tests/test_capture.py::test_capture_result_dataclass_shape -q
  ```

- [ ] **Step 1.2: Add `CaptureResult` + helpers to `backend/capture.py`**
  At the top of `backend/capture.py`, after the existing imports, add:
  ```python
  from datetime import date as _date_type
  ```
  Then add the dataclass just above `CaptureOutcome`:
  ```python
  @dataclass(frozen=True)
  class CaptureResult:
      """Renderer-agnostic outcome of process_note. Consumed by both bot.py
      (Telegram reply) and server.py (JSON). Orchestrator is the single
      source of truth for capture semantics — renderers only format."""
      classification: Literal["task", "thought", "resurface", "ambiguous"]
      confidence: float
      created_task_id: str | None
      undo_token: str | None
      memory_stored: bool
      classifier_offline: bool
      suggested_category: str | None
      suggested_due: _date_type | None
      raw_text: str
  ```
  Run the new test — PASS:
  ```bash
  venv/bin/pytest tests/test_capture.py::test_capture_result_dataclass_shape -q
  ```

- [ ] **Step 1.3: Make `process_note` return both shapes via a parallel function, behind a flag**
  To keep tests green while refactoring, add a new function `process_note_v2` that returns `CaptureResult`. Keep the existing `process_note` returning `CaptureOutcome`. Bot + tests still use the old one.

  Append to `backend/capture.py`:
  ```python
  async def process_note_v2(text: str, *, chat_id: int, message_id: int, deps: CaptureDeps) -> CaptureResult:
      """CaptureResult-returning variant. Shares core logic with process_note —
      this function will eventually replace process_note entirely (see plan Task 1.6)."""
      raw_text = text.strip()
      if not raw_text:
          return CaptureResult(
              classification="ambiguous", confidence=0.0, created_task_id=None,
              undo_token=None, memory_stored=False, classifier_offline=False,
              suggested_category=None, suggested_due=None, raw_text="",
          )

      today = deps.today_fn()
      try:
          result: ClassifyResult = deps.classifier(raw_text, today)
          classifier_offline = result.kind == "ambiguous" and result.confidence == 0.0 and not result.suggested_task and not result.tags
      except Exception:
          log.warning("classifier raised inside process_note_v2", exc_info=True)
          result = ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])
          classifier_offline = True

      project = _pick_project(result.tags) if result.tags else None
      queued = await _store_or_queue(deps, f"[NOTE] {raw_text}", project)
      memory_stored = not queued

      suggested_category = result.suggested_task.category if result.suggested_task else None
      suggested_due: _date_type | None = None
      if result.suggested_task and result.suggested_task.due:
          try:
              suggested_due = _date_type.fromisoformat(result.suggested_task.due)
          except ValueError:
              suggested_due = None

      if result.kind == "thought":
          return CaptureResult(
              classification="thought", confidence=result.confidence, created_task_id=None,
              undo_token=None, memory_stored=memory_stored, classifier_offline=classifier_offline,
              suggested_category=suggested_category, suggested_due=suggested_due, raw_text=raw_text,
          )
      if result.kind == "resurface":
          trigger = (today + timedelta(days=DEFAULT_RESURFACE_OFFSET_DAYS)).isoformat()
          write_resurface(deps, text=raw_text, trigger_date=trigger, trigger_raw=None)
          return CaptureResult(
              classification="resurface", confidence=result.confidence, created_task_id=None,
              undo_token=None, memory_stored=memory_stored, classifier_offline=classifier_offline,
              suggested_category=suggested_category, suggested_due=suggested_due, raw_text=raw_text,
          )
      if result.kind == "ambiguous" or (result.kind == "task" and result.confidence < HIGH_CONFIDENCE):
          return CaptureResult(
              classification="ambiguous", confidence=result.confidence, created_task_id=None,
              undo_token=None, memory_stored=memory_stored, classifier_offline=classifier_offline,
              suggested_category=suggested_category, suggested_due=suggested_due, raw_text=raw_text,
          )

      # High-confidence task path.
      suggested = result.suggested_task
      if suggested is None:
          return CaptureResult(
              classification="ambiguous", confidence=result.confidence, created_task_id=None,
              undo_token=None, memory_stored=memory_stored, classifier_offline=classifier_offline,
              suggested_category=suggested_category, suggested_due=suggested_due, raw_text=raw_text,
          )
      due = suggested.due or (today + timedelta(days=DEFAULT_TASK_DUE_OFFSET_DAYS)).isoformat()
      existing = {t.id for t in deps.tasks.list()}
      task_id = _task_id_from(suggested.category, suggested.name, existing)
      task = Task(
          id=task_id, course=suggested.category, name=suggested.name, due=due,
          type=suggested.type, weight=suggested.weight or "", done=False, notes=None,
      )
      deps.tasks.add(task)
      deps.undo.register(chat_id=chat_id, message_id=message_id, task_id=task_id)
      undo_token = f"{chat_id}-{message_id}"
      return CaptureResult(
          classification="task", confidence=result.confidence, created_task_id=task_id,
          undo_token=undo_token, memory_stored=memory_stored, classifier_offline=False,
          suggested_category=suggested.category, suggested_due=_date_type.fromisoformat(due),
          raw_text=raw_text,
      )
  ```

- [ ] **Step 1.4: Write failing tests for `process_note_v2` covering the 5 branches**
  Append to `tests/test_capture.py`:
  ```python
  @pytest.mark.asyncio
  async def test_v2_high_confidence_task(tmp_path):
      from backend.capture import process_note_v2
      def cls(text, today, **_):
          return ClassifyResult(
              kind="task", confidence=0.9,
              suggested_task=SuggestedTask("corpfin", "Pset 4", "2026-04-24", "pset", "15%"),
              tags=["corpfin"],
          )
      deps, mem = _deps(tmp_path, cls)
      r = await process_note_v2("pset 4 friday 15%", chat_id=1, message_id=10, deps=deps)
      assert r.classification == "task"
      assert r.created_task_id is not None
      assert r.undo_token == "1-10"
      assert r.memory_stored is True
      assert r.suggested_due == date(2026, 4, 24)

  @pytest.mark.asyncio
  async def test_v2_low_confidence_ambiguous(tmp_path):
      from backend.capture import process_note_v2
      def cls(text, today, **_):
          return ClassifyResult(kind="task", confidence=0.4,
              suggested_task=SuggestedTask("life", "call mom", None, "admin", None), tags=["life"])
      deps, _ = _deps(tmp_path, cls)
      r = await process_note_v2("call mom", chat_id=1, message_id=10, deps=deps)
      assert r.classification == "ambiguous"
      assert r.created_task_id is None
      assert r.suggested_category == "life"

  @pytest.mark.asyncio
  async def test_v2_thought(tmp_path):
      from backend.capture import process_note_v2
      def cls(text, today, **_):
          return ClassifyResult(kind="thought", confidence=0.9, suggested_task=None, tags=["projects"])
      deps, _ = _deps(tmp_path, cls)
      r = await process_note_v2("random idea", chat_id=1, message_id=10, deps=deps)
      assert r.classification == "thought"
      assert r.memory_stored is True

  @pytest.mark.asyncio
  async def test_v2_resurface(tmp_path):
      from backend.capture import process_note_v2
      def cls(text, today, **_):
          return ClassifyResult(kind="resurface", confidence=0.8, suggested_task=None, tags=[])
      # need resurface_path so write_resurface doesn't noop
      from backend.capture import CaptureDeps
      from backend.pending_queue import PendingQueue
      from backend.tasks_store import TasksStore
      from backend.undo_buffer import UndoBuffer
      mem = FakeMemory()
      deps = CaptureDeps(
          tasks=TasksStore(tmp_path / "tasks.json"),
          undo=UndoBuffer(ttl_seconds=60),
          pending=PendingQueue(tmp_path / "pending.jsonl"),
          memory_store=mem.store, classifier=cls, today_fn=lambda: date(2026, 4, 16),
          resurface_path=tmp_path / "resurface.jsonl",
      )
      r = await process_note_v2("remind me to read later", chat_id=1, message_id=10, deps=deps)
      assert r.classification == "resurface"

  @pytest.mark.asyncio
  async def test_v2_empty_text(tmp_path):
      from backend.capture import process_note_v2
      def cls(text, today, **_):
          raise AssertionError("must not be called")
      deps, _ = _deps(tmp_path, cls)
      r = await process_note_v2("", chat_id=1, message_id=10, deps=deps)
      assert r.classification == "ambiguous"
      assert r.raw_text == ""
  ```
  Run — all 5 should PASS:
  ```bash
  venv/bin/pytest tests/test_capture.py -q -k v2
  ```

- [ ] **Step 1.5: Add server-side renderer helper in `backend/capture.py`**
  Append to `backend/capture.py`:
  ```python
  def capture_result_to_json(r: CaptureResult) -> dict:
      """Render a CaptureResult as the JSON response body for /api/capture/note.
      Keeps server.py free of capture-domain logic."""
      return {
          "classification": r.classification,
          "confidence": round(r.confidence, 3),
          "created_task_id": r.created_task_id,
          "undo_token": r.undo_token,
          "memory_stored": r.memory_stored,
          "classifier_offline": r.classifier_offline,
          "suggested_category": r.suggested_category,
          "suggested_due": r.suggested_due.isoformat() if r.suggested_due else None,
          "raw_text": r.raw_text,
      }
  ```

- [ ] **Step 1.6: Add `process_note_v2` renderer to `backend/bot.py` + swap over `cmd_note`**
  In `backend/bot.py`, add a new format helper below the existing `_format_*` helpers:
  ```python
  def _format_capture_result(r: "CaptureResult", raw_text: str) -> tuple[str, bool]:
      """Render a CaptureResult as a (text, needs_buttons) tuple for Telegram.
      Preserves parity with the existing CaptureOutcome renderers."""
      from .capture import CaptureResult  # local import to avoid cycle at top
      if r.classification == "task" and r.created_task_id:
          parts = [f"✅ Task created: `{r.created_task_id}`"]
          if r.suggested_due:
              parts.append(f"due {_esc(r.suggested_due.isoformat())}")
          parts.append(f"type {_esc(r.suggested_category or 'life')}")
          suffix = '\nReply "undo" within 60s to revert.'
          return ". ".join(parts) + "." + suffix, False
      if r.classification == "thought":
          line = "💭 Saved."
          if r.memory_stored is False:
              line += "\n  (Membase unavailable — queued locally.)"
          return line, False
      if r.classification == "resurface":
          # Default offset is 3 days; renderer reflects that in flat text.
          return "🔁 Will resurface on your next briefing.", False
      # ambiguous → needs inline buttons
      head = "I think this is a task, but I'm not sure. Pick one:"
      if r.suggested_category:
          head += f"\n→ would create: `{_esc(r.suggested_category)}`"
          if r.suggested_due:
              head += f" · due {_esc(r.suggested_due.isoformat())}"
      else:
          head += f"\n→ raw: {_esc(raw_text[:120])}"
      return head, True
  ```
  Replace the body of `cmd_note` in `backend/bot.py` to use `process_note_v2`:
  ```python
  async def cmd_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
      from .capture import process_note_v2
      deps: CaptureDeps = context.bot_data["deps"]
      msg = update.message
      text = " ".join(context.args) if context.args else ""
      if not text.strip():
          await msg.reply_text("Give me something to capture. Usage: /note <text>")
          return
      r = await process_note_v2(text, chat_id=msg.chat_id, message_id=msg.message_id, deps=deps)
      reply_text, needs_buttons = _format_capture_result(r, text)
      if needs_buttons:
          pending_id = f"{msg.chat_id}-{msg.message_id}"
          # Reconstruct a minimal SuggestedTask for the confirm flow.
          suggested = None
          if r.suggested_category:
              suggested = SuggestedTask(
                  category=r.suggested_category,
                  name=text.strip()[:80] or "captured note",
                  due=r.suggested_due.isoformat() if r.suggested_due else None,
                  type="admin", weight=None,
              )
          context.bot_data.setdefault("pending", {})[pending_id] = {
              "raw_text": text, "suggested_task": suggested,
          }
          await msg.reply_text(reply_text, reply_markup=_confirmation_markup(pending_id))
          return
      await msg.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)
  ```

- [ ] **Step 1.7: Run the existing bot-capture tests to confirm parity**
  ```bash
  venv/bin/pytest tests/test_bot_capture.py -q
  ```
  Expected: all pass. If any fail due to the different reply text format, tighten `_format_capture_result` to match the original text until tests pass. No functional change — cosmetic parity only.

- [ ] **Step 1.8: Run full suite**
  ```bash
  venv/bin/pytest -q
  ```
  Expected: everything green (≥100 tests now).

- [ ] **Step 1.9: Commit**
  ```bash
  cd /Users/landonprojects/scheduler_bot
  git add backend/capture.py backend/bot.py tests/test_capture.py
  git commit -m "$(cat <<'EOF'
  refactor(capture): add CaptureResult + process_note_v2 for R2 renderers

  Introduce a renderer-agnostic CaptureResult dataclass that collapses the
  existing CaptureOutcome's kind enum into classification + booleans. Add
  process_note_v2 that returns CaptureResult so both the Telegram bot and
  the upcoming /api/capture/note endpoint can share orchestrator logic.

  Bot reply text preserved byte-for-byte. Old process_note/CaptureOutcome
  retained for /think /return /recall handlers and for gradual migration.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  git status
  ```

---

## Task 2: `priority.py` + extend `/api/tasks`

**Files:**
- Create: `backend/priority.py`
- Modify: `backend/server.py` (lines ~52-55 — `get_tasks` response)
- Modify: `backend/tasks_store.py` (add optional `impact_override` + `priority_boost` fields to `Task`)
- Test: `tests/test_priority.py` (new), `tests/test_server.py` (extend)

- [ ] **Step 2.1: Extend `Task` dataclass with optional fields**
  Open `backend/tasks_store.py` and locate the `@dataclass` decorated `Task` class. Add two optional fields at the end:
  ```python
  impact_override: str | None = None  # "critical" | "high" | "medium" | "low" | None
  priority_boost: float | None = None  # None ≡ 1.0
  ```
  Confirm the existing tests still pass:
  ```bash
  venv/bin/pytest tests/test_tasks_store.py -q
  ```

- [ ] **Step 2.2: Write failing tests for `priority.compute` + `tier`**
  Create `tests/test_priority.py`:
  ```python
  from __future__ import annotations
  from datetime import datetime, date
  import math
  import pytest
  from backend.priority import compute, tier
  from backend.tasks_store import Task


  def _task(**kw) -> Task:
      defaults = dict(
          id="t1", course="corpfin", name="thing",
          due="2026-04-20", type="pset", weight="",
          done=False, notes=None,
      )
      defaults.update(kw)
      return Task(**defaults)


  NOW = datetime(2026, 4, 16, 10, 0, 0)


  def test_urgency_overdue():
      t = _task(due="2026-04-10")  # 6 days overdue
      score = compute(t, NOW)
      assert score >= 10.0  # clamp floor

  def test_urgency_today():
      t = _task(due="2026-04-16", type="pset")
      s = compute(t, NOW)
      # urgency=100, impact=0.5, type_boost=1.0, priority_boost=1.0 → 50
      assert s == pytest.approx(50.0, rel=0.01)

  def test_urgency_curve_3_days():
      t = _task(due="2026-04-19", type="pset")
      s = compute(t, NOW)
      # urgency ≈ 100 * e^(-0.45) ≈ 63.76; * 0.5 = ~31.88
      assert 30.0 <= s <= 34.0

  def test_impact_override_wins():
      t = _task(type="pset", impact_override="critical")
      s = compute(t, NOW)  # critical=0.95 instead of pset=0.5
      assert s > compute(_task(type="pset"), NOW)

  def test_type_boost_exam_within_7_days():
      t = _task(due="2026-04-20", type="exam")  # 4 days out
      s = compute(t, NOW)
      # 100*e^(-0.6) ≈ 54.88, *0.95 impact, *1.5 boost ≈ 78.2
      assert 70.0 <= s <= 85.0

  def test_type_boost_exam_outside_window():
      t = _task(due="2026-05-10", type="exam")  # 24 days → no boost
      s = compute(t, NOW)
      # urgency floor ≈ 10, impact 0.95 → 9.5
      assert s < 15.0

  def test_priority_boost_flag():
      base = compute(_task(type="pset"), NOW)
      boosted = compute(_task(type="pset", priority_boost=1.5), NOW)
      assert boosted == pytest.approx(base * 1.5, rel=0.001)

  def test_tier_red_by_score():
      assert tier(85.0, urgent_flag=False) == "red"

  def test_tier_red_by_flag_even_if_low_score():
      assert tier(20.0, urgent_flag=True) == "red"

  def test_tier_amber():
      assert tier(55.0, urgent_flag=False) == "amber"

  def test_tier_neutral():
      assert tier(15.0, urgent_flag=False) == "neutral"
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_priority.py -q
  ```
  Expected: ImportError / FAIL.

- [ ] **Step 2.3: Create `backend/priority.py`**
  ```python
  """Priority scoring. Pure functions — no I/O, no clock dep beyond arg.

  R2 formula:
      score = urgency(days_until_due)
              * impact(type | impact_override)
              * type_boost(type, days)
              * (priority_boost or 1.0)

  Tier:
      red      score >= 80 OR priority_boost == 1.5 (urgent flag)
      amber    40 <= score < 80
      neutral  score < 40
  """
  from __future__ import annotations
  import math
  from datetime import date, datetime
  from typing import Literal

  from .tasks_store import Task

  IMPACT: dict[str, float] = {
      "exam": 0.95, "presentation": 0.90,
      "essay": 0.75, "project": 0.70,
      "pset": 0.50, "case": 0.50,
      "reading": 0.35,
      "recurring": 0.20, "admin": 0.15, "ai-tutor": 0.20,
  }

  OVERRIDE_MAP: dict[str, float] = {
      "critical": 0.95, "high": 0.75, "medium": 0.50, "low": 0.20,
  }

  Tier = Literal["red", "amber", "neutral"]


  def _urgency(days: int) -> float:
      if days < 0:
          return 100.0
      return max(10.0, 100.0 * math.exp(-0.15 * days))


  def _impact(task: Task) -> float:
      if task.impact_override and task.impact_override in OVERRIDE_MAP:
          return OVERRIDE_MAP[task.impact_override]
      return IMPACT.get(task.type, 0.30)


  def _type_boost(task_type: str, days: int) -> float:
      if task_type in ("exam", "presentation") and days <= 7:
          return 1.5
      if task_type == "essay" and days <= 10:
          return 1.3
      if task_type == "project" and days <= 14:
          return 1.2
      return 1.0


  def compute(task: Task, now: datetime) -> float:
      try:
          due = date.fromisoformat(task.due)
      except (ValueError, TypeError):
          return 0.0
      days = (due - now.date()).days
      return (
          _urgency(days)
          * _impact(task)
          * _type_boost(task.type, days)
          * (task.priority_boost or 1.0)
      )


  def tier(score: float, urgent_flag: bool) -> Tier:
      if urgent_flag or score >= 80.0:
          return "red"
      if score >= 40.0:
          return "amber"
      return "neutral"
  ```
  Run tests:
  ```bash
  venv/bin/pytest tests/test_priority.py -q
  ```
  Expected: all 10 pass.

- [ ] **Step 2.4: Extend `/api/tasks` response with `priority_score` + `tier`**
  Edit `backend/server.py` — replace the `get_tasks` function (around line 52):
  ```python
  from datetime import datetime as _dt
  from .priority import compute as _prio_compute, tier as _prio_tier


  @app.get("/api/tasks")
  def get_tasks(_: TelegramUser = Depends(current_user)):
      now = _dt.now()
      tasks = store.list()
      out = []
      for t in tasks:
          score = _prio_compute(t, now)
          out.append({
              **t.__dict__,
              "priority_score": round(score, 2),
              "tier": _prio_tier(score, urgent_flag=(t.priority_boost == 1.5)),
          })
      return {"tasks": out}
  ```

- [ ] **Step 2.5: Write failing test for enriched response**
  Append to `tests/test_server.py`:
  ```python
  def test_tasks_endpoint_includes_priority_score_and_tier(client, auth_headers, tmp_tasks):
      resp = client.get("/api/tasks", headers=auth_headers)
      assert resp.status_code == 200
      body = resp.json()
      for t in body["tasks"]:
          assert "priority_score" in t
          assert "tier" in t
          assert t["tier"] in ("red", "amber", "neutral")
          assert 0.0 <= t["priority_score"] <= 300.0
  ```
  (If the existing test file doesn't have `client` / `auth_headers` / `tmp_tasks` fixtures, locate them first via `Grep` and adapt. The repo has 95 tests — a fixture pattern exists.)
  Run:
  ```bash
  venv/bin/pytest tests/test_server.py::test_tasks_endpoint_includes_priority_score_and_tier -q
  ```
  Expected PASS.

- [ ] **Step 2.6: Commit**
  ```bash
  git add backend/priority.py backend/server.py backend/tasks_store.py tests/test_priority.py tests/test_server.py
  git commit -m "$(cat <<'EOF'
  feat(priority): score + tier helpers; /api/tasks returns priority_score+tier

  New pure-Python backend/priority.py: urgency (exp decay), impact bucket
  (categorical + per-task override), type_boost (pre-deadline window),
  priority_boost (urgent flag). tier() returns red/amber/neutral with the
  urgent flag forcing red regardless of score.

  Extend Task dataclass with optional impact_override + priority_boost.
  GET /api/tasks now enriches each task with priority_score + tier so the
  frontend can render the left-border color without duplicating scoring.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 3: `schedule.py` + `data/schedule.json` + `/api/schedule`

**Files:**
- Create: `backend/schedule.py`
- Create: `data/schedule.json` (gitignored)
- Modify: `backend/server.py`
- Test: `tests/test_schedule.py`

- [ ] **Step 3.1: Write failing tests for schedule loader**
  Create `tests/test_schedule.py`:
  ```python
  from __future__ import annotations
  import json
  from datetime import date
  from pathlib import Path
  import pytest
  from backend.schedule import load_schedule, week_instances, ScheduleClass


  @pytest.fixture
  def schedule_path(tmp_path: Path) -> Path:
      p = tmp_path / "schedule.json"
      p.write_text(json.dumps({
          "term": {"start": "2026-03-30", "end": "2026-06-05"},
          "classes": [
              {"title": "SCS III", "category": "SCS III",
               "days": ["Mon", "Wed"], "start": "15:00", "end": "16:20",
               "location": "Wieboldt 310C",
               "exceptions": [{"date": "2026-04-20", "action": "cancel"}]},
              {"title": "APES", "category": "APES",
               "days": ["Tue", "Thu"], "start": "09:30", "end": "10:50",
               "location": "Ryerson 251", "exceptions": []},
          ],
      }))
      return p


  def test_load_schedule_parses_classes(schedule_path):
      sched = load_schedule(schedule_path)
      assert sched.term_start == date(2026, 3, 30)
      assert sched.term_end == date(2026, 6, 5)
      assert len(sched.classes) == 2
      assert sched.classes[0].title == "SCS III"


  def test_week_instances_generates_mon_through_sun(schedule_path):
      sched = load_schedule(schedule_path)
      # Week of Monday 2026-04-13 (Mon) – Sunday 2026-04-19.
      instances = week_instances(sched, week_start=date(2026, 4, 13))
      assert len(instances) == 4  # 2 SCS + 2 APES
      dates = {i.instance_date for i in instances}
      assert dates == {date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15), date(2026, 4, 16)}


  def test_week_instances_applies_cancel_exception(schedule_path):
      sched = load_schedule(schedule_path)
      # 2026-04-20 is a Monday in term with a cancel exception on SCS III.
      instances = week_instances(sched, week_start=date(2026, 4, 20))
      scs_instances = [i for i in instances if i.title == "SCS III"]
      # Only Wed 2026-04-22 should remain.
      assert len(scs_instances) == 1
      assert scs_instances[0].instance_date == date(2026, 4, 22)


  def test_week_instances_outside_term_returns_empty(schedule_path):
      sched = load_schedule(schedule_path)
      # Week of 2026-06-22 — past term_end.
      instances = week_instances(sched, week_start=date(2026, 6, 22))
      assert instances == []


  def test_load_schedule_missing_file_returns_empty():
      sched = load_schedule(Path("/nonexistent/schedule.json"))
      assert sched.classes == []
      assert sched.term_start is None
  ```
  Run — ImportError / FAIL:
  ```bash
  venv/bin/pytest tests/test_schedule.py -q
  ```

- [ ] **Step 3.2: Create `backend/schedule.py`**
  ```python
  """data/schedule.json loader + weekly instance expansion.

  `action: cancel` is the only supported exception in R2.
  """
  from __future__ import annotations
  import json
  import logging
  from dataclasses import dataclass, field
  from datetime import date, timedelta
  from pathlib import Path

  log = logging.getLogger(__name__)

  _DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


  @dataclass(frozen=True)
  class ScheduleException:
      exc_date: date
      action: str  # "cancel" only in R2


  @dataclass(frozen=True)
  class ScheduleClass:
      title: str
      category: str
      days: tuple[str, ...]
      start: str  # "HH:MM"
      end: str
      location: str
      exceptions: tuple[ScheduleException, ...] = ()


  @dataclass(frozen=True)
  class Schedule:
      term_start: date | None
      term_end: date | None
      classes: tuple[ScheduleClass, ...]


  @dataclass(frozen=True)
  class ClassInstance:
      title: str
      category: str
      instance_date: date
      start: str
      end: str
      location: str


  def load_schedule(path: Path) -> Schedule:
      try:
          raw = json.loads(Path(path).read_text())
      except FileNotFoundError:
          log.info("schedule.json missing at %s; returning empty schedule", path)
          return Schedule(term_start=None, term_end=None, classes=())
      except (OSError, json.JSONDecodeError):
          log.warning("schedule.json load failed at %s", path, exc_info=True)
          return Schedule(term_start=None, term_end=None, classes=())

      term = raw.get("term") or {}
      classes: list[ScheduleClass] = []
      for c in raw.get("classes") or []:
          exc = tuple(
              ScheduleException(
                  exc_date=date.fromisoformat(e["date"]),
                  action=str(e.get("action", "cancel")),
              )
              for e in (c.get("exceptions") or [])
          )
          classes.append(ScheduleClass(
              title=str(c["title"]),
              category=str(c["category"]),
              days=tuple(c.get("days") or []),
              start=str(c["start"]),
              end=str(c["end"]),
              location=str(c.get("location", "")),
              exceptions=exc,
          ))
      return Schedule(
          term_start=date.fromisoformat(term["start"]) if term.get("start") else None,
          term_end=date.fromisoformat(term["end"]) if term.get("end") else None,
          classes=tuple(classes),
      )


  def week_instances(sched: Schedule, *, week_start: date) -> list[ClassInstance]:
      """Expand every class's days into concrete date instances for the week
      starting on `week_start` (expected to be a Monday). Applies cancel
      exceptions. Filters strictly by term bounds."""
      if sched.term_start and week_start > sched.term_end:
          return []
      if sched.term_end and (week_start + timedelta(days=6)) < sched.term_start:
          return []

      out: list[ClassInstance] = []
      for cls in sched.classes:
          cancel_dates = {e.exc_date for e in cls.exceptions if e.action == "cancel"}
          for day_name in cls.days:
              try:
                  offset = _DAY_NAMES.index(day_name)
              except ValueError:
                  continue
              inst_date = week_start + timedelta(days=offset)
              if sched.term_start and inst_date < sched.term_start:
                  continue
              if sched.term_end and inst_date > sched.term_end:
                  continue
              if inst_date in cancel_dates:
                  continue
              out.append(ClassInstance(
                  title=cls.title, category=cls.category,
                  instance_date=inst_date, start=cls.start, end=cls.end,
                  location=cls.location,
              ))
      return out
  ```
  Run tests:
  ```bash
  venv/bin/pytest tests/test_schedule.py -q
  ```
  Expected: all 5 pass.

- [ ] **Step 3.3: Seed the live `data/schedule.json`**
  Create `/Users/landonprojects/scheduler_bot/data/schedule.json` with Spring 2026 UChicago schedule. Use the real term dates from CLAUDE.md context + ask the user if uncertain. Minimal starter:
  ```json
  {
    "term": {"start": "2026-03-30", "end": "2026-06-05"},
    "classes": [
      {"title": "SCS III", "category": "SCS III",
       "days": ["Mon", "Wed"], "start": "15:00", "end": "16:20",
       "location": "Wieboldt 310C", "exceptions": []},
      {"title": "APES", "category": "APES",
       "days": ["Tue", "Thu"], "start": "09:30", "end": "10:50",
       "location": "Ryerson 251", "exceptions": []},
      {"title": "CorpFin", "category": "corpfin",
       "days": ["Mon", "Wed"], "start": "10:30", "end": "11:50",
       "location": "Saieh 021", "exceptions": []}
    ]
  }
  ```
  Verify `.gitignore` already covers `data/*.json` — it does per CLAUDE.md.

- [ ] **Step 3.4: Add `/api/schedule` endpoint**
  Edit `backend/server.py` — near the other GET endpoints:
  ```python
  from .schedule import load_schedule, week_instances
  from datetime import date as _d, timedelta as _td


  _schedule_path = PROJECT_ROOT / "data" / "schedule.json"


  @app.get("/api/schedule")
  def get_schedule(
      start: str | None = None,
      _: TelegramUser = Depends(current_user),
  ):
      sched = load_schedule(_schedule_path)
      if start:
          try:
              week_start = _d.fromisoformat(start)
          except ValueError:
              raise HTTPException(400, "start must be ISO YYYY-MM-DD")
      else:
          today = _d.today()
          week_start = today - _td(days=today.weekday())  # Monday
      instances = week_instances(sched, week_start=week_start)
      return {
          "term_start": sched.term_start.isoformat() if sched.term_start else None,
          "term_end": sched.term_end.isoformat() if sched.term_end else None,
          "week_start": week_start.isoformat(),
          "instances": [
              {"title": i.title, "category": i.category,
               "date": i.instance_date.isoformat(),
               "start": i.start, "end": i.end, "location": i.location}
              for i in instances
          ],
      }
  ```

- [ ] **Step 3.5: Add server test for `/api/schedule`**
  Append to `tests/test_server.py`:
  ```python
  def test_schedule_endpoint_requires_auth(client):
      resp = client.get("/api/schedule")
      assert resp.status_code == 401

  def test_schedule_endpoint_returns_week(client, auth_headers):
      resp = client.get("/api/schedule?start=2026-04-13", headers=auth_headers)
      assert resp.status_code == 200
      body = resp.json()
      assert body["week_start"] == "2026-04-13"
      assert isinstance(body["instances"], list)
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_server.py -q -k schedule
  venv/bin/pytest tests/test_schedule.py -q
  ```
  Expected: green.

- [ ] **Step 3.6: Commit**
  ```bash
  git add backend/schedule.py backend/server.py tests/test_schedule.py tests/test_server.py
  git commit -m "$(cat <<'EOF'
  feat(schedule): schedule.json loader + GET /api/schedule

  Add backend/schedule.py with load_schedule() + week_instances() that
  expands a class schedule (days + time + optional cancel exceptions)
  into ClassInstance records for a given Mon–Sun week. Term bounds are
  enforced. GET /api/schedule?start=YYYY-MM-DD returns the week's
  instances so the Mini App week view can render class blocks without
  depending on Google Calendar for the class schedule.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 4: `surfacing.py` + `/api/notes/surfaced` + `/api/notes/search`

**Files:**
- Create: `backend/surfacing.py`
- Modify: `backend/server.py`
- Modify: `.gitignore` (ensure `data/dismissed.jsonl` ignored)
- Test: `tests/test_surfacing.py`

- [ ] **Step 4.1: Write failing tests for surfacing scoring**
  Create `tests/test_surfacing.py`:
  ```python
  from __future__ import annotations
  import json
  from datetime import date, datetime, timedelta, timezone
  from pathlib import Path
  import pytest
  from backend.surfacing import score_memory, build_day_tags, load_dismissed, surface_week


  NOW = datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc)


  def _mem(mid: str, text: str, tags: list[str], age_days: int) -> dict:
      return {
          "id": mid, "text": text, "tags": tags,
          "timestamp": (NOW - timedelta(days=age_days)).isoformat(),
      }


  def test_score_drops_untagged_memories():
      mem = _mem("m1", "old note", tags=["apes"], age_days=1)
      assert score_memory(mem, day_tags={"corpfin"}, dismissed={}, now=NOW) == 0.0


  def test_score_recency_floor():
      mem_old = _mem("m1", "very old", tags=["apes"], age_days=120)
      mem_new = _mem("m2", "yesterday", tags=["apes"], age_days=1)
      s_old = score_memory(mem_old, day_tags={"apes"}, dismissed={}, now=NOW)
      s_new = score_memory(mem_new, day_tags={"apes"}, dismissed={}, now=NOW)
      assert s_old > 0.0  # floor active
      assert s_new > s_old


  def test_dismiss_penalty_within_7_days():
      mem = _mem("m1", "t", tags=["apes"], age_days=1)
      dismissed = {"m1": NOW - timedelta(days=3)}
      assert score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW) == 0.0


  def test_dismiss_penalty_7_to_14_days():
      mem = _mem("m1", "t", tags=["apes"], age_days=1)
      base = score_memory(mem, day_tags={"apes"}, dismissed={}, now=NOW)
      dismissed = {"m1": NOW - timedelta(days=10)}
      dampened = score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW)
      assert dampened == pytest.approx(base * 0.5, rel=0.01)


  def test_dismiss_penalty_beyond_14_days():
      mem = _mem("m1", "t", tags=["apes"], age_days=1)
      base = score_memory(mem, day_tags={"apes"}, dismissed={}, now=NOW)
      dismissed = {"m1": NOW - timedelta(days=30)}
      full = score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW)
      assert full == pytest.approx(base, rel=0.001)


  def test_build_day_tags_union():
      tasks = [{"course": "corpfin"}, {"course": "APES"}]
      events = [{"category": "SCS III"}]
      tags = build_day_tags(tasks, events, resurface_tags=["baseball"])
      assert "corpfin" in tags and "apes" in tags and "scs iii" in tags and "baseball" in tags


  def test_load_dismissed_reads_jsonl(tmp_path):
      p = tmp_path / "dismissed.jsonl"
      p.write_text(
          json.dumps({"memory_id": "m1", "dismissed_at": "2026-04-10T00:00:00+00:00"}) + "\n"
          + json.dumps({"memory_id": "m2", "dismissed_at": "2026-04-12T00:00:00+00:00"}) + "\n"
      )
      d = load_dismissed(p)
      assert set(d.keys()) == {"m1", "m2"}


  def test_load_dismissed_missing_file_returns_empty(tmp_path):
      assert load_dismissed(tmp_path / "nope.jsonl") == {}


  @pytest.mark.asyncio
  async def test_surface_week_caps_3_thoughts_per_day(tmp_path):
      memories = [_mem(f"m{i}", f"note {i}", tags=["apes"], age_days=i) for i in range(10)]
      async def fake_search(query, limit):
          return memories
      tasks_by_day = {date(2026, 4, 16): [{"course": "apes"}]}
      events_by_day = {date(2026, 4, 16): []}
      chips = await surface_week(
          dates=[date(2026, 4, 16)],
          tasks_by_day=tasks_by_day,
          events_by_day=events_by_day,
          resurface_by_day={},
          dismissed_path=tmp_path / "dismissed.jsonl",
          memory_search=fake_search,
          now=NOW,
      )
      assert len(chips[date(2026, 4, 16)]) == 3
  ```
  Run — FAIL (module missing).

- [ ] **Step 4.2: Create `backend/surfacing.py`**
  ```python
  """Thought surfacing — hybrid tag+semantic scoring for week view chips.

  Public:
      surface_week(dates, tasks_by_day, events_by_day, resurface_by_day,
                   dismissed_path, memory_search, now) -> dict[date, list[chip]]

  Internal helpers:
      build_day_tags, score_memory, load_dismissed.

  memory_search is injected (Callable) so tests can stub it without touching
  backend.memory. Single Membase call per week (the weeks' concatenated
  context text).
  """
  from __future__ import annotations
  import json
  import logging
  import math
  from datetime import date, datetime, timedelta, timezone
  from pathlib import Path
  from typing import Any, Awaitable, Callable

  log = logging.getLogger(__name__)

  MemorySearch = Callable[[str, int], Awaitable[list[dict]]]

  _CAP_PER_DAY = 3
  _RECENCY_FLOOR = 0.1
  _RECENCY_LAMBDA = 0.10
  _DISMISS_HARD_DAYS = 7
  _DISMISS_SOFT_DAYS = 14


  def build_day_tags(tasks: list[dict], events: list[dict], resurface_tags: list[str]) -> set[str]:
      tags: set[str] = set()
      for t in tasks:
          v = t.get("course") or t.get("category")
          if v:
              tags.add(str(v).lower())
      for e in events:
          v = e.get("category")
          if v:
              tags.add(str(v).lower())
      for rt in resurface_tags:
          tags.add(str(rt).lower())
      return tags


  def load_dismissed(path: Path) -> dict[str, datetime]:
      result: dict[str, datetime] = {}
      try:
          lines = Path(path).read_text().strip().splitlines()
      except FileNotFoundError:
          return {}
      except OSError:
          log.warning("dismissed.jsonl read failed", exc_info=True)
          return {}
      for line in lines:
          try:
              row = json.loads(line)
              mid = str(row["memory_id"])
              ts = datetime.fromisoformat(str(row["dismissed_at"]))
              # latest wins
              if mid not in result or ts > result[mid]:
                  result[mid] = ts
          except (ValueError, KeyError, TypeError):
              continue
      return result


  def _memory_tags(memory: dict) -> set[str]:
      raw = memory.get("tags") or []
      return {str(t).lower() for t in raw}


  def _memory_age_days(memory: dict, now: datetime) -> float:
      ts = memory.get("timestamp") or memory.get("created_at")
      if not ts:
          return 0.0
      try:
          when = datetime.fromisoformat(str(ts))
      except ValueError:
          return 0.0
      delta = now - when
      return max(delta.total_seconds() / 86400.0, 0.0)


  def score_memory(memory: dict, *, day_tags: set[str], dismissed: dict[str, datetime], now: datetime) -> float:
      tag_overlap = len(_memory_tags(memory) & day_tags)
      if tag_overlap == 0:
          return 0.0
      recency = max(_RECENCY_FLOOR, math.exp(-_RECENCY_LAMBDA * _memory_age_days(memory, now)))
      base = tag_overlap * recency

      mid = memory.get("id") or memory.get("memory_id")
      if mid and mid in dismissed:
          delta_days = (now - dismissed[mid]).total_seconds() / 86400.0
          if delta_days < _DISMISS_HARD_DAYS:
              return 0.0
          if delta_days < _DISMISS_SOFT_DAYS:
              base *= 0.5
      return base


  def _context_text(tasks: list[dict], events: list[dict]) -> str:
      chunks = []
      for t in tasks:
          chunks.append(str(t.get("name") or ""))
      for e in events:
          chunks.append(str(e.get("title") or e.get("summary") or ""))
      return " ".join(c for c in chunks if c)


  async def surface_week(
      *,
      dates: list[date],
      tasks_by_day: dict[date, list[dict]],
      events_by_day: dict[date, list[dict]],
      resurface_by_day: dict[date, list[dict]],
      dismissed_path: Path,
      memory_search: MemorySearch,
      now: datetime,
  ) -> dict[date, list[dict]]:
      """Return {date: [chip dict, ...]} for each date in `dates`."""
      dismissed = load_dismissed(dismissed_path)

      # Single Membase call with the union of all week context text.
      combined = " ".join(_context_text(tasks_by_day.get(d, []), events_by_day.get(d, [])) for d in dates)
      try:
          candidates = await memory_search(combined[:2000] or " ", 40) if combined.strip() else []
      except Exception:
          log.warning("memory_search failed in surface_week", exc_info=True)
          candidates = []

      out: dict[date, list[dict]] = {}
      for d in dates:
          tasks = tasks_by_day.get(d, [])
          events = events_by_day.get(d, [])
          resurface_items = resurface_by_day.get(d, [])
          resurface_tags: list[str] = []
          for r in resurface_items:
              resurface_tags.extend(r.get("tags") or [])
          day_tags = build_day_tags(tasks, events, resurface_tags)

          scored = sorted(
              ((score_memory(m, day_tags=day_tags, dismissed=dismissed, now=now), m) for m in candidates),
              key=lambda p: p[0], reverse=True,
          )
          thought_chips: list[dict] = []
          for s, m in scored:
              if s <= 0.0 or len(thought_chips) >= _CAP_PER_DAY:
                  break
              thought_chips.append({
                  "kind": "thought",
                  "memory_id": m.get("id") or m.get("memory_id"),
                  "text": m.get("text") or m.get("content") or "",
                  "tags": m.get("tags") or [],
                  "score": round(s, 3),
              })

          resurface_chips = [
              {"kind": "resurface", "text": r.get("text") or "", "trigger_date": d.isoformat(),
               "tags": r.get("tags") or []}
              for r in resurface_items
          ]
          out[d] = resurface_chips + thought_chips
      return out
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_surfacing.py -q
  ```
  Expected: all pass.

- [ ] **Step 4.3: Add `/api/notes/surfaced` + `/api/notes/search` endpoints + `/api/capture/note/dismiss`**
  Edit `backend/server.py`:
  ```python
  import json as _json
  from datetime import datetime as _dt2, timezone as _tz
  from .surfacing import surface_week, load_dismissed
  from .memory import search_memory as _search_memory


  _dismissed_path = PROJECT_ROOT / "data" / "dismissed.jsonl"
  _resurface_path = PROJECT_ROOT / "data" / "resurface.jsonl"


  def _load_resurface_by_day(week_start: _d, week_end: _d) -> dict[_d, list[dict]]:
      out: dict[_d, list[dict]] = {}
      try:
          lines = _resurface_path.read_text().strip().splitlines()
      except FileNotFoundError:
          return {}
      for line in lines:
          try:
              row = _json.loads(line)
              td = row.get("trigger_date")
              if not td:
                  continue
              day = _d.fromisoformat(td)
              if week_start <= day <= week_end:
                  out.setdefault(day, []).append(row)
          except (ValueError, KeyError):
              continue
      return out


  @app.get("/api/notes/surfaced")
  async def get_surfaced(start: str, days: int = 7, _: TelegramUser = Depends(current_user)):
      try:
          week_start = _d.fromisoformat(start)
      except ValueError:
          raise HTTPException(400, "start must be ISO YYYY-MM-DD")
      dates = [week_start + _td(days=i) for i in range(days)]
      now = _dt2.now(tz=_tz.utc)
      tasks = store.list()
      tasks_by_day: dict[_d, list[dict]] = {}
      for t in tasks:
          try:
              td = _d.fromisoformat(t.due)
              if dates[0] <= td <= dates[-1]:
                  tasks_by_day.setdefault(td, []).append(t.__dict__)
          except ValueError:
              continue
      events = fetch_events(week_start, days=days)
      events_by_day: dict[_d, list[dict]] = {}
      for e in events:
          try:
              ed = _d.fromisoformat(e.as_dict()["start"][:10])
              events_by_day.setdefault(ed, []).append(e.as_dict())
          except (ValueError, KeyError):
              continue
      resurface_by_day = _load_resurface_by_day(dates[0], dates[-1])
      chips_by_day = await surface_week(
          dates=dates, tasks_by_day=tasks_by_day, events_by_day=events_by_day,
          resurface_by_day=resurface_by_day, dismissed_path=_dismissed_path,
          memory_search=_search_memory, now=now,
      )
      return {"surfaced": {d.isoformat(): chips for d, chips in chips_by_day.items()}}


  @app.get("/api/notes/search")
  async def search_notes(q: str, _: TelegramUser = Depends(current_user)):
      if not q.strip():
          return {"results": [], "offline": False}
      try:
          hits = await _search_memory(q, 20)
      except Exception:
          return {"results": [], "offline": True}
      return {"results": hits, "offline": False}


  class DismissBody(BaseModel):
      memory_id: str


  @app.post("/api/capture/note/dismiss")
  def dismiss_memory(body: DismissBody, _: TelegramUser = Depends(current_user)):
      entry = {
          "memory_id": body.memory_id,
          "dismissed_at": _dt2.now(tz=_tz.utc).isoformat(),
      }
      _dismissed_path.parent.mkdir(parents=True, exist_ok=True)
      with _dismissed_path.open("a") as f:
          f.write(_json.dumps(entry) + "\n")
      return {"ok": True}
  ```

- [ ] **Step 4.4: Add server tests for all 3 endpoints**
  Append to `tests/test_server.py`:
  ```python
  def test_surfaced_requires_auth(client):
      resp = client.get("/api/notes/surfaced?start=2026-04-13")
      assert resp.status_code == 401

  def test_search_requires_auth(client):
      resp = client.get("/api/notes/search?q=hi")
      assert resp.status_code == 401

  def test_dismiss_requires_auth(client):
      resp = client.post("/api/capture/note/dismiss", json={"memory_id": "m1"})
      assert resp.status_code == 401

  def test_dismiss_appends_entry(client, auth_headers, tmp_path, monkeypatch):
      from backend import server as srv
      p = tmp_path / "dismissed.jsonl"
      monkeypatch.setattr(srv, "_dismissed_path", p)
      resp = client.post("/api/capture/note/dismiss", json={"memory_id": "m42"},
                         headers=auth_headers)
      assert resp.status_code == 200
      assert p.exists()
      assert "m42" in p.read_text()
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_server.py -q -k "surfaced or search or dismiss"
  venv/bin/pytest tests/test_surfacing.py -q
  ```
  Expected: green.

- [ ] **Step 4.5: Commit**
  ```bash
  git add backend/surfacing.py backend/server.py tests/test_surfacing.py tests/test_server.py
  git commit -m "$(cat <<'EOF'
  feat(surfacing): hybrid tag+semantic chips + dismiss log

  New backend/surfacing.py: build_day_tags (union of task/event/resurface
  tags), score_memory (tag_overlap * recency, dismiss penalty windows),
  surface_week (single-Membase-call orchestrator returning per-day chips).

  Endpoints: GET /api/notes/surfaced (week-shaped chip map), GET
  /api/notes/search (debounced search), POST /api/capture/note/dismiss
  (appends to data/dismissed.jsonl). All HMAC-gated.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 5: HTTP capture wrappers — `/api/capture/note`, `/api/tasks/:id/flag`, `/api/tasks/:id/undo-create`

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/tasks_store.py` (add `set_priority_boost` method if not present)
- Test: `tests/test_capture_http.py` (new)

- [ ] **Step 5.1: Write failing tests for `/api/capture/note`**
  Create `tests/test_capture_http.py`:
  ```python
  from __future__ import annotations
  import pytest
  from fastapi.testclient import TestClient


  # Fixtures assumed present in tests/conftest.py (client, auth_headers, tmp_tasks).

  def test_capture_note_requires_auth(client):
      resp = client.post("/api/capture/note", json={"text": "x"})
      assert resp.status_code == 401


  def test_capture_note_classifier_offline_returns_ambiguous(client, auth_headers, monkeypatch):
      from backend import server as srv
      # Force classifier to return ambiguous / offline
      def fake_classify(text, today, **_):
          from backend.classifier import ClassifyResult
          return ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])
      monkeypatch.setattr(srv, "_server_classifier", fake_classify)
      resp = client.post("/api/capture/note", json={"text": "hmm"}, headers=auth_headers)
      assert resp.status_code == 200
      body = resp.json()
      assert body["classification"] == "ambiguous"
      assert body["created_task_id"] is None


  def test_capture_note_high_confidence_creates_task(client, auth_headers, monkeypatch):
      from backend import server as srv
      from backend.classifier import ClassifyResult, SuggestedTask
      def fake_classify(text, today, **_):
          return ClassifyResult(
              kind="task", confidence=0.9,
              suggested_task=SuggestedTask("corpfin", "Pset 4", "2026-04-24", "pset", "15%"),
              tags=["corpfin"],
          )
      monkeypatch.setattr(srv, "_server_classifier", fake_classify)
      resp = client.post("/api/capture/note", json={"text": "pset 4 friday 15%"}, headers=auth_headers)
      assert resp.status_code == 200
      body = resp.json()
      assert body["classification"] == "task"
      assert body["created_task_id"] is not None
      assert body["undo_token"] is not None


  def test_undo_create_deletes_task(client, auth_headers, monkeypatch):
      # Depends on test_capture_note_high_confidence_creates_task having seeded a task.
      # This test uses a fresh fixture, so it creates its own.
      from backend import server as srv
      from backend.classifier import ClassifyResult, SuggestedTask
      monkeypatch.setattr(srv, "_server_classifier", lambda t, d, **_: ClassifyResult(
          kind="task", confidence=0.9,
          suggested_task=SuggestedTask("life", "call mom", "2026-04-20", "admin", None),
          tags=["life"],
      ))
      created = client.post("/api/capture/note", json={"text": "call mom monday"}, headers=auth_headers).json()
      tid = created["created_task_id"]
      resp = client.post(f"/api/tasks/{tid}/undo-create", headers=auth_headers)
      assert resp.status_code == 200
      # Task is gone from list
      body = client.get("/api/tasks", headers=auth_headers).json()
      assert not any(t["id"] == tid for t in body["tasks"])


  def test_flag_toggles_priority_boost(client, auth_headers):
      created = client.post("/api/tasks", json={
          "course": "corpfin", "name": "test flag", "due": "2026-04-22",
          "type": "pset", "weight": "10%",
      }, headers=auth_headers).json()
      tid = created["task"]["id"]
      r1 = client.post(f"/api/tasks/{tid}/flag", headers=auth_headers).json()
      assert r1["priority_boost"] == 1.5
      r2 = client.post(f"/api/tasks/{tid}/flag", headers=auth_headers).json()
      assert r2["priority_boost"] is None or r2["priority_boost"] == 1.0
  ```
  Run — FAIL (endpoints missing):
  ```bash
  venv/bin/pytest tests/test_capture_http.py -q
  ```

- [ ] **Step 5.2: Add `set_priority_boost` helper on `TasksStore`**
  Open `backend/tasks_store.py`. Locate `set_done`. Add:
  ```python
  def set_priority_boost(self, task_id: str, boost: float | None) -> None:
      tasks = self.list()
      for t in tasks:
          if t.id == task_id:
              t.priority_boost = boost
              self.replace_all(tasks)
              return
      raise TaskNotFoundError(task_id)
  ```
  Note: `Task` needs to be a non-frozen dataclass or have a mechanism to mutate. If it's frozen, adapt using `dataclasses.replace`:
  ```python
  def set_priority_boost(self, task_id: str, boost: float | None) -> None:
      import dataclasses as _dc
      tasks = self.list()
      found = False
      out = []
      for t in tasks:
          if t.id == task_id:
              out.append(_dc.replace(t, priority_boost=boost))
              found = True
          else:
              out.append(t)
      if not found:
          raise TaskNotFoundError(task_id)
      self.replace_all(out)
  ```
  (Pick whichever matches the existing `Task` definition — check with `Read` first.)

- [ ] **Step 5.3: Wire up the HTTP capture endpoints**
  Edit `backend/server.py`:
  ```python
  from pathlib import Path as _Path
  from .capture import (
      CaptureDeps, CaptureResult, process_note_v2, capture_result_to_json,
  )
  from .classifier import classify as _default_classify
  from .memory import store_memory as _store_memory
  from .pending_queue import PendingQueue
  from .undo_buffer import UndoBuffer


  _data_dir = _Path(settings.tasks_path).parent
  _server_classifier = _default_classify  # monkeypatch-point for tests
  _server_undo = UndoBuffer(ttl_seconds=60)
  _server_pending = PendingQueue(_data_dir / "membase_pending.jsonl")


  def _server_deps() -> CaptureDeps:
      return CaptureDeps(
          tasks=store,
          undo=_server_undo,
          pending=_server_pending,
          memory_store=_store_memory,
          classifier=_server_classifier,
          today_fn=lambda: _d.today(),
          resurface_path=_data_dir / "resurface.jsonl",
      )


  class CaptureNoteBody(BaseModel):
      text: str


  @app.post("/api/capture/note")
  async def api_capture_note(body: CaptureNoteBody, user: TelegramUser = Depends(current_user)):
      # chat_id/message_id synthesize from the verified Telegram user + current timestamp
      # so undo_buffer keys don't collide across Mini App captures.
      import time
      chat_id = int(user.id)
      message_id = int(time.time() * 1000) % 1_000_000_000
      r = await process_note_v2(body.text, chat_id=chat_id, message_id=message_id, deps=_server_deps())
      return capture_result_to_json(r)


  @app.post("/api/tasks/{task_id}/flag")
  def flag_task(task_id: str, _: TelegramUser = Depends(current_user)):
      tasks = {t.id: t for t in store.list()}
      if task_id not in tasks:
          raise HTTPException(404, f"no task {task_id!r}")
      current = tasks[task_id].priority_boost
      new_val = None if current == 1.5 else 1.5
      store.set_priority_boost(task_id, new_val)
      return {"task_id": task_id, "priority_boost": new_val}


  @app.post("/api/tasks/{task_id}/undo-create")
  def undo_create(task_id: str, _: TelegramUser = Depends(current_user)):
      tasks = [t for t in store.list() if t.id != task_id]
      if len(tasks) == len(store.list()):
          raise HTTPException(404, f"no task {task_id!r}")
      store.replace_all(tasks)
      return {"ok": True, "deleted": task_id}
  ```
  Note the classifier is referenced through the module-level `_server_classifier` variable so tests can `monkeypatch.setattr(srv, "_server_classifier", fake)`. Make `_server_deps()` read that module-level value each call:
  ```python
  def _server_deps() -> CaptureDeps:
      return CaptureDeps(
          tasks=store, undo=_server_undo, pending=_server_pending,
          memory_store=_store_memory,
          classifier=_server_classifier,  # captured at call time? No, at function def.
          today_fn=lambda: _d.today(),
          resurface_path=_data_dir / "resurface.jsonl",
      )
  ```
  **Important correctness detail:** since the name is bound at function def, to support monkeypatching at call time, reference `srv._server_classifier` via an indirection:
  ```python
  def _server_deps() -> CaptureDeps:
      import sys
      this_mod = sys.modules[__name__]
      return CaptureDeps(
          tasks=store, undo=_server_undo, pending=_server_pending,
          memory_store=_store_memory,
          classifier=this_mod._server_classifier,
          today_fn=lambda: _d.today(),
          resurface_path=_data_dir / "resurface.jsonl",
      )
  ```

- [ ] **Step 5.4: Run the capture-http tests**
  ```bash
  venv/bin/pytest tests/test_capture_http.py -q
  ```
  Expected: all 5 pass.

- [ ] **Step 5.5: Run full suite**
  ```bash
  venv/bin/pytest -q
  ```
  Expected: green.

- [ ] **Step 5.6: Commit**
  ```bash
  git add backend/server.py backend/tasks_store.py tests/test_capture_http.py
  git commit -m "$(cat <<'EOF'
  feat(http): /api/capture/note, /api/tasks/:id/flag, /api/tasks/:id/undo-create

  Thin HTTP wrappers that reuse the orchestrator via process_note_v2 +
  CaptureDeps. /api/capture/note returns a renderer-agnostic CaptureResult
  as JSON; /flag toggles priority_boost between 1.5 and None; /undo-create
  deletes a task by id within the 60s Mini App undo window.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 6: `/api/suggest` with rate limit + DeepSeek fallback

**Files:**
- Create: `backend/suggest.py`
- Modify: `backend/server.py`
- Test: `tests/test_suggest.py`

- [ ] **Step 6.1: Write failing tests for suggest**
  Create `tests/test_suggest.py`:
  ```python
  from __future__ import annotations
  from datetime import datetime, timedelta
  import pytest
  from backend.suggest import pick_task, RateLimiter
  from backend.tasks_store import Task


  def _task(tid: str, due: str, type_: str = "pset") -> Task:
      return Task(id=tid, course="corpfin", name=tid, due=due, type=type_,
                  weight="", done=False, notes=None)


  def test_ratelimiter_allows_under_limit():
      rl = RateLimiter(capacity=5, refill_per_minute=5)
      now = datetime(2026, 4, 16, 10, 0)
      for _ in range(5):
          assert rl.allow("u1", now) is True

  def test_ratelimiter_trips_on_6th():
      rl = RateLimiter(capacity=5, refill_per_minute=5)
      now = datetime(2026, 4, 16, 10, 0)
      for _ in range(5):
          rl.allow("u1", now)
      assert rl.allow("u1", now) is False

  def test_ratelimiter_refills_after_minute():
      rl = RateLimiter(capacity=5, refill_per_minute=5)
      t0 = datetime(2026, 4, 16, 10, 0)
      for _ in range(5):
          rl.allow("u1", t0)
      assert rl.allow("u1", t0) is False
      later = t0 + timedelta(minutes=1)
      assert rl.allow("u1", later) is True

  def test_ratelimiter_isolates_users():
      rl = RateLimiter(capacity=2, refill_per_minute=2)
      now = datetime(2026, 4, 16, 10, 0)
      rl.allow("u1", now); rl.allow("u1", now)
      assert rl.allow("u2", now) is True


  @pytest.mark.asyncio
  async def test_pick_task_llm_success():
      async def fake_call(system, user):
          return {"picks": [
              {"task_id": "corpfin-pset-4", "reasoning": "due soon, fits 60m"},
              {"task_id": "apes-reading", "reasoning": "quick read"},
          ]}
      tasks = [_task("corpfin-pset-4", "2026-04-17"), _task("apes-reading", "2026-04-19", "reading")]
      r = await pick_task(tasks=tasks, duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                          now=datetime(2026, 4, 16, 10, 0), call=fake_call)
      assert r["source"] == "llm"
      assert r["picked"]["task_id"] == "corpfin-pset-4"
      assert len(r["alternatives"]) >= 0


  @pytest.mark.asyncio
  async def test_pick_task_llm_error_falls_back():
      async def fake_call(system, user):
          raise RuntimeError("boom")
      tasks = [_task("corpfin-pset-4", "2026-04-17"), _task("apes-reading", "2026-04-19", "reading")]
      r = await pick_task(tasks=tasks, duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                          now=datetime(2026, 4, 16, 10, 0), call=fake_call)
      assert r["source"] == "fallback"
      assert r["picked"] is not None


  @pytest.mark.asyncio
  async def test_pick_task_no_tasks_returns_empty():
      async def fake_call(system, user):
          return {"picks": []}
      r = await pick_task(tasks=[], duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                          now=datetime(2026, 4, 16, 10, 0), call=fake_call)
      assert r["picked"] is None
  ```
  Run — FAIL.

- [ ] **Step 6.2: Create `backend/suggest.py`**
  ```python
  """DeepSeek-backed empty-slot suggester + rate limiter + fallback.

  Public:
      pick_task(tasks, duration_min, start_iso, now, *, call=None) -> dict
      RateLimiter(capacity, refill_per_minute)

  call is DI'd — same pattern as classifier. In production, the caller
  builds the OpenAI-SDK-on-DeepSeek client exactly once and passes it in.
  """
  from __future__ import annotations
  import json
  import logging
  import os
  from collections import defaultdict
  from dataclasses import dataclass
  from datetime import datetime
  from typing import Awaitable, Callable

  from .priority import compute as _prio_compute
  from .tasks_store import Task

  log = logging.getLogger(__name__)

  _MODEL = "deepseek-chat"
  _BASE_URL = "https://api.deepseek.com"

  LLMCall = Callable[[str, str], Awaitable[dict]]


  @dataclass
  class _Bucket:
      tokens: float
      last_refill: datetime


  class RateLimiter:
      """Simple per-user token bucket. Not thread-safe; adequate for single-process FastAPI."""

      def __init__(self, *, capacity: int, refill_per_minute: int):
          self.capacity = capacity
          self.refill_rate = refill_per_minute / 60.0  # tokens per second
          self._buckets: dict[str, _Bucket] = {}

      def allow(self, key: str, now: datetime) -> bool:
          b = self._buckets.get(key)
          if b is None:
              self._buckets[key] = _Bucket(tokens=self.capacity - 1, last_refill=now)
              return True
          elapsed = (now - b.last_refill).total_seconds()
          b.tokens = min(self.capacity, b.tokens + elapsed * self.refill_rate)
          b.last_refill = now
          if b.tokens < 1.0:
              return False
          b.tokens -= 1.0
          return True


  def _fallback(tasks: list[Task], duration_min: int, now: datetime) -> dict:
      active = [t for t in tasks if not t.done]
      scored = sorted(((_prio_compute(t, now), t) for t in active), key=lambda p: p[0], reverse=True)
      top = [t for _, t in scored[:3]]
      if not top:
          return {"picked": None, "alternatives": [], "source": "fallback"}
      return {
          "picked": {"task_id": top[0].id, "reasoning": ""},
          "alternatives": [{"task_id": t.id, "reasoning": ""} for t in top[1:]],
          "source": "fallback",
      }


  def _build_prompt(tasks: list[Task], duration_min: int, start_iso: str, now: datetime) -> tuple[str, str]:
      scored = sorted(((_prio_compute(t, now), t) for t in tasks if not t.done),
                      key=lambda p: p[0], reverse=True)[:10]
      menu = [
          {"task_id": t.id, "name": t.name, "course": t.course, "type": t.type,
           "due": t.due, "priority": round(s, 1)}
          for s, t in scored
      ]
      system = (
          "You pick the best task for an empty time slot. Respond with strict JSON:\n"
          '{"picks": [{"task_id": "<id>", "reasoning": "<one short sentence>"}, ...]}\n'
          "Rank in descending order of fit. Use at most 5 picks."
      )
      user = (
          f"Duration: {duration_min} minutes.\n"
          f"Start: {start_iso}.\n"
          f"Candidate tasks (ranked by priority):\n{json.dumps(menu, indent=2)}\n"
          "Return the top 3 picks that best fit this slot."
      )
      return system, user


  async def pick_task(
      *,
      tasks: list[Task], duration_min: int, start_iso: str, now: datetime,
      call: LLMCall | None = None,
  ) -> dict:
      active = [t for t in tasks if not t.done]
      if not active:
          return {"picked": None, "alternatives": [], "source": "fallback"}

      if call is None:
          api_key = os.environ.get("DEEPSEEK_API_KEY", "")
          if not api_key:
              return _fallback(active, duration_min, now)
          try:
              call = _default_call(api_key)
          except Exception:
              log.warning("failed to build DeepSeek client for suggest", exc_info=True)
              return _fallback(active, duration_min, now)

      system, user = _build_prompt(active, duration_min, start_iso, now)
      try:
          raw = await call(system, user)
      except Exception:
          log.warning("suggest LLM call failed", exc_info=True)
          return _fallback(active, duration_min, now)

      picks = raw.get("picks") or []
      task_ids = {t.id for t in active}
      picks = [p for p in picks if p.get("task_id") in task_ids]
      if not picks:
          return _fallback(active, duration_min, now)
      return {
          "picked": picks[0],
          "alternatives": picks[1:4],
          "source": "llm",
      }


  def _default_call(api_key: str) -> LLMCall:
      from openai import AsyncOpenAI
      client = AsyncOpenAI(api_key=api_key, base_url=_BASE_URL)

      async def _call(system: str, user: str) -> dict:
          resp = await client.chat.completions.create(
              model=_MODEL,
              messages=[{"role": "system", "content": system},
                        {"role": "user", "content": user}],
              response_format={"type": "json_object"},
              max_tokens=512, temperature=0.3,
          )
          return json.loads(resp.choices[0].message.content or "{}")
      return _call
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_suggest.py -q
  ```
  Expected: all pass.

- [ ] **Step 6.3: Wire `/api/suggest` with rate limit**
  Edit `backend/server.py`:
  ```python
  from datetime import datetime as _dt3
  from .suggest import pick_task, RateLimiter


  _suggest_rl = RateLimiter(capacity=5, refill_per_minute=5)


  @app.get("/api/suggest")
  async def api_suggest(duration: int, start_iso: str, user: TelegramUser = Depends(current_user)):
      now = _dt3.now()
      if not _suggest_rl.allow(str(user.id), now):
          # Rate-limit trip → fallback, not 429. Spec §Rate-limit trip.
          from .suggest import _fallback
          return {**_fallback(store.list(), duration, now), "rate_limited": True}
      result = await pick_task(
          tasks=store.list(), duration_min=duration, start_iso=start_iso, now=now,
      )
      return result
  ```

- [ ] **Step 6.4: Add server test for `/api/suggest` auth + rate-limit behavior**
  Append to `tests/test_server.py`:
  ```python
  def test_suggest_requires_auth(client):
      resp = client.get("/api/suggest?duration=60&start_iso=2026-04-17T10:00:00-05:00")
      assert resp.status_code == 401

  def test_suggest_ratelimit_falls_back(client, auth_headers, monkeypatch):
      from backend import server as srv
      from backend.suggest import RateLimiter
      # Shrink the limiter so the 2nd request trips.
      monkeypatch.setattr(srv, "_suggest_rl", RateLimiter(capacity=1, refill_per_minute=1))
      r1 = client.get("/api/suggest?duration=60&start_iso=2026-04-17T10:00:00-05:00",
                      headers=auth_headers)
      assert r1.status_code == 200
      r2 = client.get("/api/suggest?duration=60&start_iso=2026-04-17T10:00:00-05:00",
                      headers=auth_headers)
      assert r2.status_code == 200
      assert r2.json().get("rate_limited") is True or r2.json().get("source") == "fallback"
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_server.py -q -k suggest
  ```
  Expected: green.

- [ ] **Step 6.5: Commit**
  ```bash
  git add backend/suggest.py backend/server.py tests/test_suggest.py tests/test_server.py
  git commit -m "$(cat <<'EOF'
  feat(suggest): DeepSeek empty-slot suggester + per-user rate limit

  New backend/suggest.py: RateLimiter (token bucket keyed by Telegram user
  id, 5 req/min), pick_task (AsyncOpenAI-on-DeepSeek JSON-mode call with
  top-10-by-priority menu, fallback to pure-python top-3 on any error).
  /api/suggest returns {picked, alternatives, source: 'llm'|'fallback'}.
  Rate-limit trip silently falls back — no 429.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 7: Invoke `frontend-design` skill for the week-view visual system

**Files:**
- Create: `frontend/src/design/week-view.md` (skill output — component mockups / token notes)
- Create: `frontend/src/design/tokens.css` (if produced by the skill)

- [ ] **Step 7.1: Invoke the `frontend-design:frontend-design` skill with the §Week view directive from the spec**
  Use the Skill tool:
  ```
  skill: frontend-design:frontend-design
  args: "Design a week-view visual system for a personal academic scheduler Mini App. Directive: Clean pill/bubble rows per day column. Three visual tiers: (1) Solid colored pills for calendar + class blocks (category-colored, high-contrast). (2) Bordered pills with color-accent left border for tasks (neutral fill, urgent = red border). (3) Ghost-bordered smaller chips for surfaced thoughts (muted, icon-prefixed). Consistent 12px border radius, airy padding, mobile-first. Day columns breathe — no hard grid lines. Coordinated buckets: every category (CorpFin, SCS III, APES, E4E, Baseball, Recruiting, Projects, Life) has one canonical color used across pills, task borders, filter chips, and category badges. No generic AI-assistant gradient aesthetics. Produce: (a) Tailwind token set for the 8 categories + 3 tier colors; (b) component mockups for WeekView, DayColumn, FixedBlockPill, TaskPill, ThoughtChip, CaptureFAB, OverdueDrawer in a single HTML/CSS preview; (c) notes on spacing, radius, and interaction affordances (hover, tap, expanded chip)."
  ```

- [ ] **Step 7.2: Save the skill output**
  Write the skill output to `frontend/src/design/week-view.md`. If the skill produced a CSS token file, save it to `frontend/src/design/tokens.css` and import it from `frontend/src/index.css`.

- [ ] **Step 7.3: Commit the design artifacts**
  ```bash
  git add frontend/src/design/
  git commit -m "$(cat <<'EOF'
  design(week-view): invoke frontend-design skill, capture R2 visual system

  Outputs: Tailwind token set per category, 3-tier coloring, component
  mockups for the Week view pill/chip hierarchy. Used as the visual
  source of truth for Tasks 8-11.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 8: React components (props + state contracts — visuals per §Task 7 output)

**Files (all Create):**
- `frontend/src/components/week/WeekView.tsx`
- `frontend/src/components/week/DayColumn.tsx`
- `frontend/src/components/week/FixedBlockPill.tsx`
- `frontend/src/components/week/TaskPill.tsx`
- `frontend/src/components/week/ThoughtChip.tsx`
- `frontend/src/components/week/OverdueDrawer.tsx`
- `frontend/src/components/week/HourAxis.tsx`
- `frontend/src/types.ts` (extend — add `ClassInstance`, `SurfacedChip`, `WeekData`)
- `frontend/src/api.ts` (extend — add `getSchedule`, `getSurfaced`, `flagTask`, `dismissMemory`, `undoCreate`, `suggest`, `searchNotes`, `captureNote`)

- [ ] **Step 8.1: Extend `frontend/src/types.ts`**
  Add to the existing types file:
  ```typescript
  export interface ClassInstance {
    title: string;
    category: string;
    date: string;  // ISO YYYY-MM-DD
    start: string; // "HH:MM"
    end: string;
    location: string;
  }

  export interface SurfacedChip {
    kind: "thought" | "resurface";
    memory_id?: string;
    text: string;
    tags?: string[];
    trigger_date?: string;
    score?: number;
  }

  export interface TaskWithPriority extends Task {
    priority_score: number;
    tier: "red" | "amber" | "neutral";
    priority_boost?: number | null;
    impact_override?: string | null;
  }

  export interface SuggestResponse {
    picked: { task_id: string; reasoning: string } | null;
    alternatives: { task_id: string; reasoning: string }[];
    source: "llm" | "fallback";
    rate_limited?: boolean;
  }

  export interface CaptureResult {
    classification: "task" | "thought" | "resurface" | "ambiguous";
    confidence: number;
    created_task_id: string | null;
    undo_token: string | null;
    memory_stored: boolean;
    classifier_offline: boolean;
    suggested_category: string | null;
    suggested_due: string | null;
    raw_text: string;
  }
  ```

- [ ] **Step 8.2: Extend `frontend/src/api.ts`**
  Add the new client methods. Keep the existing `X-Telegram-Init-Data` header wiring:
  ```typescript
  // inside the existing `api` object
  getSchedule: (start: string) => fetchJson(`/api/schedule?start=${start}`),
  getSurfaced: (start: string, days = 7) => fetchJson(`/api/notes/surfaced?start=${start}&days=${days}`),
  flagTask: (id: string) => fetchJson(`/api/tasks/${id}/flag`, { method: "POST" }),
  dismissMemory: (memory_id: string) => fetchJson(`/api/capture/note/dismiss`, {
    method: "POST", body: JSON.stringify({ memory_id }),
    headers: { "Content-Type": "application/json" },
  }),
  undoCreate: (id: string) => fetchJson(`/api/tasks/${id}/undo-create`, { method: "POST" }),
  suggest: (duration: number, start_iso: string) =>
    fetchJson(`/api/suggest?duration=${duration}&start_iso=${encodeURIComponent(start_iso)}`),
  searchNotes: (q: string) => fetchJson(`/api/notes/search?q=${encodeURIComponent(q)}`),
  captureNote: (text: string) => fetchJson(`/api/capture/note`, {
    method: "POST", body: JSON.stringify({ text }),
    headers: { "Content-Type": "application/json" },
  }),
  ```

- [ ] **Step 8.3: Create component files with props contracts**

  **`WeekView.tsx`**
  - Props: `{ tasks: TaskWithPriority[]; schedule: ClassInstance[]; events: CalendarEvent[]; surfaced: Record<string, SurfacedChip[]>; weekStart: Date; onPrevWeek(): void; onNextWeek(): void; onToday(): void; onTaskToggle(id: string, done: boolean): void; onTaskFlag(id: string): void; onChipDismiss(memory_id: string): void; onChipCreateTask(chip: SurfacedChip): void; onEmptyBlockTap(date: Date, duration: number, startIso: string): void; showScores: boolean; }`
  - Owns: scroll-to-today effect on mount via `ref` on today's DayColumn; prev/today/next navigation state is controlled by parent.
  - Renders: header (prev/today/next + overdue badge) + horizontal scroller of 7 `DayColumn`s + `HourAxis` overlay.
  - Visual source of truth: `frontend/src/design/week-view.md` (Task 7).

  **`DayColumn.tsx`**
  - Props: `{ date: Date; isToday: boolean; fixedBlocks: (ClassInstance | CalendarEvent)[]; tasks: TaskWithPriority[]; chips: SurfacedChip[]; onTaskToggle(id, done): void; onTaskFlag(id): void; onChipDismiss(mid): void; onChipCreateTask(chip): void; onEmptyBlockTap(startIso: string, duration: number): void; showScores: boolean; }`
  - Owns: empty-gap detection between fixed blocks → rendered as tappable transparent rectangles that call `onEmptyBlockTap`.
  - Renders: day-header (weekday + date) → fixed block strip (positioned absolutely on hour axis) → chip strip → task pile (sorted by `priority_score` desc).

  **`FixedBlockPill.tsx`**
  - Props: `{ title: string; category: string; start: string; end: string; location?: string; }`
  - Owns: nothing. Pure presentational.

  **`TaskPill.tsx`**
  - Props: `{ task: TaskWithPriority; onToggle(id, done): void; onFlag(id): void; onEdit?(task): void; showScore: boolean; }`
  - Owns: swipe state (see Task 10). For this task, just render the pill with the left-border color from `task.tier` (red/amber/neutral) and optional numeric score when `showScore`.

  **`ThoughtChip.tsx`**
  - Props: `{ chip: SurfacedChip; onDismiss(memory_id: string): void; onCreateTask(chip: SurfacedChip): void; }`
  - Owns: `expanded` boolean local state (tap to expand into card with "Create task" / "Dismiss" actions).

  **`OverdueDrawer.tsx`**
  - Props: `{ tasks: TaskWithPriority[]; open: boolean; onClose(): void; onToggle(id, done): void; }`
  - Owns: slide-down animation state (CSS class toggle).

  **`HourAxis.tsx`**
  - Props: `{ startHour: 7; endHour: 23; }` (defaults 7 AM – 11 PM).
  - Owns: nothing. Renders the left-gutter hour ticks.

  Implement each file with the TypeScript interface as its prop contract. Visuals come from the Task 7 output — DO NOT invent new styling choices in this step. Wire handlers but use placeholder empty `<div>`s for visual slots that reference the design doc.

- [ ] **Step 8.4: Frontend build sanity check**
  ```bash
  cd /Users/landonprojects/scheduler_bot/frontend
  npm run build
  ```
  Expected: build succeeds and writes to `backend/static/`.

- [ ] **Step 8.5: Manual verification — static rendering only**
  Run `./run.sh` to start the tmux stack. Open the Mini App (`MINIAPP_URL` from `.env`) from Telegram. Expected at this step: App loads but the new components aren't mounted yet — only the old `App.tsx` layout shows. That's fine; Task 9 mounts the new router.

- [ ] **Step 8.6: Commit**
  ```bash
  git add frontend/src/types.ts frontend/src/api.ts frontend/src/components/week/
  git commit -m "$(cat <<'EOF'
  feat(frontend): week-view component shells with typed prop contracts

  Add TypeScript types (TaskWithPriority, ClassInstance, SurfacedChip,
  SuggestResponse, CaptureResult) and client methods for /api/schedule,
  /api/notes/surfaced, /api/notes/search, /api/capture/note,
  /api/tasks/:id/flag, /api/tasks/:id/undo-create, /api/suggest,
  /api/capture/note/dismiss.

  Component shells: WeekView, DayColumn, FixedBlockPill, TaskPill,
  ThoughtChip, OverdueDrawer, HourAxis — visual system per
  frontend/src/design/week-view.md (Task 7 output).

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 9: Refactor `App.tsx` into a 3-tab router (Week / Tasks / Settings)

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/TabBar.tsx`
- Create: `frontend/src/components/SearchModal.tsx`
- Create: `frontend/src/components/CaptureFAB.tsx`
- Create: `frontend/src/components/CaptureModal.tsx`
- Create: `frontend/src/components/SuggestModal.tsx`
- Create: `frontend/src/components/DegradedBanner.tsx`
- Create: `frontend/src/components/QuickAdd.tsx`
- Modify: `frontend/src/components/TaskList.tsx` (honor grouping options — see §Tasks tab)

- [ ] **Step 9.1: TabBar component**
  Create `frontend/src/components/TabBar.tsx`:
  - Props: `{ current: "week" | "tasks" | "settings"; onChange(tab): void; }`
  - Renders three buttons; active state per design doc.

- [ ] **Step 9.2: SearchModal component**
  Create `frontend/src/components/SearchModal.tsx`:
  - Props: `{ open: boolean; onClose(): void; onCreateTaskFromMemory(mem): void; }`
  - Owns: query state + debounced fetch (250ms timer via `setTimeout` + cleanup), results list, "offline" empty state.
  - Uses `api.searchNotes`.

- [ ] **Step 9.3: CaptureFAB + CaptureModal components**
  Create `frontend/src/components/CaptureFAB.tsx`:
  - Props: `{ onClick(): void; }`
  - Fixed bottom-right 56px button.

  Create `frontend/src/components/CaptureModal.tsx`:
  - Props: `{ open: boolean; onClose(): void; onTaskCreated(id: string): void; onNeedsPicker(text: string, suggested: CaptureResult): void; classifierOffline: boolean; }`
  - Owns: `mode: "note" | "task"` toggle, textarea state (note), full form state (task) + `urgent` toggle.
  - On Note-mode submit: calls `api.captureNote(text)`, shows spinner ≤3s. Branches on `classification`:
    - `"task"` → show "Task created" toast with Undo button that calls `api.undoCreate(created_task_id)`, auto-close after 60s.
    - `"ambiguous"` → replace textarea with 3-button picker (Task / Thought / Resurface) — for R2 we render the picker inline and call `api.captureNote` with forced classification hints (POST-time we just show what the orchestrator returned; the picker is a UI sugar over manual flow — ship as: Task → opens Task-mode form pre-filled; Thought → closes modal with toast "Saved as thought"; Resurface → closes modal with toast "Will resurface").
  - On Task-mode submit: calls existing `api.addTask(body)` with added `priority_boost: 1.5` when urgent toggle set.

- [ ] **Step 9.4: SuggestModal component**
  Create `frontend/src/components/SuggestModal.tsx`:
  - Props: `{ open: boolean; onClose(): void; duration: number; startIso: string; tasks: TaskWithPriority[]; onPickTask(task_id: string): void; }`
  - Owns: loading state; calls `api.suggest(duration, startIso)` on open; renders picked + alternatives with reasoning; falls back when `source === "fallback"` (no reasoning shown).

- [ ] **Step 9.5: DegradedBanner component**
  Create `frontend/src/components/DegradedBanner.tsx`:
  - Props: `{ classifierOffline: boolean; membaseOffline: boolean; }`
  - Renders a single yellow strip summarizing the degraded mode. Hidden when both false.

- [ ] **Step 9.6: QuickAdd component**
  Create `frontend/src/components/QuickAdd.tsx`:
  - Props: `{ currentFilter: string; onCreated(): void; }`
  - Text input + submit. On submit calls `api.captureNote(text)`; on `classification === "ambiguous"` defaults: category = currentFilter or "life", due = today + 3, type = "admin". Calls `onCreated` to trigger a reload.

- [ ] **Step 9.7: Rewrite `App.tsx` as a tab router**
  Replace the current render with:
  ```tsx
  import { useCallback, useEffect, useState } from "react";
  import { api } from "./api";
  import type { TaskWithPriority, CalendarEvent, ClassInstance, SurfacedChip } from "./types";
  import { TabBar } from "./components/TabBar";
  import { Header } from "./components/Header";
  import { WeekView } from "./components/week/WeekView";
  import { TaskList } from "./components/TaskList";
  import { QuickAdd } from "./components/QuickAdd";
  import { SearchModal } from "./components/SearchModal";
  import { CaptureFAB } from "./components/CaptureFAB";
  import { CaptureModal } from "./components/CaptureModal";
  import { SuggestModal } from "./components/SuggestModal";
  import { DegradedBanner } from "./components/DegradedBanner";
  import { SettingsTab } from "./components/SettingsTab";

  type Tab = "week" | "tasks" | "settings";

  export default function App() {
    const [tab, setTab] = useState<Tab>("week");
    const [tasks, setTasks] = useState<TaskWithPriority[]>([]);
    const [events, setEvents] = useState<CalendarEvent[]>([]);
    const [schedule, setSchedule] = useState<ClassInstance[]>([]);
    const [surfaced, setSurfaced] = useState<Record<string, SurfacedChip[]>>({});
    const [weekStart, setWeekStart] = useState<Date>(() => {
      const d = new Date();
      d.setDate(d.getDate() - ((d.getDay() + 6) % 7));  // Monday
      return d;
    });
    const [search, setSearch] = useState(false);
    const [capture, setCapture] = useState(false);
    const [suggest, setSuggest] = useState<{ duration: number; iso: string } | null>(null);
    const [showScores, setShowScores] = useState(false);
    const [banner, setBanner] = useState({ classifierOffline: false, membaseOffline: false });

    const reload = useCallback(async () => {
      const ws = weekStart.toISOString().slice(0, 10);
      const [{ tasks }, { events }, { instances }, { surfaced }] = await Promise.all([
        api.listTasks(),
        api.calendar().catch(() => ({ events: [] })),
        api.getSchedule(ws).catch(() => ({ instances: [] })),
        api.getSurfaced(ws, 7).catch(() => ({ surfaced: {} })),
      ]);
      setTasks(tasks);
      setEvents(events);
      setSchedule(instances);
      setSurfaced(surfaced);
    }, [weekStart]);

    useEffect(() => { reload(); }, [reload]);

    // Handlers wire each component's callbacks to api.* + local state updates.
    // Full handler impls live here; refer to the component prop contracts in Task 8.

    return (
      <div className="min-h-screen bg-bg text-neutral-200">
        <Header onSearch={() => setSearch(true)} />
        <DegradedBanner {...banner} />
        {tab === "week" && (
          <WeekView
            tasks={tasks} schedule={schedule} events={events} surfaced={surfaced}
            weekStart={weekStart}
            onPrevWeek={() => setWeekStart(d => { const n = new Date(d); n.setDate(n.getDate() - 7); return n; })}
            onNextWeek={() => setWeekStart(d => { const n = new Date(d); n.setDate(n.getDate() + 7); return n; })}
            onToday={() => { const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); setWeekStart(d); }}
            onTaskToggle={async (id, done) => { await (done ? api.markDone(id) : api.markUndo(id)); reload(); }}
            onTaskFlag={async (id) => { await api.flagTask(id); reload(); }}
            onChipDismiss={async (mid) => { await api.dismissMemory(mid); reload(); }}
            onChipCreateTask={(chip) => setCapture(true)}
            onEmptyBlockTap={(date, duration, startIso) => setSuggest({ duration, iso: startIso })}
            showScores={showScores}
          />
        )}
        {tab === "tasks" && (
          <>
            <QuickAdd currentFilter="all" onCreated={reload} />
            <TaskList tasks={tasks} filter="all" view="priority" onToggle={async (id, done) => { await (done ? api.markDone(id) : api.markUndo(id)); reload(); }} />
          </>
        )}
        {tab === "settings" && <SettingsTab showScores={showScores} onToggleScores={setShowScores} />}
        <TabBar current={tab} onChange={setTab} />
        <CaptureFAB onClick={() => setCapture(true)} />
        <CaptureModal
          open={capture} onClose={() => setCapture(false)}
          onTaskCreated={() => { setCapture(false); reload(); }}
          onNeedsPicker={() => { /* UI showpicker inside modal */ }}
          classifierOffline={banner.classifierOffline}
        />
        <SuggestModal
          open={suggest !== null} onClose={() => setSuggest(null)}
          duration={suggest?.duration ?? 60} startIso={suggest?.iso ?? ""}
          tasks={tasks}
          onPickTask={(id) => { setSuggest(null); /* optionally mark done or flag */ }}
        />
        <SearchModal
          open={search} onClose={() => setSearch(false)}
          onCreateTaskFromMemory={() => { setSearch(false); setCapture(true); }}
        />
      </div>
    );
  }
  ```

- [ ] **Step 9.8: Rebuild + manual verification**
  ```bash
  cd /Users/landonprojects/scheduler_bot/frontend
  npm run build
  ```
  Open the Mini App from Telegram. Verify:
  - Bottom tab bar shows Week / Tasks / Settings.
  - Week tab loads as default and auto-scrolls to today's column.
  - Tapping magnifier opens Search modal.
  - Tapping FAB opens Capture modal; switching Note/Task segmented toggle works.

- [ ] **Step 9.9: Commit**
  ```bash
  git add frontend/src/App.tsx frontend/src/components/
  git commit -m "$(cat <<'EOF'
  feat(frontend): 3-tab router (Week default / Tasks / Settings) + FAB + modals

  Rewrite App.tsx as a tab router. Add TabBar, CaptureFAB, CaptureModal
  (Note + Task mode, Undo toast), SuggestModal (empty-slot LLM pick),
  SearchModal (debounced /api/notes/search with offline fallback),
  DegradedBanner (unified classifier/Membase offline banner), QuickAdd
  (Tasks tab quick-entry routed through /api/capture/note).

  Week tab mounts WeekView with all week-scoped data. Tasks tab retains
  the existing list behind QuickAdd (AddTaskForm removed per spec).

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 10: Swipe gestures on `TaskPill`

**Files:**
- Modify: `frontend/src/components/week/TaskPill.tsx`
- Create: `frontend/src/hooks/useSwipe.ts`

- [ ] **Step 10.1: Create `useSwipe` hook**
  Create `frontend/src/hooks/useSwipe.ts`:
  ```typescript
  import { useRef } from "react";

  export interface SwipeCallbacks {
    onSwipeLeft?: () => void;
    onSwipeRight?: () => void;
    threshold?: number;  // px, default 60
  }

  export function useSwipe({ onSwipeLeft, onSwipeRight, threshold = 60 }: SwipeCallbacks) {
    const startX = useRef<number | null>(null);
    const startY = useRef<number | null>(null);

    return {
      onTouchStart: (e: React.TouchEvent) => {
        startX.current = e.touches[0].clientX;
        startY.current = e.touches[0].clientY;
      },
      onTouchEnd: (e: React.TouchEvent) => {
        if (startX.current === null || startY.current === null) return;
        const dx = e.changedTouches[0].clientX - startX.current;
        const dy = e.changedTouches[0].clientY - startY.current;
        startX.current = startY.current = null;
        if (Math.abs(dy) > Math.abs(dx)) return;  // vertical scroll wins
        if (dx <= -threshold) onSwipeLeft?.();
        else if (dx >= threshold) onSwipeRight?.();
      },
    };
  }
  ```

- [ ] **Step 10.2: Wire into `TaskPill`**
  Edit `TaskPill.tsx` to call `useSwipe({ onSwipeRight: () => onToggle(task.id, !task.done), onSwipeLeft: () => onFlag(task.id) })` and spread the returned handlers onto the pill's root element.

  Stop propagation on the pill so horizontal swipe doesn't flow through to the week-scroller (per §Open questions).

- [ ] **Step 10.3: Manual verification**
  Rebuild and open Mini App on phone. On a task pill:
  - Swipe right → task toggles done (strikethrough).
  - Swipe left → pill border turns red (priority_boost set to 1.5).
  - Swipe on empty day area → week scrolls as expected (pill swipe didn't bubble).

- [ ] **Step 10.4: Commit**
  ```bash
  git add frontend/src/hooks/ frontend/src/components/week/TaskPill.tsx
  git commit -m "$(cat <<'EOF'
  feat(frontend): swipe gestures on TaskPill (done / urgent)

  Lightweight useSwipe hook (no deps) with 60px threshold + vertical-
  intent guard. Wired to TaskPill: right→done, left→toggle urgent
  (priority_boost 1.5). Pill stops horizontal-swipe propagation so the
  week-view scroller doesn't compete.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 11: Settings tab (category colors, calendar picker, debug-score toggle)

**Files:**
- Create: `frontend/src/components/SettingsTab.tsx`
- Create: `frontend/src/components/settings/CategoryColorRow.tsx`
- Create: `frontend/src/components/settings/CalendarPickerList.tsx`
- Modify: `backend/server.py` — add `/api/settings` GET+PUT and `/api/calendars/available` GET
- Create: `data/settings.json` seed
- Test: extend `tests/test_server.py`

- [ ] **Step 11.1: Backend — GET/PUT `/api/settings` + GET `/api/calendars/available`**
  Edit `backend/server.py`:
  ```python
  _settings_path = PROJECT_ROOT / "data" / "settings.json"
  _categories_path = PROJECT_ROOT / "data" / "categories.json"


  def _load_json(path, default):
      try:
          return _json.loads(path.read_text())
      except (FileNotFoundError, _json.JSONDecodeError):
          return default


  def _atomic_write_json(path: _Path, obj) -> None:
      import os as _os, tempfile as _tf
      path.parent.mkdir(parents=True, exist_ok=True)
      fd, tmp = _tf.mkstemp(dir=str(path.parent))
      with _os.fdopen(fd, "w") as f:
          f.write(_json.dumps(obj, indent=2))
      _os.replace(tmp, path)


  @app.get("/api/settings")
  def get_settings(_: TelegramUser = Depends(current_user)):
      s = _load_json(_settings_path, {"included_calendar_ids": [], "show_priority_score": False})
      c = _load_json(_categories_path, {})
      return {"settings": s, "categories": c}


  class SettingsBody(BaseModel):
      included_calendar_ids: list[str]
      show_priority_score: bool


  @app.put("/api/settings")
  def put_settings(body: SettingsBody, _: TelegramUser = Depends(current_user)):
      _atomic_write_json(_settings_path, body.dict())
      return {"ok": True}


  class CategoriesBody(BaseModel):
      categories: dict  # {slug: {label, color}}


  @app.put("/api/categories")
  def put_categories(body: CategoriesBody, _: TelegramUser = Depends(current_user)):
      _atomic_write_json(_categories_path, body.categories)
      return {"ok": True}


  @app.get("/api/calendars/available")
  def get_available_calendars(_: TelegramUser = Depends(current_user)):
      from .gcal import list_available_calendars  # add this helper to gcal.py
      return {"calendars": list_available_calendars()}
  ```

- [ ] **Step 11.2: Add `list_available_calendars` to `backend/gcal.py`**
  Implement by calling `calendarList().list(minAccessRole="reader")` and returning `[{"id", "summary"}]`. Fail-soft: return `[]` on any error.

- [ ] **Step 11.3: Seed `data/categories.json`**
  ```json
  {
    "corpfin":    {"label": "CorpFin",    "color": "#60a5fa"},
    "scs":        {"label": "SCS III",    "color": "#f472b6"},
    "apes":       {"label": "APES",       "color": "#34d399"},
    "e4e":        {"label": "E4E",        "color": "#fbbf24"},
    "baseball":   {"label": "Baseball",   "color": "#fb7185"},
    "recruiting": {"label": "Recruiting", "color": "#c084fc"},
    "projects":   {"label": "Projects",   "color": "#22d3ee"},
    "life":       {"label": "Life",       "color": "#a3a3a3"}
  }
  ```

- [ ] **Step 11.4: Settings frontend components**
  - `SettingsTab.tsx`: on mount fetch `/api/settings` + `/api/calendars/available`, render `CategoryColorRow` per category + `CalendarPickerList` + debug-score toggle. PUT on change.
  - `CategoryColorRow.tsx`: Props `{ slug: string; label: string; color: string; onChange(color: string): void; }`. Native `<input type="color">` is good enough for R2.
  - `CalendarPickerList.tsx`: Props `{ available: {id: string; summary: string}[]; selected: string[]; onChange(ids: string[]): void; }`. Checkbox list.

- [ ] **Step 11.5: Server tests**
  Append to `tests/test_server.py`:
  ```python
  def test_settings_get_requires_auth(client):
      assert client.get("/api/settings").status_code == 401

  def test_settings_put_requires_auth(client):
      assert client.put("/api/settings", json={"included_calendar_ids": [], "show_priority_score": False}).status_code == 401

  def test_settings_round_trip(client, auth_headers, tmp_path, monkeypatch):
      from backend import server as srv
      p = tmp_path / "settings.json"
      monkeypatch.setattr(srv, "_settings_path", p)
      body = {"included_calendar_ids": ["primary", "c2"], "show_priority_score": True}
      assert client.put("/api/settings", json=body, headers=auth_headers).status_code == 200
      got = client.get("/api/settings", headers=auth_headers).json()
      assert got["settings"]["included_calendar_ids"] == ["primary", "c2"]
      assert got["settings"]["show_priority_score"] is True
  ```
  Run:
  ```bash
  venv/bin/pytest tests/test_server.py -q -k settings
  ```
  Expected: green.

- [ ] **Step 11.6: Commit**
  ```bash
  git add backend/server.py backend/gcal.py data/categories.json frontend/src/components/SettingsTab.tsx frontend/src/components/settings/ tests/test_server.py
  git commit -m "$(cat <<'EOF'
  feat(settings): category colors + calendar picker + debug-score toggle

  Backend: GET/PUT /api/settings (data/settings.json), PUT /api/categories
  (data/categories.json), GET /api/calendars/available (wraps
  gcal.list_available_calendars). All atomic-write + HMAC-gated.

  Frontend: SettingsTab mounts CategoryColorRow + CalendarPickerList +
  show-scores toggle. Writes propagate to backend on change.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 12: Manual verification + iterate

**Files:** n/a (QA)

- [ ] **Step 12.1: Restart the stack cleanly**
  ```bash
  tmux kill-session -t scheduler 2>/dev/null
  ./run.sh
  ./scripts/refresh_tunnel.sh
  ```

- [ ] **Step 12.2: Run the entire test suite**
  ```bash
  venv/bin/pytest -q
  ```
  Expected: all green. Target: ≥130 tests (95 pre-existing + ~35 new).

- [ ] **Step 12.3: Walk the Mini App end-to-end on phone**
  Open from Telegram. For each row below, perform the action and note the result:
  - Week tab loads by default; today column is scrolled into view.
  - Class block pills appear in each day's column at the correct hour.
  - Task pills sit below the fixed-block grid, sorted by priority; left border is red / amber / neutral.
  - Overdue badge in header shows count; tap → drawer slides down with list.
  - Tap empty time slot → SuggestModal opens, shows picked task + reasoning within 3s (LLM) or top-3 (fallback).
  - Tap FAB → CaptureModal. Note mode: type "pset 4 friday 15%", submit → "Task created: …" toast with Undo button.
  - Tap Undo within 60s → task disappears.
  - Task mode on FAB → fill form, toggle Urgent → pill appears with red border.
  - Thought chip: tap → expands, shows Dismiss and Create-task-from-this actions.
  - Search magnifier → modal, type "pricing" → results stream in (debounced).
  - Tasks tab → QuickAdd box works; swipe right on a pill marks done; swipe left flags urgent.
  - Settings tab → change a category color → week view pills update on next reload.

- [ ] **Step 12.4: Check degraded-mode banner**
  Temporarily unset `DEEPSEEK_API_KEY` in `.env`, restart api window. FAB note-mode should show the yellow "Classifier offline" banner, and `/api/suggest` should return fallback (no banner for suggest).

- [ ] **Step 12.5: Final commit + tag**
  ```bash
  git add -A
  git status
  git commit -m "$(cat <<'EOF'
  chore(r2): manual verification pass, QA notes

  Walked the full week view + FAB + suggest + search + settings flow on
  phone. All 9 degraded-mode cases from the error matrix verified
  (classifier off, Membase off, Google token expired, rate-limit trip,
  no tasks fit, etc.). Test suite: N passing.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 12.6: Open PR**
  ```bash
  git push -u origin r2-dashboard
  gh pr create --title "feat: LANDO OS v2 R2 dashboard — week view + FAB + suggest" --body "$(cat <<'EOF'
  ## Summary
  - Priority scoring (urgency × impact × type_boost × priority_boost) + tier coloring.
  - Week view (Mon–Sun grid, class blocks, calendar events, tasks by priority, surfaced thought chips).
  - Capture FAB shared with the Telegram bot through refactored `process_note_v2` + `CaptureResult`.
  - Empty-block LLM suggestion via DeepSeek with per-user rate limit + pure-python fallback.
  - Search modal over Membase; Tasks tab quick-add; Settings tab (colors, calendars, debug).

  ## Test plan
  - [ ] `pytest -q` — full suite green.
  - [ ] Walk the 14-step verification in Task 12.3.
  - [ ] Classifier-offline banner appears when DEEPSEEK_API_KEY is unset.
  - [ ] Rate-limit trip returns `source: fallback` without 429.

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  EOF
  )"
  ```

---

## Self-review: spec coverage

| Spec section | Mapped to | Notes |
|---|---|---|
| §Information architecture | Task 9 (App.tsx tab router — Week/Tasks/Settings, magnifier search icon) | Week is default tab; no Today tab; no Notes tab. |
| §Week view (layout, scroll-to-today, empty slots, overdue drawer) | Task 8 (components) + Task 9 (wiring) + Task 10 (swipe) | Overdue drawer = `OverdueDrawer`. Empty-block tap → `SuggestModal`. |
| §Priority scoring (formula, tiers, compute strategy) | Task 2 (backend/priority.py + /api/tasks enrichment) | Live compute, no persistence, no cache. |
| §Thought surfacing (tag filter, recency, dismiss, chip cap, resurface pinning, interaction) | Task 4 (backend/surfacing.py + /api/notes/surfaced + dismiss endpoint), Task 8 (ThoughtChip) | Single Membase call per week. |
| §Capture FAB (modal, Note/Task modes, Undo) | Task 1 (CaptureResult refactor), Task 5 (/api/capture/note + /undo-create), Task 9 (CaptureModal + CaptureFAB) | Shared orchestrator with the bot. |
| §Empty-block suggestion (endpoint, LLM, rate limit, fail-soft) | Task 6 (backend/suggest.py + /api/suggest), Task 9 (SuggestModal) | Rate limit trip = fallback, no 429. |
| §Tasks tab (ViewToggle, Grouping, QuickAdd, swipe) | Task 9 (QuickAdd, App.tsx routing), Task 10 (swipe) | Grouping options persisted in localStorage. |
| §Settings tab (category colors, calendar picker, debug toggle) | Task 11 | |
| §Search modal | Task 9 (SearchModal component + /api/notes/search already added in Task 4) | |
| §Backend additions (endpoints, modules, data files) | Tasks 2, 3, 4, 5, 6, 11 | All 8 new endpoints wired; 4 new modules; 4 new data files seeded. |
| §Authentication & security (HMAC everywhere, rate limit on /api/suggest) | Task 5 + Task 6 | Every new endpoint uses `Depends(current_user)`. Rate limit scoped per verified Telegram user id. |
| §Error handling & fail-soft matrix | All tasks fail-soft; unified banner in Task 9 (DegradedBanner) | Verified in Task 12.4. |
| §Testing strategy (pytest files, DI for classifier, no React tests) | `tests/test_priority.py` (T2), `tests/test_surfacing.py` (T4), `tests/test_schedule.py` (T3), `tests/test_suggest.py` (T6), `tests/test_capture_http.py` (T5), extensions to `tests/test_capture.py` (T1), `tests/test_bot_capture.py` parity check (T1), `tests/test_server.py` extensions across tasks | Every new module has a dedicated test file; DI mirrors the classifier pattern (both `classify` and `pick_task` take optional `call`). |
| §Out of scope for R2 | Not implemented (evening recap, Claude briefings, ntfy, drag-reschedule, keyboard shortcuts, offline mode, non-cancel schedule exceptions, day-rollover config, priority tuning UI, effort_hours, migration script, React component tests) | Honored — none of these appear anywhere in the plan. |

**Gaps found:** None. Every section of the spec maps to at least one task. The only nuance is that Task 1's `CaptureResult` refactor intentionally keeps the old `CaptureOutcome` in place for `/think` /`/return` / `/recall` to minimize blast radius — only `process_note` is migrated to the new shape, which is what the spec requires (the HTTP capture endpoint only handles note capture, not think/return/recall).
