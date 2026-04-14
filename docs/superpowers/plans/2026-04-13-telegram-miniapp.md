# Academic Scheduler Telegram Mini App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram Mini App (mobile-first React dashboard) backed by a local FastAPI server on a Mac Mini, exposed via Cloudflare Quick Tunnel, with a Telegram bot that opens the Mini App via menu button + inline briefing-message button and sends a daily 7am briefing via cron.

**Architecture:**
- **Backend:** Python 3.11+ / FastAPI serves `/api/*` endpoints and the built Mini App static bundle. All API routes (except `/` static serving) require a valid Telegram `initData` HMAC header. State lives in a single `data/tasks.json` file with file-locked read-modify-write.
- **Bot:** `python-telegram-bot` v21 sets the chat menu button, handles `/start` and `/briefing`, and attaches an inline "Open Dashboard" button to the daily briefing message. A cron job runs `bot.py send` every morning at 7am.
- **Frontend:** React 18 + Vite + Tailwind, single-page Mini App using `window.Telegram.WebApp`. Passes `initData` as `X-Telegram-Init-Data` header on every fetch. Ported from `academic_planner.jsx` but mobile-first.
- **Tunnel:** Cloudflare Quick Tunnel (`cloudflared tunnel --url http://localhost:8000`). URL changes on each restart, so a `refresh_tunnel.sh` script captures the new URL and updates the Telegram menu button via `setChatMenuButton`.

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, uvicorn, python-telegram-bot 21.x, python-dotenv, httpx, pytest
- Frontend: React 18, Vite, TypeScript, Tailwind CSS, Telegram WebApp JS SDK (`telegram-web-app.js`)
- Infra: Cloudflare `cloudflared` (Homebrew), tmux, macOS `cron`

**Out of scope (deferred to follow-up plans):** Google Calendar integration, Claude API-enhanced briefings, web browser dashboard (Mini App replaces it), concurrent write safety beyond single-process file locking.

**Conventions:**
- Working directory for all commands: `/Users/landonprojects/scheduler_bot` (hereafter `$PROJECT`)
- Python venv: `$PROJECT/venv`
- Commit cadence: after every task completes
- Commit message prefix: `feat:`, `test:`, `chore:`, `fix:`, `docs:`

---

## File Structure

```
/Users/landonprojects/scheduler_bot/
├── venv/                           # Python virtual env (gitignored)
├── backend/
│   ├── __init__.py
│   ├── config.py                   # Load .env, expose settings object
│   ├── tasks_store.py              # Atomic read/write of data/tasks.json
│   ├── auth.py                     # Telegram initData HMAC verification
│   ├── briefing.py                 # Generate briefing markdown text
│   ├── server.py                   # FastAPI app (API + static)
│   ├── bot.py                      # python-telegram-bot entrypoint (modes: bot, send, setup)
│   └── static/                     # Vite build output (gitignored)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx                # Bootstraps React + Telegram WebApp
│       ├── App.tsx                 # Top-level dashboard
│       ├── api.ts                  # fetch wrapper injecting initData header
│       ├── telegram.ts             # window.Telegram.WebApp typed access
│       ├── types.ts                # Task type
│       ├── utils.ts                # daysUntil, formatDate, urgencyColor, priorityScore
│       ├── theme.ts                # COURSE_COLORS, TYPE_ICONS
│       ├── index.css               # Tailwind directives + base styles
│       └── components/
│           ├── Header.tsx
│           ├── AlertBanner.tsx
│           ├── CourseStats.tsx
│           ├── ViewToggle.tsx
│           ├── Milestones.tsx
│           ├── TaskList.tsx
│           ├── TaskRow.tsx
│           ├── AddTaskForm.tsx
│           └── CrunchNotice.tsx
├── data/
│   └── tasks.json                  # Source of truth (gitignored)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_tasks_store.py
│   ├── test_auth.py
│   ├── test_briefing.py
│   └── test_server.py
├── scripts/
│   ├── refresh_tunnel.sh           # Start tunnel, capture URL, update menu button
│   ├── update_menu_button.py       # Call Telegram setChatMenuButton
│   └── seed_tasks.py               # Seed data/tasks.json from hardcoded defaults
├── .env.example
├── .env                            # gitignored
├── .gitignore
├── requirements.txt
├── run.sh                          # Start bot + uvicorn in tmux panes
├── README.md
└── pytest.ini
```

---

## Task 1: Project scaffolding, git init, venv, deps, .env

