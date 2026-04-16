# LANDO OS v2 — R1: Capture + Membase Design

**Date:** 2026-04-16
**Scope:** Release 1 of the LANDO OS v2 vision. Telegram-only capture flow with Membase as episodic memory. Mini App UI changes and priority algorithm are explicitly out of scope here and deferred to R1.5 and R2 respectively.
**Status:** Design approved, pending spec review.

---

## 1. Goals and non-goals

### Goals
- Let the user drop any thought (action, idea, or stash-for-later) into Telegram with minimal friction and have the bot do the right thing with it.
- Guarantee no captured thought is ever lost. Every capture writes to Membase before any classification or task creation.
- Add Membase as a persistent cross-surface memory layer: the scheduler bot, the morning/evening briefing, and future agents all read from the same store.
- Do not regress any existing functionality: briefing, `/add`, `/done`, `/undo`, Google Calendar integration, Mini App task list, and cron delivery must keep working unchanged.

### Non-goals (R1)
- Priority scoring algorithm. Deferred to R2.
- Mini App Notes tab or any front-end changes. Deferred to R1.5.
- Evening recap cron, weekly review cron, pattern detection. Independent future work.
- ntfy.sh or any secondary notification channel. The existing Telegram push is sufficient.
- File restructure from `backend/` to `core/ + bot/ + server/`. The current layout is already modular; rename is churn.
- Schema migration on `tasks.json`. R1 adds no required fields.
- Claude-synthesized connection narratives on `/think`. Plain Membase semantic search is sufficient for R1.

---

## 2. User-facing surface

### New Telegram commands

| Command | Purpose |
|---|---|
| `/note <text>` | Default capture. Classifier decides what to do (see §4). |
| `/think <text>` | Explicit thought capture. No classifier, no task extraction. Returns related Membase items. |
| `/return <text> [\| <trigger>]` | Explicit resurface-later. Stored with trigger metadata; surfaces in a future briefing. |
| `/recall <query>` | Semantic search against Membase. Returns top 5 snippets. |
| `/help` | Formatted list of all commands. |

Existing commands (`/add`, `/done`, `/undo`, briefing flows) are untouched.

### Command discoverability

- `bot.set_my_commands([...])` populates Telegram's native `/` hint popup. Every new command is registered with a one-line description.
- A `/help` command mirrors the same content in message form as a backup.
- The Mini App menu button slot is already bound to the web app URL and is not reused.

---

## 3. Architecture

### New modules (all under `backend/`)

| Module | Responsibility |
|---|---|
| `membase_client.py` | Thin wrapper over the Python Membase client (in development by a separate agent). Defined as a `Protocol` with `add_memory(text, tags=[], metadata={})`, `search_memory(query, limit=5)`, and `add_wiki(title, content)`. A stub implementation lives in the repo and can be swapped for the real client with a single import change. |
| `classifier.py` | Anthropic API call. Input: raw text, today's date, category list. Output: `ClassifyResult` (pydantic model). Uses strict JSON output via tool use. Model: `claude-haiku-4-5`. |
| `capture.py` | Orchestrator. Owns `process_note(text, user_id) -> CaptureOutcome` and the high-conf vs. low-conf vs. thought branching. Also `process_think`, `process_return`, `process_recall`. |
| `undo_buffer.py` | In-memory dict `{chat_id: [PendingUndo]}` with 60-second TTL on each entry. Single-process only (the bot is single-process). Lost on restart — acceptable because the window is 60 s. |

### Extensions to existing files

- `bot.py`: new command handlers for `/note`, `/think`, `/return`, `/recall`, `/help`; a callback-query handler for inline buttons; and a text-message handler scoped to recognize `undo` replies within the 60 s window.
- `config.py`: add `anthropic_api_key` and whatever the Membase client needs (endpoint, API key, or similar — finalized once the client interface is ready).
- `tasks_store.py`: no change in R1.

### Data artifacts

- `data/membase_pending.jsonl` (new, gitignored): append-only retry queue for failed Membase writes. Drained on bot startup and at the start of each briefing run.
- No changes to `data/tasks.json` schema.

---

## 4. Data flows

### 4.1 `/note <text>`

