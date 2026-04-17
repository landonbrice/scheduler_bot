from __future__ import annotations
from datetime import datetime, date
import math
import pytest
from backend.priority import compute, tier
from backend.tasks_store import Task


def _task(**kw) -> Task:
    defaults = dict(
        id="t1", course="corpfin", name="thing",
        due="2026-04-20", type="pset", weight="",
        done=False, notes=None,
    )
    defaults.update(kw)
    return Task(**defaults)


NOW = datetime(2026, 4, 16, 10, 0, 0)


def test_urgency_overdue():
    t = _task(due="2026-04-10")  # 6 days overdue
    score = compute(t, NOW)
    assert score >= 10.0  # clamp floor

def test_urgency_today():
    t = _task(due="2026-04-16", type="pset")
    s = compute(t, NOW)
    # urgency=100, impact=0.5, type_boost=1.0, priority_boost=1.0 → 50
    assert s == pytest.approx(50.0, rel=0.01)

def test_urgency_curve_3_days():
    t = _task(due="2026-04-19", type="pset")
    s = compute(t, NOW)
    # urgency ≈ 100 * e^(-0.45) ≈ 63.76; * 0.5 = ~31.88
    assert 30.0 <= s <= 34.0

def test_impact_override_wins():
    t = _task(type="pset", impact_override="critical")
    s = compute(t, NOW)  # critical=0.95 instead of pset=0.5
    assert s > compute(_task(type="pset"), NOW)

def test_type_boost_exam_within_7_days():
    t = _task(due="2026-04-20", type="exam")  # 4 days out
    s = compute(t, NOW)
    # 100*e^(-0.6) ≈ 54.88, *0.95 impact, *1.5 boost ≈ 78.2
    assert 70.0 <= s <= 85.0

def test_type_boost_exam_outside_window():
    t = _task(due="2026-05-10", type="exam")  # 24 days → no boost
    s = compute(t, NOW)
    # urgency floor ≈ 10, impact 0.95 → 9.5
    assert s < 15.0

def test_priority_boost_flag():
    base = compute(_task(type="pset"), NOW)
    boosted = compute(_task(type="pset", priority_boost=1.5), NOW)
    assert boosted == pytest.approx(base * 1.5, rel=0.001)

def test_tier_red_by_score():
    assert tier(85.0, urgent_flag=False) == "red"

def test_tier_red_by_flag_even_if_low_score():
    assert tier(20.0, urgent_flag=True) == "red"

def test_tier_amber():
    assert tier(55.0, urgent_flag=False) == "amber"

def test_tier_neutral():
    assert tier(15.0, urgent_flag=False) == "neutral"
