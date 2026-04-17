from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
from backend.surfacing import score_memory, build_day_tags, load_dismissed, surface_week


NOW = datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc)


def _mem(mid: str, text: str, tags: list[str], age_days: int) -> dict:
    return {
        "id": mid, "text": text, "tags": tags,
        "timestamp": (NOW - timedelta(days=age_days)).isoformat(),
    }


def test_score_drops_untagged_memories():
    mem = _mem("m1", "old note", tags=["apes"], age_days=1)
    assert score_memory(mem, day_tags={"corpfin"}, dismissed={}, now=NOW) == 0.0


def test_score_recency_floor():
    mem_old = _mem("m1", "very old", tags=["apes"], age_days=120)
    mem_new = _mem("m2", "yesterday", tags=["apes"], age_days=1)
    s_old = score_memory(mem_old, day_tags={"apes"}, dismissed={}, now=NOW)
    s_new = score_memory(mem_new, day_tags={"apes"}, dismissed={}, now=NOW)
    assert s_old > 0.0  # floor active
    assert s_new > s_old


def test_dismiss_penalty_within_7_days():
    mem = _mem("m1", "t", tags=["apes"], age_days=1)
    dismissed = {"m1": NOW - timedelta(days=3)}
    assert score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW) == 0.0


def test_dismiss_penalty_7_to_14_days():
    mem = _mem("m1", "t", tags=["apes"], age_days=1)
    base = score_memory(mem, day_tags={"apes"}, dismissed={}, now=NOW)
    dismissed = {"m1": NOW - timedelta(days=10)}
    dampened = score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW)
    assert dampened == pytest.approx(base * 0.5, rel=0.01)


def test_dismiss_penalty_beyond_14_days():
    mem = _mem("m1", "t", tags=["apes"], age_days=1)
    base = score_memory(mem, day_tags={"apes"}, dismissed={}, now=NOW)
    dismissed = {"m1": NOW - timedelta(days=30)}
    full = score_memory(mem, day_tags={"apes"}, dismissed=dismissed, now=NOW)
    assert full == pytest.approx(base, rel=0.001)


def test_build_day_tags_union():
    tasks = [{"course": "corpfin"}, {"course": "APES"}]
    events = [{"category": "SCS III"}]
    tags = build_day_tags(tasks, events, resurface_tags=["baseball"])
    assert "corpfin" in tags and "apes" in tags and "scs iii" in tags and "baseball" in tags


def test_load_dismissed_reads_jsonl(tmp_path):
    p = tmp_path / "dismissed.jsonl"
    p.write_text(
        json.dumps({"memory_id": "m1", "dismissed_at": "2026-04-10T00:00:00+00:00"}) + "\n"
        + json.dumps({"memory_id": "m2", "dismissed_at": "2026-04-12T00:00:00+00:00"}) + "\n"
    )
    d = load_dismissed(p)
    assert set(d.keys()) == {"m1", "m2"}


def test_load_dismissed_missing_file_returns_empty(tmp_path):
    assert load_dismissed(tmp_path / "nope.jsonl") == {}


@pytest.mark.asyncio
async def test_surface_week_caps_3_thoughts_per_day(tmp_path):
    memories = [_mem(f"m{i}", f"note {i}", tags=["apes"], age_days=i) for i in range(10)]
    async def fake_search(query, limit):
        return memories
    tasks_by_day = {date(2026, 4, 16): [{"course": "apes"}]}
    events_by_day = {date(2026, 4, 16): []}
    chips = await surface_week(
        dates=[date(2026, 4, 16)],
        tasks_by_day=tasks_by_day,
        events_by_day=events_by_day,
        resurface_by_day={},
        dismissed_path=tmp_path / "dismissed.jsonl",
        memory_search=fake_search,
        now=NOW,
    )
    assert len(chips[date(2026, 4, 16)]) == 3
