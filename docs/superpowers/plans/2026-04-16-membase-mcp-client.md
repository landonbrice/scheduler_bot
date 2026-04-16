# Membase MCP Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `backend/memory.py` — a fail-soft async client that lets the rest of the codebase store and search Membase memories via three top-level functions.

**Architecture:** Spawn `npx -y mcp-remote@latest https://mcp.membase.so/mcp` as a subprocess, connect via the `mcp` Python SDK's stdio transport, and reuse a single `ClientSession` for the host process's lifetime (lazy singleton, guarded by an asyncio lock). All errors are caught, logged, and converted to safe defaults — callers never see exceptions.

**Tech Stack:** Python 3.14, `mcp>=1.0` (Anthropic's official MCP Python SDK), `pytest` with `asyncio_mode = auto`, Node `npx` available on PATH at runtime.

**Spec:** `docs/superpowers/specs/2026-04-16-membase-mcp-client-design.md`

**File map:**
- Create: `backend/memory.py` (~120 lines)
- Create: `tests/test_memory.py` (2 tests)
- Modify: `requirements.txt` (add one line)

No other files change. Bot wiring is owned by a parallel agent and is explicitly out of scope.

---

## Task 1: Add the `mcp` dependency

**Files:**
- Modify: `/Users/landonprojects/scheduler_bot/requirements.txt`

- [ ] **Step 1: Add `mcp>=1.0` to requirements.txt**

The current file is:

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
python-telegram-bot==21.*
python-dotenv==1.0.*
httpx==0.27.*
pytest==8.*
pytest-asyncio==0.24.*
google-api-python-client==2.*
google-auth-oauthlib==1.2.*
google-auth-httplib2==0.2.*
```

Append one line so it becomes:

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
python-telegram-bot==21.*
python-dotenv==1.0.*
httpx==0.27.*
pytest==8.*
pytest-asyncio==0.24.*
google-api-python-client==2.*
google-auth-oauthlib==1.2.*
google-auth-httplib2==0.2.*
mcp>=1.0
```

- [ ] **Step 2: Install into the project venv**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pip install 'mcp>=1.0'`

Expected: pip resolves and installs `mcp` plus its transitive deps (`anyio`, `httpx-sse`, `pydantic`, etc.). Exit code 0.

- [ ] **Step 3: Verify the import works**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/python -c "from mcp import ClientSession, StdioServerParameters; from mcp.client.stdio import stdio_client; print('ok')"`

Expected: `ok` printed, exit code 0.

If this fails, the `mcp` package layout may have shifted in the version that resolved. Look up the current import path with `venv/bin/python -c "import mcp; print(mcp.__file__)"` and adjust the imports used in Task 2 to match. Do not proceed until this step prints `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add requirements.txt
git commit -m "deps: add mcp Python SDK for Membase client"
```

---

## Task 2: Implement `backend/memory.py`

**Files:**
- Create: `/Users/landonprojects/scheduler_bot/backend/memory.py`
- Create: `/Users/landonprojects/scheduler_bot/tests/test_memory.py`

This task uses TDD: write the signature test first (which only checks the public API surface), then implement the full module so the test passes. The fail-soft test comes in Task 3.

- [ ] **Step 1: Write the public-API signature test**

Create `/Users/landonprojects/scheduler_bot/tests/test_memory.py` with:

```python
"""Unit tests for backend.memory — Membase MCP client."""
from __future__ import annotations

import inspect
import logging

from backend import memory


def test_public_api_signatures():
    """The three documented public functions exist with the right parameters."""
    sig_store = inspect.signature(memory.store_memory)
    assert list(sig_store.parameters.keys()) == ["content", "project"]
    assert sig_store.parameters["content"].annotation is str
    assert sig_store.parameters["project"].default is None

    sig_search = inspect.signature(memory.search_memory)
    assert list(sig_search.parameters.keys()) == ["query", "limit"]
    assert sig_search.parameters["query"].annotation is str
    assert sig_search.parameters["limit"].default == 10

    sig_wiki = inspect.signature(memory.search_wiki)
    assert list(sig_wiki.parameters.keys()) == ["query"]
    assert sig_wiki.parameters["query"].annotation is str
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pytest tests/test_memory.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.memory'` (or similar import error). The test file collected, the import failed.

- [ ] **Step 3: Implement `backend/memory.py`**

Create `/Users/landonprojects/scheduler_bot/backend/memory.py` with the following exact contents:

```python
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
```

- [ ] **Step 4: Run the signature test to confirm it passes**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pytest tests/test_memory.py::test_public_api_signatures -v`

Expected: PASS, 1 test passed.

- [ ] **Step 5: Run the full test suite to confirm nothing else regressed**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pytest -q`

Expected: 25 passed (the 24 existing tests plus the new signature test). Deprecation warnings from pytest-asyncio on Python 3.14 are expected and noted in `CLAUDE.md` — ignore them.

- [ ] **Step 6: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add backend/memory.py tests/test_memory.py
git commit -m "feat(memory): Membase MCP client with fail-soft async API"
```

---

## Task 3: Verify fail-soft behavior end-to-end

This task adds the second test — the one that proves init failure produces safe defaults and a logged warning, not an exception. The implementation from Task 2 already satisfies the contract; this test locks it in.

**Files:**
- Modify: `/Users/landonprojects/scheduler_bot/tests/test_memory.py`

- [ ] **Step 1: Write the fail-soft test**

Append the following to `/Users/landonprojects/scheduler_bot/tests/test_memory.py` (after the existing `test_public_api_signatures` function, with one blank line separating them):

```python


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
```

Note: the project's `pytest.ini` sets `asyncio_mode = auto`, so `async def` test functions run as asyncio tests automatically — no `@pytest.mark.asyncio` decoration needed. The `monkeypatch` fixture restores all attributes after the test, so `_DISABLED`, `_SESSION`, etc. are reset for any later tests.

- [ ] **Step 2: Run the new test**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pytest tests/test_memory.py::test_fail_soft_when_bridge_command_invalid -v`

Expected: PASS. The bogus command causes `stdio_client` to fail (the subprocess `exec` raises `FileNotFoundError`), the `except Exception` in `_get_session` catches it, logs the warning, sets `_DISABLED = True`, and returns `None`. Each public function then returns its safe default.

If this test fails because the expected log message isn't present, inspect `caplog.records` — you may need to widen the logger filter or check that `propagate` is not disabled on `backend.memory` (it isn't by default; the module uses `logging.getLogger(__name__)` with no further configuration).

