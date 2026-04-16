"""Membase MCP client.

Three public async entry points:
  - store_memory(content, project=None) -> bool
  - search_memory(query, limit=10) -> list[dict]
  - search_wiki(query) -> list[dict]

All three are fail-soft: any error (missing SDK, bridge subprocess won't start,
MCP protocol error, tool error) is caught, logged at WARNING, and converted
to a safe default (False / []). The caller never sees an exception.

Connection model: a single MCP ClientSession is opened lazily on first call
and reused for the lifetime of the host process. The session talks to an
`npx mcp-remote` subprocess that bridges to https://mcp.membase.so/mcp.
This is the same bridge Claude Desktop uses, so OAuth tokens stored in
~/.mcp-auth/ are shared and no new browser flow is needed at runtime.

If session init fails once, the module disables itself for the rest of the
process and returns safe defaults without retrying. Restart the host
process to recover.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import Any

log = logging.getLogger(__name__)

# The bridge command. Module-level so tests can monkeypatch it.
_BRIDGE_COMMAND: list[str] = [
    "npx",
    "-y",
    "mcp-remote@latest",
    "https://mcp.membase.so/mcp",
]

# Lazy-singleton state. Underscore-prefixed — not part of the public API.
_SESSION: Any = None  # mcp.ClientSession when initialized
_STACK: AsyncExitStack | None = None
_LOCK = asyncio.Lock()
_DISABLED = False


async def _get_session() -> Any:
    """Return the cached ClientSession, initializing on first call.

    Returns None if init has failed for this process or fails on this call.
    """
    global _SESSION, _STACK, _DISABLED

    if _DISABLED:
        return None
    if _SESSION is not None:
        return _SESSION

    async with _LOCK:
        if _SESSION is not None:
            return _SESSION
        if _DISABLED:
            return None

        stack = AsyncExitStack()
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=_BRIDGE_COMMAND[0],
                args=list(_BRIDGE_COMMAND[1:]),
                env=None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except Exception:
            log.warning(
                "Membase MCP session init failed; disabling memory features for this process",
                exc_info=True,
            )
            _DISABLED = True
            try:
                await stack.aclose()
            except Exception:
                pass
            return None

        _STACK = stack
        _SESSION = session
        return session


def _content_to_dicts(result: Any) -> list[dict]:
    """Convert an MCP CallToolResult's content list into a list of dicts.

    Each content item with a .text attribute is JSON-parsed when possible.
    Non-JSON text is wrapped as {"text": ...}. Items without text are skipped.
    """
    items: list[dict] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            items.append({"text": text})
            continue
        if isinstance(parsed, list):
            for p in parsed:
                items.append(p if isinstance(p, dict) else {"value": p})
        elif isinstance(parsed, dict):
            items.append(parsed)
        else:
            items.append({"value": parsed})
    return items


async def store_memory(content: str, project: str | None = None) -> bool:
    """Store a memory in Membase. Returns True on success, False on any failure."""
    session = await _get_session()
    if session is None:
        return False
    try:
        args: dict[str, Any] = {"content": content}
        if project is not None:
            args["project"] = project
        result = await session.call_tool("add_memory", args)
        return not bool(getattr(result, "isError", False))
    except Exception:
        log.warning("Membase add_memory call failed", exc_info=True)
        return False


async def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search Membase memories. Returns a list of result dicts; [] on failure."""
    session = await _get_session()
    if session is None:
        return []
    try:
        result = await session.call_tool(
            "search_memory", {"query": query, "limit": limit}
        )
        if getattr(result, "isError", False):
            log.warning("Membase search_memory returned isError=True")
            return []
        return _content_to_dicts(result)
    except Exception:
        log.warning("Membase search_memory call failed", exc_info=True)
        return []


async def search_wiki(query: str) -> list[dict]:
    """Search Membase wiki. Returns a list of result dicts; [] on failure."""
    session = await _get_session()
    if session is None:
        return []
    try:
        result = await session.call_tool("search_wiki", {"query": query})
        if getattr(result, "isError", False):
            log.warning("Membase search_wiki returned isError=True")
            return []
        return _content_to_dicts(result)
    except Exception:
        log.warning("Membase search_wiki call failed", exc_info=True)
        return []