1. Bot handler receives the message.
2. `capture.process_note(text, user_id)` is called.
3. **Always first:** `membase.add_memory(f"[NOTE] {text}", tags=["capture"])`. On failure, the text is appended to `data/membase_pending.jsonl` and the flow continues.
4. `classifier.classify(text, today, categories)` returns `ClassifyResult(kind, confidence, suggested_task?, tags)`.
5. Branch on `kind` and `confidence`:

    | Case | Action | Reply |
    |---|---|---|
    | `kind == "task"` and `confidence >= 0.75` | Create the task via `TasksStore.add`. Register an undo entry keyed on `(chat_id, message_id, task_id)` with a 60 s expiry. | `✅ Task created: <id> — <name> · due <date> · <weight> · type <type>. Reply "undo" within 60s to revert.` |
    | `kind == "task"` and `confidence < 0.75`, **or** `kind == "ambiguous"` | No write yet. Send an inline keyboard. | `I think this is a task, but I'm not sure. Pick one:` + buttons `[✅ Create task]` `[💭 Just a thought]` `[🔁 Resurface later]` |
    | `kind == "thought"` | No task created (Membase write already happened in step 3). | `💭 Saved. Tagged: [<tags>].` |
    | `kind == "resurface"` | Update the Membase entry with `resurface: true` and the extracted trigger in metadata. | `🔁 Saved. Will resurface <when>.` |

6. If the user replies with the literal text `undo` within 60 s of a high-confidence write, the task is deleted from `tasks.json` and the bot replies `Reverted.`
7. If the user taps an inline button:
    - `✅ Create task` → run the high-confidence write path. If `suggested_task` is present, use it. If not, create a minimal task with `name = <note text truncated to 80 chars>`, `category = "life"`, `type = "admin"`, `due = today + 7 days`, `weight = ""`. The reply flags the defaults explicitly so the user can edit via `/add` or the Mini App.
    - `💭 Just a thought` → no further action (the Membase write already happened). Reply `💭 Kept as a thought.`
    - `🔁 Resurface later` → update the Membase entry with `resurface: true` and a default trigger of 3 days from now. Reply with the scheduled date.

    `✏️ Edit details` is intentionally omitted from the button set in R1. If the user wants precise fields, they use `/add` directly — the classifier path is optimized for drop-and-go, not fine-tuning.

### 4.2 `/think <text>`

1. `membase.add_memory(f"[THINKING] {text}", tags=["thinking"])` synchronously.
2. `membase.search_memory(text, limit=3)`.
3. Reply: `💭 Saved.` followed by up to three related snippets, each line formatted `· <relative-time> · <snippet (truncated to 120 chars)>`. If no hits, omit the related block.
4. No classifier call.

### 4.3 `/return <text> [| <trigger>]`

1. Parse the trigger. R1 supports three forms:
    - Bare (no `|`): default trigger = tomorrow's briefing.
    - `| in N days` → target date = today + N.
    - `| next <weekday>` → target date = next occurrence of that weekday.
    - Anything else after `|` is stored verbatim in `trigger_raw` with no `trigger_date` set. These entries never auto-surface in the briefing; they are only retrievable via `/recall`. The reply makes this explicit: `🔁 Saved. (Trigger not auto-parsed — find this with /recall later.)`
2. `membase.add_memory(f"[RETURN] {text}", metadata={"resurface": true, "trigger_date": "<ISO date>", "trigger_raw": "<raw>"})`.
3. Reply: `🔁 Will resurface on <date>.`
4. The morning and evening briefing generators add a `🔁 RESURFACING` block that pulls `[RETURN]` items whose `trigger_date <= today`. (Implementation of the briefing hook is in scope for R1.)

### 4.4 `/recall <query>`

1. `membase.search_memory(query, limit=5)`.
2. Reply with each hit on its own line: `· <relative-time> · <snippet (truncated to 140 chars)>`.
3. If zero hits, reply `No matching notes found.`

### 4.5 `/help`

Static message listing every command and its one-line description. Kept in sync with the `set_my_commands` registrations by being built from the same source list in code.

---

## 5. Classifier

### Interface

```python
@dataclass(frozen=True)
class SuggestedTask:
    category: str        # one of the known category slugs
    name: str
    due: str | None      # ISO YYYY-MM-DD or None if not extractable
    type: str            # one of the known task types
    weight: str | None   # verbatim from the note, e.g. "35%", or None

@dataclass(frozen=True)
class ClassifyResult:
    kind: Literal["task", "thought", "resurface", "ambiguous"]
    confidence: float    # 0.0 to 1.0
    suggested_task: SuggestedTask | None
    tags: list[str]
```

### Prompt shape

- System: "Classify a captured thought. Output JSON matching the schema. Today is {today}. Known categories: {category_list}. Known types: {type_list}. For a task, resolve relative dates ('Friday', 'next week') to absolute ISO dates. If a weight is visible in the text (e.g. '35%'), include it verbatim; otherwise omit."
- The category list and type list are sourced from the existing `tasks.json` vocabulary plus the non-class categories (baseball, recruiting, projects, life). These are defined in a module-level constant so the prompt stays in sync with the rest of the system.
- Structured output is enforced via Anthropic tool use, not prose parsing.
- Model: `claude-haiku-4-5`. Latency and cost matter more than raw capability for a classifier of this shape.

