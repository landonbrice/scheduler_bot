from datetime import date, datetime, timezone
from types import SimpleNamespace
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
