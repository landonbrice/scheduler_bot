#!/usr/bin/env bash
# Start a Cloudflare Quick Tunnel pointed at the local API, capture the public
# https URL, write it to .env as MINIAPP_URL=..., then update the Telegram chat
# menu button so tapping it opens the fresh URL.
#
# Usage:  ./scripts/refresh_tunnel.sh
# Leaves cloudflared running in the foreground; Ctrl-C to stop.

set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

API_PORT="${API_PORT:-8000}"
LOG_FILE="$(mktemp -t cloudflared).log"
URL_FILE="$PROJECT_ROOT/.tunnel_url"
ENV_FILE="$PROJECT_ROOT/.env"

echo "→ starting cloudflared quick tunnel (port $API_PORT), log: $LOG_FILE"
cloudflared tunnel --no-autoupdate --url "http://localhost:$API_PORT" > "$LOG_FILE" 2>&1 &
CF_PID=$!
trap 'echo "→ stopping cloudflared"; kill "$CF_PID" 2>/dev/null || true' EXIT

# Wait up to 30s for the URL to appear
URL=""
for _ in $(seq 1 60); do
    URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | head -n1 || true)"
    [ -n "$URL" ] && break
    sleep 0.5
done

if [ -z "$URL" ]; then
    echo "✗ failed to detect tunnel URL after 30s. log dump:" >&2
    cat "$LOG_FILE" >&2
    exit 1
fi

echo "→ tunnel URL: $URL"
echo "$URL" > "$URL_FILE"

# Rewrite MINIAPP_URL line in .env (or append if missing)
if [ ! -f "$ENV_FILE" ]; then
    echo "✗ $ENV_FILE does not exist. Copy .env.example to .env and fill in credentials first." >&2
    exit 1
fi
if grep -q '^MINIAPP_URL=' "$ENV_FILE"; then
    sed -i '' "s|^MINIAPP_URL=.*|MINIAPP_URL=$URL|" "$ENV_FILE"
else
    echo "MINIAPP_URL=$URL" >> "$ENV_FILE"
fi

echo "→ updating Telegram chat menu button"
source venv/bin/activate
python -m backend.bot setup-menu

echo "✓ tunnel live. Keep this terminal open. Ctrl-C to stop."
wait "$CF_PID"
