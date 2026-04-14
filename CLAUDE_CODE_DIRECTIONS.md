# ACADEMIC BRIEFING BOT — Claude Code Direction Doc

## What this is
You are setting up two things:
1. A **Telegram bot** that sends me a daily briefing of my academic schedule each morning at 7am
2. A **local web dashboard** I can access via browser (served from this Mac Mini) to visually manage tasks, see my calendar, and interact with my schedule

Both share the same `tasks.json` backend. The bot pushes notifications, the dashboard gives me a rich UI.

## Project structure
Create everything in `~/academic-bot/`. The final structure should be:

```
~/academic-bot/
├── venv/                    # Python virtual environment
├── daily_briefing.py        # Telegram bot script
├── server.py                # FastAPI server for the web dashboard + API
├── tasks.json               # Persisted task database (shared by bot + server)
├── config.env               # Environment variables (gitignored)
├── setup_google.py          # One-time Google OAuth helper
├── requirements.txt
├── README.md
└── static/
    └── index.html           # Single-file React dashboard (served by FastAPI)
```

## Step-by-step instructions

### 1. Create venv and install deps

```bash
cd ~/academic-bot
python3 -m venv venv
source venv/bin/activate
pip install python-telegram-bot==21.* google-api-python-client google-auth-oauthlib anthropic fastapi uvicorn python-dotenv
pip freeze > requirements.txt
```

### 2. Create `config.env`

Prompt me for each of these values interactively:
- `TELEGRAM_BOT_TOKEN` — I already created the bot via BotFather
- `TELEGRAM_CHAT_ID` — Ask me to message @userinfobot on Telegram if I don't have this
- `ANTHROPIC_API_KEY` — I have this already (check if `ANTHROPIC_API_KEY` is already in my shell env first)

Write them to `config.env` in the format:
```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
ANTHROPIC_API_KEY=xxx
```

### 3. Google Calendar API setup

Create a helper script `setup_google.py` that:
- Checks if `~/.config/academic-bot/google_creds.json` exists
- If not, prints clear instructions for how to get it from Google Cloud Console (create project → enable Calendar API → create OAuth Desktop credentials → download JSON → save to that path)
- If it does exist, runs the OAuth flow to generate `~/.config/academic-bot/google_token.json`
- Since this Mac Mini is headless, use `flow.run_local_server(port=8080)` and tell me to open `http://MAC_MINI_IP:8080` in my browser OR use `flow.run_console()` as a fallback

### 4. Create `daily_briefing.py`

This is the main bot. Here's the complete task database and logic:

#### Task Database (seed into tasks.json)

