#!/usr/bin/env bash
# Regenerate the demo screenshots in docs/user-guide/img/ from a running demo server.
#
# Usage: demo/screenshots.sh [base-url]      (default http://127.0.0.1:8742)
# Needs a Chromium or Chrome binary: set CHROME, or it uses the first one found on PATH or in the
# Playwright cache. The pages only contain the fictional Civic District sample data.
set -euo pipefail

BASE="${1:-http://127.0.0.1:8742}"
OUT="$(cd "$(dirname "$0")/.." && pwd)/docs/user-guide/img"

find_chrome() {
  for c in "${CHROME:-}" chromium chromium-browser google-chrome; do
    [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return; }
  done
  ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | sort | tail -1
}
CHROME_BIN="$(find_chrome)"
[ -n "$CHROME_BIN" ] || { echo "no Chromium found; set CHROME" >&2; exit 1; }
curl -sf -o /dev/null "$BASE/health" || { echo "demo not reachable at $BASE (run python demo/server.py)" >&2; exit 1; }

mkdir -p "$OUT"
shot() { # name, width, height, url fragment
  "$CHROME_BIN" --headless --no-sandbox --disable-gpu --hide-scrollbars --window-size="$2,$3" \
    --virtual-time-budget=5000 --screenshot="$OUT/$1.png" "$BASE/demo/$4" 2>/dev/null
  echo "wrote docs/user-guide/img/$1.png"
}
shot demo-t1-access 1440 1000 "#t1"
shot demo-t2-supply 1440 1700 "#t2"
shot demo-t3-permit 1440 1700 "#t3"
shot demo-phone 390 1600 ""   # no #step: on a phone the browser would scroll to the card
