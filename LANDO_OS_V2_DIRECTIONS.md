# LANDO OS v2 — Personal Cognitive Infrastructure

## Vision

This is not a task tracker. This is a **personal operating system** — a system that captures your thinking, reasons about your time, and proactively surfaces the right thing at the right moment. It should feel like a sharp chief of staff who knows your schedule, your projects, your half-formed ideas, and your energy patterns.

The north star: **you should never have to think about what to work on next.** You open Telegram or the dashboard, and the system has already figured it out — accounting for deadlines, grade weights, your available time blocks, what you captured at 2am last night, and the fact that you have a game tomorrow.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LANDO OS v2                                  │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐               │
│  │ CAPTURE  │   │   MEMORY     │   │  SCHEDULER   │               │
│  │          │   │              │   │              │               │
│  │ /note    │──▶│  Membase     │──▶│  Priority    │               │
│  │ /task    │   │  (semantic)  │   │  Algorithm   │               │
│  │ /think   │   │              │   │              │               │
│  │ voice*   │   │  tasks.json  │   │  Time Block  │               │
│  │          │   │  (structured)│   │  Engine      │               │
│  └──────────┘   └──────┬───────┘   └──────┬───────┘               │
│                        │                  │                        │
│                  ┌─────▼──────────────────▼─────┐                 │
│                  │       REASONING LAYER         │                 │
│                  │    (Claude API on each run)    │                 │
│                  └─────┬───────────────────┬─────┘                 │
│                        │                   │                       │
│                  ┌─────▼─────┐      ┌─────▼──────┐               │
│                  │  PUSH     │      │  DASHBOARD  │               │
│                  │           │      │             │               │
│                  │ Telegram  │      │  Week View  │               │
│                  │ ntfy.sh   │      │  Task List  │               │
│                  │ Cron 7am  │      │  Notes Feed │               │
│                  │ Evening   │      │  FastAPI    │               │
│                  └───────────┘      └─────────────┘               │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    DATA SOURCES                               │  │
│  │  Google Calendar · tasks.json · Membase · Class Schedule DB  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Design Decisions (already made — Claude Code should follow these)

### 1. Membase is episodic memory, tasks.json is structured state

Do NOT try to replace tasks.json with Membase. They serve different purposes:
- `tasks.json` = structured, queryable, mutable state. "What's due Friday?" is a JSON filter.
- Membase `memory` = episodic stream. "What was I thinking about the CorpFin project?" is semantic search.
- Membase `wiki` = reference docs. Course syllabi, class schedule, grade weights, recurring patterns.

The reasoning layer (Claude API) reads BOTH on each briefing generation. It queries Membase for relevant context, reads tasks.json for deadlines, and synthesizes.

### 2. Capture is unstructured, classification is automatic

The `/note` command should accept raw text — no format requirements. Claude extracts:
- **Task?** → create structured task in tasks.json, store original note in Membase with task ID link
- **Thinking note?** → store in Membase memory, tag with relevant courses/projects
- **Return-to flag?** → store in Membase with `resurface: true` flag, attach trigger conditions
- **Ambiguous?** → store in Membase, don't create a task, let it surface naturally via semantic search

The bot should confirm what it did: "📝 Saved note. Created task `cf-proj-research` due Apr 25. Linked to your valuation project."

### 3. Priority is a score, not just a sort

Every task gets a `priority_score` computed on each briefing run. The score is a weighted product:

```python
def compute_priority(task, now, context):
    days = (task.due - now).days
    
    # Urgency: exponential decay as deadline approaches
    # 0 days = 100, 1 day = 80, 3 days = 50, 7 days = 25, 14+ days = 10
    urgency = max(10, 100 * math.exp(-0.15 * max(days, 0)))
    
    # Impact: based on grade weight
    # Parse weight string to percentage, normalize to 0-100
    impact = parse_weight_to_score(task.weight)  # e.g., "35%" → 70, "part of 15%" → 25
    
    # Effort mismatch: penalize if estimated hours > available hours in next block
    # (requires effort_hours field on tasks + awareness of current time/calendar)
    effort_fit = 1.0  # default, refined when we have effort estimates
    
    # Staleness: boost tasks not touched in a while
    days_since_touched = (now - task.last_touched).days if task.last_touched else days
    staleness = min(1.5, 1.0 + 0.05 * days_since_touched)
    
    # Type boost: exams and major papers get a prep-time bonus
    # (you need to START studying 5+ days before an exam, not the night before)
    type_boost = 1.0
    if task.type == "exam" and days <= 7:
        type_boost = 1.5
    elif task.type == "essay" and days <= 10:
        type_boost = 1.3
    elif task.type == "project" and days <= 14:
        type_boost = 1.2
    
    return urgency * (impact / 100) * effort_fit * staleness * type_boost
```

