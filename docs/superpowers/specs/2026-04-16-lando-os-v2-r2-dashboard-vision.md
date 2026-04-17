# LANDO OS v2 — R2 Dashboard Design

**Date:** 2026-04-16
**Status:** Design spec — ready for implementation planning.
**Scope:** Full R2 in a single ship — priority scoring + week view + FAB capture + thought surfacing + empty-block LLM suggestion.
**Supersedes:** The 2026-04-16 "R2 Dashboard Vision" draft (this file replaces it).

---

## One-sentence vision

Open the Mini App → see this week's Monday-to-Sunday grid with calendar blocks, priority-ranked tasks, and related past thoughts surfaced on the days they matter — plus a one-tap capture button that routes through the same classifier as the Telegram bot.

---

## Scope commit

R2 ships as **one spec, one implementation plan**, covering:

1. Priority scoring (3-factor formula, categorical impact, type boosts, urgency flag).
2. Week view as the new default tab (Mon–Sun grid, calendar + tasks + thoughts overlaid).
3. Capture FAB (note + task modes, shared orchestrator with the Telegram bot).
4. Thought surfacing (hybrid tag+semantic scoring, chips per day, dismiss memory).
5. Empty-block LLM suggestion (DeepSeek picks the best task for an open slot).
6. Search modal (semantic search over Membase memories).
7. Tasks + Settings tabs (refined list view + minimal preferences).

The vision doc's R2.0 / R2.1 / R2.2 decomposition is discarded; R2 ships whole.

---

## Information architecture

```
[ Week * ]  [ Tasks ]  [ Settings ]
    ^default — auto-scrolls today into view on load
```

- **Week** (default): 7-column Mon–Sun grid; auto-scrolls so today's column is centered on load.
- **Tasks**: full task list with category filter, view toggle (priority / timeline / course), sort + grouping options.
- **Settings**: category colors + which Google calendars to include.
- **No Today tab.** The Week view's today-highlight + Tasks tab together cover its use.
- **No Notes tab.** Notes surface contextually inside Week view. A header magnifying-glass icon opens a full-screen search modal on every tab.

---

## Week view

### Layout

- **7 columns**, Mon–Sun. Horizontal scroll on narrow viewports (phone). Today's column has a subtle border/tint and is scrolled into view on load.
- **Hour axis** on the left (7 AM – 11 PM).
- **Fixed blocks** (calendar events + `data/schedule.json` class blocks) render as solid colored pills positioned by time, colored by category.
- **Tasks due** render as bordered pills at the bottom of their due-date column, sorted by priority score (high → low). Left-border color encodes priority tier. Urgent-flagged tasks always show a red left border regardless of numerical score.
- **Surfaced thoughts** render as ghost-bordered chips between the fixed-block grid and the task pile. See §Thought surfacing.
- **Empty time slots** between fixed blocks are tappable — triggers the `/api/suggest` flow (see §Empty-block suggestion).

### Visual system (direction for frontend-design skill)

Implementation uses the `frontend-design:frontend-design` skill with this directive:

> Clean pill/bubble rows per day column. Three visual tiers:
> - **Solid colored pills** for calendar + class blocks (category-colored, high-contrast).
> - **Bordered pills with color-accent left border** for tasks (neutral fill, urgent = red border).
> - **Ghost-bordered smaller chips** for surfaced thoughts (muted, icon-prefixed).
>
> Consistent 12px border radius, airy padding, mobile-first. Day columns breathe — no hard grid lines. Coordinated buckets: every category has one canonical color used across pills, task borders, filter chips, and category badges. No generic AI-assistant gradient aesthetics.

### Week window + navigation

- **Calendar week (Mon–Sun).** Today's column floats within that week; visual emphasis is via border/tint, not position.
- **Prev / Today / Next buttons** up top.
- **Bounded by `schedule.json` term_start..term_end.** Prev disabled outside term_start; Next disabled past term_end. Default view is the current calendar week.
- Weeks before today are reachable (not disabled) but rarely useful — surfaced thoughts fade after 14 days (floor = 0.1× score) so past weeks stay quiet.

### Overdue tasks

