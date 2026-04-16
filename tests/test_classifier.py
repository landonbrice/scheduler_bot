from __future__ import annotations
import json
from datetime import date
import pytest
from backend.classifier import classify, ClassifyResult, SuggestedTask


def _fake_anthropic(result_json: dict):
    """Return a callable matching the classifier's `call_tool` signature
    that echoes the given tool-use result."""
    def _call(system: str, user: str, tool_schema: dict) -> dict:
        return result_json
    return _call


def test_classifies_as_task_with_date():
    fake = _fake_anthropic({
        "kind": "task",
        "confidence": 0.9,
        "suggested_task": {
            "category": "corpfin", "name": "Pset 4",
            "due": "2026-04-24", "type": "pset", "weight": "15%",
        },
        "tags": ["corpfin", "pset"],
    })
    result = classify("pset 4 due friday 15%", date(2026, 4, 16), call=fake)
    assert result.kind == "task"
    assert result.confidence == 0.9
    assert result.suggested_task is not None
    assert result.suggested_task.category == "corpfin"
    assert result.suggested_task.due == "2026-04-24"
    assert result.tags == ["corpfin", "pset"]


def test_classifies_as_thought_with_no_suggested_task():
    fake = _fake_anthropic({
        "kind": "thought",
        "confidence": 0.85,
        "suggested_task": None,
        "tags": ["projects", "pricing"],
    })
    result = classify("maybe pricing should be per-team not per-seat", date(2026, 4, 16), call=fake)
    assert result.kind == "thought"
    assert result.suggested_task is None
    assert "pricing" in result.tags


def test_ambiguous_falls_back_to_inline_buttons_via_low_confidence():
    fake = _fake_anthropic({
        "kind": "task", "confidence": 0.4,
        "suggested_task": {"category": "life", "name": "call mom", "due": None, "type": "admin", "weight": None},
        "tags": ["life"],
    })
    result = classify("call mom", date(2026, 4, 16), call=fake)
    assert result.kind == "task"
    assert result.confidence == 0.4


def test_anthropic_failure_returns_ambiguous():
    def broken_call(*args, **kwargs):
        raise RuntimeError("api down")
    result = classify("anything", date(2026, 4, 16), call=broken_call)
    assert result.kind == "ambiguous"
    assert result.confidence == 0.0
    assert result.suggested_task is None


def test_malformed_json_returns_ambiguous():
    def bad_call(*args, **kwargs):
        return {"not_the": "right shape"}
    result = classify("anything", date(2026, 4, 16), call=bad_call)
    assert result.kind == "ambiguous"
    assert result.confidence == 0.0


def test_missing_api_key_short_circuits_to_ambiguous(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = classify("anything", date(2026, 4, 16), call=None)
    assert result.kind == "ambiguous"


def test_suggested_task_dataclass_has_expected_fields():
    t = SuggestedTask(category="apes", name="Lab 3", due="2026-04-20", type="pset", weight="5%")
    assert t.category == "apes"
    assert t.due == "2026-04-20"
