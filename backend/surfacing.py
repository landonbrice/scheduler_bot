"""Thought surfacing — hybrid tag+semantic scoring for week view chips.

Public:
    surface_week(dates, tasks_by_day, events_by_day, resurface_by_day,
                 dismissed_path, memory_search, now) -> dict[date, list[chip]]

Internal helpers:
    build_day_tags, score_memory, load_dismissed.

memory_search is injected (Callable) so tests can stub it without touching
backend.memory. Single Membase call per week (the weeks' concatenated
context text).
"""
from __future__ import annotations
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

MemorySearch = Callable[[str, int], Awaitable[list[dict]]]

_CAP_PER_DAY = 3
_RECENCY_FLOOR = 0.1
_RECENCY_LAMBDA = 0.10
_DISMISS_HARD_DAYS = 7
_DISMISS_SOFT_DAYS = 14


def build_day_tags(tasks: list[dict], events: list[dict], resurface_tags: list[str]) -> set[str]:
    tags: set[str] = set()
    for t in tasks:
        v = t.get("course") or t.get("category")
        if v:
            tags.add(str(v).lower())
    for e in events:
        v = e.get("category")
        if v:
            tags.add(str(v).lower())
    for rt in resurface_tags:
        tags.add(str(rt).lower())
    return tags


def load_dismissed(path: Path) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    try:
        lines = Path(path).read_text().strip().splitlines()
    except FileNotFoundError:
        return {}
    except OSError:
        log.warning("dismissed.jsonl read failed", exc_info=True)
        return {}
    for line in lines:
        try:
            row = json.loads(line)
            mid = str(row["memory_id"])
            ts = datetime.fromisoformat(str(row["dismissed_at"]))
            # latest wins
            if mid not in result or ts > result[mid]:
                result[mid] = ts
        except (ValueError, KeyError, TypeError):
            continue
    return result


def _memory_tags(memory: dict) -> set[str]:
    raw = memory.get("tags") or []
    return {str(t).lower() for t in raw}


def _memory_age_days(memory: dict, now: datetime) -> float:
    ts = memory.get("timestamp") or memory.get("created_at")
    if not ts:
        return 0.0
    try:
        when = datetime.fromisoformat(str(ts))
    except ValueError:
        return 0.0
    delta = now - when
    return max(delta.total_seconds() / 86400.0, 0.0)


def score_memory(memory: dict, *, day_tags: set[str], dismissed: dict[str, datetime], now: datetime) -> float:
    tag_overlap = len(_memory_tags(memory) & day_tags)
    if tag_overlap == 0:
        return 0.0
    recency = max(_RECENCY_FLOOR, math.exp(-_RECENCY_LAMBDA * _memory_age_days(memory, now)))
    base = tag_overlap * recency

    mid = memory.get("id") or memory.get("memory_id")
    if mid and mid in dismissed:
        delta_days = (now - dismissed[mid]).total_seconds() / 86400.0
        if delta_days < _DISMISS_HARD_DAYS:
            return 0.0
        if delta_days < _DISMISS_SOFT_DAYS:
            base *= 0.5
    return base


def _context_text(tasks: list[dict], events: list[dict]) -> str:
    chunks = []
    for t in tasks:
        chunks.append(str(t.get("name") or ""))
    for e in events:
        chunks.append(str(e.get("title") or e.get("summary") or ""))
    return " ".join(c for c in chunks if c)


async def surface_week(
    *,
    dates: list[date],
    tasks_by_day: dict[date, list[dict]],
    events_by_day: dict[date, list[dict]],
    resurface_by_day: dict[date, list[dict]],
    dismissed_path: Path,
    memory_search: MemorySearch,
    now: datetime,
) -> dict[date, list[dict]]:
    """Return {date: [chip dict, ...]} for each date in `dates`."""
    dismissed = load_dismissed(dismissed_path)

    # Single Membase call with the union of all week context text.
    combined = " ".join(_context_text(tasks_by_day.get(d, []), events_by_day.get(d, [])) for d in dates)
    query = combined[:2000].strip() or " "
    try:
        candidates = await memory_search(query, 40)
    except Exception:
        log.warning("memory_search failed in surface_week", exc_info=True)
        candidates = []

    out: dict[date, list[dict]] = {}
    for d in dates:
        tasks = tasks_by_day.get(d, [])
        events = events_by_day.get(d, [])
        resurface_items = resurface_by_day.get(d, [])
        resurface_tags: list[str] = []
        for r in resurface_items:
            resurface_tags.extend(r.get("tags") or [])
        day_tags = build_day_tags(tasks, events, resurface_tags)

        scored = sorted(
            ((score_memory(m, day_tags=day_tags, dismissed=dismissed, now=now), m) for m in candidates),
            key=lambda p: p[0], reverse=True,
        )
        thought_chips: list[dict] = []
        for s, m in scored:
            if s <= 0.0 or len(thought_chips) >= _CAP_PER_DAY:
                break
            thought_chips.append({
                "kind": "thought",
                "memory_id": m.get("id") or m.get("memory_id"),
                "text": m.get("text") or m.get("content") or "",
                "tags": m.get("tags") or [],
                "score": round(s, 3),
            })

        resurface_chips = [
            {"kind": "resurface", "text": r.get("text") or "", "trigger_date": d.isoformat(),
             "tags": r.get("tags") or []}
            for r in resurface_items
        ]
        out[d] = resurface_chips + thought_chips
    return out