```json
[
  {"id": "cf-case2", "course": "CorpFin", "name": "Case 2", "due": "2026-04-15", "type": "case", "weight": "part of 15%", "done": false},
  {"id": "cf-ps3", "course": "CorpFin", "name": "Problem Set 3", "due": "2026-04-17", "type": "pset", "weight": "part of 15%", "done": false},
  {"id": "cf-topic", "course": "CorpFin", "name": "Send project topic to professor", "due": "2026-04-20", "type": "admin", "weight": "", "done": false},
  {"id": "cf-ps4", "course": "CorpFin", "name": "Problem Set 4", "due": "2026-04-24", "type": "pset", "weight": "part of 15%", "done": false},
  {"id": "cf-mid", "course": "CorpFin", "name": "Midterm Exam (in-class, closed book)", "due": "2026-05-01", "type": "exam", "weight": "25%", "done": false},
  {"id": "cf-ps5", "course": "CorpFin", "name": "Problem Set 5", "due": "2026-05-08", "type": "pset", "weight": "part of 15%", "done": false},
  {"id": "cf-proj", "course": "CorpFin", "name": "Valuation Project Presentation (15 min, must use ChatGPT)", "due": "2026-05-09", "type": "project", "weight": "15%", "done": false},
  {"id": "cf-final", "course": "CorpFin", "name": "Final Exam (in-class, closed book)", "due": "2026-05-22", "type": "exam", "weight": "35-60%", "done": false},

  {"id": "scs-fb", "course": "SCS III", "name": "Self-Feedback Exercise", "due": "2026-04-19", "type": "essay", "weight": "10%", "done": false},
  {"id": "scs-mid", "course": "SCS III", "name": "Midterm Essay (major paper)", "due": "2026-04-28", "type": "essay", "weight": "35%", "done": false},
  {"id": "scs-pres", "course": "SCS III", "name": "Final Paper Presentation", "due": "2026-05-13", "type": "presentation", "weight": "5%", "done": false},
  {"id": "scs-final", "course": "SCS III", "name": "Final Paper", "due": "2026-05-28", "type": "essay", "weight": "30%", "done": false},

  {"id": "apes-mid", "course": "APES", "name": "Online Midterm (9am-8pm, Weeks 1-4)", "due": "2026-04-21", "type": "exam", "weight": "50/280 pts", "done": false},
  {"id": "apes-debate", "course": "APES", "name": "Debate Presentation (group, slideshow+script+sources)", "due": "2026-04-28", "type": "presentation", "weight": "50/280 pts", "done": false},
  {"id": "apes-zoo", "course": "APES", "name": "Zoo Report or Individual Poster (hard+electronic copy)", "due": "2026-05-14", "type": "project", "weight": "50/280 pts", "done": false},
  {"id": "apes-final", "course": "APES", "name": "Online Final Exam (9am-8pm, Weeks 5-9)", "due": "2026-05-21", "type": "exam", "weight": "50/280 pts", "done": false},

  {"id": "e4e-ai4", "course": "E4E", "name": "AI Tutor Wk 4 (Behavioral Econ)", "due": "2026-04-20", "type": "ai-tutor", "weight": "discussion grade", "done": false},
  {"id": "e4e-mid", "course": "E4E", "name": "Midterm (in-class Tuesday)", "due": "2026-04-21", "type": "exam", "weight": "midterm", "done": false},
  {"id": "e4e-ai6", "course": "E4E", "name": "AI Tutor Wk 6 (Markets)", "due": "2026-05-04", "type": "ai-tutor", "weight": "discussion grade", "done": false},
  {"id": "e4e-ai7", "course": "E4E", "name": "AI Tutor Wk 7 (Uncertainty)", "due": "2026-05-11", "type": "ai-tutor", "weight": "discussion grade", "done": false},
  {"id": "e4e-ai8", "course": "E4E", "name": "AI Tutor Wk 8 (Risk/Labor)", "due": "2026-05-18", "type": "ai-tutor", "weight": "discussion grade", "done": false},
  {"id": "e4e-final", "course": "E4E", "name": "Final Exam (in-class Thursday)", "due": "2026-05-21", "type": "exam", "weight": "midterm", "done": false},
  {"id": "e4e-ai9", "course": "E4E", "name": "AI Tutor Wk 9", "due": "2026-05-25", "type": "ai-tutor", "weight": "discussion grade", "done": false},
  {"id": "e4e-proj", "course": "E4E", "name": "Final Project", "due": "2026-05-29", "type": "project", "weight": "TBD", "done": false}
]
```

#### Bot features

The bot should have THREE modes, selected by CLI argument:

**`python daily_briefing.py send`** — Cron mode. Sends one briefing message and exits.
- Load tasks from `tasks.json`
- Fetch Google Calendar events for the next 7 days (gracefully handle missing credentials)
- Generate a prioritized briefing (see format below)
- Optionally enhance with Claude API if ANTHROPIC_API_KEY is set
- Send via Telegram
- Exit

**`python daily_briefing.py bot`** — Interactive mode. Runs a polling Telegram bot.
- `/status` or `/briefing` — Generate and send the daily briefing on demand
- `/list` — Show all active (undone) tasks with their IDs
- `/done <task_id>` — Mark a task as completed, persist to tasks.json
- `/add <course> | <name> | <due_date>` — Add a new task (generate an ID from course+name)
- `/undo <task_id>` — Unmark a task as done
- `/week` — Show only tasks due in the next 7 days
- `/crunch` — Show weeks with 3+ overlapping deadlines

**`python daily_briefing.py init`** — Seed the task database from the hardcoded DEFAULT_TASKS above.

#### Briefing message format

Use Telegram Markdown. The briefing should look like:

```
☀️ *Monday, April 14*

📅 *TODAY'S SCHEDULE*
  9:30 — APES Lecture (Eckhart 133)
  3:00 — SCS III (Wieboldt 310C)

🔴 *OVERDUE*
  ⚠️ E4E: AI Tutor Wk 3 (1d late)

🟡 *DUE TODAY*
  → CorpFin: Case 2

📋 *THIS WEEK* (by urgency)
  · CorpFin: Problem Set 3 — Fri Apr 17 (3d)
  ★ SCS III: Self-Feedback Exercise — Sun Apr 19 (5d)

🔮 *NEXT WEEK*
  ◆ APES: Online Midterm — Tue Apr 21
  ◆ E4E: Midterm — Tue Apr 21
  · E4E: AI Tutor Wk 4 — Mon Apr 20
  ★ SCS III: Midterm Essay — Tue Apr 28

⚡ *CRUNCH ALERT*
  Apr 21: TWO MIDTERMS (APES + E4E) on same day!

🎯 *FOCUS TODAY*
  1. CorpFin: Case 2 (due today)
  2. CorpFin: PS3 (due Fri)
  3. Start studying for APES midterm (7d out)

Active: 24 tasks | This week: 3
```

#### AI-enhanced briefing (when ANTHROPIC_API_KEY is set)

Pass the task list + calendar events to Claude Sonnet with this system prompt:

```
You are an academic scheduling assistant for a UChicago junior who plays varsity baseball. 
Generate a concise daily briefing. Be direct and actionable. Use Telegram markdown.

Rules:
- Under 400 words
- Prioritize by: urgency, grade weight, preparation time needed
- Flag dangerous overlaps (two exams same day, heavy project + exam week)
- Suggest what to work on in specific time blocks between classes
- Account for baseball practice (usually afternoons)
- Be encouraging but honest about workload
- If a major paper or exam is 5+ days out, suggest starting prep NOW with a micro-task
```

#### Google Calendar integration

```python
# Fetch from Google Calendar API
# Use google-auth-oauthlib for OAuth
# Credentials at ~/.config/academic-bot/google_creds.json
# Token cached at ~/.config/academic-bot/google_token.json
# SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
# Fetch events from primary calendar, next 7 days
# Return list of {summary, start, end}
# If credentials don't exist or fail, return empty list and log a warning (don't crash)
```

#### Loading config

Load environment variables from `config.env` using python-dotenv (add to requirements) OR just read the file manually. Also check os.environ as fallback (for when vars are exported in shell).

### 5. Set up cron job

After everything is working, add a cron entry:
```
0 7 * * * cd ~/academic-bot && ~/academic-bot/venv/bin/python daily_briefing.py send >> ~/academic-bot/briefing.log 2>&1
```

Verify with `crontab -l` after adding.

### 6. Run the interactive bot in tmux

```bash
tmux new -s academic-bot
cd ~/academic-bot && source venv/bin/activate
python daily_briefing.py bot
# Ctrl+B, D to detach
```

### 7. Test everything

- Run `python daily_briefing.py send` and verify I get a Telegram message
- Run `python daily_briefing.py bot` and test `/status`, `/list`, `/done cf-case2`, `/undo cf-case2`
- Verify `tasks.json` persists changes

## Important notes

- The Mac Mini is headless, accessed via Tailscale SSH. For Google OAuth, use `run_local_server(port=8080, bind_addr="0.0.0.0")` so I can open the auth URL from my laptop browser pointed at the Mac Mini's Tailscale IP.
- Don't crash if Google Calendar credentials are missing — just skip calendar and use tasks only.
- Don't crash if ANTHROPIC_API_KEY is missing — just use the basic briefing format.
- `tasks.json` is the source of truth. Every `/done` and `/add` command should read→modify→write atomically.
- The SCS III Canvas posts are recurring (due night before each M/W class) — don't track these individually, just mention "SCS Canvas post due tonight" in the briefing on Sunday and Tuesday evenings. You can hardcode the class schedule: MW 3:00-4:20.

## My class schedule (for reference in briefings)

- **CorpFin (BUSN 20410)**: Check Canvas for section time
- **SCS III**: MW 3:00-4:20pm, Wieboldt 310C
- **APES (ANTH 21428)**: TTh 9:30-10:10am lecture + 10:20-10:50am lab, Eckhart 133 / Haskell basement
- **E4E**: Check Canvas for section time

## Success criteria

I should be able to:
1. Get a Telegram message at 7am every morning with my prioritized day
2. Reply `/done cf-ps3` to mark things complete
3. Reply `/status` anytime to see where I stand
4. Reply `/add CorpFin | New Assignment | 2026-05-01` to add tasks on the fly
5. Open `http://MAC_MINI_TAILSCALE_IP:8000` in my browser and see a full interactive dashboard
6. Mark tasks done, add tasks, and filter by course from the dashboard — changes reflect in Telegram and vice versa

