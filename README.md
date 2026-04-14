# Academic Scheduler — Telegram Mini App

Personal scheduler bot for UChicago Spring 2026. Backend on Mac Mini, exposed via Cloudflare Quick Tunnel, consumed by a Telegram Mini App + daily 7am briefing cron.

## Setup

1. `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. `cd frontend && npm install && npm run build && cd ..`
3. `cp .env.example .env` and fill `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
4. `python scripts/seed_tasks.py`
5. `brew install cloudflared`
6. `./run.sh`

## Modes

- `python -m backend.bot bot` — polling bot
- `python -m backend.bot send` — one-shot briefing (cron uses this)
- `python -m backend.bot setup-menu` — re-apply chat menu button URL

## Daily operation

`run.sh` starts three tmux windows (api, bot, tunnel). The tunnel window holds the Quick Tunnel; restarting it changes the URL and automatically updates the Telegram chat menu button via `setup-menu`.

## Tests

`pytest -v`
