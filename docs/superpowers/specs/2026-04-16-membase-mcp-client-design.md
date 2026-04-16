# Membase MCP Client — `backend/memory.py`

**Date:** 2026-04-16
**Status:** Approved (pending implementation)
**Scope:** Standalone Python module that connects to the Membase MCP server. No bot wiring — that work is owned by a parallel agent and is out of scope here.

## Goal

Provide the rest of the `scheduler_bot` codebase with three async functions for talking to Membase, hiding all MCP-protocol and subprocess details:

```python
async def store_memory(content: str, project: str | None = None) -> bool
async def search_memory(query: str, limit: int = 10) -> list[dict]
async def search_wiki(query: str) -> list[dict]
```

Callers must never need to import from `mcp`, manage sessions, or know that a subprocess is involved.

## Non-goals

- Wiring memory into bot commands (`/done`, `/note`, `/recall`) — separate agent.
- Wiring memory into briefing generation — separate agent, and depends on the not-yet-built Anthropic-API briefing path.
- Adding new bot commands.
- Authentication management — `mcp-remote` already handles OAuth and stores tokens in `~/.mcp-auth/`. We rely on existing tokens.

## Background

The Membase MCP server is a **remote HTTPS server** at `https://mcp.membase.so/mcp`. It is not a local Python or Node program. The user's Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`) and `~/.claude.json` both reach it through the `mcp-remote` Node bridge:

```json
{
  "command": "npx",
  "args": ["-y", "mcp-remote@latest", "https://mcp.membase.so/mcp"]
}
```

`mcp-remote` translates remote streamable-HTTP MCP traffic into local stdio MCP, and handles the OAuth flow on first run (writing tokens to `~/.mcp-auth/`). Because the user is already authenticated through Claude Desktop, the bot will reuse those tokens with no new browser flow.

## Architecture

### Connection model

`backend/memory.py` spawns the same `mcp-remote` subprocess used by Claude Desktop and connects to its stdin/stdout via the `mcp` Python SDK's `stdio_client`. One subprocess per host process, kept alive for the host's lifetime.

```
┌─────────────────────────────────┐
│  scheduler_bot host process     │
│  (bot.py polling, or cron       │
│   briefing one-shot)            │
│                                 │
│  ┌───────────────────────────┐  │
│  │  backend/memory.py        │  │
│  │  ─ lazy singleton session │  │
│  └────────────┬──────────────┘  │
└───────────────┼─────────────────┘
                │ stdio (JSON-RPC)
                ▼
┌─────────────────────────────────┐
│  npx mcp-remote (Node)          │
│  spawned subprocess             │
└────────────┬────────────────────┘
             │ HTTPS (streamable HTTP MCP)
             ▼
       https://mcp.membase.so/mcp
```

### Lifecycle: lazy singleton

A module-level coroutine `_get_session()` initializes the MCP `ClientSession` on first call and caches it. Subsequent calls reuse the cached session.

- **Bot polling process:** session opens on first memory call and lives until the bot exits. Subprocess is reaped by the OS at shutdown.
- **Cron briefing one-shot:** session opens on first call, used during the briefing assembly, and is torn down with the process when the script returns.
- **No explicit `close()` API.** Callers do not own the lifecycle.

The `mcp` SDK's `stdio_client` and `ClientSession` are async-context-managed. To hold them open across calls without an enclosing `async with`, we will manually call `__aenter__` on first use and store the entered objects on a module global. Process exit handles cleanup; we do not call `__aexit__` explicitly.

A single `asyncio.Lock` guards the init path so concurrent first-callers don't race to spawn two subprocesses.

### Error handling: fail-soft

The module never raises to its callers. Mirroring the `gcal.fetch_events` pattern in `backend/gcal.py`, every public function:

