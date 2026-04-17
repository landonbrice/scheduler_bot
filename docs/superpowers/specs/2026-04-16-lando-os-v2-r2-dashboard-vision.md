# LANDO OS v2 — R2 Dashboard Vision

**Date:** 2026-04-16
**Status:** High-level vision — NOT implementation-ready. Next session will decompose this into one or more concrete specs + plans.
**Scope:** The Mini App becomes the chief-of-staff surface. Week view is the default. Notes are not a separate tab — they surface contextually inside the week. Capture happens from the dashboard via a floating button. Tasks are sorted by a lightweight priority score.

---

## One-sentence vision

Open the Mini App → see the week at a glance, with your calendar blocks, tasks sorted by priority, and relevant past thoughts surfaced on the days they matter — plus a one-tap capture button that writes straight to Membase.

---

## The four integrations

### 1. Week View (new default)

Replaces the task list as the home tab. List view stays accessible as a secondary tab.

- **Layout:** 7-column grid (Mon–Sun), scrolls horizontally on narrow viewports. Current day has a subtle border/tint.
- **Time axis:** hours 7 AM – 11 PM on the left, day columns on the right.
- **Fixed blocks** (render as colored bars): Google Calendar events + hardcoded class schedule from `data/schedule.json` (new). Color by category.
- **Tasks due** render as cards at the bottom of their due-date column, ordered by priority score (high → low). Overdue tasks stack at the top of today's column in red.
- **Surfaced thoughts** (see §2) render as small muted chips, also in the relevant day's column but visually distinct from tasks (ghost border, smaller).
- **Empty time blocks** are clickable → triggers a "what should I work on right now?" API call (deferred to R2.5 — priority + available duration → Claude picks).
- **Navigation:** `< Prev week` / `Today` / `Next week >` buttons up top.

### 2. Surfaced thoughts (the novel piece)

Notes captured via `/note` or `/think` don't live in a passive feed anywhere — they surface **on the days they're relevant**, weighted by three signals:

1. **Tag/project match with that day's tasks or events.** A thought tagged `projects` surfaces on days where a `projects` task is due or a relevant calendar block appears.
2. **Recency decay.** Newer thoughts weigh more; drop off after ~14 days unless re-referenced.
3. **Explicit resurface.** Any `[RETURN]` item with a `trigger_date` of that day pins to the top of the chip strip.

Each chip shows: a ghost icon (💭 for thought, 🔁 for resurface), truncated text, and a tap action that expands inline with full text + "create task from this" + "dismiss."

**Key design question for next session:** what's the scoring function? Options include (a) simple tag-overlap count, (b) Membase semantic search where the query is the day's tasks+events text, (c) LLM ranking over candidates. Start with (a), upgrade to (b) if (a) feels stale.

### 3. Capture FAB (floating button)

Bottom-right `+` button on every tab. Tap → modal with two modes:

- **Note** (default): single free-text area. Submits to `POST /api/capture/note` which routes through the same `capture.process_note` orchestrator as the Telegram bot. Same confirmation flow — high-conf writes task immediately with an in-modal "undo"; low-conf shows the same 3-button picker inline.
- **Task**: structured form (category, name, due, type, weight, notes). Skips the classifier entirely — just writes a task.

Modal closes on success with a toast confirming what happened ("Task created" or "Note saved").

### 4. Lightweight priority scoring

`score = urgency(days_until_due) × impact(parsed_weight) × type_boost(type, days)` — exactly the R2 spec from the vision doc, deliberately *not* including effort/staleness/freshness. Computed on demand in `/api/tasks` and the briefing. **No schema change** to tasks.json.

