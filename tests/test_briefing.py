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
    assert "Final" not in text.split("NEXT WEEK")[-1]


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


def test_today_schedule_block_renders_events_before_overdue():
    from datetime import datetime, timezone
    from backend.gcal import CalendarEvent
    tasks = [_t("old", "APES", "Old thing", "2026-04-10")]
    events = [
        CalendarEvent(summary="APES Lecture",
                      start=datetime(2026, 4, 13, 9, 30, tzinfo=timezone.utc),
                      end=datetime(2026, 4, 13, 10, 10, tzinfo=timezone.utc), all_day=False),
        CalendarEvent(summary="SCS III",
                      start=datetime(2026, 4, 13, 15, 0, tzinfo=timezone.utc),
                      end=datetime(2026, 4, 13, 16, 20, tzinfo=timezone.utc), all_day=False),
    ]
    text = generate_briefing(tasks, today=date(2026, 4, 13), events=events)
    assert "TODAY'S SCHEDULE" in text
    assert "APES Lecture" in text
    assert "SCS III" in text
    assert text.index("TODAY'S SCHEDULE") < text.index("OVERDUE")


def test_events_from_other_days_excluded():
    from datetime import datetime, timezone
    from backend.gcal import CalendarEvent
    events = [CalendarEvent(summary="Tomorrow meeting",
                            start=datetime(2026, 4, 14, 9, 0, tzinfo=timezone.utc),
                            end=datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc), all_day=False)]
    text = generate_briefing([], today=date(2026, 4, 13), events=events)
    assert "TODAY'S SCHEDULE" not in text


def test_no_events_argument_is_backward_compatible():
    text = generate_briefing([], today=date(2026, 4, 13))
    assert "TODAY'S SCHEDULE" not in text


def test_resurfacing_block_surfaces_due_items(tmp_path):
    import json
    p = tmp_path / "resurface.jsonl"
    p.write_text(
        json.dumps({"text": "read econ paper", "trigger_date": "2026-04-13", "trigger_raw": None, "created_at": "x"}) + "\n"
        + json.dumps({"text": "future thing", "trigger_date": "2026-05-01", "trigger_raw": None, "created_at": "x"}) + "\n"
    )
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" in text
    assert "read econ paper" in text
    assert "future thing" not in text


def test_resurfacing_block_absent_when_no_items(tmp_path):
    p = tmp_path / "resurface.jsonl"
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" not in text


def test_resurfacing_unparseable_trigger_never_surfaces(tmp_path):
    import json
    p = tmp_path / "resurface.jsonl"
    p.write_text(
        json.dumps({"text": "maybe revisit", "trigger_date": None, "trigger_raw": "sometime", "created_at": "x"}) + "\n"
    )
    text = generate_briefing([], today=date(2026, 4, 13), resurface_path=p)
    assert "RESURFACING" not in text