### 4. Non-class tasks are first-class citizens

Add these categories alongside the four courses:
- **Baseball** — practice schedules, player follow-ups, app development work
- **Recruiting** — interview prep, networking follow-ups, application deadlines  
- **Projects** — baseball SaaS platform, personal infra, side projects
- **Life** — errands, health, social, personal

Color scheme extensions:
- Baseball: `#dc2626` (red)
- Recruiting: `#0ea5e9` (sky blue)
- Projects: `#f97316` (orange)
- Life: `#a3a3a3` (neutral gray)

These categories should work identically to course tasks — they show up in the priority algorithm, the week view, the briefing, everything.

### 5. Week view is the primary dashboard view

The default dashboard view should be a **7-day calendar grid**, not the task list. The list view still exists as a secondary view.

Week view spec:
- 7 columns (Mon–Sun), scrollable if on mobile
- **Fixed blocks** (from Google Calendar + hardcoded class schedule) render as colored bars with time + title
- **Tasks due** render at the bottom of their due-date column as cards
- **Available time** is visible as white/empty space between fixed blocks
- Clicking an available time block opens a "What should I work on?" suggestion (Claude API call using priority scores + available duration)
- Tasks can be dragged between days to adjust due dates (stretch goal, not MVP)
- Current day column has a subtle highlight/border
- Overdue tasks stack at the top of today's column in red

### 6. The evening recap is as important as the morning briefing

Add a second cron at 9pm:
- "Here's what you got done today" (tasks marked complete)
- "Here's what's still open for tomorrow"
- "Heads up: [X] is due in 2 days and you haven't started"
- If there are Membase notes from today, surface them: "You noted: [note]. Want to create a task from this?"

### 7. Push notifications via ntfy.sh

Add ntfy.sh alongside Telegram. It gives native iOS/Mac notifications without building a full app.

Setup:
```bash
# Self-hosted (on the Mac Mini) or use ntfy.sh cloud
# Topic: lando-academic (private, password-protected)
# iOS: install ntfy app, subscribe to topic
# Mac: ntfy app or just curl from scripts

# Sending a notification:
curl -d "SCS Midterm Essay due in 2 days — 35% of grade" \
     -H "Title: ⚠️ Deadline Alert" \
     -H "Priority: high" \
     -H "Tags: warning" \
     https://ntfy.sh/lando-academic-RANDOM_SUFFIX
```

Notification triggers:
- Task due tomorrow (8pm the night before)
- Task due today (7am morning briefing)
- Crunch week detected (Sunday evening)
- Exam in 3 days with no study sessions logged

---

## Updated File Structure

```
~/academic-bot/
├── venv/
├── config.env                    # All secrets and config
├── requirements.txt
│
├── core/
│   ├── __init__.py
│   ├── tasks.py                  # Task CRUD, priority computation, tasks.json I/O
│   ├── memory.py                 # Membase integration (add/search memory + wiki)
│   ├── calendar_client.py        # Google Calendar API wrapper
│   ├── capture.py                # /note processing — Claude extraction + classification
│   ├── priority.py               # Priority algorithm (the scoring function)
│   ├── briefing.py               # Briefing generation (morning + evening)
│   └── notifications.py          # ntfy.sh + Telegram push logic
│
├── bot/
│   ├── __init__.py
│   └── telegram_bot.py           # All Telegram command handlers
│
├── server/
│   ├── __init__.py
│   ├── app.py                    # FastAPI app, API routes, serves static
│   └── static/
│       └── index.html            # React dashboard (single file, CDN deps)
│
├── data/
│   ├── tasks.json                # Structured task state
│   ├── schedule.json             # Hardcoded class schedule (times, locations)
│   └── categories.json           # Course + non-course category definitions
│
├── scripts/
│   ├── setup_google.py           # One-time Google OAuth
│   ├── seed_membase.py           # Seed Membase wiki with syllabi + schedule
│   └── run.sh                    # Start bot + server + cron
│
├── cron/
│   ├── morning_briefing.py       # 7am cron entry point
│   └── evening_recap.py          # 9pm cron entry point
│
└── CLAUDE_CODE_DIRECTIONS.md     # This file
```

