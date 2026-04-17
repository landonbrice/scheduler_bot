"""DeepSeek-backed empty-slot suggester + rate limiter + fallback.

Public:
    pick_task(tasks, duration_min, start_iso, now, *, call=None) -> dict
    RateLimiter(capacity, refill_per_minute)

call is DI'd — same pattern as classifier. In production, the caller
builds the OpenAI-SDK-on-DeepSeek client exactly once and passes it in.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from .priority import compute as _prio_compute
from .tasks_store import Task

log = logging.getLogger(__name__)

_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"

LLMCall = Callable[[str, str], Awaitable[dict]]


@dataclass
class _Bucket:
    tokens: float
    last_refill: datetime


class RateLimiter:
    """Simple per-user token bucket. Not thread-safe; adequate for single-process FastAPI."""

    def __init__(self, *, capacity: int, refill_per_minute: int):
        self.capacity = capacity
        self.refill_rate = refill_per_minute / 60.0  # tokens per second
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str, now: datetime) -> bool:
        b = self._buckets.get(key)
        if b is None:
            self._buckets[key] = _Bucket(tokens=self.capacity - 1, last_refill=now)
            return True
        elapsed = (now - b.last_refill).total_seconds()
        b.tokens = min(self.capacity, b.tokens + elapsed * self.refill_rate)
        b.last_refill = now
        if b.tokens < 1.0:
            return False
        b.tokens -= 1.0
        return True


def _fallback(tasks: list[Task], duration_min: int, now: datetime) -> dict:
    active = [t for t in tasks if not t.done]
    scored = sorted(((_prio_compute(t, now), t) for t in active), key=lambda p: p[0], reverse=True)
    top = [t for _, t in scored[:3]]
    if not top:
        return {"picked": None, "alternatives": [], "source": "fallback"}
    return {
        "picked": {"task_id": top[0].id, "reasoning": ""},
        "alternatives": [{"task_id": t.id, "reasoning": ""} for t in top[1:]],
        "source": "fallback",
    }


def _build_prompt(tasks: list[Task], duration_min: int, start_iso: str, now: datetime) -> tuple[str, str]:
    scored = sorted(((_prio_compute(t, now), t) for t in tasks if not t.done),
                    key=lambda p: p[0], reverse=True)[:10]
    menu = [
        {"task_id": t.id, "name": t.name, "course": t.course, "type": t.type,
         "due": t.due, "priority": round(s, 1)}
        for s, t in scored
    ]
    system = (
        "You pick the best task for an empty time slot. Respond with strict JSON:\n"
        '{"picks": [{"task_id": "<id>", "reasoning": "<one short sentence>"}, ...]}\n'
        "Rank in descending order of fit. Use at most 5 picks."
    )
    user = (
        f"Duration: {duration_min} minutes.\n"
        f"Start: {start_iso}.\n"
        f"Candidate tasks (ranked by priority):\n{json.dumps(menu, indent=2)}\n"
        "Return the top 3 picks that best fit this slot."
    )
    return system, user


async def pick_task(
    *,
    tasks: list[Task], duration_min: int, start_iso: str, now: datetime,
    call: LLMCall | None = None,
) -> dict:
    active = [t for t in tasks if not t.done]
    if not active:
        return {"picked": None, "alternatives": [], "source": "fallback"}

    if call is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return _fallback(active, duration_min, now)
        try:
            call = _default_call(api_key)
        except Exception:
            log.warning("failed to build DeepSeek client for suggest", exc_info=True)
            return _fallback(active, duration_min, now)

    system, user = _build_prompt(active, duration_min, start_iso, now)
    try:
        raw = await call(system, user)
    except Exception:
        log.warning("suggest LLM call failed", exc_info=True)
        return _fallback(active, duration_min, now)

    picks = raw.get("picks") or []
    task_ids = {t.id for t in active}
    picks = [p for p in picks if p.get("task_id") in task_ids]
    if not picks:
        return _fallback(active, duration_min, now)
    return {
        "picked": picks[0],
        "alternatives": picks[1:4],
        "source": "llm",
    }


def _default_call(api_key: str) -> LLMCall:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=_BASE_URL)

    async def _call(system: str, user: str) -> dict:
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=512, temperature=0.3,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    return _call