- **Floating badge in header:** `3 overdue` pill, red-tinted, always visible.
- Tap → drawer sliding down from the header with a compact red-bordered list of all overdue tasks (name, days-overdue, category, actions).
- Overdue items do **not** re-render inside today's column. This keeps the grid clean and signals "this is past-due work, not today's plan."

---

## Priority scoring

### Formula

```python
score = urgency(days_until_due) * impact(task.type, task.impact_override) * type_boost(task.type, days_until_due) * priority_boost
```

**3 core factors + 1 optional flag.** No staleness and no effort_fit on tasks. (Staleness is reserved for thought surfacing decay only — tasks can't go "stale" if they have a due date.)

#### Urgency

Exponential decay based on days until due:

```python
days = (task.due - now.date()).days
urgency = max(10.0, 100.0 * math.exp(-0.15 * max(days, 0)))
# overdue (days < 0) = 100.0
```

Intuition: 0 days = 100, 1 day ≈ 86, 3 days ≈ 64, 7 days ≈ 35, 14 days ≈ 12, 30+ days = 10.

#### Impact (categorical buckets, derived from `type`)

```python
IMPACT = {
    "exam":         0.95,   # critical
    "presentation": 0.90,   # critical
    "essay":        0.75,   # high
    "project":      0.70,   # high
    "pset":         0.50,   # medium
    "case":         0.50,   # medium
    "reading":      0.35,   # medium
    "recurring":    0.20,   # low
    "admin":        0.15,   # low
    "ai-tutor":     0.20,   # low
}
```

Optional per-task override: `task.impact_override` (one of `"critical"|"high"|"medium"|"low"`) wins if present. Maps to `{critical: 0.95, high: 0.75, medium: 0.50, low: 0.20}`. Override is **not** set by default; AddTaskForm / FAB expose it as an optional dropdown.

#### Type boost

Applies only as deadline approaches (parent-doc values):

```python
if task.type in ("exam", "presentation") and days <= 7:  return 1.5
if task.type == "essay" and days <= 10:                  return 1.3
if task.type == "project" and days <= 14:                return 1.2
return 1.0
```

#### Priority boost (urgency flag)

`task.priority_boost: float = 1.0` — set to `1.5` when the user explicitly marks a task urgent (via AddTaskForm toggle, FAB toggle, or swipe-left gesture). Absent field = 1.0.

### Display (color-intensity only)

Each task pill has a color-coded left border:

- **Red:** score ≥ 80, OR task has `priority_boost == 1.5` (urgency flag always wins).
- **Amber:** 40 ≤ score < 80.
- **Neutral:** score < 40.

No numeric score rendered on the card. No qualitative label text. If a user wants to understand the ranking, the Settings tab exposes a "show scores (debug)" toggle that reveals the raw number per card.

### Compute strategy

- `backend/priority.py` — new pure-Python module. Exports `compute(task, now: datetime) -> float` and `tier(score, urgent_flag) -> "red" | "amber" | "neutral"`.
- Computed **live on every `/api/tasks` request**. No cache. At ~40 tasks the compute is <1ms.
- No persistence of score in tasks.json.

---

## Thought surfacing

### Where it appears

Inside each day's column in week view, between the fixed-block grid and the task pile. Chips are small, ghost-bordered, icon-prefixed.

- `🔁 resurface` — explicit `[RETURN]` item whose `trigger_date` is today. Pinned to top, doesn't count toward the per-day chip cap.
- `💭 thought` — `[NOTE]` or `[THINKING]` memory surfaced by scoring. Subject to cap.

### Per-day chip cap

- **Up to 3 thought chips + any number of resurface chips** per day.
- 4th+ thought chips collapse under a `+N more` pill inline; tap expands the overflow into the chip strip.
- Resurface chips never collapse.

### Scoring function (hybrid)

Given a day and its context (all tasks due + all calendar/class events + all category colors for the day):

1. **Tag filter (fast, deterministic).** Build a set `day_tags = categories(tasks) ∪ category_of(events) ∪ resurface_trigger_tags`. Score every memory by `tag_overlap = |memory.tags ∩ day_tags|`. Drop memories with `tag_overlap == 0`.
2. **Recency weight.** For each surviving memory, compute `recency = max(0.1, exp(-0.10 * age_days))`. Floor at 0.1× so old-but-tagged thoughts can still surface. (`[RETURN]` items with triggered dates bypass decay — they're pinned directly.)
3. **Semantic rank (expressive, bounded).** Take the top 20 candidates by `tag_overlap * recency`. For each, call `membase.search_memory` with query = day's concatenated task+event text, limit=20. Use returned similarity scores to break ties and reorder. Single Membase call per week (not per day) — see API below.
4. **Dismiss penalty.** For each memory in `data/dismissed.jsonl` with `dismissed_at` within the last 7 days: multiply score by 0 (fully hidden). 7–14 days: multiply by 0.5. Older: no penalty.
5. Return the top 3 per day.

### Dismiss persistence

`data/dismissed.jsonl` (gitignored, append-only):

```json
{"memory_id": "mb_abc123", "dismissed_at": "2026-04-16T14:22:00-05:00"}
```

Surfacing reads the file on each `/api/notes/surfaced` request, builds an in-memory map `{memory_id: dismissed_at}`, applies penalty. New dismissals append a line. No deduplication needed — latest entry wins.

### Chip interaction

- **Tap → inline expand.** Chip grows into a card showing: full text, timestamp, tags, "Create task from this", "Dismiss". Column reflows; other chips push down. Tap again (or an explicit `×`) collapses.
- **"Create task from this"** opens the FAB Task modal pre-filled with: `name` = chip text (truncated at 80 chars if longer), `category` = primary tag from the memory, `due` = the chip's day, `type` + `weight` blank.
- **"Dismiss"** appends to `dismissed.jsonl` and optimistically removes the chip from the UI.

---

## Capture FAB

### Placement

Bottom-right, every tab (Week, Tasks, Settings). Fixed position, ~56px circular, `+` icon.

### Modal

Two modes, segmented toggle at top: **Note** (default) · **Task**.

#### Note mode

- Single `<textarea>` for free text.
- **Submit blocks with spinner** (≤3s) while `/api/capture/note` calls `capture.process_note`.
  - High-conf result (≥0.75 + extractable date) → task created, modal shows "Task created: X" with 60s **Undo** button, then auto-closes.
  - Low-conf result → modal replaces textarea with 3-button picker (Task / Thought / Resurface), mirroring the Telegram inline-button flow.
  - Classifier offline (DEEPSEEK_API_KEY empty or 5xx) → falls through to the 3-button picker directly.
- Membase write is fire-and-forget from the orchestrator's perspective; failure queues to `data/membase_pending.jsonl` as with the bot.

#### Task mode

- Full field set: category, name, due, type, weight (free text), notes, **⚡ Urgent toggle**.
- Urgent toggle sets `priority_boost: 1.5` on creation.
- Submits to `POST /api/tasks` — no classifier round-trip.
- Modal closes on success, toast: "Task created: X" with 60s Undo button.

### Undo behavior

- Shared `undo_buffer` module with the bot, keyed by `(source, message_id_or_toast_id)`.
- Same 60s TTL.
- Mini App clicks the Undo button → `POST /api/tasks/:id/undo` (new) deletes the task + removes the Membase memory entry that was linked (if task was created via classifier).

### Share with the bot (orchestrator refactor)

`backend/capture.py` is refactored:

**Before:** `process_note` directly sends Telegram replies.

**After:** `process_note(text, *, chat_id, message_id, deps) -> CaptureResult` where `CaptureResult` is a new dataclass:

```python
@dataclass(frozen=True)
class CaptureResult:
    classification: Literal["task", "thought", "resurface", "ambiguous"]
    confidence: float
    created_task_id: str | None
    undo_token: str | None
    memory_stored: bool
    classifier_offline: bool
    suggested_category: str | None
    suggested_due: date | None
    raw_text: str
```

Two renderers consume this:
- `backend/bot.py` — renders as Telegram message + inline buttons.
- `backend/server.py` — renders as JSON response.

No logic duplication. The orchestrator remains the single source of truth for capture semantics.

---

## Empty-block suggestion

### Trigger

Tap an empty time slot (no fixed block) in week view → modal opens with a 1-line duration prompt (pre-filled from the slot's gap, editable) → call `/api/suggest`.

### Endpoint: `/api/suggest`

`GET /api/suggest?duration=60&start_iso=2026-04-17T10:00:00-05:00`

Returns:

```json
{
  "picked": {"task_id": "scs-kuhn-reading", "reasoning": "Due tomorrow, 60 min fits a single reading pass..."},
  "alternatives": [{"task_id": "...", "reasoning": "..."}, ...],
  "source": "llm" | "fallback"
}
```

### LLM call (DeepSeek)

- Same DeepSeek client as classifier, `model=deepseek-chat`, JSON mode.
- Prompt: top 10 active tasks by priority score + requested duration + start time-of-day + today's calendar context (what's adjacent to the slot). Returns ranked picks + one-sentence reasoning each.
- Rate limit: **5 requests/min per auth'd session.** Token-bucket in `backend/server.py`.

### Fail-soft

- Rate-limit trip → `source: "fallback"`, pick = top 3 active tasks by priority score that can be done in `<= duration` hours (using task `effort_hours` if present, otherwise assume any task fits). No reasoning text. Response still populates `picked` + `alternatives`.
- DeepSeek error → same fallback.
- No tasks fit → empty `picked`, toast says "Nothing fits that slot."

---

## Tasks tab

### Keep current structure, add

- **ViewToggle:** priority (default) / timeline / course — unchanged.
- **Grouping options** (new dropdown): None (flat, default) / Day (today/tomorrow/this week/later) / Category. Works independently of ViewToggle. Persists in localStorage.
- **Quick-add input** at the top of the list: single text field + submit button.
  - Submits to `POST /api/capture/note`. The classifier path handles parsing dates + categorizing.
  - Defaults when the classifier can't extract: `category` = current filter (falls back to `life` if filter is `all`), `due` = today+3, `type` = `admin`.
- **Remove** the inline `AddTaskForm` at the bottom of the list. FAB is the rich-entry path.
- **Swipe gestures on task pills:**
  - Swipe right → mark done (existing tap-to-toggle migrates here).
  - Swipe left → toggle urgent (sets/unsets `priority_boost: 1.5`).
  - Tap → open edit modal (name, due, category, type, weight, urgent toggle).

---

## Settings tab

Minimal for R2.

- **Category colors:** one swatch per category (CorpFin, SCS III, APES, E4E, Baseball, Recruiting, Projects, Life) with a color picker. Persists to `data/categories.json`.
- **Calendars to include:** checklist of Google Calendars discovered via `calendarList().list(minAccessRole="reader")`. Persists selected IDs to `data/settings.json` (new).
- **Debug: show priority scores** toggle (hidden gear reveal). Renders the raw score number on task pills when enabled.

Out of scope for R2: priority formula tuning, day-boundary rollover config, test user management.

---

## Search modal

- Magnifying-glass icon in the app header, every tab.
- Tap → full-screen modal with a single input + results list.
- Debounced (~250ms) `GET /api/notes/search?q=...` → wraps `membase.search_memory(q, limit=20)`.
- Each result card: timestamp, full text, tags, category badge, "Create task from this" action (same pre-fill behavior as chips).
- Empty state: recent memories (last 10) surfaced as a chronological list — browsing mode.
- Close via × or swipe-down.

---

## Backend additions

### Endpoints

```
GET  /api/tasks                          (extended) — adds priority_score + tier per task
GET  /api/schedule                       (new)     — returns data/schedule.json + computed weekly instances
GET  /api/notes/surfaced?start=<iso>&days=7   (new)  — returns {date: [chips]} for the whole week in one call
GET  /api/notes/search?q=...             (new)     — wraps membase.search_memory
POST /api/capture/note                   (new)     — proxies capture.process_note, returns CaptureResult JSON
POST /api/capture/note/dismiss           (new)     — appends to data/dismissed.jsonl
POST /api/tasks/:id/flag                 (new)     — toggles priority_boost
POST /api/tasks/:id/undo-create          (new)     — deletes task + unlinks memory; 60s window
GET  /api/suggest?duration=<min>&start_iso=<iso>   (new) — DeepSeek pick + fallback
```

Existing endpoints (`/api/calendar`, `/api/tasks` POST/PATCH/DELETE, `/api/tasks/:id/done`) are unchanged in contract.

### New modules

- `backend/priority.py` — scoring function + tier helper. Pure Python, no I/O.
- `backend/surfacing.py` — hybrid tag/semantic scoring for `/api/notes/surfaced`. Imports `membase.search_memory` and reads `dismissed.jsonl`.
- `backend/schedule.py` — loads `data/schedule.json`, expands weekly instances, applies term bounds + exceptions.
- `backend/suggest.py` — DeepSeek call + rate-limit bucket + fallback logic.
- `backend/capture.py` — refactored to return `CaptureResult`; no Telegram calls inside.

### New data files

- `data/schedule.json` — see schema below.
- `data/categories.json` — `{slug: {label, color}}` for all 8 categories.
- `data/settings.json` — `{included_calendar_ids: [...], show_priority_score: bool}`.
- `data/dismissed.jsonl` — append-only dismissal log.

### `data/schedule.json` schema

```json
{
  "term": {"start": "2026-03-30", "end": "2026-06-05"},
  "classes": [
    {
      "title": "SCS III",
      "category": "SCS III",
      "days": ["Mon", "Wed"],
      "start": "15:00",
      "end": "16:20",
      "location": "Wieboldt 310C",
      "exceptions": [{"date": "2026-04-20", "action": "cancel"}]
    }
  ]
}
```

Only `action: "cancel"` is supported in R2. Other actions (move, override) are out of scope.

### Data model changes (tasks.json)

No breaking changes. Two new optional fields:

- `impact_override: "critical" | "high" | "medium" | "low" | null` — default null (absent = derive from type).
- `priority_boost: float | null` — default null (absent = 1.0).

**No migration script.** The 37 existing tasks keep working; fields fall back to defaults. New AddTaskForm / FAB / quick-add can set both.

---

## Authentication & security

- All new endpoints use the existing `X-Telegram-Init-Data` HMAC-verified dependency. No new auth surface.
- **Rate limit on `/api/suggest`:** 5 requests / minute / session. Uses a simple in-memory token bucket keyed by the verified Telegram user ID. Trip → fallback to pure-Python top-3.
- `/api/capture/note/dismiss` has no rate limit but is append-only, so failure modes are bounded.

---

## Error handling & fail-soft matrix

| Failure | Behavior |
|---------|----------|
| DeepSeek offline (capture) | FAB Note mode falls through to 3-button picker. Persistent yellow banner at top: "Classifier offline — notes saved without auto-classification." |
| DeepSeek offline (`/api/suggest`) | Fall back to pure-Python top-3. No banner. |
| Membase offline (store) | Note text queued to `membase_pending.jsonl`. Toast confirms save. Banner: "Memory sync delayed." |
| Membase offline (search) | `/api/notes/search` returns `{results: [], offline: true}`. Search modal shows "Search offline." |
| Membase offline (surface) | `/api/notes/surfaced` returns empty chip list. Week view silently shows no chips. |
| Google Calendar token expired | `/api/calendar` returns `{events: []}` + warning log. Week view shows tasks + schedule.json without external events. |
| tasks.json write fails | 500 to client. Existing behavior. |
| Rate-limit tripped on `/api/suggest` | 200 with fallback payload + `source: "fallback"`. No error. |

One unified degraded-mode banner component handles the classifier-offline + Membase-offline cases.

---

## Testing strategy

Backend-heavy, matching the current 95-test pytest pattern. No React unit tests. Manual verification in Telegram / the Mini App for UI changes.

New pytest files:

- `tests/test_priority.py` — urgency curve, impact bucket mapping, type_boost windows, priority_boost multiplier, tier thresholds + urgency-flag override.
- `tests/test_surfacing.py` — tag overlap filter, recency floor, dismiss penalty windows (0–7d, 7–14d, 14+d), resurface pinning, chip cap, semantic rank integration (mocked Membase).
- `tests/test_schedule.py` — loader, weekly instance expansion, term bounds, `cancel` exception handling.
- `tests/test_suggest.py` — DeepSeek success path (mocked), rate-limit bucket behavior, fallback on error, fallback on rate-limit trip.
- `tests/test_capture_http.py` — `/api/capture/note` renders `CaptureResult` to JSON correctly for each classification outcome. Classifier DI'd.
- Extend `tests/test_capture.py` — confirm `process_note` returns `CaptureResult` shape instead of calling Telegram.
- Extend `tests/test_bot_capture.py` — confirm the bot renderer turns `CaptureResult` into the same messages it used to send.
- Extend `tests/test_server.py` — auth on every new endpoint; shapes of responses; dismissal appends correctly.

**UI verification** is manual: ship to the Mac Mini, open the Mini App from Telegram on phone, walk through the week view, add tasks via FAB, tap chips, swipe cards, verify suggestion flow. Document findings in commit messages.

---

## Implementation order (for plan author)

1. **Refactor `capture.process_note` → `CaptureResult` + split renderers.** No behavior change; tests stay green. Unblocks the HTTP capture endpoint.
2. **`priority.py` + extend `/api/tasks`.** Add fields + tier computation. No UI change yet.
3. **`schedule.py` + `data/schedule.json` + `/api/schedule`.** Load, expand, bound.
4. **`surfacing.py` + `/api/notes/surfaced` + `/api/notes/search`.** Wire Membase, read dismissed.jsonl.
5. **`/api/capture/note` + `/api/capture/note/dismiss` + `/api/tasks/:id/flag` + `/api/tasks/:id/undo-create`.** Thin HTTP wrappers on existing logic.
6. **`/api/suggest` with rate limit + fallback.**
7. **Invoke `frontend-design:frontend-design` skill** to design the week-view visual system per the directive in §Week view. Output a fresh component set.
8. **New React components:** `WeekView`, `DayColumn`, `FixedBlockPill`, `TaskPill`, `ThoughtChip`, `CaptureFAB`, `CaptureModal`, `SuggestModal`, `SearchModal`, `OverdueDrawer`, `DegradedBanner`.
9. **Refactor `App.tsx`** into a tab router (Week / Tasks / Settings). Remove `AddTaskForm` from Tasks tab; replace with `QuickAdd`.
10. **Swipe gestures on `TaskPill`.** Lightweight touch handler; no external lib.
11. **Settings tab** (category colors, calendar picker, debug-score toggle).
12. Manual verification + iterate.

---

## Out of scope for R2

- Evening recap cron.
- Claude-enhanced morning briefings (priority score does NOT change briefing output in R2).
- ntfy.sh / second push rail.
- Drag-to-reschedule in week view.
- Keyboard shortcuts.
- Offline mode / service worker.
- Schedule exceptions other than `cancel` (move, override).
- Day-boundary rollover config (locked at local midnight).
- Priority formula tuning UI in Settings.
- `effort_hours` field on tasks (would require enter-time input; defer until staleness/effort becomes a pressing signal).
- Migration script for existing 37 tasks (optional fields default cleanly).
- React component tests (Vitest / Playwright).

---

## Open questions (deferred, noted for post-ship)

- **Swipe on mobile gesture conflict:** swipe-right = done, horizontal-scroll = next week. Conflict on phone. Mitigation: task pills live inside day columns with vertical scroll; horizontal swipe on a pill is handled by the pill, not the grid. Edge case: swipe starts on a pill but extends past its bounds. Decide during implementation.
- **Category colors overriding theme:** if the user picks a red for Projects and the priority tier also uses red, task pills could double-encode. Pick the tier color from a reserved palette that doesn't overlap category colors (e.g., desaturated warn tones), OR disable category color on the left border when tier is red. Implementation-time call.
- **Resurface count cap:** `resurface chips don't count toward the 3-chip cap` — if you have 10 active resurfaces on one day, the column explodes. In practice, <3 expected. Revisit if it happens.
- **Dismiss granularity:** currently per-memory for 7 days. No UI to "undismiss." If you miss one, it reappears in 7 days on its own. Good enough for v1.

---

## Reference

- R1 spec: `docs/superpowers/specs/2026-04-16-lando-os-v2-r1-capture-design.md`
- R1 plan: `docs/superpowers/plans/2026-04-16-lando-os-v2-r1-capture.md`
- Parent vision: `LANDO_OS_V2_DIRECTIONS.md` (§3 priority, §5 week view, §7 push — push remains out of scope)
- Memory spec: `docs/superpowers/specs/2026-04-16-membase-mcp-client-design.md`
- Mini App plan: `docs/superpowers/plans/2026-04-13-telegram-miniapp.md`
- Visual system: invoke `frontend-design:frontend-design` skill with the directive in §Week view during implementation.
