"""DeepSeek-backed classifier for captured thoughts.

Public API:
    classify(text, today, *, call=None) -> ClassifyResult

`call` is an optional dependency-injected callable used in tests. In
production it is None and the module builds a live OpenAI client
pointed at DeepSeek from the DEEPSEEK_API_KEY env var. If no API key is
available or the call fails for any reason, returns an ambiguous result
with confidence 0.0 — callers then fall through to the inline-button
flow.

DeepSeek's API is OpenAI-compatible. We use JSON mode
(response_format={"type": "json_object"}) with the schema described in
the system prompt; this is more reliable than function-calling with
DeepSeek's current models.
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

_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"

# The DI callable's signature: (system_prompt, user_text) -> parsed_dict.
# The real implementation wraps an OpenAI-SDK JSON-mode call; tests inject fakes.
LLMCall = Callable[[str, str], dict]


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
        "You classify a single captured thought from a student and respond with a "
        "single JSON object (no prose, no markdown fences).\n"
        f"Today is {today.isoformat()}. Resolve relative dates ('Friday', 'next week') "
        "to absolute ISO dates (YYYY-MM-DD).\n"
        "\n"
        "Output schema (keys must match exactly):\n"
        "{\n"
        '  "kind": "task" | "thought" | "resurface" | "ambiguous",\n'
        '  "confidence": <number in [0,1]>,\n'
        '  "suggested_task": null | {\n'
        '    "category": <one of the known categories>,\n'
        '    "name": <short task name>,\n'
        '    "due": <ISO YYYY-MM-DD or null>,\n'
        '    "type": <one of the known task types>,\n'
        '    "weight": <string like "35%" or null>\n'
        "  },\n"
        '  "tags": [<string>, ...]\n'
        "}\n"
        "\n"
        f"Known categories: {', '.join(CATEGORIES)}.\n"
        f"Known task types: {', '.join(TASK_TYPES)}.\n"
        "Kinds:\n"
        "- 'task': an action the user needs to do, ideally with a deadline.\n"
        "- 'thought': an idea, observation, or half-formed note with no action.\n"
        "- 'resurface': something to bring back later ('remind me', 'look into').\n"
        "- 'ambiguous': unclear — the user should pick manually.\n"
        "Confidence is your self-estimate; use 0.75+ only when you are clearly correct. "
        "For a task, if you cannot extract a due date, set due to null. Set suggested_task "
        "to null when kind is not 'task'."
    )


def _default_call(api_key: str) -> LLMCall:
    """Build a production caller that hits the DeepSeek API via the OpenAI SDK."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def _call(system: str, user: str) -> dict:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        return json.loads(content)

    return _call


def classify(
    text: str,
    today: date,
    *,
    call: LLMCall | None = None,
) -> ClassifyResult:
    if call is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            log.info("DEEPSEEK_API_KEY unset; classifier disabled")
            return _AMBIGUOUS
        try:
            call = _default_call(api_key)
        except Exception:
            log.warning("failed to build DeepSeek client", exc_info=True)
            return _AMBIGUOUS

    try:
        raw = call(_build_system_prompt(today), text)
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
