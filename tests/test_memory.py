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