1. Catches all exceptions (including `ImportError` if `mcp` isn't installed, subprocess startup errors, MCP protocol errors, tool-call errors, asyncio cancellation).
2. Logs a warning via the standard `logging` module (`logger = logging.getLogger(__name__)`).
3. Returns the documented safe default:
   - `store_memory` → `False`
   - `search_memory` → `[]`
   - `search_wiki` → `[]`

Once initialization fails for the lifetime of the host process, the module enters a "disabled" state — subsequent calls return safe defaults immediately without retrying the subprocess spawn. This avoids per-call latency penalties when Membase is durably unreachable. (Trade-off: requires a process restart to recover from a transient init failure. Acceptable because the bot already restarts cleanly.)

### Tool mapping

The Membase server exposes (per the MCP-server instructions in this session): `add_memory`, `search_memory`, `search_wiki`, `add_wiki`, `update_wiki`, `delete_wiki`, `get_current_date`. We expose only the three required by the brief. Mapping:

| Public function | MCP tool       | Argument mapping                                  |
| --------------- | -------------- | ------------------------------------------------- |
| `store_memory`  | `add_memory`   | `{"content": content, "project": project}` (omit `project` key when `None`) |
| `search_memory` | `search_memory`| `{"query": query, "limit": limit}`                |
| `search_wiki`   | `search_wiki`  | `{"query": query}`                                |

Return-value handling:

- `store_memory`: returns `True` if the tool call completes without an MCP `isError` flag, `False` otherwise.
- `search_memory` / `search_wiki`: the tool result's `content` is a list of MCP content items (`TextContent`, etc.). Each item's `.text` is parsed as JSON if possible; on parse failure, wrapped as `{"text": <raw>}`. The function returns a `list[dict]`. If the server returns no content, returns `[]`.

This shape ("list of dicts") gives downstream callers (the parallel agent's bot wiring) something useful without committing to a strict Membase-specific schema we don't fully control.

## Public API

```python
# backend/memory.py

async def store_memory(content: str, project: str | None = None) -> bool:
    """Store a memory in Membase. Returns True on success, False on any failure."""

async def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search Membase memories. Returns a list of result dicts; [] on failure."""

async def search_wiki(query: str) -> list[dict]:
    """Search Membase wiki. Returns a list of result dicts; [] on failure."""
```

No other names are part of the public API. Any session/lock/state globals are underscore-prefixed.

## Dependencies

- **Python:** add `mcp>=1.0` to `requirements.txt`. The MCP Python SDK provides `mcp.client.stdio.stdio_client` and `mcp.ClientSession`.
- **Runtime:** `npx` must be on `PATH` when any memory function is called. (Already true on this Mac mini — Claude Desktop uses the same.)
- **Auth:** `~/.mcp-auth/` must contain valid Membase tokens. Already present from Claude Desktop usage.

## Tests

`tests/test_memory.py` — two unit tests, no network, no real Membase contact.

1. **`test_fail_soft_when_bridge_command_invalid`**
   Monkeypatch the module's bridge command to a guaranteed-to-fail value (e.g., `/nonexistent/path/to/npx`). Call all three public functions. Assert each returns its safe default and that a warning was logged. Verifies the fail-soft contract end-to-end.

2. **`test_public_api_signatures`**
   Use `inspect.signature` to verify the three public functions exist with the documented parameters and defaults. Cheap regression guard against accidental API drift.

No integration test against live Membase — would require network and OAuth state, which is brittle in CI and unnecessary for module-level confidence.

## File layout

```
backend/
  memory.py           # new (~80–120 lines)
tests/
  test_memory.py      # new (2 tests)
requirements.txt      # add: mcp>=1.0
```

No changes to `bot.py`, `briefing.py`, `server.py`, or `tasks_store.py`. The parallel agent will wire the public API into the bot in a separate change.

## Trade-offs and rejected alternatives

- **Bridge (`mcp-remote`) vs. direct streamable-HTTP MCP client.** Chose the bridge to reuse existing OAuth state and minimize moving parts. A direct HTTP client would remove the Node dependency but would require us to implement OAuth from scratch — high effort for no current benefit.
- **Lazy singleton vs. explicit context manager.** Chose the singleton for ergonomic call sites (`await store_memory(...)` is one line). An explicit `async with memory_session() as m:` would be more correct about resource ownership but pushes lifecycle management onto every caller.
- **Permanent-disable on init failure vs. retry every call.** Chose permanent-disable to bound latency. The bot restarts on cron and on user `./run.sh` invocations, so recovery is cheap.
- **No live integration test.** Live tests against a remote OAuth-gated service produce flaky CI. Fail-soft behavior is the contract that matters; we test that directly.

## Open questions

None. All scope and behavior decisions are settled.
