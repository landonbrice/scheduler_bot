# Scheduler Bot

Personal academic scheduler for UChicago Spring 2026. Telegram Mini App + daily 7am briefing, backend on Mac Mini exposed via Cloudflare Quick Tunnel.

## Architecture
- **`backend/`** — FastAPI on `127.0.0.1:8000`; endpoints under `/api/*` require `X-Telegram-Init-Data` header (HMAC-verified via `backend/auth.py`). Serves Vite build at `/`.
- **`frontend/`** — React + Vite + Tailwind. `npm run build` outputs to `backend/static/`.
- **Bot** — `backend/bot.py` modes: `bot` (polling) · `send` (cron) · `setup-menu` (re-point menu button).
- **State** — `data/tasks.json` (gitignored). Seeded by `scripts/seed_tasks.py`.
- **Tunnel** — `scripts/refresh_tunnel.sh` starts cloudflared, writes `MINIAPP_URL` to `.env`, re-runs `setup-menu`.

## Ops
- `./run.sh` — starts tmux session `scheduler` with windows `api`, `bot`, `tunnel`. Attach: `tmux attach -t scheduler`.
- Inspect running windows: `tmux capture-pane -t scheduler:<window> -p`.
- Cron: `0 7 * * *` → `venv/bin/python -m backend.bot send`. Logs to `briefing.log`.
- `.env` auto-loaded by `backend/config.py` relative to `PROJECT_ROOT`; cron needs no cwd or shell env.

## Gotchas
- **Python 3.14 + python-telegram-bot 21**: `asyncio.get_event_loop()` no longer auto-creates. `run_bot()` in `backend/bot.py` sets the loop explicitly before `run_polling`.
- **Quick Tunnel URL rotates** on every cloudflared restart. Always rerun `./scripts/refresh_tunnel.sh` after reboots — it rewrites `.env` and re-points the Telegram menu button.
- **pytest-asyncio on 3.14** prints hundreds of deprecation warnings. Cosmetic; tests pass.
- **Bot can't DM you unless you `/start` it once.** Cron sends will silently fail otherwise.

## Tests
`pytest -v` — 24 tests across `tests/test_{tasks_store,auth,briefing,server}.py`. No React tests (pragmatic); verify UI manually in Telegram.

## Conventions
- Python: `from __future__ import annotations` in all backend modules, frozen dataclasses for config, atomic writes via `tempfile.mkstemp + os.replace`.
- TS: strict mode, `noUnusedLocals`. Global `Window.Telegram` typed in `frontend/src/telegram.ts`.
- Dates: backend uses real `date.today()`; frontend uses real `new Date()`. (JSX mockup hardcoded 2026-04-13 — do not propagate.)

## Status (as of 2026-04-13)
- ✅ Backend + Mini App + bot + cron live end-to-end.
- ⏭️ **Next: Google Calendar integration** — `setup_google.py` OAuth helper + `/api/calendar` endpoint + briefing augmentation. Scope per `CLAUDE_CODE_DIRECTIONS.md` §3 and §4.
- ⏭️ Later: Claude-enhanced briefings (Anthropic API); extra bot commands (`/list`, `/done`, `/add`, `/undo`, `/week`, `/crunch`).

## Reference
- Plan: `docs/superpowers/plans/2026-04-13-telegram-miniapp.md`
- Original spec: `CLAUDE_CODE_DIRECTIONS.md`
- JSX design reference: `academic_planner.jsx` (retained for visual spec)
