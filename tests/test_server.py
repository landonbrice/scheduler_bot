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


def test_tasks_endpoint_includes_priority_score_and_tier(client):
    resp = client.get("/api/tasks", headers={"X-Telegram-Init-Data": _init_data()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tasks"], "need at least one seeded task for this assertion"
    for t in body["tasks"]:
        assert "priority_score" in t
        assert "tier" in t
        assert t["tier"] in ("red", "amber", "neutral")
        assert 0.0 <= t["priority_score"] <= 300.0


def test_schedule_endpoint_requires_auth(client):
    resp = client.get("/api/schedule")
    assert resp.status_code == 401


def test_schedule_endpoint_returns_week(client):
    resp = client.get(
        "/api/schedule?start=2026-04-13",
        headers={"X-Telegram-Init-Data": _init_data()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["week_start"] == "2026-04-13"
    assert isinstance(body["instances"], list)


def test_schedule_endpoint_normalizes_start_to_monday(client):
    # Wed 2026-04-15 → Monday 2026-04-13
    resp = client.get(
        "/api/schedule?start=2026-04-15",
        headers={"X-Telegram-Init-Data": _init_data()},
    )
    assert resp.status_code == 200
    assert resp.json()["week_start"] == "2026-04-13"


def test_surfaced_requires_auth(client):
    resp = client.get("/api/notes/surfaced?start=2026-04-13")
    assert resp.status_code == 401


def test_search_requires_auth(client):
    resp = client.get("/api/notes/search?q=hi")
    assert resp.status_code == 401


def test_dismiss_requires_auth(client):
    resp = client.post("/api/capture/note/dismiss", json={"memory_id": "m1"})
    assert resp.status_code == 401


def test_dismiss_appends_entry(client, tmp_path, monkeypatch):
    from backend import server as srv
    p = tmp_path / "dismissed.jsonl"
    monkeypatch.setattr(srv, "_dismissed_path", p)
    resp = client.post(
        "/api/capture/note/dismiss",
        json={"memory_id": "m42"},
        headers={"X-Telegram-Init-Data": _init_data()},
    )
    assert resp.status_code == 200
    assert p.exists()
    assert "m42" in p.read_text()
