from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from .tasks_store import Task

if TYPE_CHECKING:
    from .gcal import CalendarEvent


def _parse_due(t: Task) -> date:
    return datetime.strptime(t.due, "%Y-%m-%d").date()


def _fmt(d: date) -> str:
    return d.strftime("%a %b %-d")


def generate_briefing(
    tasks: list[Task],
    today: date,
    events: list["CalendarEvent"] | None = None,
    resurface_path: Path | None = None,
) -> str:
    active = [t for t in tasks if not t.done]
    # "This week" = through the upcoming Friday of the current work week.
    # "Next week" = after that, through the following Friday (+7 days).
    days_to_friday = (4 - today.weekday()) % 7
    if days_to_friday == 0 and today.weekday() != 4:
        days_to_friday = 7
    this_week_end = today.toordinal() + days_to_friday
    next_week_end = this_week_end + 7

    overdue = [t for t in active if _parse_due(t) < today]
    due_today = [t for t in active if _parse_due(t) == today]
    week = [
        t for t in active
        if today < _parse_due(t) and _parse_due(t).toordinal() <= this_week_end
    ]
    next_week = [
        t for t in active
        if this_week_end < _parse_due(t).toordinal() <= next_week_end
    ]

    lines: list[str] = []
    lines.append(f"☀️ *{today.strftime('%A, %B %-d')}*\n")

    today_events = [e for e in (events or []) if e.start.date() == today]
    today_events.sort(key=lambda e: e.start)
    if today_events:
        lines.append("📅 *TODAY'S SCHEDULE*")
        for e in today_events:
            if e.all_day:
                lines.append(f"  • all-day — {e.summary}")
            else:
                local = e.start.astimezone()
                lines.append(f"  • {local.strftime('%-I:%M %p')} — {e.summary}")
        lines.append("")

    if overdue:
        lines.append("🔴 *OVERDUE*")
        for t in sorted(overdue, key=_parse_due):
            days_late = (today - _parse_due(t)).days
            lines.append(f"  ⚠️ {t.course}: {t.name} ({days_late}d late)")
        lines.append("")

    if due_today:
        lines.append("🟡 *DUE TODAY*")
        for t in due_today:
            lines.append(f"  → {t.course}: {t.name}")
        lines.append("")

    if week:
        lines.append("📋 *THIS WEEK* (by urgency)")
        for t in sorted(week, key=_parse_due):
            d = _parse_due(t)
            delta = (d - today).days
            lines.append(f"  · {t.course}: {t.name} — {_fmt(d)} ({delta}d)")
        lines.append("")

    if next_week:
        lines.append("🔮 *NEXT WEEK*")
        for t in sorted(next_week, key=_parse_due):
            lines.append(f"  ◆ {t.course}: {t.name} — {_fmt(_parse_due(t))}")
        lines.append("")

    # Crunch: any date (within next 21d) with 2+ exams or 3+ total items
    by_date: dict[date, list[Task]] = defaultdict(list)
    for t in active:
        d = _parse_due(t)
        if 0 <= (d - today).days <= 21:
            by_date[d].append(t)
    crunch = []
    for d, ts in sorted(by_date.items()):
        exams = [t for t in ts if t.type == "exam"]
        if len(exams) >= 2 or len(ts) >= 3:
            crunch.append((d, ts))
    if crunch:
        lines.append("⚡ *CRUNCH ALERT*")
        for d, ts in crunch:
            kinds = ", ".join(f"{t.course} {t.type}" for t in ts)
            lines.append(f"  {_fmt(d)}: {kinds}")
        lines.append("")

    # Resurface items from /return whose trigger_date <= today
    if resurface_path is not None and resurface_path.exists():
        import json
        due_resurface: list[str] = []
        for line in resurface_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            trig = entry.get("trigger_date")
            if trig and trig <= today.isoformat():
                due_resurface.append(entry.get("text", ""))
        if due_resurface:
            lines.append("🔁 *RESURFACING*")
            for t in due_resurface:
                lines.append(f"  · {t}")
            lines.append("")

    lines.append(f"Active: {len(active)} tasks | This week: {len(week) + len(due_today)}")
    return "\n".join(lines)
