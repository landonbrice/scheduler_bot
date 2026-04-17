"""HTTP wrappers for capture/flag/undo-create.

These tests import the `_init_data` helper and `client` fixture style from
test_server.py — there is no repo-wide `auth_headers` fixture.
"""
from __future__ import annotations
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
    tasks_file.write_text("[]")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TASKS_PATH", str(tasks_file))
    import importlib
    import backend.server as server_module
    importlib.reload(server_module)
    return TestClient(server_module.app)


def _auth():
    return {"X-Telegram-Init-Data": _init_data()}


def test_capture_note_requires_auth(client):
    r = client.post("/api/capture/note", json={"text": "hello"})
    assert r.status_code == 401


def test_capture_note_classifier_offline_returns_ambiguous(client, monkeypatch):
    from backend import server as srv
    from backend.classifier import ClassifyResult

    def fake(text, today, **_):
        return ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])

    monkeypatch.setattr(srv, "_server_classifier", fake)
    # store_memory returns False => memory_stored should be False (queued)
    async def fake_store(content, project=None):
        return False
    monkeypatch.setattr(srv, "_store_memory_fn", fake_store)

    r = client.post("/api/capture/note", json={"text": "something vague"}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["classification"] == "ambiguous"
    assert body["created_task_id"] is None
    assert body["undo_token"] is None


def test_capture_note_high_confidence_creates_task(client, monkeypatch):
    from backend import server as srv
    from backend.classifier import ClassifyResult, SuggestedTask

    def fake(text, today, **_):
        return ClassifyResult(
            kind="task",
            confidence=0.9,
            suggested_task=SuggestedTask(
                category="corpfin",
                name="Pset 5",
                due="2026-04-30",
                type="pset",
                weight="15%",
            ),
            tags=["corpfin"],
        )

    monkeypatch.setattr(srv, "_server_classifier", fake)
    async def fake_store(content, project=None):
        return True
    monkeypatch.setattr(srv, "_store_memory_fn", fake_store)

    r = client.post("/api/capture/note", json={"text": "pset 5 due thursday 15%"}, headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["classification"] == "task"
    assert body["created_task_id"] is not None
    assert body["undo_token"] is not None
    assert body["suggested_category"] == "corpfin"

    # Confirm persisted to tasks.json
    listed = client.get("/api/tasks", headers=_auth()).json()["tasks"]
    assert any(t["id"] == body["created_task_id"] for t in listed)


def test_undo_create_deletes_task(client, monkeypatch):
    from backend import server as srv
    from backend.classifier import ClassifyResult, SuggestedTask

    def fake(text, today, **_):
        return ClassifyResult(
            kind="task",
            confidence=0.9,
            suggested_task=SuggestedTask(
                category="life", name="buy milk", due="2026-04-20",
                type="admin", weight=None,
            ),
            tags=["life"],
        )
    monkeypatch.setattr(srv, "_server_classifier", fake)
    async def fake_store(content, project=None):
        return True
    monkeypatch.setattr(srv, "_store_memory_fn", fake_store)

    r = client.post("/api/capture/note", json={"text": "buy milk"}, headers=_auth())
    task_id = r.json()["created_task_id"]
    assert task_id is not None

    # Undo it
    r2 = client.post(f"/api/tasks/{task_id}/undo-create", headers=_auth())
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "deleted": task_id}

    # Gone from tasks
    listed = client.get("/api/tasks", headers=_auth()).json()["tasks"]
    assert not any(t["id"] == task_id for t in listed)

    # 404 on re-undo
    r3 = client.post(f"/api/tasks/{task_id}/undo-create", headers=_auth())
    assert r3.status_code == 404


def test_flag_toggles_priority_boost(client):
    h = _auth()
    body = {"course": "APES", "name": "Flag Test", "due": "2026-05-01", "type": "admin", "weight": ""}
    r = client.post("/api/tasks", json=body, headers=h)
    assert r.status_code == 201
    task_id = r.json()["task"]["id"]

    # First flag: priority_boost -> 1.5
    r1 = client.post(f"/api/tasks/{task_id}/flag", headers=h)
    assert r1.status_code == 200
    assert r1.json() == {"task_id": task_id, "priority_boost": 1.5}

    # Second flag: toggles back to None
    r2 = client.post(f"/api/tasks/{task_id}/flag", headers=h)
    assert r2.status_code == 200
    assert r2.json() == {"task_id": task_id, "priority_boost": None}

    # 404 on unknown task
    r3 = client.post("/api/tasks/nope/flag", headers=h)
    assert r3.status_code == 404