---

## Part 2: Web Dashboard (`server.py` + `static/index.html`)

### API Server (`server.py`)

Create a FastAPI app that:
- Serves `static/index.html` at `/`
- Exposes a JSON API that the dashboard calls:

```
GET  /api/tasks              → return all tasks from tasks.json
POST /api/tasks/:id/done     → mark task done, save to tasks.json
POST /api/tasks/:id/undo     → mark task not done, save
POST /api/tasks              → add a new task (body: {course, name, due, type, weight})
GET  /api/calendar           → return Google Calendar events (next 7 days)
GET  /api/briefing           → return the generated briefing text
```

- Bind to `0.0.0.0:8000` so it's accessible from my laptop via Tailscale
- Load config from `config.env` or environment
- Use the same `tasks.json` file that the Telegram bot uses
- Add CORS middleware (allow all origins) so the frontend can call the API

Run command: `uvicorn server:app --host 0.0.0.0 --port 8000`

### Web Dashboard (`static/index.html`)

Create a single-file HTML page with React (loaded from CDN), Tailwind (CDN), and all the dashboard UI inline. This is a self-contained file — no build step.

The dashboard should replicate and improve on the JSX artifact I built earlier. Here is the full design spec:

#### Visual Design
- **Dark theme**: Background `#0a0a0a`, cards `#141414`, borders `#262626`
- **Monospace font**: Use JetBrains Mono from Google Fonts
- **Course color scheme**:
  - CorpFin: purple accent `#a78bfa`
  - SCS III: amber accent `#f59e0b`
  - APES: emerald accent `#34d399`
  - E4E: indigo accent `#818cf8`
- **Urgency colors**: red (<= 2 days), amber (<= 7 days), blue (<= 14 days), gray (> 14 days)

#### Layout (top to bottom)

1. **Header bar**: "SPRING 2026 — COMMAND CENTER" with today's date, active task count, tasks due this week count

2. **Alert banner** (conditional): Red gradient banner showing tasks due today or overdue. Only show if there are any.

3. **Course stat cards** (horizontal row, 4 cards): One per course showing:
   - Course name (colored)
   - Number of remaining tasks (big number)
   - Next upcoming task name
   - Clickable to filter the task list by that course

4. **View toggles**: Buttons to sort by "Priority" (default), "Date", or "Course". Plus an "All Courses" reset button.

5. **Major Milestones section**: Horizontal cards showing only exams, projects, essays, and presentations. Each shows course, name, due date, and days remaining with urgency coloring.

6. **Full task list**: Each task is a row with:
   - Checkbox (click to toggle done → calls `POST /api/tasks/:id/done` or `/undo`)
   - Type icon (◆ exam, ✎ essay, ≡ pset, ★ project, ▶ presentation, ⚡ ai-tutor)
   - Course label (colored pill)
   - Task name
   - Grade weight
   - Due date + "X days" urgency label
   - Completed tasks should be faded with strikethrough, sorted to bottom

7. **Add task form** (collapsible): Simple form with fields for course (dropdown), name, due date, type. Calls `POST /api/tasks` on submit.

8. **Key Notes footer**: Static notes about assumptions (CorpFin Case 2 date, SCS Canvas posts, etc.)

#### Interactivity
- All task mutations (done/undo/add) should call the API and update the UI optimistically
- Course cards are clickable filters
- Sort toggles work client-side
- Auto-refresh task list every 60 seconds (poll `GET /api/tasks`)
- Add task form auto-generates an ID from course abbreviation + name

#### Technical constraints
- Single HTML file, no build step
- React 18 via CDN (`https://esm.sh/react@18` and `https://esm.sh/react-dom@18`)
- Use `<script type="module">` with import maps or esm.sh
- Tailwind CSS via CDN (`https://cdn.tailwindcss.com`)
- All API calls use `fetch()` to the FastAPI backend

### Running the dashboard

Add the dashboard server to the tmux setup alongside the bot:

```bash
tmux new -s academic-bot
# Pane 1: Telegram bot
cd ~/academic-bot && source venv/bin/activate
python daily_briefing.py bot

# Ctrl+B, % to split pane
# Pane 2: Web dashboard
cd ~/academic-bot && source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8000
```

Or create a simple `run.sh` that starts both:
```bash
#!/bin/bash
cd ~/academic-bot
source venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8000 &
python daily_briefing.py bot &
wait
```
