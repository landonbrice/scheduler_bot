# Google Calendar Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch the user's Google Calendar events for the next 7 days and display them in both the briefing message and the Mini App, failing gracefully when credentials are missing.

**Architecture:** Add a `backend/gcal.py` module that wraps the Google Calendar API with a read-through fetch (no caching in v1). A one-time `scripts/setup_google.py` runs the OAuth flow and persists the token at `~/.config/scheduler-bot/google_token.json`. The FastAPI server gets a new auth-guarded `/api/calendar` endpoint. `backend/briefing.py` receives calendar events as an additional argument and renders them in a `📅 TODAY'S SCHEDULE` block. The Mini App gains a `TodaySchedule` component pinned above the alert banner that hides when there are no events.

**Tech Stack:**
- `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` (OAuth + Calendar v3)
- Existing: FastAPI, React + Vite, python-telegram-bot

**Credentials paths (hardcoded, per `CLAUDE.md`):**
- Client secrets: `~/.config/scheduler-bot/google_creds.json` (user-provided)
- Cached OAuth token: `~/.config/scheduler-bot/google_token.json` (written by `setup_google.py`)
- Scopes: `["https://www.googleapis.com/auth/calendar.readonly"]`

**Out of scope:** Multiple calendars (primary only), write access, recurring-event expansion edge cases (library handles it), calendar caching, calendar-backed task creation, webhook/push subscriptions.

---

## File Structure

```
backend/
├── gcal.py                   # NEW — fetch_events(today, days) → list[CalendarEvent]; CalendarEvent dataclass; TokenMissing exception
├── briefing.py               # MODIFY — generate_briefing(tasks, today, events=None) adds optional events arg + today-schedule block
└── server.py                 # MODIFY — add GET /api/calendar endpoint; thread events into GET /api/briefing

scripts/
└── setup_google.py           # NEW — one-time OAuth flow helper (headless-friendly)

tests/
├── test_gcal.py              # NEW — behavior tests with injected fake calendar service
└── test_briefing.py          # MODIFY — add test for events block rendering

frontend/src/
├── types.ts                  # MODIFY — add CalendarEvent type
├── api.ts                    # MODIFY — add api.calendar()
└── components/
    └── TodaySchedule.tsx     # NEW — horizontal scroll of today's events
```

`CLAUDE.md` also gets a one-line update once the flow works.

---

## Task 1: Install Google client libs + bump requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append Google deps to `requirements.txt`**

Replace the file so Google deps appear at the bottom:

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
python-telegram-bot==21.*
python-dotenv==1.0.*
httpx==0.27.*
pytest==8.*
pytest-asyncio==0.24.*
google-api-python-client==2.*
google-auth-oauthlib==1.2.*
google-auth-httplib2==0.2.*
```

- [ ] **Step 2: Install into venv**

```bash
cd /Users/landonprojects/scheduler_bot
source venv/bin/activate
pip install -r requirements.txt
```

Expected: installs `google-api-python-client` and its transitive deps. No failures.

- [ ] **Step 3: Smoke-check imports**

```bash
python -c "from googleapiclient.discovery import build; from google_auth_oauthlib.flow import InstalledAppFlow; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add google-api-python-client + auth libs"
```

---

## Task 2: PAUSE — user provides Google OAuth client secrets

**This is a human checkpoint. No code changes in this task.**

The executing agent MUST pause here and direct the user to complete the Google Cloud Console setup before proceeding to Task 3.

- [ ] **Step 1: Instruct the user**

Print these exact instructions and wait for confirmation:

```
Google Calendar OAuth setup (one-time, ~5 minutes):

1. Go to https://console.cloud.google.com/
2. Create a new project (e.g. "scheduler-bot") OR pick an existing one.
3. Enable the Google Calendar API:
   https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