**Files:**
- Create: `$PROJECT/.gitignore`
- Create: `$PROJECT/.env.example`
- Create: `$PROJECT/requirements.txt`
- Create: `$PROJECT/pytest.ini`
- Create: `$PROJECT/backend/__init__.py`
- Create: `$PROJECT/backend/config.py`
- Create: `$PROJECT/tests/__init__.py`
- Create: `$PROJECT/tests/conftest.py`
- Create: `$PROJECT/data/` (directory)

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/landonprojects/scheduler_bot
git init
git add academic_planner.jsx CLAUDE_CODE_DIRECTIONS.md docs/
git commit -m "chore: initial commit with design spec"
```

- [ ] **Step 2: Create `.gitignore`**

```
venv/
__pycache__/
*.pyc
.pytest_cache/
.env
data/tasks.json
data/*.bak
backend/static/
frontend/node_modules/
frontend/dist/
.DS_Store
briefing.log
.tunnel_url
```

- [ ] **Step 3: Create `.env.example`**

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
# Miniapp HTTPS URL — populated by scripts/refresh_tunnel.sh on each tunnel start
MINIAPP_URL=
# Bind address for uvicorn; keep localhost because Cloudflare tunnel connects locally
API_HOST=127.0.0.1
API_PORT=8000
# Absolute path to tasks.json; defaults to <project>/data/tasks.json if unset
TASKS_PATH=
```

- [ ] **Step 4: Create `requirements.txt`**

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
python-telegram-bot==21.*
python-dotenv==1.0.*
httpx==0.27.*
pytest==8.*
pytest-asyncio==0.24.*
```

- [ ] **Step 5: Create venv and install**

```bash
cd /Users/landonprojects/scheduler_bot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Expected: installs complete without errors.

- [ ] **Step 6: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
pythonpath = .
```

- [ ] **Step 7: Create `backend/__init__.py` and `tests/__init__.py`**

Both empty files.

- [ ] **Step 8: Create `backend/config.py`**

```python
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    miniapp_url: str
    api_host: str
    api_port: int
    tasks_path: Path


def load_settings() -> Settings:
    tasks_path = os.environ.get("TASKS_PATH") or str(PROJECT_ROOT / "data" / "tasks.json")
    return Settings(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        miniapp_url=os.environ.get("MINIAPP_URL", ""),
        api_host=os.environ.get("API_HOST", "127.0.0.1"),
        api_port=int(os.environ.get("API_PORT", "8000")),
        tasks_path=Path(tasks_path),
    )
```

- [ ] **Step 9: Create `tests/conftest.py`**

```python
import json
from pathlib import Path
import pytest


@pytest.fixture
def tmp_tasks_path(tmp_path: Path) -> Path:
    p = tmp_path / "tasks.json"
    p.write_text("[]")
    return p
```

- [ ] **Step 10: Commit**

```bash
git add .gitignore .env.example requirements.txt pytest.ini backend/ tests/
git commit -m "chore: project scaffolding, venv, config module"
```

---

## Task 2: Tasks store — atomic JSON CRUD with tests

**Files:**
- Create: `$PROJECT/backend/tasks_store.py`
- Create: `$PROJECT/tests/test_tasks_store.py`

- [ ] **Step 1: Write failing tests**

`tests/test_tasks_store.py`:

```python
import json
from pathlib import Path
import pytest
from backend.tasks_store import TasksStore, Task, TaskNotFoundError


def _seed(path: Path, tasks: list[dict]) -> None:
    path.write_text(json.dumps(tasks))


def test_list_returns_empty_for_empty_file(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    assert store.list() == []


def test_list_returns_tasks_preserving_order(tmp_tasks_path: Path):
    _seed(tmp_tasks_path, [
        {"id": "a", "course": "CorpFin", "name": "A", "due": "2026-05-01", "type": "pset", "weight": "", "done": False},
        {"id": "b", "course": "APES", "name": "B", "due": "2026-05-02", "type": "exam", "weight": "", "done": False},
    ])
    store = TasksStore(tmp_tasks_path)
    tasks = store.list()
    assert [t.id for t in tasks] == ["a", "b"]


def test_add_appends_task_and_persists(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    store.add(Task(id="x", course="E4E", name="Quiz", due="2026-05-10", type="exam", weight="10%", done=False))
    assert json.loads(tmp_tasks_path.read_text())[0]["id"] == "x"


def test_add_rejects_duplicate_id(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    t = Task(id="x", course="E4E", name="Quiz", due="2026-05-10", type="exam", weight="", done=False)
    store.add(t)
    with pytest.raises(ValueError):
        store.add(t)


def test_mark_done_flips_flag(tmp_tasks_path: Path):
    _seed(tmp_tasks_path, [
        {"id": "a", "course": "CorpFin", "name": "A", "due": "2026-05-01", "type": "pset", "weight": "", "done": False},
    ])
    store = TasksStore(tmp_tasks_path)
    store.set_done("a", True)
    assert json.loads(tmp_tasks_path.read_text())[0]["done"] is True
    store.set_done("a", False)
    assert json.loads(tmp_tasks_path.read_text())[0]["done"] is False


def test_set_done_on_missing_raises(tmp_tasks_path: Path):
    store = TasksStore(tmp_tasks_path)
    with pytest.raises(TaskNotFoundError):
        store.set_done("nope", True)


def test_auto_creates_parent_dir_and_empty_file(tmp_path: Path):
    path = tmp_path / "sub" / "tasks.json"
    store = TasksStore(path)
    assert store.list() == []
    assert path.exists()


def test_write_is_atomic_on_corruption(tmp_tasks_path: Path, monkeypatch):
    # If a write mid-flight crashes, the prior file must remain readable.
    _seed(tmp_tasks_path, [{"id": "a", "course": "X", "name": "A", "due": "2026-01-01", "type": "pset", "weight": "", "done": False}])
    store = TasksStore(tmp_tasks_path)
    original = json.loads(tmp_tasks_path.read_text())
    # Simulate: any crash after write-to-tmp but before rename should leave original intact
    import os
    real_replace = os.replace
    def boom(*a, **kw): raise RuntimeError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(RuntimeError):
        store.add(Task(id="b", course="X", name="B", due="2026-01-02", type="pset", weight="", done=False))
    assert json.loads(tmp_tasks_path.read_text()) == original
```

- [ ] **Step 2: Run tests, expect import failures**

```bash
cd /Users/landonprojects/scheduler_bot
source venv/bin/activate
pytest tests/test_tasks_store.py -v
```

Expected: ModuleNotFoundError for `backend.tasks_store`.

- [ ] **Step 3: Implement `backend/tasks_store.py`**

```python
from __future__ import annotations
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from threading import Lock
from typing import Optional


class TaskNotFoundError(LookupError):
    pass


@dataclass
class Task:
    id: str
    course: str
    name: str
    due: str           # ISO date YYYY-MM-DD
    type: str          # exam | pset | essay | case | project | presentation | reading | ai-tutor | recurring | admin
    weight: str
    done: bool
    notes: Optional[str] = None


class TasksStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def list(self) -> list[Task]:
        with self._lock:
            raw = json.loads(self.path.read_text() or "[]")
        return [Task(**t) for t in raw]

    def add(self, task: Task) -> None:
        with self._lock:
            tasks = self._read()
            if any(t["id"] == task.id for t in tasks):
                raise ValueError(f"task id {task.id!r} already exists")
            tasks.append(asdict(task))
            self._write(tasks)

    def set_done(self, task_id: str, done: bool) -> None:
        with self._lock:
            tasks = self._read()
            for t in tasks:
                if t["id"] == task_id:
                    t["done"] = done
                    self._write(tasks)
                    return
            raise TaskNotFoundError(task_id)

    def replace_all(self, tasks: list[Task]) -> None:
        with self._lock:
            self._write([asdict(t) for t in tasks])

    def _read(self) -> list[dict]:
        return json.loads(self.path.read_text() or "[]")

    def _write(self, tasks: list[dict]) -> None:
        fd, tmp = tempfile.mkstemp(prefix=".tasks-", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(tasks, f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_tasks_store.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tasks_store.py tests/test_tasks_store.py
git commit -m "feat: atomic JSON tasks store with tests"
```

---

## Task 3: Telegram initData HMAC verification with tests

Telegram Mini Apps send an `initData` string generated by the client. The server verifies it by HMAC-SHA256 using a key derived from the bot token (`HMAC_SHA256("WebAppData", bot_token)`). Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

**Files:**
- Create: `$PROJECT/backend/auth.py`
- Create: `$PROJECT/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

`tests/test_auth.py`:

```python
import hashlib
import hmac
import time
from urllib.parse import urlencode
import pytest
from backend.auth import verify_init_data, InitDataInvalid


BOT_TOKEN = "123456:TESTTOKEN"


def _sign(data: dict, token: str = BOT_TOKEN) -> str:
    """Build a valid initData string the way Telegram's client would."""
    # exclude hash, sort keys, join as k=v\n
    pairs = sorted((k, v) for k, v in data.items() if k != "hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**data, "hash": h})


def test_verify_returns_user_on_valid_data():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":42,"first_name":"L"}', "query_id": "q"})
    result = verify_init_data(init, BOT_TOKEN)
    assert result.user_id == 42


def test_rejects_tampered_hash():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":42}'})
    tampered = init.replace("id%22%3A42", "id%22%3A99")
    with pytest.raises(InitDataInvalid):
        verify_init_data(tampered, BOT_TOKEN)


def test_rejects_expired_auth_date():
    old = int(time.time()) - 60 * 60 * 25  # 25h ago
    init = _sign({"auth_date": str(old), "user": '{"id":1}'})
    with pytest.raises(InitDataInvalid):
        verify_init_data(init, BOT_TOKEN, max_age_seconds=86400)


def test_rejects_missing_hash():
    with pytest.raises(InitDataInvalid):
        verify_init_data("auth_date=1&user=%7B%22id%22%3A1%7D", BOT_TOKEN)


def test_rejects_wrong_bot_token():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":1}'})
    with pytest.raises(InitDataInvalid):
        verify_init_data(init, "999:WRONG")
```

- [ ] **Step 2: Run tests, expect import failure**

```bash
pytest tests/test_auth.py -v
```

- [ ] **Step 3: Implement `backend/auth.py`**

```python
from __future__ import annotations
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataInvalid(ValueError):
    pass


@dataclass
class TelegramUser:
    user_id: int
    first_name: str
    username: str | None


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> TelegramUser:
    """Validate a Telegram Mini App initData string.

    Raises InitDataInvalid on any failure. Returns the parsed user on success.
    """
    if not init_data:
        raise InitDataInvalid("empty initData")

    # parse_qsl preserves order; we do NOT pass keep_blank_values
    pairs = parse_qsl(init_data, strict_parsing=False)
    data = dict(pairs)

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataInvalid("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise InitDataInvalid("hash mismatch")

    auth_date = int(data.get("auth_date", "0"))
    if auth_date <= 0 or (time.time() - auth_date) > max_age_seconds:
        raise InitDataInvalid("auth_date expired or missing")

    user_json = data.get("user")
    if not user_json:
        raise InitDataInvalid("missing user")
    user = json.loads(user_json)
    return TelegramUser(
        user_id=int(user["id"]),
        first_name=user.get("first_name", ""),
        username=user.get("username"),
    )
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_auth.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: Telegram initData HMAC verification"
```

---

## Task 4: Briefing text generator with tests

Generates the daily briefing markdown exactly matching the format in `CLAUDE_CODE_DIRECTIONS.md` §4 "Briefing message format" (minus calendar rows, since Google Calendar is deferred).

**Files:**
- Create: `$PROJECT/backend/briefing.py`
- Create: `$PROJECT/tests/test_briefing.py`

- [ ] **Step 1: Write failing tests**

`tests/test_briefing.py`:

```python
from datetime import date
from backend.briefing import generate_briefing
from backend.tasks_store import Task


def _t(id, course, name, due, type_="pset", weight="", done=False) -> Task:
    return Task(id=id, course=course, name=name, due=due, type=type_, weight=weight, done=done)


def test_empty_state_still_produces_header():
    text = generate_briefing([], today=date(2026, 4, 13))
    assert "Monday, April 13" in text
    assert "Active: 0 tasks" in text


def test_categorizes_overdue_due_today_week_next_week():
    tasks = [
        _t("overdue", "APES", "Old thing", "2026-04-10"),
        _t("today", "CorpFin", "Case 2", "2026-04-13"),
        _t("week", "E4E", "Midterm", "2026-04-17", type_="exam"),
        _t("next", "SCS III", "Self-Feedback", "2026-04-19", type_="essay"),
        _t("far", "CorpFin", "Final", "2026-05-22", type_="exam"),
    ]
    text = generate_briefing(tasks, today=date(2026, 4, 13))
    assert "OVERDUE" in text and "Old thing" in text
    assert "DUE TODAY" in text and "Case 2" in text
    assert "THIS WEEK" in text and "Midterm" in text
    assert "NEXT WEEK" in text and "Self-Feedback" in text
    assert "Final" not in text.split("NEXT WEEK")[-1]  # far-future omitted


def test_completed_tasks_are_excluded():
    tasks = [_t("a", "APES", "X", "2026-04-13", done=True)]
    text = generate_briefing(tasks, today=date(2026, 4, 13))
    assert "DUE TODAY" not in text


def test_crunch_detection_flags_same_day_exams():
    tasks = [
        _t("a", "APES", "Mid", "2026-04-21", type_="exam"),
        _t("b", "E4E", "Mid", "2026-04-21", type_="exam"),
    ]
    text = generate_briefing(tasks, today=date(2026, 4, 13))
    assert "CRUNCH" in text
    assert "Apr 21" in text


def test_counts_line_reflects_active_and_week():
    tasks = [
        _t("a", "APES", "X", "2026-04-15"),
        _t("b", "E4E", "Y", "2026-04-30"),
        _t("c", "CorpFin", "Z", "2026-04-14", done=True),
    ]
    text = generate_briefing(tasks, today=date(2026, 4, 13))
    assert "Active: 2 tasks" in text
    assert "This week: 1" in text
```

- [ ] **Step 2: Run tests, expect import error**

```bash
pytest tests/test_briefing.py -v
```

- [ ] **Step 3: Implement `backend/briefing.py`**

```python
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from .tasks_store import Task


def _parse_due(t: Task) -> date:
    return datetime.strptime(t.due, "%Y-%m-%d").date()


def _fmt(d: date) -> str:
    return d.strftime("%a %b %-d")


def generate_briefing(tasks: list[Task], today: date) -> str:
    active = [t for t in tasks if not t.done]
    overdue = [t for t in active if _parse_due(t) < today]
    due_today = [t for t in active if _parse_due(t) == today]
    week = [t for t in active if 0 < (_parse_due(t) - today).days <= 7]
    next_week = [t for t in active if 7 < (_parse_due(t) - today).days <= 14]

    lines: list[str] = []
    lines.append(f"☀️ *{today.strftime('%A, %B %-d')}*\n")

    if overdue:
        lines.append("🔴 *OVERDUE*")
        for t in sorted(overdue, key=_parse_due):
            days_late = (today - _parse_due(t)).days
            lines.append(f"  ⚠️ {t.course}: {t.name} ({days_late}d late)")
        lines.append("")

    if due_today:
        lines.append("🟡 *DUE TODAY*")
        for t in due_today:
            lines.append(f"  → {t.course}: {t.name}")
        lines.append("")

    if week:
        lines.append("📋 *THIS WEEK* (by urgency)")
        for t in sorted(week, key=_parse_due):
            d = _parse_due(t)
            delta = (d - today).days
            lines.append(f"  · {t.course}: {t.name} — {_fmt(d)} ({delta}d)")
        lines.append("")

    if next_week:
        lines.append("🔮 *NEXT WEEK*")
        for t in sorted(next_week, key=_parse_due):
            lines.append(f"  ◆ {t.course}: {t.name} — {_fmt(_parse_due(t))}")
        lines.append("")

    # Crunch: any date (within next 21d) with 2+ exams or 3+ total items
    by_date: dict[date, list[Task]] = defaultdict(list)
    for t in active:
        d = _parse_due(t)
        if 0 <= (d - today).days <= 21:
            by_date[d].append(t)
    crunch = []
    for d, ts in sorted(by_date.items()):
        exams = [t for t in ts if t.type == "exam"]
        if len(exams) >= 2 or len(ts) >= 3:
            crunch.append((d, ts))
    if crunch:
        lines.append("⚡ *CRUNCH ALERT*")
        for d, ts in crunch:
            kinds = ", ".join(f"{t.course} {t.type}" for t in ts)
            lines.append(f"  {_fmt(d)}: {kinds}")
        lines.append("")

    lines.append(f"Active: {len(active)} tasks | This week: {len(week) + len(due_today)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_briefing.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/briefing.py tests/test_briefing.py
git commit -m "feat: daily briefing text generator"
```

---

## Task 5: Seed script + default tasks data

**Files:**
- Create: `$PROJECT/scripts/seed_tasks.py`
- Create: `$PROJECT/data/tasks.json` (via running script)

- [ ] **Step 1: Create `scripts/seed_tasks.py`**

```python
"""Seed data/tasks.json with the Spring 2026 defaults from CLAUDE_CODE_DIRECTIONS.md."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import load_settings  # noqa: E402

DEFAULT_TASKS = [
    {"id": "cf-case2", "course": "CorpFin", "name": "Case 2", "due": "2026-04-15", "type": "case", "weight": "part of 15%", "done": False},
    {"id": "cf-ps3", "course": "CorpFin", "name": "Problem Set 3", "due": "2026-04-17", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-topic", "course": "CorpFin", "name": "Send project topic to professor", "due": "2026-04-20", "type": "admin", "weight": "", "done": False},
    {"id": "cf-ps4", "course": "CorpFin", "name": "Problem Set 4", "due": "2026-04-24", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-mid", "course": "CorpFin", "name": "Midterm Exam (in-class, closed book)", "due": "2026-05-01", "type": "exam", "weight": "25%", "done": False},
    {"id": "cf-ps5", "course": "CorpFin", "name": "Problem Set 5", "due": "2026-05-08", "type": "pset", "weight": "part of 15%", "done": False},
    {"id": "cf-proj", "course": "CorpFin", "name": "Valuation Project Presentation (15 min, must use ChatGPT)", "due": "2026-05-09", "type": "project", "weight": "15%", "done": False},
    {"id": "cf-final", "course": "CorpFin", "name": "Final Exam (in-class, closed book)", "due": "2026-05-22", "type": "exam", "weight": "35-60%", "done": False},
    {"id": "scs-fb", "course": "SCS III", "name": "Self-Feedback Exercise", "due": "2026-04-19", "type": "essay", "weight": "10%", "done": False},
    {"id": "scs-mid", "course": "SCS III", "name": "Midterm Essay (major paper)", "due": "2026-04-28", "type": "essay", "weight": "35%", "done": False},
    {"id": "scs-pres", "course": "SCS III", "name": "Final Paper Presentation", "due": "2026-05-13", "type": "presentation", "weight": "5%", "done": False},
    {"id": "scs-final", "course": "SCS III", "name": "Final Paper", "due": "2026-05-28", "type": "essay", "weight": "30%", "done": False},
    {"id": "apes-mid", "course": "APES", "name": "Online Midterm (9am-8pm, Weeks 1-4)", "due": "2026-04-21", "type": "exam", "weight": "50/280 pts", "done": False},
    {"id": "apes-debate", "course": "APES", "name": "Debate Presentation (group, slideshow+script+sources)", "due": "2026-04-28", "type": "presentation", "weight": "50/280 pts", "done": False},
    {"id": "apes-zoo", "course": "APES", "name": "Zoo Report or Individual Poster (hard+electronic copy)", "due": "2026-05-14", "type": "project", "weight": "50/280 pts", "done": False},
    {"id": "apes-final", "course": "APES", "name": "Online Final Exam (9am-8pm, Weeks 5-9)", "due": "2026-05-21", "type": "exam", "weight": "50/280 pts", "done": False},
    {"id": "e4e-ai4", "course": "E4E", "name": "AI Tutor Wk 4 (Behavioral Econ)", "due": "2026-04-20", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-mid", "course": "E4E", "name": "Midterm (in-class Tuesday)", "due": "2026-04-21", "type": "exam", "weight": "midterm", "done": False},
    {"id": "e4e-ai6", "course": "E4E", "name": "AI Tutor Wk 6 (Markets)", "due": "2026-05-04", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-ai7", "course": "E4E", "name": "AI Tutor Wk 7 (Uncertainty)", "due": "2026-05-11", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-ai8", "course": "E4E", "name": "AI Tutor Wk 8 (Risk/Labor)", "due": "2026-05-18", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-final", "course": "E4E", "name": "Final Exam (in-class Thursday)", "due": "2026-05-21", "type": "exam", "weight": "midterm", "done": False},
    {"id": "e4e-ai9", "course": "E4E", "name": "AI Tutor Wk 9", "due": "2026-05-25", "type": "ai-tutor", "weight": "discussion grade", "done": False},
    {"id": "e4e-proj", "course": "E4E", "name": "Final Project", "due": "2026-05-29", "type": "project", "weight": "TBD", "done": False},
]


def main() -> None:
    settings = load_settings()
    path = settings.tasks_path
    path.parent.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    if path.exists() and not force:
        existing = json.loads(path.read_text() or "[]")
        if existing:
            print(f"{path} already has {len(existing)} tasks. Pass --force to overwrite.")
            return
    path.write_text(json.dumps(DEFAULT_TASKS, indent=2))
    print(f"Seeded {len(DEFAULT_TASKS)} tasks → {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run seed script**

```bash
cd /Users/landonprojects/scheduler_bot
source venv/bin/activate
python scripts/seed_tasks.py
```

Expected output: `Seeded 24 tasks → /Users/landonprojects/scheduler_bot/data/tasks.json`

- [ ] **Step 3: Verify JSON parses**

```bash
python -c "import json; print(len(json.load(open('data/tasks.json'))))"
```

Expected: `24`

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_tasks.py
git commit -m "feat: seed script for Spring 2026 default tasks"
```

---

## Task 6: FastAPI server — API endpoints with auth, integration tests

**Files:**
- Create: `$PROJECT/backend/server.py`
- Create: `$PROJECT/tests/test_server.py`

Endpoints (all under `/api`, all require `X-Telegram-Init-Data` header except OPTIONS preflight):
- `GET  /api/tasks` → `{tasks: [...]}`
- `POST /api/tasks/{id}/done` → `{ok: true}`
- `POST /api/tasks/{id}/undo` → `{ok: true}`
- `POST /api/tasks` → body `{course, name, due, type, weight?}` → `{task: {...}}`, server generates `id`
- `GET  /api/briefing` → `{text: "..."}`
- Static mount: `/` → `backend/static/` (index.html + assets, built later by frontend)

- [ ] **Step 1: Write failing tests**

`tests/test_server.py`:

```python
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode
import pytest
from fastapi.testclient import TestClient


BOT_TOKEN = "123:TEST"


def _init_data(user_id: int = 42, token: str = BOT_TOKEN) -> str:
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "L"}),
    }
    pairs = sorted(data.items())
    dcs = "\n".join(f"{k}={v}" for k, v in pairs)
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode({**data, "hash": h})


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps([
        {"id": "a", "course": "APES", "name": "X", "due": "2026-04-15", "type": "exam", "weight": "10%", "done": False},
    ]))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TASKS_PATH", str(tasks_file))
    # Re-import server with fresh settings
    import importlib
    import backend.server as server_module
    importlib.reload(server_module)
    return TestClient(server_module.app)


def test_get_tasks_requires_init_data(client):
    r = client.get("/api/tasks")
    assert r.status_code == 401


def test_get_tasks_with_valid_init_data_returns_list(client):
    r = client.get("/api/tasks", headers={"X-Telegram-Init-Data": _init_data()})
    assert r.status_code == 200
    assert r.json()["tasks"][0]["id"] == "a"


def test_mark_done_and_undo(client):
    h = {"X-Telegram-Init-Data": _init_data()}
    assert client.post("/api/tasks/a/done", headers=h).status_code == 200
    assert client.get("/api/tasks", headers=h).json()["tasks"][0]["done"] is True
    assert client.post("/api/tasks/a/undo", headers=h).status_code == 200
    assert client.get("/api/tasks", headers=h).json()["tasks"][0]["done"] is False


def test_mark_done_missing_returns_404(client):
    r = client.post("/api/tasks/nope/done", headers={"X-Telegram-Init-Data": _init_data()})
    assert r.status_code == 404


def test_add_task_generates_id_and_persists(client):
    h = {"X-Telegram-Init-Data": _init_data()}
    body = {"course": "E4E", "name": "New Quiz", "due": "2026-05-01", "type": "exam", "weight": "5%"}
    r = client.post("/api/tasks", json=body, headers=h)
    assert r.status_code == 201
    new_id = r.json()["task"]["id"]
    assert new_id.startswith("e4e-")
    got = client.get("/api/tasks", headers=h).json()["tasks"]
    assert any(t["id"] == new_id for t in got)


def test_briefing_endpoint_returns_text(client):
    r = client.get("/api/briefing", headers={"X-Telegram-Init-Data": _init_data()})
    assert r.status_code == 200
    assert isinstance(r.json()["text"], str)
    assert len(r.json()["text"]) > 0
```

- [ ] **Step 2: Run tests, expect import error**

```bash
pytest tests/test_server.py -v
```

- [ ] **Step 3: Implement `backend/server.py`**

```python
from __future__ import annotations
import re
import uuid
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import verify_init_data, InitDataInvalid, TelegramUser
from .briefing import generate_briefing
from .config import load_settings, PROJECT_ROOT
from .tasks_store import Task, TasksStore, TaskNotFoundError


settings = load_settings()
store = TasksStore(settings.tasks_path)
app = FastAPI(title="Academic Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tunnel host varies; auth is via initData, not origin
    allow_methods=["*"],
    allow_headers=["*"],
)


async def current_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> TelegramUser:
    if not settings.telegram_bot_token:
        raise HTTPException(500, "TELEGRAM_BOT_TOKEN not configured")
    if not x_telegram_init_data:
        raise HTTPException(401, "missing X-Telegram-Init-Data header")
    try:
        return verify_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except InitDataInvalid as e:
        raise HTTPException(401, f"invalid initData: {e}")


class AddTaskBody(BaseModel):
    course: str
    name: str
    due: str
    type: str
    weight: str = ""
    notes: str | None = None


@app.get("/api/tasks")
def get_tasks(_: TelegramUser = Depends(current_user)):
    return {"tasks": [t.__dict__ for t in store.list()]}


@app.post("/api/tasks/{task_id}/done")
def mark_done(task_id: str, _: TelegramUser = Depends(current_user)):
    try:
        store.set_done(task_id, True)
    except TaskNotFoundError:
        raise HTTPException(404, f"no task {task_id!r}")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/undo")
def mark_undo(task_id: str, _: TelegramUser = Depends(current_user)):
    try:
        store.set_done(task_id, False)
    except TaskNotFoundError:
        raise HTTPException(404, f"no task {task_id!r}")
    return {"ok": True}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@app.post("/api/tasks", status_code=201)
def add_task(body: AddTaskBody, _: TelegramUser = Depends(current_user)):
    course_slug = _slug(body.course)[:8] or "task"
    name_slug = _slug(body.name)[:16] or uuid.uuid4().hex[:6]
    base = f"{course_slug}-{name_slug}"
    existing = {t.id for t in store.list()}
    task_id = base
    i = 2
    while task_id in existing:
        task_id = f"{base}-{i}"
        i += 1
    task = Task(
        id=task_id, course=body.course, name=body.name, due=body.due,
        type=body.type, weight=body.weight, done=False, notes=body.notes,
    )
    store.add(task)
    return {"task": task.__dict__}


@app.get("/api/briefing")
def get_briefing(_: TelegramUser = Depends(current_user)):
    text = generate_briefing(store.list(), today=date.today())
    return {"text": text}


# Static Mini App bundle — mounted last so /api/* wins. Built into backend/static/ by Vite.
_static_dir = PROJECT_ROOT / "backend" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_server.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
pytest -v
```

Expected: all tests across all files pass (24 total).

- [ ] **Step 6: Commit**

```bash
git add backend/server.py tests/test_server.py
git commit -m "feat: FastAPI server with initData auth and tasks/briefing endpoints"
```

---

## Task 7: Frontend scaffold — Vite + React + Tailwind + TS

**Files:**
- Create: `$PROJECT/frontend/package.json`
- Create: `$PROJECT/frontend/vite.config.ts`
- Create: `$PROJECT/frontend/tsconfig.json`
- Create: `$PROJECT/frontend/tailwind.config.js`
- Create: `$PROJECT/frontend/postcss.config.js`
- Create: `$PROJECT/frontend/index.html`
- Create: `$PROJECT/frontend/src/main.tsx`
- Create: `$PROJECT/frontend/src/index.css`
- Create: `$PROJECT/frontend/src/App.tsx` (placeholder)

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "scheduler-miniapp",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.7",
    "typescript": "^5.5.3",
    "vite": "^5.3.4"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

Vite will output into `backend/static/` so FastAPI can serve it directly.

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: path.resolve(__dirname, "../backend/static"),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["'JetBrains Mono'", "'SF Mono'", "monospace"],
      },
      colors: {
        bg: "#0a0a0a",
        card: "#141414",
        border: "#262626",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 5: Create `frontend/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 6: Create `frontend/index.html`**

The Telegram SDK must load before our app so `window.Telegram.WebApp` exists synchronously in `main.tsx`.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#0a0a0a" />
    <title>Scheduler</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
  </head>
  <body class="bg-bg text-neutral-200 font-mono">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root { height: 100%; }
body { -webkit-tap-highlight-color: transparent; }
```

- [ ] **Step 8: Create `frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 9: Create placeholder `frontend/src/App.tsx`**

```tsx
export default function App() {
  return <div className="p-6">Loading…</div>;
}
```

- [ ] **Step 10: Install & verify build**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npm install
npm run build
```

Expected: builds to `/Users/landonprojects/scheduler_bot/backend/static/index.html` + assets. No TS errors.

- [ ] **Step 11: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/package.json frontend/vite.config.ts frontend/tsconfig.json frontend/tailwind.config.js frontend/postcss.config.js frontend/index.html frontend/src/
git add frontend/package-lock.json
git commit -m "feat: frontend Vite+React+Tailwind scaffold"
```

---

## Task 8: Frontend — types, telegram helper, api client, utils, theme

**Files:**
- Create: `$PROJECT/frontend/src/types.ts`
- Create: `$PROJECT/frontend/src/telegram.ts`
- Create: `$PROJECT/frontend/src/api.ts`
- Create: `$PROJECT/frontend/src/utils.ts`
- Create: `$PROJECT/frontend/src/theme.ts`

- [ ] **Step 1: Create `frontend/src/types.ts`**

```ts
export type Task = {
  id: string;
  course: "CorpFin" | "SCS III" | "APES" | "E4E" | string;
  name: string;
  due: string; // YYYY-MM-DD
  type: "exam" | "pset" | "essay" | "case" | "project" | "presentation" | "reading" | "ai-tutor" | "recurring" | "admin";
  weight: string;
  done: boolean;
  notes?: string | null;
};

export type View = "priority" | "timeline" | "course";
```

- [ ] **Step 2: Create `frontend/src/telegram.ts`**

Thin typed wrapper. In dev (outside Telegram) we fall back to a stub so the page still renders.

```ts
type WebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  HapticFeedback?: { impactOccurred: (s: "light" | "medium" | "heavy") => void };
  colorScheme: "light" | "dark";
};

declare global {
  interface Window { Telegram?: { WebApp: WebApp } }
}

export function tg(): WebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function initData(): string {
  return tg()?.initData ?? "";
}

export function haptic(kind: "light" | "medium" | "heavy" = "light") {
  tg()?.HapticFeedback?.impactOccurred(kind);
}
```

- [ ] **Step 3: Create `frontend/src/api.ts`**

```ts
import { initData } from "./telegram";
import type { Task } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const api = {
  listTasks: () => request<{ tasks: Task[] }>("/api/tasks"),
  markDone: (id: string) => request(`/api/tasks/${encodeURIComponent(id)}/done`, { method: "POST" }),
  markUndo: (id: string) => request(`/api/tasks/${encodeURIComponent(id)}/undo`, { method: "POST" }),
  addTask: (body: Omit<Task, "id" | "done">) =>
    request<{ task: Task }>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  briefing: () => request<{ text: string }>("/api/briefing"),
};
```

- [ ] **Step 4: Create `frontend/src/utils.ts`**

```ts
import type { Task } from "./types";

export function daysUntil(dateStr: string, today = new Date()): number {
  const d = new Date(dateStr + "T00:00:00");
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.ceil((d.getTime() - t.getTime()) / 86400000);
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function urgencyColor(days: number): string {
  if (days < 0) return "#6b7280";
  if (days <= 2) return "#ef4444";
  if (days <= 7) return "#f59e0b";
  if (days <= 14) return "#3b82f6";
  return "#6b7280";
}

export function priorityScore(t: Task): number {
  if (t.done) return 999;
  const days = daysUntil(t.due);
  if (days < 0) return 998;
  let score = days;
  if (t.type === "exam") score -= 5;
  if (t.type === "essay" && t.weight?.includes("35")) score -= 4;
  if (t.type === "project") score -= 3;
  if (t.type === "presentation") score -= 2;
  return score;
}
```

- [ ] **Step 5: Create `frontend/src/theme.ts`**

```ts
export const COURSE_COLORS: Record<string, { bg: string; text: string; accent: string; light: string }> = {
  "CorpFin": { bg: "#1a1a2e", text: "#e0d6ff", accent: "#a78bfa", light: "#2d2b55" },
  "SCS III": { bg: "#1c1917", text: "#fde68a", accent: "#f59e0b", light: "#292524" },
  "APES":    { bg: "#052e16", text: "#bbf7d0", accent: "#34d399", light: "#14532d" },
  "E4E":     { bg: "#1e1b4b", text: "#c7d2fe", accent: "#818cf8", light: "#312e81" },
};

export const TYPE_ICONS: Record<string, string> = {
  exam: "◆", essay: "✎", pset: "≡", case: "◈",
  project: "★", presentation: "▶", reading: "◻",
  "ai-tutor": "⚡", recurring: "↻", admin: "·",
};

export const DEFAULT_COURSE_COLOR = { bg: "#111", text: "#ddd", accent: "#999", light: "#222" };
```

- [ ] **Step 6: Verify TS compiles**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npx tsc -b --noEmit
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/src/types.ts frontend/src/telegram.ts frontend/src/api.ts frontend/src/utils.ts frontend/src/theme.ts
git commit -m "feat: frontend shared modules (types, api, utils, theme)"
```

---

## Task 9: Frontend components — Header, AlertBanner, CourseStats, ViewToggle

Mobile-first adaptations vs. original JSX: stat cards scroll horizontally on narrow screens; tap targets are ≥44px.

**Files:**
- Create: `$PROJECT/frontend/src/components/Header.tsx`
- Create: `$PROJECT/frontend/src/components/AlertBanner.tsx`
- Create: `$PROJECT/frontend/src/components/CourseStats.tsx`
- Create: `$PROJECT/frontend/src/components/ViewToggle.tsx`

- [ ] **Step 1: Create `components/Header.tsx`**

```tsx
type Props = { today: Date; activeCount: number; weekCount: number };

export function Header({ today, activeCount, weekCount }: Props) {
  const dateStr = today.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return (
    <div className="mb-6">
      <h1 className="text-xl font-bold text-neutral-50 tracking-tight">SPRING 2026 — COMMAND CENTER</h1>
      <p className="text-[11px] text-neutral-500 mt-1">
        {dateStr} · {activeCount} active · {weekCount} due this week
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Create `components/AlertBanner.tsx`**

```tsx
import type { Task } from "../types";
import { formatDate } from "../utils";

export function AlertBanner({ thisWeek }: { thisWeek: Task[] }) {
  if (thisWeek.length === 0) return null;
  return (
    <div className="rounded-lg border border-red-600 p-3 mb-4 text-xs"
         style={{ background: "linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%)" }}>
      <span className="font-bold text-red-300">⚠ THIS WEEK:</span>{" "}
      <span className="text-red-100">
        {thisWeek.map(t => `${t.name} (${t.course}, ${formatDate(t.due)})`).join(" · ")}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Create `components/CourseStats.tsx`**

```tsx
import type { Task } from "../types";
import { COURSE_COLORS } from "../theme";
import { daysUntil } from "../utils";
import { haptic } from "../telegram";

type Props = {
  tasks: Task[];
  filter: string;
  onFilter: (course: string) => void;
};

export function CourseStats({ tasks, filter, onFilter }: Props) {
  return (
    <div className="flex gap-2 mb-5 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
      {Object.entries(COURSE_COLORS).map(([course, colors]) => {
        const courseTasks = tasks.filter(t => t.course === course);
        const active = courseTasks.filter(t => !t.done && daysUntil(t.due) >= 0);
        const next = [...active].sort((a, b) => a.due.localeCompare(b.due))[0];
        const selected = filter === course;
        return (
          <button
            key={course}
            onClick={() => { haptic("light"); onFilter(selected ? "all" : course); }}
            className="snap-start flex-shrink-0 rounded-lg px-4 py-3 text-left min-w-[140px] transition-colors"
            style={{
              background: selected ? colors.light : "#171717",
              border: `1px solid ${selected ? colors.accent : "#262626"}`,
            }}
          >
            <div className="text-[10px] font-bold uppercase tracking-widest" style={{ color: colors.accent }}>{course}</div>
            <div className="text-2xl font-bold mt-0.5" style={{ color: colors.text }}>{active.length}</div>
            <div className="text-[10px] text-neutral-500 mt-0.5 truncate max-w-[140px]">
              {next ? `Next: ${next.name}` : "All done"}
            </div>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Create `components/ViewToggle.tsx`**

```tsx
import type { View } from "../types";

type Props = {
  view: View;
  onView: (v: View) => void;
  filter: string;
  onResetFilter: () => void;
};

const VIEWS: { key: View; label: string }[] = [
  { key: "priority", label: "Priority" },
  { key: "timeline", label: "Date" },
  { key: "course", label: "Course" },
];

export function ViewToggle({ view, onView, filter, onResetFilter }: Props) {
  return (
    <div className="flex gap-2 mb-4 items-center flex-wrap">
      {VIEWS.map(v => {
        const active = view === v.key;
        return (
          <button
            key={v.key}
            onClick={() => onView(v.key)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              active ? "bg-neutral-800 border-neutral-600 text-neutral-50" : "border-neutral-800 text-neutral-500"
            } border`}
          >
            {v.label}
          </button>
        );
      })}
      <div className="flex-1" />
      {filter !== "all" && (
        <button onClick={onResetFilter}
                className="rounded-md px-3 py-1.5 text-xs border border-neutral-800 text-neutral-400">
          All Courses
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verify TS compiles**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npx tsc -b --noEmit
```

- [ ] **Step 6: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/src/components/Header.tsx frontend/src/components/AlertBanner.tsx frontend/src/components/CourseStats.tsx frontend/src/components/ViewToggle.tsx
git commit -m "feat: miniapp header, alert banner, course stats, view toggle"
```

---

## Task 10: Frontend components — Milestones, TaskRow, TaskList, AddTaskForm, CrunchNotice

**Files:**
- Create: `$PROJECT/frontend/src/components/Milestones.tsx`
- Create: `$PROJECT/frontend/src/components/TaskRow.tsx`
- Create: `$PROJECT/frontend/src/components/TaskList.tsx`
- Create: `$PROJECT/frontend/src/components/AddTaskForm.tsx`
- Create: `$PROJECT/frontend/src/components/CrunchNotice.tsx`

- [ ] **Step 1: Create `components/Milestones.tsx`**

```tsx
import type { Task } from "../types";
import { COURSE_COLORS, TYPE_ICONS, DEFAULT_COURSE_COLOR } from "../theme";
import { daysUntil, formatDate, urgencyColor } from "../utils";

export function Milestones({ tasks }: { tasks: Task[] }) {
  const items = tasks
    .filter(t => !t.done && daysUntil(t.due) >= 0 && ["exam", "project", "essay", "presentation"].includes(t.type))
    .sort((a, b) => a.due.localeCompare(b.due))
    .slice(0, 8);
  if (items.length === 0) return null;
  return (
    <div className="mb-6">
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">Major Milestones</h2>
      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
        {items.map(t => {
          const days = daysUntil(t.due);
          const colors = COURSE_COLORS[t.course] ?? DEFAULT_COURSE_COLOR;
          return (
            <div key={t.id} className="snap-start flex-shrink-0 rounded-lg px-3 py-2.5 min-w-[160px]"
                 style={{ background: colors.light, border: `1px solid ${colors.accent}40` }}>
              <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold" style={{ color: colors.accent }}>{t.course}</span>
                <span className="text-[10px] font-bold" style={{ color: urgencyColor(days) }}>
                  {days === 0 ? "TODAY" : days === 1 ? "TOMORROW" : `${days}d`}
                </span>
              </div>
              <div className="text-[13px] font-semibold mt-1" style={{ color: colors.text }}>
                {TYPE_ICONS[t.type] ?? "·"} {t.name}
              </div>
              <div className="text-[10px] text-neutral-500 mt-0.5">{formatDate(t.due)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `components/TaskRow.tsx`**

```tsx
import type { Task } from "../types";
import { COURSE_COLORS, TYPE_ICONS, DEFAULT_COURSE_COLOR } from "../theme";
import { daysUntil, formatDate, urgencyColor } from "../utils";
import { haptic } from "../telegram";

type Props = { task: Task; onToggle: (id: string, done: boolean) => void };

export function TaskRow({ task: t, onToggle }: Props) {
  const days = daysUntil(t.due);
  const colors = COURSE_COLORS[t.course] ?? DEFAULT_COURSE_COLOR;
  const isPast = days < 0 && !t.done;
  const handle = () => { haptic("light"); onToggle(t.id, !t.done); };
  return (
    <div onClick={handle}
         className={`flex items-center gap-3 rounded-md px-3 py-3 cursor-pointer transition-opacity ${t.done ? "opacity-40" : ""}`}
         style={{
           background: t.done ? "#0a0a0a" : isPast ? "#1a0a0a" : "#141414",
           border: `1px solid ${t.done ? "#1a1a1a" : isPast ? "#3f1515" : "#222"}`,
           borderLeft: `3px solid ${t.done ? "#333" : colors.accent}`,
         }}>
      <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-black"
           style={{
             border: `2px solid ${t.done ? "#525252" : colors.accent}`,
             background: t.done ? colors.accent : "transparent",
           }}>
        {t.done && "✓"}
      </div>
      <span className="text-sm w-4 text-center flex-shrink-0" style={{ color: colors.accent }}>
        {TYPE_ICONS[t.type] ?? "·"}
      </span>
      <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded flex-shrink-0 w-[56px] text-center"
            style={{ color: colors.accent, background: `${colors.accent}15` }}>
        {t.course}
      </span>
      <span className={`text-[13px] flex-1 min-w-0 truncate ${t.done ? "line-through text-neutral-600" : "text-neutral-200"}`}>
        {t.name}
      </span>
      <div className="text-right flex-shrink-0">
        <div className="text-[10px] text-neutral-500">{formatDate(t.due)}</div>
        <div className="text-[10px] font-bold" style={{ color: urgencyColor(days) }}>
          {t.done ? "DONE" : days < 0 ? "PAST" : days === 0 ? "TODAY" : days === 1 ? "TMRW" : `${days}d`}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `components/TaskList.tsx`**

```tsx
import type { Task, View } from "../types";
import { priorityScore } from "../utils";
import { TaskRow } from "./TaskRow";
import { useMemo } from "react";

type Props = {
  tasks: Task[];
  filter: string;
  view: View;
  onToggle: (id: string, done: boolean) => void;
};

export function TaskList({ tasks, filter, view, onToggle }: Props) {
  const visible = useMemo(() => {
    let ts = filter === "all" ? [...tasks] : tasks.filter(t => t.course === filter);
    if (view === "priority") ts.sort((a, b) => priorityScore(a) - priorityScore(b));
    else if (view === "timeline") ts.sort((a, b) => a.due.localeCompare(b.due));
    else ts.sort((a, b) => a.course === b.course ? a.due.localeCompare(b.due) : a.course.localeCompare(b.course));
    return ts;
  }, [tasks, filter, view]);

  return (
    <div>
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">
        All Tasks {filter !== "all" && `— ${filter}`}
      </h2>
      <div className="flex flex-col gap-1">
        {visible.map(t => <TaskRow key={t.id} task={t} onToggle={onToggle} />)}
        {visible.length === 0 && <div className="text-sm text-neutral-500 py-8 text-center">No tasks.</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `components/AddTaskForm.tsx`**

```tsx
import { useState } from "react";
import type { Task } from "../types";
import { COURSE_COLORS } from "../theme";

type Props = { onAdd: (body: Omit<Task, "id" | "done">) => Promise<void> };

const TYPES = ["exam", "essay", "pset", "case", "project", "presentation", "reading", "ai-tutor", "admin"] as const;

export function AddTaskForm({ onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [course, setCourse] = useState("CorpFin");
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [type, setType] = useState<typeof TYPES[number]>("pset");
  const [weight, setWeight] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!name || !due) return;
    setSubmitting(true);
    try {
      await onAdd({ course, name, due, type, weight });
      setName(""); setDue(""); setWeight("");
      setOpen(false);
    } finally { setSubmitting(false); }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
              className="w-full mt-4 py-3 rounded-md border border-dashed border-neutral-700 text-sm text-neutral-400">
        + Add Task
      </button>
    );
  }

  return (
    <div className="mt-4 p-4 rounded-lg bg-card border border-border space-y-2">
      <div className="flex gap-2">
        <select value={course} onChange={e => setCourse(e.target.value)}
                className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm">
          {Object.keys(COURSE_COLORS).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={type} onChange={e => setType(e.target.value as typeof TYPES[number])}
                className="bg-neutral-900 border border-border rounded px-2 py-2 text-sm">
          {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <input placeholder="Task name" value={name} onChange={e => setName(e.target.value)}
             className="w-full bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
      <div className="flex gap-2">
        <input type="date" value={due} onChange={e => setDue(e.target.value)}
               className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
        <input placeholder="Weight (opt)" value={weight} onChange={e => setWeight(e.target.value)}
               className="flex-1 bg-neutral-900 border border-border rounded px-2 py-2 text-sm" />
      </div>
      <div className="flex gap-2">
        <button onClick={submit} disabled={submitting || !name || !due}
                className="flex-1 py-2 rounded bg-neutral-100 text-neutral-900 text-sm font-semibold disabled:opacity-50">
          {submitting ? "Adding…" : "Add"}
        </button>
        <button onClick={() => setOpen(false)}
                className="px-4 py-2 rounded border border-border text-sm text-neutral-400">Cancel</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `components/CrunchNotice.tsx`**

```tsx
import type { Task } from "../types";
import { daysUntil } from "../utils";

export function CrunchNotice({ tasks }: { tasks: Task[] }) {
  const buckets: Record<string, number> = {};
  tasks.filter(t => !t.done && daysUntil(t.due) >= 0).forEach(t => {
    const d = new Date(t.due + "T00:00:00");
    d.setDate(d.getDate() - d.getDay());
    const key = d.toISOString().slice(0, 10);
    buckets[key] = (buckets[key] ?? 0) + 1;
  });
  const crunch = Object.entries(buckets).filter(([, n]) => n >= 3).map(([k]) => k);
  if (crunch.length === 0) return null;
  return (
    <div className="mt-6 p-4 rounded-lg border" style={{ background: "#1c1917", borderColor: "#78350f" }}>
      <div className="text-xs font-bold text-amber-400 mb-1">⚡ CRUNCH WEEKS DETECTED</div>
      <div className="text-xs text-neutral-400">
        Weeks with 3+ deadlines: {crunch.map(w => new Date(w + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })).join(", ")}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Verify TS compiles**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npx tsc -b --noEmit
```

- [ ] **Step 7: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/src/components/Milestones.tsx frontend/src/components/TaskRow.tsx frontend/src/components/TaskList.tsx frontend/src/components/AddTaskForm.tsx frontend/src/components/CrunchNotice.tsx
git commit -m "feat: miniapp milestones, task list/row, add form, crunch notice"
```

---

## Task 11: Frontend — wire App.tsx to API, polling, optimistic updates

**Files:**
- Modify: `$PROJECT/frontend/src/App.tsx`

- [ ] **Step 1: Replace `frontend/src/App.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Task, View } from "./types";
import { daysUntil } from "./utils";
import { Header } from "./components/Header";
import { AlertBanner } from "./components/AlertBanner";
import { CourseStats } from "./components/CourseStats";
import { ViewToggle } from "./components/ViewToggle";
import { Milestones } from "./components/Milestones";
import { TaskList } from "./components/TaskList";
import { AddTaskForm } from "./components/AddTaskForm";
import { CrunchNotice } from "./components/CrunchNotice";

export default function App() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [view, setView] = useState<View>("priority");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const { tasks } = await api.listTasks();
      setTasks(tasks);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    reload();
    const id = setInterval(reload, 60_000);
    return () => clearInterval(id);
  }, [reload]);

  const toggle = useCallback(async (id: string, done: boolean) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, done } : t));
    try {
      if (done) await api.markDone(id);
      else await api.markUndo(id);
    } catch (e) {
      setError(String(e));
      await reload();
    }
  }, [reload]);

  const add = useCallback(async (body: Omit<Task, "id" | "done">) => {
    const { task } = await api.addTask(body);
    setTasks(prev => [...prev, task]);
  }, []);

  const today = new Date();
  const active = tasks.filter(t => !t.done);
  const dueTodayOrSoon = active.filter(t => {
    const d = daysUntil(t.due, today);
    return d >= 0 && d <= 7;
  });

  return (
    <div className="min-h-screen bg-bg text-neutral-200 p-4 max-w-3xl mx-auto">
      <Header today={today} activeCount={active.length} weekCount={dueTodayOrSoon.length} />
      {error && <div className="mb-3 p-2 rounded bg-red-950 border border-red-800 text-xs text-red-300">{error}</div>}
      <AlertBanner thisWeek={dueTodayOrSoon} />
      <CourseStats tasks={tasks} filter={filter} onFilter={setFilter} />
      <ViewToggle view={view} onView={setView} filter={filter} onResetFilter={() => setFilter("all")} />
      <Milestones tasks={filter === "all" ? tasks : tasks.filter(t => t.course === filter)} />
      <TaskList tasks={tasks} filter={filter} view={view} onToggle={toggle} />
      <AddTaskForm onAdd={add} />
      <CrunchNotice tasks={tasks} />
      <div className="mt-8 p-3 rounded bg-card border border-border text-[11px] text-neutral-500">
        Tap any task to toggle done. Pulls update every 60s.
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build and verify output**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npm run build
ls ../backend/static/
```

Expected: `index.html` + `assets/` directory present in `backend/static/`.

- [ ] **Step 3: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/src/App.tsx
git commit -m "feat: miniapp App wiring with polling and optimistic updates"
```

---

## Task 12: Telegram bot — /start, /briefing, menu button, send-mode for cron

The bot has three CLI modes:
- `python -m backend.bot bot` — long-running polling bot (handles `/start`, `/briefing`, replies with inline "Open Dashboard" button)
- `python -m backend.bot send` — one-shot: send today's briefing to `TELEGRAM_CHAT_ID` (used by cron)
- `python -m backend.bot setup-menu` — set the chat menu button to open the Mini App at `MINIAPP_URL`

**Files:**
- Create: `$PROJECT/backend/bot.py`

- [ ] **Step 1: Create `backend/bot.py`**

```python
"""Telegram bot entrypoint. Modes: bot | send | setup-menu.

  python -m backend.bot bot          # long-running polling bot
  python -m backend.bot send         # one-shot daily briefing (cron)
  python -m backend.bot setup-menu   # set chat menu button to open the miniapp
"""
from __future__ import annotations
import asyncio
import logging
import sys
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from .briefing import generate_briefing
from .config import load_settings
from .tasks_store import TasksStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def _open_dashboard_markup(miniapp_url: str) -> InlineKeyboardMarkup | None:
    if not miniapp_url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton("📱 Open Dashboard", web_app=WebAppInfo(url=miniapp_url))]])


async def _send_briefing(app: Application, chat_id: str, miniapp_url: str) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    text = generate_briefing(store.list(), today=date.today())
    await app.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(miniapp_url),
    )


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    await update.message.reply_text(
        "Academic Scheduler ready. Use /briefing for today's plan or tap the menu to open the dashboard.",
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )


async def cmd_briefing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    text = generate_briefing(store.list(), today=date.today())
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )


def _build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    return app


async def run_setup_menu() -> None:
    settings = load_settings()
    if not settings.miniapp_url:
        log.error("MINIAPP_URL is empty; set it in .env or via refresh_tunnel.sh first")
        sys.exit(2)
    app = _build_app(settings.telegram_bot_token)
    async with app:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Dashboard", web_app=WebAppInfo(url=settings.miniapp_url)),
        )
    log.info("Menu button set → %s", settings.miniapp_url)


async def run_send() -> None:
    settings = load_settings()
    if not settings.telegram_chat_id:
        log.error("TELEGRAM_CHAT_ID missing"); sys.exit(2)
    app = _build_app(settings.telegram_bot_token)
    async with app:
        await _send_briefing(app, settings.telegram_chat_id, settings.miniapp_url)
    log.info("Briefing sent.")


def run_bot() -> None:
    settings = load_settings()
    app = _build_app(settings.telegram_bot_token)
    log.info("Polling bot started. miniapp_url=%s", settings.miniapp_url or "(not set)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "bot"
    if mode == "bot":
        run_bot()
    elif mode == "send":
        asyncio.run(run_send())
    elif mode == "setup-menu":
        asyncio.run(run_setup_menu())
    else:
        print(f"unknown mode: {mode}. use: bot | send | setup-menu"); sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test — `send` mode without sending (dry parse)**

```bash
cd /Users/landonprojects/scheduler_bot
source venv/bin/activate
python -c "from backend.bot import run_send; print('import ok')"
```

Expected: `import ok` — no import errors. (A real send requires a valid token; that happens in Task 14.)

- [ ] **Step 3: Commit**

```bash
git add backend/bot.py
git commit -m "feat: telegram bot with /start, /briefing, menu button, send mode"
```

---

## Task 13: Tunnel script + menu button updater

Cloudflare Quick Tunnel URL changes on every restart. `refresh_tunnel.sh` starts `cloudflared`, parses the URL from stderr, writes it to `.env` (`MINIAPP_URL=`) and `.tunnel_url`, then runs `python -m backend.bot setup-menu` to update the Telegram chat menu button so tapping it opens the fresh URL.

**Files:**
- Create: `$PROJECT/scripts/refresh_tunnel.sh`
- Create: `$PROJECT/scripts/update_menu_button.py`

- [ ] **Step 1: Install cloudflared**

```bash
brew install cloudflared
cloudflared --version
```

Expected: prints a version (e.g. `cloudflared version 2024...`).

- [ ] **Step 2: Create `scripts/refresh_tunnel.sh`**

```bash
#!/usr/bin/env bash
# Start a Cloudflare Quick Tunnel pointed at the local API, capture the public
# https URL, write it to .env as MINIAPP_URL=..., then update the Telegram chat
# menu button so tapping it opens the fresh URL.
#
# Usage:  ./scripts/refresh_tunnel.sh
# Leaves cloudflared running in the foreground; Ctrl-C to stop.

set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

API_PORT="${API_PORT:-8000}"
LOG_FILE="$(mktemp /tmp/cloudflared.XXXXXX.log)"
URL_FILE="$PROJECT_ROOT/.tunnel_url"
ENV_FILE="$PROJECT_ROOT/.env"

echo "→ starting cloudflared quick tunnel (port $API_PORT), log: $LOG_FILE"
cloudflared tunnel --no-autoupdate --url "http://localhost:$API_PORT" > "$LOG_FILE" 2>&1 &
CF_PID=$!
trap 'echo "→ stopping cloudflared"; kill "$CF_PID" 2>/dev/null || true' EXIT

# Wait up to 30s for the URL to appear
URL=""
for _ in $(seq 1 60); do
    URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | head -n1 || true)"
    [ -n "$URL" ] && break
    sleep 0.5
done

if [ -z "$URL" ]; then
    echo "✗ failed to detect tunnel URL after 30s. log dump:" >&2
    cat "$LOG_FILE" >&2
    exit 1
fi

echo "→ tunnel URL: $URL"
echo "$URL" > "$URL_FILE"

# Rewrite MINIAPP_URL line in .env (or append if missing)
if grep -q '^MINIAPP_URL=' "$ENV_FILE"; then
    # portable in-place edit on macOS
    sed -i '' "s|^MINIAPP_URL=.*|MINIAPP_URL=$URL|" "$ENV_FILE"
else
    echo "MINIAPP_URL=$URL" >> "$ENV_FILE"
fi

echo "→ updating Telegram chat menu button"
source venv/bin/activate
python -m backend.bot setup-menu

echo "✓ tunnel live. Keep this terminal open. Ctrl-C to stop."
wait "$CF_PID"
```

- [ ] **Step 3: Make it executable**

```bash
chmod +x scripts/refresh_tunnel.sh
```

- [ ] **Step 4: Remove unused `scripts/update_menu_button.py`**

The `setup-menu` mode on `backend/bot.py` already does this. No separate script needed. (This bullet is a no-op — the initial file list had a stub; confirm we don't create it.)

- [ ] **Step 5: Commit**

```bash
git add scripts/refresh_tunnel.sh
git commit -m "feat: cloudflare quick tunnel + menu button refresh script"
```

---

## Task 14: Cron job, run.sh, end-to-end manual test

**Files:**
- Create: `$PROJECT/run.sh`
- Create: `$PROJECT/README.md`
- Modify: user's crontab (`crontab -e`)

- [ ] **Step 1: User provides credentials — pause and ask**

At this point, halt and ask the user for:
- `TELEGRAM_BOT_TOKEN` (from BotFather)
- `TELEGRAM_CHAT_ID` (message @userinfobot on Telegram to get this)

Then populate `$PROJECT/.env`:

```bash
cp .env.example .env
# Edit .env, fill in the two values. Leave MINIAPP_URL empty — refresh_tunnel.sh will fill it.
```

- [ ] **Step 2: Build frontend once**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npm run build
```

Expected: `../backend/static/index.html` exists.

- [ ] **Step 3: Create `run.sh`**

```bash
#!/usr/bin/env bash
# Start all three long-running processes inside tmux windows:
#   0: uvicorn  (FastAPI on 127.0.0.1:8000)
#   1: bot      (telegram polling)
#   2: tunnel   (cloudflared + menu update)
#
# Attach with `tmux attach -t scheduler`, detach with Ctrl-B D.

set -euo pipefail
cd "$(dirname "$0")"
SESSION=scheduler

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "session $SESSION already running. tmux attach -t $SESSION"
    exit 0
fi

tmux new-session -d -s "$SESSION" -n api \
    "cd $(pwd) && source venv/bin/activate && uvicorn backend.server:app --host 127.0.0.1 --port 8000"

tmux new-window -t "$SESSION" -n bot \
    "cd $(pwd) && source venv/bin/activate && python -m backend.bot bot"

tmux new-window -t "$SESSION" -n tunnel \
    "cd $(pwd) && ./scripts/refresh_tunnel.sh"

echo "started. tmux attach -t $SESSION"
```

```bash
chmod +x run.sh
```

- [ ] **Step 4: Start services and verify each window**

```bash
cd /Users/landonprojects/scheduler_bot
./run.sh
tmux attach -t scheduler
```

Check each window (Ctrl-B + window-number):
- `api`: uvicorn startup, listening on 127.0.0.1:8000
- `bot`: polling started, no auth errors
- `tunnel`: prints `tunnel URL: https://<something>.trycloudflare.com`, then `Menu button set`

Detach with Ctrl-B D.

- [ ] **Step 5: Verify API reachable through tunnel**

```bash
curl -s "$(cat .tunnel_url)/api/tasks"
```

Expected: `{"detail":"missing X-Telegram-Init-Data header"}` (401 — correct, auth is enforced).

- [ ] **Step 6: Test bot interaction from Telegram**

On your phone:
1. Open the bot chat.
2. Send `/start` — reply includes "Open Dashboard" inline button. Tap it.
3. Mini App should open inside Telegram, showing the dashboard with 24 tasks.
4. Tap a task — it should check/uncheck, haptic fires.
5. Close the Mini App. Tap the persistent **menu button** (next to the chat input) — should also open the dashboard.
6. Send `/briefing` — reply is the markdown briefing with the Open Dashboard button.

If the Mini App shows a blank screen, open the browser devtools via Telegram desktop client (`@BotFather` → `/devtools` enable) to see console errors.

- [ ] **Step 7: Add cron entry for 7am daily briefing**

```bash
crontab -l 2>/dev/null > /tmp/crontab.bak
{
  crontab -l 2>/dev/null
  echo "0 7 * * * cd /Users/landonprojects/scheduler_bot && /Users/landonprojects/scheduler_bot/venv/bin/python -m backend.bot send >> /Users/landonprojects/scheduler_bot/briefing.log 2>&1"
} | crontab -
crontab -l | tail -5
```

Expected: the 7am line appears in crontab output.

- [ ] **Step 8: Dry-run the cron command manually**

```bash
cd /Users/landonprojects/scheduler_bot && ./venv/bin/python -m backend.bot send
```

Expected: Telegram message arrives in the chat within seconds, with the Open Dashboard button attached.

- [ ] **Step 9: Create `README.md`**

```markdown
# Academic Scheduler — Telegram Mini App

Personal scheduler bot for UChicago Spring 2026. Backend on Mac Mini, exposed via Cloudflare Quick Tunnel, consumed by a Telegram Mini App + daily 7am briefing cron.

## Setup

1. `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. `cd frontend && npm install && npm run build && cd ..`
3. `cp .env.example .env` and fill `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
4. `python scripts/seed_tasks.py`
5. `brew install cloudflared`
6. `./run.sh`

## Modes

- `python -m backend.bot bot` — polling bot
- `python -m backend.bot send` — one-shot briefing (cron uses this)
- `python -m backend.bot setup-menu` — re-apply chat menu button URL

## Daily operation

`run.sh` starts three tmux windows (api, bot, tunnel). The tunnel window holds the Quick Tunnel; restarting it changes the URL and automatically updates the Telegram chat menu button via `setup-menu`.

## Tests

`pytest -v`
```

- [ ] **Step 10: Commit**

```bash
git add run.sh README.md
git commit -m "feat: run.sh orchestrator, cron setup, README"
```

---

## Self-Review Checklist (post-write)

**Spec coverage:**
- ✅ Mini App replaces JSX — Tasks 7–11
- ✅ Backend + tasks.json — Tasks 1–6
- ✅ Menu button + inline button on briefing — Task 12 (`_open_dashboard_markup`, `MenuButtonWebApp`)
- ✅ Cron 7am daily briefing — Task 14 Step 7
- ✅ Cloudflare Quick Tunnel — Task 13
- ✅ Telegram initData auth — Task 3, enforced Task 6
- ✅ Mobile-first (scroll-snap horizontal rails, 44px tap targets, viewport-fit=cover) — Tasks 9–10
- ✅ Pragmatic tests on auth + task store + briefing + endpoints; UI tested manually in Task 14
- ⏭️ Deferred (intentional): Google Calendar, Claude-enhanced briefings, web browser dashboard

**Type consistency:** `Task`, `TelegramUser`, `View`, `TasksStore.set_done`, `api.markDone/markUndo` — names match across definition and usage.

**Credentials handoff points:** Task 14 Step 1 is the checkpoint where the executing agent must pause for `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from the user.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-13-telegram-miniapp.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
