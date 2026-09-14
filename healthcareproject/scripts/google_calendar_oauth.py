"""One-time local OAuth consent flow for calendar_sync's real Google
Calendar integration (services/booking/app/services/google_calendar.py).

Run this ONCE, locally (not in Docker) — it opens your browser, you sign
in and grant access, and it prints the refresh_token to put in
google-calendar.env alongside the client id/secret already there.

Usage:
    python scripts/google_calendar_oauth.py

Reads GOOGLE_CALENDAR_CLIENT_ID / GOOGLE_CALENDAR_CLIENT_SECRET from the
environment — export them first, or run via:
    set -a; source google-calendar.env; set +a
    python scripts/google_calendar_oauth.py
"""

from __future__ import annotations

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> None:
    client_id = os.environ.get("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "Set GOOGLE_CALENDAR_CLIENT_ID and GOOGLE_CALENDAR_CLIENT_SECRET "
            "in your environment first (see google-calendar.env).",
            file=sys.stderr,
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # Opens your default browser; after you sign in and grant access, it
    # captures the response on a local loopback server automatically.
    credentials = flow.run_local_server(port=0)

    print("\nSuccess. Add this to google-calendar.env:\n")
    print(f"GOOGLE_CALENDAR_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()