---

## Membase Integration Details

### Seeding (run once via `seed_membase.py`)

Create wiki documents for each course:

```python
# For each course, create a wiki doc with:
wiki_docs = [
    {
        "title": "CorpFin (BUSN 20410) — Spring 2026",
        "content": """
        Professor: Constantine Yannelis
        Schedule: [section time TBD]
        Grading: Final 35-60%, Midterm 0-25%, Homeworks 15%, Project 15%, Participation 10%
        Key dates: Midterm May 1, Project presentations May 9, Final May 22
        Notes: Closed book exams. Groups up to 6 for HW. Project must use ChatGPT.
        Textbook: Berk and DeMarzo (optional). Problem sets are best exam prep.
        """
    },
    {
        "title": "SCS III — Spring 2026",
        "content": """
        Instructor: Connor Strobel
        Schedule: MW 3:00-4:20pm, Wieboldt 310C
        Office Hours: Mondays 9:30-12:30, Gates-Blake 331
        Grading: Final Paper 30%, Midterm Essay 35%, Participation 15%, Self-Feedback 10%, Canvas Posts 5%, Presentation 5%
        Key dates: Self-Feedback Apr 19, Midterm Essay Apr 28, Presentation May 13, Final Paper May 28
        Canvas posts due 11:59pm night before each class (every M/W).
        Reading sequence: Kuhn → Foucault → West & Zimmerman → Said → Mahmood → Arendt → Herman & Chomsky → Horkheimer & Adorno → Eco → Zizek
        3+ unexcused absences may result in failing.
        """
    },
    {
        "title": "APES (ANTH 21428) — Spring 2026",
        "content": """
        Instructor: Dr. Larissa Smith
        Schedule: TTh 9:30-10:10am lecture (Eckhart 133) + 10:20-10:50am lab (Haskell basement)
        Grading: 280 total points — Lecture Attendance 30, Lab Attendance 10, Lab Exercises 40, Midterm 50, Final 50, Debate 50, Individual Project 50
        Key dates: Midterm Apr 21 (online 9am-8pm), Debates Week 6-8, Zoo Report/Poster May 14, Final May 21 (online 9am-8pm)
        Exams are non-cumulative but know key terms from earlier. No curve. No extra credit.
        Late projects: -10% per day, weekends count as 2 days.
        """
    },
    {
        "title": "E4E (Economics for Everyone) — Spring 2026",
        "content": """
        Schedule: [section time TBD]
        Assignments: Weekly AI tutor discussions due Mondays 11:59pm (lowest 2 dropped)
        Key dates: Midterm 1 Apr 21 (in-class Tue), Midterm 2 May 21 (in-class Thu), Final Project May 29
        Discussion rubric: Application of principles 20%, Integration of course content 20%, Evidence & reasoning 20%, Implications analysis 20%, Complexity awareness 20%
        Late policy: -33% per 24 hours, 0 after 3 days.
        """
    },
    {
        "title": "Class Schedule — Spring 2026",
        "content": """
        Monday: SCS III 3:00-4:20pm (Wieboldt 310C)
        Tuesday: APES 9:30-10:50am (Eckhart 133 + Haskell), [CorpFin TBD], [E4E TBD]
        Wednesday: SCS III 3:00-4:20pm (Wieboldt 310C)
        Thursday: APES 9:30-10:50am (Eckhart 133 + Haskell), [CorpFin TBD], [E4E TBD]
        Friday: Open
        Baseball: Practice typically afternoons, games vary
        """
    }
]
```

### Runtime memory operations

**On `/note`:**
```python
# 1. Send note text to Claude for classification
# 2. Store in Membase:
await membase.add_memory(f"[NOTE] {note_text} [tags: {extracted_tags}]")
# 3. If task extracted, also create in tasks.json
# 4. If linked to existing task, add cross-reference
```

