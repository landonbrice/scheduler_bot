"""Priority scoring. Pure functions — no I/O, no clock dep beyond arg.

R2 formula:
    score = urgency(days_until_due)
            * impact(type | impact_override)
            * type_boost(type, days)
            * (priority_boost or 1.0)

Tier:
    red      score >= 80 OR priority_boost == 1.5 (urgent flag)
    amber    40 <= score < 80
    neutral  score < 40
"""
from __future__ import annotations
import math
from datetime import date, datetime
from typing import Literal

from .tasks_store import Task

IMPACT: dict[str, float] = {
    "exam": 0.95, "presentation": 0.90,
    "essay": 0.75, "project": 0.70,
    "pset": 0.50, "case": 0.50,
    "reading": 0.35,
    "recurring": 0.20, "admin": 0.15, "ai-tutor": 0.20,
}

OVERRIDE_MAP: dict[str, float] = {
    "critical": 0.95, "high": 0.75, "medium": 0.50, "low": 0.20,
}

Tier = Literal["red", "amber", "neutral"]


def _urgency(days: int) -> float:
    if days < 0:
        return 100.0
    return max(10.0, 100.0 * math.exp(-0.15 * days))


def _impact(task: Task) -> float:
    if task.impact_override and task.impact_override in OVERRIDE_MAP:
        return OVERRIDE_MAP[task.impact_override]
    return IMPACT.get(task.type, 0.30)


def _type_boost(task_type: str, days: int) -> float:
    if task_type in ("exam", "presentation") and days <= 7:
        return 1.5
    if task_type == "essay" and days <= 10:
        return 1.3
    if task_type == "project" and days <= 14:
        return 1.2
    return 1.0


def compute(task: Task, now: datetime) -> float:
    try:
        due = date.fromisoformat(task.due)
    except (ValueError, TypeError):
        return 0.0
    days = (due - now.date()).days
    return (
        _urgency(days)
        * _impact(task)
        * _type_boost(task.type, days)
        * (task.priority_boost or 1.0)
    )


def tier(score: float, urgent_flag: bool) -> Tier:
    if urgent_flag or score >= 80.0:
        return "red"
    if score >= 40.0:
        return "amber"
    return "neutral"
