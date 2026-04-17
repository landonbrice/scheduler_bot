"""data/schedule.json loader + weekly instance expansion.

`action: cancel` is the only supported exception in R2.
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class ScheduleException:
    exc_date: date
    action: str  # "cancel" only in R2


@dataclass(frozen=True)
class ScheduleClass:
    title: str
    category: str
    days: tuple[str, ...]
    start: str  # "HH:MM"
    end: str
    location: str
    exceptions: tuple[ScheduleException, ...] = ()


@dataclass(frozen=True)
class Schedule:
    term_start: date | None
    term_end: date | None
    classes: tuple[ScheduleClass, ...]


@dataclass(frozen=True)
class ClassInstance:
    title: str
    category: str
    instance_date: date
    start: str
    end: str
    location: str


def load_schedule(path: Path) -> Schedule:
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError:
        log.info("schedule.json missing at %s; returning empty schedule", path)
        return Schedule(term_start=None, term_end=None, classes=())
    except (OSError, json.JSONDecodeError):
        log.warning("schedule.json load failed at %s", path, exc_info=True)
        return Schedule(term_start=None, term_end=None, classes=())

    term = raw.get("term") or {}
    classes: list[ScheduleClass] = []
    for c in raw.get("classes") or []:
        exc = tuple(
            ScheduleException(
                exc_date=date.fromisoformat(e["date"]),
                action=str(e.get("action", "cancel")),
            )
            for e in (c.get("exceptions") or [])
        )
        classes.append(ScheduleClass(
            title=str(c["title"]),
            category=str(c["category"]),
            days=tuple(c.get("days") or []),
            start=str(c["start"]),
            end=str(c["end"]),
            location=str(c.get("location", "")),
            exceptions=exc,
        ))
    return Schedule(
        term_start=date.fromisoformat(term["start"]) if term.get("start") else None,
        term_end=date.fromisoformat(term["end"]) if term.get("end") else None,
        classes=tuple(classes),
    )


def week_instances(sched: Schedule, *, week_start: date) -> list[ClassInstance]:
    """Expand every class's days into concrete date instances for the week
    starting on `week_start` (expected to be a Monday). Applies cancel
    exceptions. Filters strictly by term bounds."""
    if sched.term_start and week_start > sched.term_end:
        return []
    if sched.term_end and (week_start + timedelta(days=6)) < sched.term_start:
        return []

    out: list[ClassInstance] = []
    for cls in sched.classes:
        cancel_dates = {e.exc_date for e in cls.exceptions if e.action == "cancel"}
        for day_name in cls.days:
            try:
                offset = _DAY_NAMES.index(day_name)
            except ValueError:
                continue
            inst_date = week_start + timedelta(days=offset)
            if sched.term_start and inst_date < sched.term_start:
                continue
            if sched.term_end and inst_date > sched.term_end:
                continue
            if inst_date in cancel_dates:
                continue
            out.append(ClassInstance(
                title=cls.title, category=cls.category,
                instance_date=inst_date, start=cls.start, end=cls.end,
                location=cls.location,
            ))
    return out