4. Configure the OAuth consent screen:
   - APIs & Services → OAuth consent screen
   - User type: External (unless you have a Workspace org → Internal is fine)
   - App name: "scheduler-bot" · support email: your email
   - Scopes: you can skip the scope picker (we'll request readonly at runtime)
   - Test users: add your own Google account
5. Create OAuth client:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**  ← important, not Web app
   - Name: "scheduler-bot-desktop"
   - Download the JSON
6. On the Mac Mini, save the file to exactly:
   ~/.config/scheduler-bot/google_creds.json

Tell me when the file is in place.
```

- [ ] **Step 2: Verify file exists before proceeding**

```bash
ls -la ~/.config/scheduler-bot/google_creds.json
```

Expected: file listed, size > 0. If missing, do not proceed — loop back with clarifying questions.

---

## Task 3: `gcal.py` — module + tests (TDD)

**Files:**
- Create: `backend/gcal.py`
- Create: `tests/test_gcal.py`

This task does not touch Google's network. Tests inject a fake `service` object to verify the event-mapping logic. Real OAuth/network happens in Task 4.

- [ ] **Step 1: Write failing tests — `tests/test_gcal.py`**

```python
from datetime import date, datetime, timezone
from types import SimpleNamespace
import pytest
from backend.gcal import CalendarEvent, TokenMissing, events_from_api_response, fetch_events_with_service


def _ev(summary="X", start_iso="2026-04-13T09:00:00-05:00", end_iso="2026-04-13T10:00:00-05:00", all_day=False):
    if all_day:
        return {"summary": summary, "start": {"date": start_iso[:10]}, "end": {"date": end_iso[:10]}}
    return {"summary": summary, "start": {"dateTime": start_iso}, "end": {"dateTime": end_iso}}


def test_maps_timed_event():
    api = {"items": [_ev("Class", "2026-04-13T09:30:00-05:00", "2026-04-13T10:10:00-05:00")]}
    evs = events_from_api_response(api)
    assert len(evs) == 1
    e = evs[0]
    assert e.summary == "Class"
    assert e.start.hour == 9 and e.start.minute == 30
    assert e.all_day is False


def test_maps_all_day_event():
    api = {"items": [_ev("Birthday", "2026-04-13", "2026-04-14", all_day=True)]}
    evs = events_from_api_response(api)
    assert evs[0].all_day is True
    assert evs[0].summary == "Birthday"


def test_skips_events_without_summary():
    api = {"items": [{"start": {"dateTime": "2026-04-13T09:00:00-05:00"}, "end": {"dateTime": "2026-04-13T10:00:00-05:00"}}]}
    evs = events_from_api_response(api)
    assert evs == []


def test_fetch_with_injected_service_calls_correct_window():
    captured = {}
    def _events_list(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(execute=lambda: {"items": []})
    fake_events = SimpleNamespace(list=_events_list)
    fake_service = SimpleNamespace(events=lambda: fake_events)

    today = date(2026, 4, 13)
    result = fetch_events_with_service(fake_service, today=today, days=7)
    assert result == []
    assert captured["calendarId"] == "primary"
    assert captured["singleEvents"] is True
    assert captured["orderBy"] == "startTime"
    # timeMin should be today 00:00 UTC; timeMax should be today+7 00:00 UTC
    assert captured["timeMin"].startswith("2026-04-13T")
    assert captured["timeMax"].startswith("2026-04-20T")


def test_token_missing_is_a_known_exception():
    assert issubclass(TokenMissing, Exception)


def test_calendar_event_dataclass_is_jsonable_dict():
    ev = CalendarEvent(summary="Lab", start=datetime(2026, 4, 13, 10, 20, tzinfo=timezone.utc),
                       end=datetime(2026, 4, 13, 10, 50, tzinfo=timezone.utc), all_day=False)
    d = ev.as_dict()
    assert d["summary"] == "Lab"
    assert d["start"].endswith("+00:00") or d["start"].endswith("Z") or "T" in d["start"]
    assert d["all_day"] is False
```

- [ ] **Step 2: Run tests — expect ImportError / ModuleNotFoundError**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
pytest tests/test_gcal.py -v
```

- [ ] **Step 3: Implement `backend/gcal.py`**

```python
"""Google Calendar fetcher.

Two public entry points:
  - fetch_events(today, days=7) -> list[CalendarEvent]  # loads creds + builds service
  - fetch_events_with_service(service, today, days=7)   # accepts an injected service (tests)

Both return an empty list if there are no events. fetch_events() returns [] and
logs a warning if credentials are missing or the API call fails — it never raises
into the caller, because we don't want the briefing or the miniapp to crash when
calendar isn't configured.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

CREDS_PATH = Path.home() / ".config" / "scheduler-bot" / "google_creds.json"
TOKEN_PATH = Path.home() / ".config" / "scheduler-bot" / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


class TokenMissing(Exception):
    """Raised when no cached OAuth token exists (user must run setup_google.py)."""


@dataclass
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime
    all_day: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "all_day": self.all_day,
        }


def _parse_edge(edge: dict) -> tuple[datetime, bool]:
    """Return (dt, all_day) from a Google Calendar event start/end object."""
    if "dateTime" in edge:
        # e.g. "2026-04-13T09:30:00-05:00"
        return datetime.fromisoformat(edge["dateTime"]), False
    # All-day events use "date": "YYYY-MM-DD"
    d = date.fromisoformat(edge["date"])
    return datetime.combine(d, time.min, tzinfo=timezone.utc), True


def events_from_api_response(api: dict) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for item in api.get("items", []):
        summary = item.get("summary")
        if not summary:
            continue
        start_dt, all_day = _parse_edge(item["start"])
        end_dt, _ = _parse_edge(item["end"])
        out.append(CalendarEvent(summary=summary, start=start_dt, end=end_dt, all_day=all_day))
    return out


def fetch_events_with_service(service: Any, today: date, days: int = 7) -> list[CalendarEvent]:
    time_min = datetime.combine(today, time.min, tzinfo=timezone.utc).isoformat()
    time_max = datetime.combine(today + timedelta(days=days), time.min, tzinfo=timezone.utc).isoformat()
    resp = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()
    return events_from_api_response(resp)


def _build_service() -> Any:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not TOKEN_PATH.exists():
        raise TokenMissing(f"no token at {TOKEN_PATH} — run scripts/setup_google.py")
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
        else:
            raise TokenMissing("cached token is invalid — re-run scripts/setup_google.py")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def fetch_events(today: date, days: int = 7) -> list[CalendarEvent]:
    """Fetch events; never raise. Returns [] on any failure (logs a warning)."""
    try:
        service = _build_service()
        return fetch_events_with_service(service, today=today, days=days)
    except TokenMissing as e:
        log.warning("calendar disabled: %s", e)
        return []
    except Exception as e:  # network, API errors, revoked token, etc.
        log.warning("calendar fetch failed: %s", e)
        return []
```

- [ ] **Step 4: Run tests — expect 6 pass**

```bash
pytest tests/test_gcal.py -v
```

- [ ] **Step 5: Full suite regression**

```bash
pytest -v
```

Expected: 30 total pass (24 existing + 6 new).

- [ ] **Step 6: Commit**

```bash
git add backend/gcal.py tests/test_gcal.py
git commit -m "feat: google calendar fetcher with pure-function tests"
```

---

## Task 4: `setup_google.py` — one-time OAuth helper

**Files:**
- Create: `scripts/setup_google.py`

The Mac Mini is headless but reachable over Tailscale from the user's laptop. `InstalledAppFlow.run_local_server(port=8080, bind_addr="0.0.0.0")` starts a temporary HTTP server the user can hit from their laptop browser pointed at the Mac Mini's Tailscale IP or hostname.

- [ ] **Step 1: Create `scripts/setup_google.py`**

```python
"""One-time Google OAuth setup.

Run this on the Mac Mini:
  source venv/bin/activate
  python scripts/setup_google.py

The script starts a local HTTP server on 0.0.0.0:8080 and prints an authorization
URL. Open it from any device that can reach the Mac Mini (Tailscale works), grant
access, and the script persists the token to ~/.config/scheduler-bot/google_token.json.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gcal import CREDS_PATH, TOKEN_PATH, SCOPES  # noqa: E402


def main() -> None:
    if not CREDS_PATH.exists():
        print(f"✗ missing {CREDS_PATH}")
        print("  1. Google Cloud Console → Create OAuth client (Desktop app)")
        print("  2. Download the JSON → save it to the path above")
        sys.exit(2)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    print("→ starting local auth server on 0.0.0.0:8080")
    print("  Open the URL below from any device that can reach this Mac (Tailscale works).")
    print("  If the redirect doesn't resolve from your laptop, replace 'localhost' in the URL")
    print("  with this Mac's Tailscale hostname / IP.")
    creds = flow.run_local_server(host="0.0.0.0", port=8080, open_browser=False)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"✓ token saved to {TOKEN_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Syntax-check and import-check**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
python -c "import ast; ast.parse(open('scripts/setup_google.py').read()); print('syntax ok')"
python -c "import scripts.setup_google" 2>&1 | head -3
```

Expected: `syntax ok`. The import-check may warn about `scripts` not being a package (no `__init__.py`) — that's fine; `setup_google.py` is run directly.

- [ ] **Step 3: Commit**

```bash
git add scripts/setup_google.py
git commit -m "feat: one-time google OAuth setup helper"
```

---

## Task 5: PAUSE — user runs `setup_google.py`

**Human checkpoint.**

- [ ] **Step 1: Instruct the user**

Print exactly:

```
Run this on the Mac Mini:

  cd /Users/landonprojects/scheduler_bot
  source venv/bin/activate
  python scripts/setup_google.py

The script will print a URL. Open it from your laptop's browser. If the URL
begins with http://localhost:8080/..., replace "localhost" with the Mac's
Tailscale name (e.g. http://mac-mini.tail-scale.ts.net:8080/...) so your
laptop can reach the redirect.

Grant access. The script exits with "✓ token saved to ..." once done.
```

- [ ] **Step 2: Verify token file exists**

```bash
ls -la ~/.config/scheduler-bot/google_token.json
```

Expected: file present. If missing, do not proceed.

- [ ] **Step 3: End-to-end fetch smoke test**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
python -c "from datetime import date; from backend.gcal import fetch_events; evs = fetch_events(date.today()); print(f'fetched {len(evs)} events'); [print('-', e.summary, e.start.isoformat()) for e in evs[:5]]"
```

Expected: prints `fetched N events` with N >= 0. If you have upcoming events, they appear. No tracebacks.

---

## Task 6: `/api/calendar` endpoint + regression tests

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add failing test — append to `tests/test_server.py`**

```python
def test_calendar_endpoint_returns_events_list(client, monkeypatch):
    from backend import server as server_module
    from backend.gcal import CalendarEvent
    from datetime import datetime, timezone

    fake = [CalendarEvent(
        summary="APES Lecture",
        start=datetime(2026, 4, 14, 9, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 14, 10, 10, tzinfo=timezone.utc),
        all_day=False,
    )]
    monkeypatch.setattr(server_module, "fetch_events", lambda today, days=7: fake)
    r = client.get("/api/calendar", headers={"X-Telegram-Init-Data": _init_data()})
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["summary"] == "APES Lecture"
    assert events[0]["all_day"] is False


def test_calendar_endpoint_requires_auth(client):
    r = client.get("/api/calendar")
    assert r.status_code == 401
```

- [ ] **Step 2: Run the two new tests — expect failure (endpoint missing)**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
pytest tests/test_server.py::test_calendar_endpoint_returns_events_list tests/test_server.py::test_calendar_endpoint_requires_auth -v
```

Expected: both fail with 404 on the first and likely 404 on the second.

- [ ] **Step 3: Modify `backend/server.py` — add import + endpoint**

Locate the existing imports block near the top of `backend/server.py` and add:

```python
from .gcal import fetch_events
```

Then locate the existing `@app.get("/api/briefing")` handler. Immediately **before** it, insert the new calendar endpoint:

```python
@app.get("/api/calendar")
def get_calendar(_: TelegramUser = Depends(current_user)):
    events = fetch_events(date.today(), days=7)
    return {"events": [e.as_dict() for e in events]}
```

The import `date` is already imported at the top of `server.py`.

- [ ] **Step 4: Run the two new tests — expect pass**

```bash
pytest tests/test_server.py::test_calendar_endpoint_returns_events_list tests/test_server.py::test_calendar_endpoint_requires_auth -v
```

- [ ] **Step 5: Full regression**

```bash
pytest -v
```

Expected: 32 total pass (30 previous + 2 new).

- [ ] **Step 6: Commit**

```bash
git add backend/server.py tests/test_server.py
git commit -m "feat: /api/calendar endpoint backed by gcal.fetch_events"
```

---

## Task 7: Briefing integrates calendar events

**Files:**
- Modify: `backend/briefing.py`
- Modify: `tests/test_briefing.py`
- Modify: `backend/bot.py` (threading events into `run_send` + `/briefing` handler)

The briefing stays a pure function: callers supply the events. `bot.py` fetches them and passes them in. This keeps the briefing testable without Google mocks.

- [ ] **Step 1: Add failing test — append to `tests/test_briefing.py`**

```python
from datetime import date, datetime, timezone
from backend.gcal import CalendarEvent


def test_today_schedule_block_renders_events_before_overdue():
    tasks = [
        _t("old", "APES", "Old thing", "2026-04-10"),  # overdue
    ]
    events = [
        CalendarEvent(
            summary="APES Lecture",
            start=datetime(2026, 4, 13, 9, 30, tzinfo=timezone.utc),
            end=datetime(2026, 4, 13, 10, 10, tzinfo=timezone.utc),
            all_day=False,
        ),
        CalendarEvent(
            summary="SCS III",
            start=datetime(2026, 4, 13, 15, 0, tzinfo=timezone.utc),
            end=datetime(2026, 4, 13, 16, 20, tzinfo=timezone.utc),
            all_day=False,
        ),
    ]
    text = generate_briefing(tasks, today=date(2026, 4, 13), events=events)
    assert "TODAY'S SCHEDULE" in text
    assert "APES Lecture" in text
    assert "SCS III" in text
    # schedule block comes before overdue
    assert text.index("TODAY'S SCHEDULE") < text.index("OVERDUE")


def test_events_from_other_days_excluded():
    events = [CalendarEvent(
        summary="Tomorrow meeting",
        start=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc),
        all_day=False,
    )]
    text = generate_briefing([], today=date(2026, 4, 13), events=events)
    assert "TODAY'S SCHEDULE" not in text


def test_no_events_argument_is_backward_compatible():
    # Existing callers that don't pass events still work.
    text = generate_briefing([], today=date(2026, 4, 13))
    assert "TODAY'S SCHEDULE" not in text
```

- [ ] **Step 2: Run these three tests — expect fail on new signature**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
pytest tests/test_briefing.py -v
```

- [ ] **Step 3: Modify `backend/briefing.py`**

Update the imports and function signature, and insert the TODAY'S SCHEDULE block immediately after the date header (before OVERDUE). Replace the existing `generate_briefing` signature line and add the block:

Current signature line:
```python
def generate_briefing(tasks: list[Task], today: date) -> str:
```

Change to:
```python
def generate_briefing(tasks: list[Task], today: date, events: list["CalendarEvent"] | None = None) -> str:
```

Add this import near the top of the file (after the existing `from .tasks_store import Task`):

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .gcal import CalendarEvent
```

Then, immediately after the existing `lines.append(f"☀️ *{today.strftime('%A, %B %-d')}*\n")` line and **before** the `if overdue:` block, insert:

```python
    today_events = [e for e in (events or []) if e.start.date() == today]
    today_events.sort(key=lambda e: e.start)
    if today_events:
        lines.append("📅 *TODAY'S SCHEDULE*")
        for e in today_events:
            if e.all_day:
                lines.append(f"  • all-day — {e.summary}")
            else:
                local = e.start.astimezone()
                lines.append(f"  • {local.strftime('%-I:%M %p')} — {e.summary}")
        lines.append("")
```

- [ ] **Step 4: Run briefing tests — expect pass**

```bash
pytest tests/test_briefing.py -v
```

- [ ] **Step 5: Modify `backend/bot.py` to pass events into the briefing**

Locate `_send_briefing`. Replace its body so it fetches calendar events and threads them through:

Current:
```python
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
```

New:
```python
async def _send_briefing(app: Application, chat_id: str, miniapp_url: str) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    await app.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(miniapp_url),
    )
```

Do the same inside `cmd_briefing`:

Current:
```python
async def cmd_briefing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    text = generate_briefing(store.list(), today=date.today())
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )
```

New:
```python
async def cmd_briefing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    settings = load_settings()
    store = TasksStore(settings.tasks_path)
    from .gcal import fetch_events
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_open_dashboard_markup(settings.miniapp_url),
    )
```

- [ ] **Step 6: Also update `/api/briefing` in `backend/server.py`**

Current:
```python
@app.get("/api/briefing")
def get_briefing(_: TelegramUser = Depends(current_user)):
    text = generate_briefing(store.list(), today=date.today())
    return {"text": text}
```

New:
```python
@app.get("/api/briefing")
def get_briefing(_: TelegramUser = Depends(current_user)):
    events = fetch_events(date.today(), days=1)
    text = generate_briefing(store.list(), today=date.today(), events=events)
    return {"text": text}
```

(`fetch_events` was already imported in Task 6.)

- [ ] **Step 7: Full regression**

```bash
pytest -v
```

Expected: 35 total pass (32 + 3 new). The existing `test_briefing_endpoint_returns_text` still passes because `fetch_events` returns `[]` when there's no token cached in the test environment (test fixtures don't mock it, and the live token won't be used during pytest runs thanks to the graceful degradation).

*If `test_briefing_endpoint_returns_text` fails because the test environment happens to find a real token, add a fixture-level monkeypatch:*

```python
# in test_server.py `client` fixture, after monkeypatch.setenv calls:
monkeypatch.setattr("backend.server.fetch_events", lambda *a, **k: [])
```

Only add this if the test actually fails. Don't speculatively modify.

- [ ] **Step 8: Commit**

```bash
git add backend/briefing.py backend/bot.py backend/server.py tests/test_briefing.py
git commit -m "feat: integrate calendar events into briefing + bot handlers"
```

---

## Task 8: Frontend — fetch + render today's schedule

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/TodaySchedule.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Extend `frontend/src/types.ts`**

Append to the existing file:

```ts
export type CalendarEvent = {
  summary: string;
  start: string;  // ISO string with timezone
  end: string;
  all_day: boolean;
};
```

- [ ] **Step 2: Extend `frontend/src/api.ts`**

Add the import and the `calendar` method to the `api` object. The final file should look like:

```ts
import { initData } from "./telegram";
import type { Task, CalendarEvent } from "./types";

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
  calendar: () => request<{ events: CalendarEvent[] }>("/api/calendar"),
};
```

- [ ] **Step 3: Create `frontend/src/components/TodaySchedule.tsx`**

```tsx
import type { CalendarEvent } from "../types";

type Props = { events: CalendarEvent[] };

function isToday(iso: string): boolean {
  const d = new Date(iso);
  const now = new Date();
  return d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate();
}

function timeLabel(e: CalendarEvent): string {
  if (e.all_day) return "all-day";
  const d = new Date(e.start);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function TodaySchedule({ events }: Props) {
  const today = events.filter(e => isToday(e.start)).sort((a, b) => a.start.localeCompare(b.start));
  if (today.length === 0) return null;
  return (
    <div className="mb-4">
      <h2 className="text-[11px] text-neutral-400 font-semibold uppercase tracking-widest mb-2">📅 Today's Schedule</h2>
      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1 snap-x">
        {today.map((e, i) => (
          <div key={i} className="snap-start flex-shrink-0 rounded-lg px-3 py-2.5 min-w-[160px] bg-card border border-border">
            <div className="text-[10px] font-bold text-neutral-400">{timeLabel(e)}</div>
            <div className="text-[13px] font-semibold text-neutral-200 mt-1 truncate">{e.summary}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire `TodaySchedule` into `frontend/src/App.tsx`**

Modify imports at the top to add `CalendarEvent` and `TodaySchedule`:

```tsx
import type { Task, View, CalendarEvent } from "./types";
import { TodaySchedule } from "./components/TodaySchedule";
```

Add an events state and a parallel loader. Replace the top of the `App` function body so it reads:

```tsx
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [view, setView] = useState<View>("priority");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [{ tasks }, { events }] = await Promise.all([
        api.listTasks(),
        api.calendar().catch(() => ({ events: [] as CalendarEvent[] })),
      ]);
      setTasks(tasks);
      setEvents(events);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);
```

Then in the JSX, insert `<TodaySchedule events={events} />` between `<Header ... />` and `<AlertBanner ... />`. The JSX block should read:

```tsx
      <Header today={today} activeCount={active.length} weekCount={dueTodayOrSoon.length} />
      {error && <div className="mb-3 p-2 rounded bg-red-950 border border-red-800 text-xs text-red-300">{error}</div>}
      <TodaySchedule events={events} />
      <AlertBanner thisWeek={dueTodayOrSoon} />
```

- [ ] **Step 5: TypeScript check**

```bash
cd /Users/landonprojects/scheduler_bot/frontend
npx tsc -b --noEmit
```

Expected: no errors.

- [ ] **Step 6: Build**

```bash
npm run build
ls ../backend/static/assets/ | head
```

Expected: fresh `index-*.js` and `index-*.css`. No TS errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add frontend/src/types.ts frontend/src/api.ts frontend/src/components/TodaySchedule.tsx frontend/src/App.tsx
git commit -m "feat: miniapp today's schedule from /api/calendar"
```

---

## Task 9: Live end-to-end verification

No code changes — verify the full system.

- [ ] **Step 1: Restart the api + bot windows so they pick up new code**

The uvicorn dev server (`backend.server:app`) and the bot process both cache imported modules. Kill and restart:

```bash
tmux send-keys -t scheduler:api C-c
tmux send-keys -t scheduler:api "source venv/bin/activate && uvicorn backend.server:app --host 127.0.0.1 --port 8000" Enter
tmux send-keys -t scheduler:bot C-c
tmux send-keys -t scheduler:bot "source venv/bin/activate && python -m backend.bot bot" Enter
sleep 2
tmux capture-pane -t scheduler:api -p | tail -5
tmux capture-pane -t scheduler:bot -p | tail -5
```

Expected: uvicorn reports "Application startup complete"; bot reports "Application started".

- [ ] **Step 2: API spot-check from localhost**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
python -c "
from datetime import date
from backend.gcal import fetch_events
for e in fetch_events(date.today(), days=1):
    print(e.start.isoformat(), e.summary)
"
```

Expected: lists today's events (or prints nothing if the calendar is empty today). No stack trace.

- [ ] **Step 3: Test from Telegram**

On your phone:
1. Send `/briefing` to the bot. Verify the briefing now has a `📅 TODAY'S SCHEDULE` block (if you have events today).
2. Open the Mini App from the menu button. Verify the "Today's Schedule" horizontal card rail appears above the alert banner (or is hidden if you have no events today).

Do not mark this task complete if either check fails. Report what you see and we'll debug.

- [ ] **Step 4: Fire a scheduled `send` to confirm cron path**

```bash
cd /Users/landonprojects/scheduler_bot && source venv/bin/activate
python -m backend.bot send
```

Expected: Telegram message arrives with the schedule block.

---

## Task 10: Update CLAUDE.md with calendar status

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Open `CLAUDE.md` and update the Status section**

Current lines (in the Status section):
```
- ⏭️ **Next: Google Calendar integration** — `setup_google.py` OAuth helper + `/api/calendar` endpoint + briefing augmentation. Scope per `CLAUDE_CODE_DIRECTIONS.md` §3 and §4.
- ⏭️ Later: Claude-enhanced briefings (Anthropic API); extra bot commands (`/list`, `/done`, `/add`, `/undo`, `/week`, `/crunch`).
```

Replace with:
```
- ✅ Google Calendar integration live (`backend/gcal.py`, `/api/calendar`, briefing "TODAY'S SCHEDULE" block, Mini App schedule rail). Credentials at `~/.config/scheduler-bot/google_{creds,token}.json`. Fetch fails soft — returns `[]` on missing token.
- ⏭️ Later: Claude-enhanced briefings (Anthropic API); extra bot commands (`/list`, `/done`, `/add`, `/undo`, `/week`, `/crunch`).
```

Also add a gotcha line to the Gotchas section:
```
- **Google token refresh**: `Credentials.from_authorized_user_file` auto-refreshes expired tokens when `refresh_token` is present. If refresh fails (revoked, scope changed), `fetch_events` returns `[]` and logs a warning — rerun `scripts/setup_google.py` to re-auth.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: mark google calendar integration complete in CLAUDE.md"
```

---

## Self-Review

**Spec coverage (vs. `CLAUDE_CODE_DIRECTIONS.md` §3 Google setup and §4 calendar integration):**
- ✅ `setup_google.py` helper — Task 4
- ✅ Creds at a stable path (now `~/.config/scheduler-bot/`, intentional rename from `academic-bot`) — Tasks 3+4
- ✅ `flow.run_local_server(port=8080, bind_addr=...)` headless-friendly — Task 4
- ✅ Fetch primary calendar, next N days, return `[{summary, start, end}]` — Task 3 (extended with `all_day`)
- ✅ Graceful on missing creds / crash — Task 3 `fetch_events` catches all exceptions
- ✅ Briefing includes calendar events — Task 7
- ✅ Mini App shows today's schedule — Task 8
- ✅ `/api/calendar` endpoint — Task 6
- ⏭️ Deferred (not in this plan): Claude AI enhancement that weaves events into narrative suggestions — still covered by future Claude-enhanced-briefings plan.

**Type consistency:**
- `CalendarEvent` has identical field names (`summary`, `start`, `end`, `all_day`) across `backend/gcal.py`, `frontend/src/types.ts`, and `TodaySchedule.tsx`.
- `fetch_events(today, days=7)` signature used consistently in `backend/server.py`, `backend/bot.py`, and `tests/test_server.py` monkeypatch.
- `events_from_api_response` and `fetch_events_with_service` both return `list[CalendarEvent]`.
- Mini App calls `api.calendar()`, backend returns `{events: [...]}` — same shape on both sides.

**Placeholder scan:** None. Every step has concrete code or commands.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-13-google-calendar.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — I run each task in this session with checkpoints at the two human-pause tasks (Google Cloud Console setup + running `setup_google.py`).

Since the first pause is ~5 minutes of clicking in Google Cloud Console and the second requires you to open a URL from your laptop, **inline execution** probably suits this one better — less handoff overhead, tighter pause/resume around the credential steps. Tell me which you prefer.