**On task completion (`/done`):**
```python
# Store completion event
await membase.add_memory(f"[COMPLETED] {task.course}: {task.name}. {optional_reflection}")
```

**On briefing generation:**
```python
# Search for relevant context for today's priority tasks
for task in top_5_tasks:
    related_notes = await membase.search_memory(f"{task.course} {task.name}")
    # Feed these into Claude briefing prompt as context
```

**On `/think` command (new):**
```python
# Dedicated thinking capture — longer form, no task extraction expected
# User sends a thought, bot stores it and responds with connections
note = user_message
await membase.add_memory(f"[THINKING] {note}")

# Search for related memories
related = await membase.search_memory(note, limit=5)
# Claude synthesizes: "This connects to your earlier note about X and your task Y"
```

---

## Telegram Command Reference (complete)

### Task Management
- `/done <id>` — Mark task complete
- `/undo <id>` — Unmark task
- `/add <category> | <name> | <due_date>` — Add structured task
- `/edit <id> <field> <value>` — Edit task field (due date, name, etc.)
- `/drop <id>` — Delete a task entirely

### Views
- `/status` or `/briefing` — Full daily briefing
- `/list` — All active tasks with IDs
- `/week` — 7-day overview (text-formatted calendar)
- `/today` — Just today's schedule + due items
- `/crunch` — Show upcoming weeks with 3+ overlapping deadlines
- `/course <name>` — Filter to one course/category

### Capture
- `/note <text>` — Unstructured capture (auto-classified)
- `/think <text>` — Thinking note (no task extraction, connections surfaced)
- `/return <text>` — Flag something to resurface later

### Memory
- `/recall <query>` — Search Membase for past notes/thoughts
- `/review` — Weekly review: synthesize all notes from past 7 days

### Meta
- `/help` — Show all commands
- `/categories` — Show all task categories
- `/sync` — Force re-fetch Google Calendar

---

## Dashboard Spec (Updated)

### Navigation
Top bar with three tabs:
1. **Week** (default) — Calendar grid view
2. **Tasks** — Full task list (the current view, refined)
3. **Notes** — Feed of all captured notes from Membase, searchable

### Week View (primary)
See design spec in "Design Decisions #5" above. Key technical details:
- Fetch class schedule from `data/schedule.json` (hardcoded, fast)
- Fetch Google Calendar events from `/api/calendar`
- Fetch tasks from `/api/tasks`
- Overlay all three onto a 7-column grid
- Each column is divided into hour blocks (7am–11pm)
- Fixed events are solid colored blocks
- Tasks appear as cards at the bottom of their due-date column
- Clicking empty space calls `/api/suggest?duration=60&time=10:00` which returns the highest-priority task that fits

### Task View (secondary)
Same as current dashboard but with additions:
- Category filter now includes Baseball, Recruiting, Projects, Life
- Sort options: Priority Score (default), Date, Course, Weight
- Each task row shows its computed priority score as a small number
- Inline edit: click a due date to change it, click the name to edit
- Bulk actions: multi-select + mark done

### Notes View (new)
- Chronological feed of all Membase memories tagged with `[NOTE]`, `[THINKING]`, `[RETURN]`
- Search bar at top (calls Membase semantic search)
- Each note card shows: timestamp, text, linked tasks (if any), tags
- Click a note to expand and see Claude's classification + connections
- "Create task from this" button on each note

### Add Task / Note
- Floating action button (bottom right) that opens a modal
- Two modes: "Task" (structured fields) and "Note" (free text box)
- Task mode: category dropdown, name, due date, type, estimated hours
- Note mode: just a text area. Submit sends to `/note` endpoint which classifies.

---

## API Endpoints (Updated)

```
# Tasks
GET    /api/tasks                    → all tasks, with computed priority_score
POST   /api/tasks                    → add new task
PATCH  /api/tasks/:id                → update task fields
POST   /api/tasks/:id/done           → mark done
POST   /api/tasks/:id/undo           → mark undone
DELETE /api/tasks/:id                → delete task

# Calendar
GET    /api/calendar?days=7          → Google Calendar events
GET    /api/schedule                 → Hardcoded class schedule

# Intelligence
GET    /api/briefing                 → Generate current briefing
GET    /api/suggest?duration=60      → Suggest best task for available time block
POST   /api/capture                  → Process unstructured note (Claude classification)

# Memory (proxies to Membase)
GET    /api/notes?q=<query>          → Search Membase memories
GET    /api/notes/recent?days=7      → Recent notes
POST   /api/notes                    → Store a note directly

# Meta
GET    /api/categories               → All categories with colors
GET    /api/health                   → Server status
```

