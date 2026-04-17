from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from backend.suggest import pick_task, RateLimiter
from backend.tasks_store import Task


def _task(tid: str, due: str, type_: str = "pset") -> Task:
    return Task(id=tid, course="corpfin", name=tid, due=due, type=type_,
                weight="", done=False, notes=None)


def test_ratelimiter_allows_under_limit():
    rl = RateLimiter(capacity=5, refill_per_minute=5)
    now = datetime(2026, 4, 16, 10, 0)
    for _ in range(5):
        assert rl.allow("u1", now) is True

def test_ratelimiter_trips_on_6th():
    rl = RateLimiter(capacity=5, refill_per_minute=5)
    now = datetime(2026, 4, 16, 10, 0)
    for _ in range(5):
        rl.allow("u1", now)
    assert rl.allow("u1", now) is False

def test_ratelimiter_refills_after_minute():
    rl = RateLimiter(capacity=5, refill_per_minute=5)
    t0 = datetime(2026, 4, 16, 10, 0)
    for _ in range(5):
        rl.allow("u1", t0)
    assert rl.allow("u1", t0) is False
    later = t0 + timedelta(minutes=1)
    assert rl.allow("u1", later) is True

def test_ratelimiter_isolates_users():
    rl = RateLimiter(capacity=2, refill_per_minute=2)
    now = datetime(2026, 4, 16, 10, 0)
    rl.allow("u1", now); rl.allow("u1", now)
    assert rl.allow("u2", now) is True


@pytest.mark.asyncio
async def test_pick_task_llm_success():
    async def fake_call(system, user):
        return {"picks": [
            {"task_id": "corpfin-pset-4", "reasoning": "due soon, fits 60m"},
            {"task_id": "apes-reading", "reasoning": "quick read"},
        ]}
    tasks = [_task("corpfin-pset-4", "2026-04-17"), _task("apes-reading", "2026-04-19", "reading")]
    r = await pick_task(tasks=tasks, duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                        now=datetime(2026, 4, 16, 10, 0), call=fake_call)
    assert r["source"] == "llm"
    assert r["picked"]["task_id"] == "corpfin-pset-4"
    assert len(r["alternatives"]) >= 0


@pytest.mark.asyncio
async def test_pick_task_llm_error_falls_back():
    async def fake_call(system, user):
        raise RuntimeError("boom")
    tasks = [_task("corpfin-pset-4", "2026-04-17"), _task("apes-reading", "2026-04-19", "reading")]
    r = await pick_task(tasks=tasks, duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                        now=datetime(2026, 4, 16, 10, 0), call=fake_call)
    assert r["source"] == "fallback"
    assert r["picked"] is not None


@pytest.mark.asyncio
async def test_pick_task_no_tasks_returns_empty():
    async def fake_call(system, user):
        return {"picks": []}
    r = await pick_task(tasks=[], duration_min=60, start_iso="2026-04-17T10:00:00-05:00",
                        now=datetime(2026, 4, 16, 10, 0), call=fake_call)
    assert r["picked"] is None
