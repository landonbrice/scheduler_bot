#!/usr/bin/env bash
# Start all three long-running processes inside tmux windows:
#   0: api     (FastAPI on 127.0.0.1:8000)
#   1: bot     (telegram polling)
#   2: tunnel  (cloudflared + menu update)
#
# Attach with `tmux attach -t scheduler`, detach with Ctrl-B D.

set -euo pipefail
cd "$(dirname "$0")"
SESSION=scheduler

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "session $SESSION already running. tmux attach -t $SESSION"
    exit 0
fi

tmux new-session -d -s "$SESSION" -n api \
    "cd $(pwd) && source venv/bin/activate && uvicorn backend.server:app --host 127.0.0.1 --port 8000"

tmux new-window -t "$SESSION" -n bot \
    "cd $(pwd) && source venv/bin/activate && python -m backend.bot bot"

tmux new-window -t "$SESSION" -n tunnel \
    "cd $(pwd) && ./scripts/refresh_tunnel.sh"

echo "started. tmux attach -t $SESSION"
