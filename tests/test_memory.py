"""Unit tests for backend.memory — Membase MCP client."""
from __future__ import annotations

import inspect
import logging
import typing

from backend import memory


def test_public_api_signatures():
    """The three documented public functions exist with the right parameters."""
    hints_store = typing.get_type_hints(memory.store_memory)
    sig_store = inspect.signature(memory.store_memory)
    assert list(sig_store.parameters.keys()) == ["content", "project"]
    assert hints_store["content"] is str
    assert sig_store.parameters["project"].default is None

    hints_search = typing.get_type_hints(memory.search_memory)
    sig_search = inspect.signature(memory.search_memory)
    assert list(sig_search.parameters.keys()) == ["query", "limit"]
    assert hints_search["query"] is str
    assert sig_search.parameters["limit"].default == 10

    hints_wiki = typing.get_type_hints(memory.search_wiki)
    sig_wiki = inspect.signature(memory.search_wiki)
    assert list(sig_wiki.parameters.keys()) == ["query"]
    assert hints_wiki["query"] is str


async def test_fail_soft_when_bridge_command_invalid(monkeypatch, caplog):
    """If the bridge subprocess can't start, all three functions return safe defaults."""
    # Reset module state and point _BRIDGE_COMMAND at a guaranteed-to-fail path.
    monkeypatch.setattr(
        memory, "_BRIDGE_COMMAND", ["/nonexistent/bogus/binary-for-tests"]
    )
    monkeypatch.setattr(memory, "_SESSION", None)
    monkeypatch.setattr(memory, "_STACK", None)
    monkeypatch.setattr(memory, "_DISABLED", False)

    with caplog.at_level(logging.WARNING, logger="backend.memory"):
        # First call triggers init, which must fail and disable the module.
        assert await memory.store_memory("hello world") is False
        # Subsequent calls must short-circuit on _DISABLED and return safe defaults.
        assert await memory.search_memory("anything") == []
        assert await memory.search_wiki("anything") == []

    # The init failure produced at least one WARNING log on backend.memory.
    membase_warnings = [
        r for r in caplog.records
        if r.name == "backend.memory" and r.levelno >= logging.WARNING
    ]
    assert membase_warnings, "expected at least one warning on backend.memory"
    assert any("Membase" in r.getMessage() for r in membase_warnings)

    # The module marked itself disabled.
    assert memory._DISABLED is True
