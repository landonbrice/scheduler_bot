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
        return datetime.fromisoformat(edge["dateTime"]), False
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
    except Exception as e:
        log.warning("calendar fetch failed: %s", e)
        return []