- Tasks view sorts by score by default (toggle to date/course available).
- Week view uses score to order within a day's task stack.
- Priority is visible as a small number on each task card (transparency — you can see why something's ranked high).

---

## Information architecture (tabs)

```
[ Today ]  [ Week * ]  [ Tasks ]  [ Settings ]
                ^default
```

- **Today:** condensed version of the current dashboard (today's schedule + today's tasks + surfaced thoughts for today). Quick-look view for "what am I doing right now."
- **Week:** the new default — §1 above.
- **Tasks:** the current full list view, refined with the priority score sort.
- **Settings:** category colors, which calendars to include, test-user management later.

Notes are NOT a separate tab — they live inside Week and Today via the surfacing mechanism, plus a search modal accessible from anywhere (tap a magnifying glass in the header → semantic search UI).

---

## Backend additions this vision implies

- `GET /api/tasks` — extend response with `priority_score` field.
- `GET /api/schedule` — new endpoint, returns `data/schedule.json` (hardcoded class times).
- `GET /api/notes/surfaced?date=<iso>` — returns Membase memories weighted for that date (this is the novel endpoint; design TBD next session).
- `GET /api/notes/search?q=...` — wraps `search_memory`.
- `POST /api/capture/note` — proxies to `capture.process_note` so FAB and bot share the same flow.
- `POST /api/capture/task-confirm` — for the inline-button equivalent flow inside the modal.
- `priority.py` module — new, pure-Python scoring function.
- `data/schedule.json` — new, static class schedule.

No tasks.json schema change required.

---

## Proposed decomposition (three separate ships)

This vision is too big for one spec + plan. Next session should pick one:

**R2.0 — Priority scoring (backend + minimal UI)**
- `priority.py` module, extend `/api/tasks` response.
- Tasks view: add sort toggle + show score number.
- No week view yet, no FAB, no surfacing. Proves the scoring feels right before we build UI on top of it.
- Smallest ship, ~1 session.

**R2.1 — Week view + FAB**
- Full week grid, tabs, capture FAB.
- Uses priority score for task ordering within days.
- No thought surfacing yet (chips render empty slots).
- ~2–3 sessions.

**R2.2 — Thought surfacing**
- `/api/notes/surfaced` endpoint with scoring function.
- Chip strip in the week view.
- Notes search modal.
- ~1–2 sessions, high design judgment required on the scoring function.

I'd do **R2.0 first** — it's small, it de-risks the scoring formula with real usage, and both R2.1 and R2.2 depend on it.

---

## Open questions for next session

These need real brainstorming before any implementation:

1. **Thought-surfacing weight function.** Tag overlap vs semantic search vs LLM ranking. Start simple, but which simple?
2. **Capture FAB "Note" mode and classifier round-trip.** Do we block the modal UI on the classifier call (1-3 s), or fire-and-forget with a toast + later notification? Latency-vs-consistency tradeoff.
3. **Week view on mobile.** 7 columns on a phone is cramped. Do we collapse to a day-list view below ~600 px, or keep scrolling and accept the squeeze?
4. **Timezone handling.** Current code uses `date.today()` in local time and `datetime.now(timezone.utc)` for Membase timestamps. Week view needs consistent boundary logic for "when does today end."
5. **Priority score transparency.** Show the number (current plan), or hide it and show a qualitative label ("urgent" / "soon" / "flexible")? Users who see numbers will argue with them.
6. **Settings tab scope.** Is it worth shipping in R2, or punt entirely? Category colors and calendar-include toggles are the two real items.
7. **Schedule.json structure.** Flat list of {day, start, end, title, location}? Per-class blocks with a category? Do we need recurrence rules?
8. **Notes search UI.** Modal over the current tab, or dedicated search view? Results rendering?

---

## What's out of scope for R2 entirely

- Evening recap cron (cheap, orthogonal — add whenever).
- Claude-enhanced briefings (pending data + usage feedback).
- ntfy.sh / second notification rail (not needed — Telegram push works).
- Drag-to-reschedule in week view (stretch, explicit deferral).
- Keyboard shortcuts (not relevant — mobile-first).
- Offline mode / service worker (not needed — always online).

---

## Reference

- R1 spec: `docs/superpowers/specs/2026-04-16-lando-os-v2-r1-capture-design.md`
- R1 plan: `docs/superpowers/plans/2026-04-16-lando-os-v2-r1-capture.md`
- Vision: `LANDO_OS_V2_DIRECTIONS.md` (§3 priority, §5 week view, §7 push — all relevant)