### Fallback

If the Anthropic call fails or returns malformed JSON, the classifier returns `ClassifyResult(kind="ambiguous", confidence=0.0, suggested_task=None, tags=[])` and the user sees the inline-button flow. The bad output is logged for prompt tuning.

---

## 6. Failure modes

| Failure | Behavior |
|---|---|
| Anthropic API down or rate-limited on `/note` | Classifier returns `ambiguous`. User gets the inline-button flow. Reply includes a brief note `(classifier unavailable — pick manually)`. Membase write still happens. |
| Membase write fails on any capture | Text is appended to `data/membase_pending.jsonl`. Reply still confirms capture. Queue drains on bot startup and at the start of each briefing run. |
| Membase search fails on `/think` or `/recall` | Reply `💭 Saved. (Couldn't fetch related right now.)` for `/think`, or `Search unavailable — try again later.` for `/recall`. `/think` still succeeded at the save step. |
| Classifier returns malformed JSON | Same as API failure: `ambiguous` + inline buttons. |
| User taps an inline button after a bot restart | Callback data is self-contained (the message_id plus the pending action encoded in the callback payload), so it survives restart. |
| `undo` reply after the 60 s window | Reply `Too late — task <id> still stands. Use /done <id> or edit via the Mini App.` |
| `/note` classifies as task but no `due` was extractable | Create the task anyway with `due = today + 7 days`. Reply flags the default explicitly: `⚠️ No due date found — defaulted to <date>. Reply "undo" or edit.` |
| Empty command body (`/note`, `/think`, `/return`, `/recall` with no text) | Short usage hint, no write. |
| Concurrent `/note` from the same chat inside 60 s | Each has its own undo entry; `undo` reverts the most recent one only. |

All failure replies are phrased so the user always knows what was and was not saved.

---

## 7. Testing

Following the existing pattern: pytest, `tests/test_*.py`, no live external services in the test suite.

- `tests/test_classifier.py` — fixtures for each `kind` plus a malformed-JSON case. Anthropic is mocked.
- `tests/test_capture.py` — `process_note` covering: high-confidence write, low-confidence buttons, pure thought, resurface, Membase failure, classifier failure, no-date task fallback. Uses an in-memory `TasksStore` and a fake `MembaseClient`.
- `tests/test_undo_buffer.py` — add, retrieve within window, retrieve after expiry, cleanup, multiple entries per chat.
- `tests/test_membase_client.py` — retry-queue drain with a stub client that fails-then-succeeds; verifies `membase_pending.jsonl` is emptied only on successful flush.
- `tests/test_bot_capture.py` — integration. Bot handler with stubbed externals. Covers the command router, callback-button flow, and the `undo` text-handler scoping.

Not automated: live Anthropic, live Membase, real Telegram. Manual end-to-end smoke test against the live bot before merging R1.

---

## 8. Dependencies and sequencing

- R1 implementation can begin immediately against the stub `MembaseClient` protocol. When the separate agent's real Python client is ready, swap the import in `backend/membase_client.py`. Tests do not exercise the real client, so they continue to pass.
- Requires `ANTHROPIC_API_KEY` in `.env`, loaded by `config.py`.
- Bot restart is required after deploy because `set_my_commands` runs once at startup.

---

## 9. Rollout

1. Build modules, tests, and handlers on a feature branch.
2. Run `pytest -v` — all 24 existing tests plus the new suites pass.
3. Stop the `bot` tmux window, restart with the new code, and run `python -m backend.bot setup-menu` to refresh the `/` command hints.
4. Manual smoke: `/note pset 4 due friday 15%` (expect high-conf write), `/note maybe rework the pricing model` (expect buttons), `/think <long thought>` (expect save + related), `/recall <query>`, `/return <text> | in 3 days`.
5. Watch `briefing.log` and the bot tmux window for a day; classifier mis-fires are expected and acceptable during initial tuning.
6. When the separate agent's Membase client lands, swap the stub import, rerun tests, redeploy.

---

## 10. Open items explicitly deferred

- R1.5: Mini App Notes tab (chronological feed, search, "create task from this" button on each note).
- R2: Priority algorithm (lightweight: `urgency × impact × type_boost`, no `effort_fit` or `staleness`, no schema change).
- R3+: evening recap cron, weekly review cron, `/api/suggest` endpoint, week-view grid in Mini App.

Each of these gets its own spec and plan cycle.
