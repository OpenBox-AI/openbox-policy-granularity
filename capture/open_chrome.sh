#!/usr/bin/env bash
# Open a Chrome window on the OpenBox dashboard with remote debugging on :9333,
# so capture/openbox.py can take screenshots from your signed-in session.
# The dashboard asks for a password on every new login, so a saved session
# cannot be replayed headlessly; sign in here and leave the window open.
set -euo pipefail
DASHBOARD_URL="${OPENBOX_DASHBOARD_URL:-http://localhost:3233}"
CHROME="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
PROFILE="$(mktemp -d -t openbox-compare-chrome)"
exec "$CHROME" --remote-debugging-port=9333 --user-data-dir="$PROFILE" \
  --no-first-run --window-size=1600,1000 "$DASHBOARD_URL/login"
