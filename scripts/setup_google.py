"""One-time Google OAuth setup.

Run this on the Mac Mini:
  source venv/bin/activate
  python scripts/setup_google.py

The script starts a local HTTP server on 0.0.0.0:8080 and prints an authorization
URL. Open it from any device that can reach the Mac Mini (Tailscale works), grant
access, and the script persists the token to ~/.config/scheduler-bot/google_token.json.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.gcal import CREDS_PATH, TOKEN_PATH, SCOPES  # noqa: E402


def main() -> None:
    if not CREDS_PATH.exists():
        print(f"✗ missing {CREDS_PATH}")
        print("  1. Google Cloud Console → Create OAuth client (Desktop app)")
        print("  2. Download the JSON → save it to the path above")
        sys.exit(2)

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    print("→ starting local auth server on localhost:8080")
    print("  Google OAuth for Desktop apps only accepts localhost/127.0.0.1 as redirect URIs.")
    print("  Since this Mac is headless, SSH-port-forward 8080 from your laptop before")
    print("  opening the URL:")
    print("      ssh -L 8080:localhost:8080 <this-mac>")
    print("  Then open the authorization URL below in your LAPTOP browser.")
    creds = flow.run_local_server(host="localhost", port=8080, open_browser=False)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"✓ token saved to {TOKEN_PATH}")


if __name__ == "__main__":
    main()
