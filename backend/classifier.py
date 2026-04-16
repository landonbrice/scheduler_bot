"""Anthropic-backed classifier for captured thoughts.

Public API:
    classify(text, today, *, call=None) -> ClassifyResult

`call` is an optional dependency-injected callable used in tests. In
production it is None and the module builds a live Anthropic client
from the ANTHROPIC_API_KEY env var. If no API key is available or the
call fails for any reason, returns an ambiguous result with confidence
0.0 — callers then fall through to the inline-button flow.
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

log = logging.getLogger(__name__)

CATEGORIES = [
    "corpfin", "scs", "apes", "e4e",
    "baseball", "recruiting", "projects", "life",
]

TASK_TYPES = [
    "exam", "pset", "essay", "case", "project",
    "presentation", "reading", "ai-tutor", "admin",
]

_MODEL = "claude-haiku-4-5"

_TOOL_SCHEMA = {
    "name": "classify_thought",
    "description": "Classify a captured thought and optionally extract a task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["task", "thought", "resurface", "ambiguous"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "suggested_task": {
                "type": ["object", "null"],
                "properties": {
                    "category": {"type": "string", "enum": CATEGORIES},
                    "name": {"type": "string"},
                    "due": {"type": ["string", "null"], "description": "ISO YYYY-MM-DD or null"},
                    "type": {"type": "string", "enum": TASK_TYPES},
                    "weight": {"type": ["string", "null"]},
                },
                "required": ["category", "name", "type"],
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "confidence", "tags"],
    },
}

AnthropicCall = Callable[[str, str, dict], dict]


@dataclass(frozen=True)
class SuggestedTask:
    category: str
    name: str
    due: str | None
    type: str
    weight: str | None


@dataclass(frozen=True)
class ClassifyResult:
    kind: Literal["task", "thought", "resurface", "ambiguous"]
    confidence: float
    suggested_task: SuggestedTask | None
    tags: list[str]


_AMBIGUOUS = ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])


def _build_system_prompt(today: date) -> str:
    return (
        "You classify a single captured thought from a student. Use the "
        "classify_thought tool to return structured output.\n"
        f"Today is {today.isoformat()}. Resolve relative dates "
        "('Friday', 'next week') to absolute ISO dates.\n"
        f"Known categories: {', '.join(CATEGORIES)}.\n"
        f"Known task types: {', '.join(TASK_TYPES)}.\n"
        "Kinds:\n"
        "- 'task': an action the user needs to do, ideally with a deadline.\n"
        "- 'thought': an idea, observation, or half-formed note with no action.\n"
        "- 'resurface': something to bring back later ('remind me', 'look into').\n"
        "- 'ambiguous': unclear — the user should pick manually.\n"
        "Confidence is your self-estimate; use 0.75+ only when you are "
        "clearly correct. For a task, if you cannot extract a due date, "
        "set due to null."
    )


def _default_call(api_key: str) -> AnthropicCall:
    """Build a production caller that hits the real Anthropic API."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    def _call(system: str, user: str, tool_schema: dict) -> dict:
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": user}],
        )
        # Find the tool_use block and return its input.
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError("no tool_use block in Anthropic response")

    return _call


def classify(
    text: str,
    today: date,
    *,
    call: AnthropicCall | None = None,
) -> ClassifyResult:
    if call is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            log.info("ANTHROPIC_API_KEY unset; classifier disabled")
            return _AMBIGUOUS
        try:
            call = _default_call(api_key)
        except Exception:
            log.warning("failed to build Anthropic client", exc_info=True)
            return _AMBIGUOUS

    try:
        raw = call(_build_system_prompt(today), text, _TOOL_SCHEMA)
    except Exception:
        log.warning("classifier call failed", exc_info=True)
        return _AMBIGUOUS

    return _parse_result(raw)


def _parse_result(raw: dict) -> ClassifyResult:
    try:
        kind = raw["kind"]
        if kind not in ("task", "thought", "resurface", "ambiguous"):
            return _AMBIGUOUS
        confidence = float(raw.get("confidence", 0.0))
        tags = list(raw.get("tags") or [])
        st_raw = raw.get("suggested_task")
        if st_raw:
            suggested = SuggestedTask(
                category=str(st_raw.get("category", "life")),
                name=str(st_raw.get("name", "")),
                due=st_raw.get("due"),
                type=str(st_raw.get("type", "admin")),
                weight=st_raw.get("weight"),
            )
        else:
            suggested = None
        return ClassifyResult(kind=kind, confidence=confidence, suggested_task=suggested, tags=tags)
    except (KeyError, TypeError, ValueError):
        log.warning("malformed classifier output: %s", json.dumps(raw)[:200])
        return _AMBIGUOUS
