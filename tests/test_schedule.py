from __future__ import annotations
import json
from datetime import date
from pathlib import Path
import pytest
from backend.schedule import load_schedule, week_instances, ScheduleClass


@pytest.fixture
def schedule_path(tmp_path: Path) -> Path:
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps({
        "term": {"start": "2026-03-30", "end": "2026-06-05"},
        "classes": [
            {"title": "SCS III", "category": "SCS III",
             "days": ["Mon", "Wed"], "start": "15:00", "end": "16:20",
             "location": "Wieboldt 310C",
             "exceptions": [{"date": "2026-04-20", "action": "cancel"}]},
            {"title": "APES", "category": "APES",
             "days": ["Tue", "Thu"], "start": "09:30", "end": "10:50",
             "location": "Ryerson 251", "exceptions": []},
        ],
    }))
    return p


def test_load_schedule_parses_classes(schedule_path):
    sched = load_schedule(schedule_path)
    assert sched.term_start == date(2026, 3, 30)
    assert sched.term_end == date(2026, 6, 5)
    assert len(sched.classes) == 2
    assert sched.classes[0].title == "SCS III"


def test_week_instances_generates_mon_through_sun(schedule_path):
    sched = load_schedule(schedule_path)
    # Week of Monday 2026-04-13 (Mon) – Sunday 2026-04-19.
    instances = week_instances(sched, week_start=date(2026, 4, 13))
    assert len(instances) == 4  # 2 SCS + 2 APES
    dates = {i.instance_date for i in instances}
    assert dates == {date(2026, 4, 13), date(2026, 4, 14), date(2026, 4, 15), date(2026, 4, 16)}


def test_week_instances_applies_cancel_exception(schedule_path):
    sched = load_schedule(schedule_path)
    # 2026-04-20 is a Monday in term with a cancel exception on SCS III.
    instances = week_instances(sched, week_start=date(2026, 4, 20))
    scs_instances = [i for i in instances if i.title == "SCS III"]
    # Only Wed 2026-04-22 should remain.
    assert len(scs_instances) == 1
    assert scs_instances[0].instance_date == date(2026, 4, 22)


def test_week_instances_outside_term_returns_empty(schedule_path):
    sched = load_schedule(schedule_path)
    # Week of 2026-06-22 — past term_end.
    instances = week_instances(sched, week_start=date(2026, 6, 22))
    assert instances == []


def test_load_schedule_missing_file_returns_empty():
    sched = load_schedule(Path("/nonexistent/schedule.json"))
    assert sched.classes == ()
    assert sched.term_start is None


def test_load_schedule_drops_unsupported_exception_action(tmp_path, caplog):
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps({
        "term": {"start": "2026-03-30", "end": "2026-06-05"},
        "classes": [{
            "title": "SCS III", "category": "SCS III",
            "days": ["Mon"], "start": "15:00", "end": "16:20",
            "location": "x",
            "exceptions": [
                {"date": "2026-04-20", "action": "cancel"},
                {"date": "2026-04-27", "action": "reschedule"},
            ],
        }],
    }))
    import logging
    with caplog.at_level(logging.WARNING, logger="backend.schedule"):
        sched = load_schedule(p)
    cls = sched.classes[0]
    assert len(cls.exceptions) == 1
    assert cls.exceptions[0].action == "cancel"
    assert any("reschedule" in rec.message for rec in caplog.records)


def test_week_instances_skips_unknown_day_name(tmp_path):
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps({
        "term": {"start": "2026-03-30", "end": "2026-06-05"},
        "classes": [{
            "title": "Ghost", "category": "x",
            "days": ["Xyz", "Mon"], "start": "09:00", "end": "10:00",
            "location": "x", "exceptions": [],
        }],
    }))
    sched = load_schedule(p)
    instances = week_instances(sched, week_start=date(2026, 4, 13))
    assert len(instances) == 1
    assert instances[0].instance_date == date(2026, 4, 13)


def test_week_instances_when_only_term_start_set(tmp_path):
    # Regression for the None-compare bug in term-bound prune.
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps({
        "term": {"start": "2026-03-30"},
        "classes": [{
            "title": "Any", "category": "x",
            "days": ["Mon"], "start": "09:00", "end": "10:00",
            "location": "x", "exceptions": [],
        }],
    }))
    sched = load_schedule(p)
    assert sched.term_end is None
    # Should NOT raise TypeError.
    instances = week_instances(sched, week_start=date(2026, 4, 13))
    assert len(instances) == 1


def test_week_instances_when_only_term_end_set(tmp_path):
    p = tmp_path / "schedule.json"
    p.write_text(json.dumps({
        "term": {"end": "2026-06-05"},
        "classes": [{
            "title": "Any", "category": "x",
            "days": ["Mon"], "start": "09:00", "end": "10:00",
            "location": "x", "exceptions": [],
        }],
    }))
    sched = load_schedule(p)
    assert sched.term_start is None
    instances = week_instances(sched, week_start=date(2026, 4, 13))
    assert len(instances) == 1