---

## Cron Schedule

```crontab
# Morning briefing — 7:00 AM
0 7 * * * cd ~/academic-bot && ~/academic-bot/venv/bin/python -m cron.morning_briefing >> ~/academic-bot/logs/morning.log 2>&1

# Evening recap — 9:00 PM  
0 21 * * * cd ~/academic-bot && ~/academic-bot/venv/bin/python -m cron.evening_recap >> ~/academic-bot/logs/evening.log 2>&1

# Deadline alerts — check every 2 hours for imminent deadlines
0 */2 * * * cd ~/academic-bot && ~/academic-bot/venv/bin/python -m cron.deadline_check >> ~/academic-bot/logs/alerts.log 2>&1

# Weekly review — Sunday 8:00 PM
0 20 * * 0 cd ~/academic-bot && ~/academic-bot/venv/bin/python -m cron.weekly_review >> ~/academic-bot/logs/weekly.log 2>&1
```

---

## Implementation Order

Claude Code should build in this order, each step testable independently:

### Phase 1: Refactor current code into modular structure
- Move current monolithic `daily_briefing.py` into `core/` + `bot/` + `server/` structure
- Extract task CRUD into `core/tasks.py`
- Extract calendar into `core/calendar_client.py`
- Extract briefing into `core/briefing.py`
- Verify everything still works: bot commands, cron send, dashboard

### Phase 2: Priority algorithm
- Implement `core/priority.py` with the scoring function
- Add `priority_score` to `/api/tasks` response
- Add `last_touched` field to tasks (updated on `/done`, `/edit`, creation)
- Add `effort_hours` field (optional, defaults to None)
- Update dashboard task list to show and sort by priority score

### Phase 3: Non-class categories + schedule.json
- Create `data/categories.json` with all 8 categories (4 courses + Baseball, Recruiting, Projects, Life)
- Create `data/schedule.json` with hardcoded class times
- Update dashboard with new category colors and filters
- Update `/add` command to accept any category

### Phase 4: Week view
- Build the calendar grid component in the dashboard
- Overlay class schedule + Google Calendar + task due dates
- Highlight current day
- Show available time blocks
- Make it the default view

### Phase 5: Membase integration
- Install/configure Membase MCP connection
- Create `core/memory.py` wrapper
- Run `scripts/seed_membase.py` to populate wiki with syllabi
- Wire into briefing generation (search for relevant notes per task)

### Phase 6: Capture system
- Implement `/note` command with Claude classification
- Implement `/think` and `/return` commands
- Store all captures in Membase
- Add Notes tab to dashboard
- Wire capture into task creation flow

### Phase 7: Push notifications
- Set up ntfy.sh (self-hosted or cloud)
- Add `core/notifications.py` with Telegram + ntfy dual-send
- Implement deadline alert cron (2-hour check)
- Implement evening recap cron
- Implement Sunday weekly review

### Phase 8: Intelligence layer
- `/api/suggest` endpoint (Claude picks best task for available time)
- Clicking empty time blocks in week view triggers suggestion
- Weekly review synthesis (Claude summarizes week's notes + progress)
- Pattern detection over time ("you always leave essays to the last 2 days")

---

## Important Constraints

- **Don't break what works.** Phase 1 is a refactor, not a rewrite. Every phase should end with all existing functionality intact.
- **tasks.json is sacred.** It's the source of truth for structured tasks. Membase is additive context, not a replacement.
- **Fail gracefully.** Missing Google creds → skip calendar. Missing Anthropic key → use basic briefing. Missing Membase → skip memory features. The core task tracker always works.
- **Single HTML file for dashboard.** No build step. React + Tailwind from CDN. This is critical for maintainability — Lando should be able to edit the UI by editing one file.
- **Mac Mini is headless.** All setup that requires a browser should use `0.0.0.0` binding + Tailscale IP access from laptop.
- **Keep the Telegram bot responsive.** Long-running operations (Claude API calls, Membase searches) should not block command responses. Use async properly.