If this test fails because an exception escapes, the fail-soft contract is broken. Inspect the traceback — most likely a code path inside `_get_session` is raising before the `try` block (e.g., the `from contextlib import AsyncExitStack` is unreachable). Move any code that could raise inside the `try`.

- [ ] **Step 3: Run the full test suite**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/pytest -q`

Expected: 26 passed.

- [ ] **Step 4: Smoke-test against real Membase (manual, optional but recommended)**

Run: `cd /Users/landonprojects/scheduler_bot && venv/bin/python -c "
import asyncio
from backend import memory

async def main():
    ok = await memory.store_memory('scheduler_bot smoke test from Task 3')
    print('store_memory ok:', ok)
    hits = await memory.search_memory('scheduler_bot smoke test', limit=5)
    print('search_memory hits:', len(hits))
    if hits:
        print('first hit keys:', list(hits[0].keys()))

asyncio.run(main())
"`

Expected: `store_memory ok: True` and `search_memory hits: <some integer >= 0>`. First-call latency will be a few seconds (npm subprocess startup + first MCP handshake). On a fresh install with no cached `~/.mcp-auth/` tokens, this will instead print `store_memory ok: False` and the script will exit cleanly — that means the user needs to authenticate Membase via Claude Desktop first. Not a code defect.

This step is optional because it touches a remote service and a live OAuth state, but it's the only way to confirm the wire format is right before another agent starts depending on the API. If skipped, leave a note in the commit message so a follow-up can run it.

- [ ] **Step 5: Commit**

```bash
cd /Users/landonprojects/scheduler_bot
git add tests/test_memory.py
git commit -m "test(memory): verify fail-soft behavior on bridge subprocess failure"
```

---

## Self-review checklist (run before handing off)

- **Spec coverage.**
  - Public API (3 functions, exact signatures) → Task 2 Step 3.
  - Bridge subprocess via `mcp-remote` → Task 2 Step 3, `_BRIDGE_COMMAND` constant + `stdio_client(params)`.
  - Lazy singleton with asyncio lock → Task 2 Step 3, `_get_session` + `_LOCK`.
  - Fail-soft (try/except, log warning, safe default) → Task 2 Step 3, all three public functions + `_get_session`.
  - Permanent-disable on init failure → Task 2 Step 3, `_DISABLED` flag.
  - Content-list-to-dicts conversion → Task 2 Step 3, `_content_to_dicts`.
  - `store_memory` omits `project` when `None` → Task 2 Step 3, `if project is not None: args["project"] = project`.
  - `mcp>=1.0` in requirements.txt → Task 1.
  - `tests/test_memory.py` with two tests → Tasks 2 & 3.
  - No edits to bot.py / briefing.py / server.py / tasks_store.py → confirmed by file map.

- **Placeholder scan.** No "TBD" / "TODO" / "implement later" / "appropriate error handling" / "similar to" — every step has the actual code or command. Verified.

- **Type / name consistency.** `_BRIDGE_COMMAND`, `_SESSION`, `_STACK`, `_LOCK`, `_DISABLED` named identically across implementation and test. `add_memory` / `search_memory` / `search_wiki` are the Membase tool names per the MCP server instructions. `_content_to_dicts` is used in both `search_memory` and `search_wiki`.
