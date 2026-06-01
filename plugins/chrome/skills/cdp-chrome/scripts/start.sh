#!/bin/bash
# CDP Chrome per-OS-user launcher.
# Starts Chrome in GUI mode with remote debugging enabled.
# Key: does NOT use --enable-automation, so navigator.webdriver stays false.

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

cdp_apply_config

mkdir -p "$CDP_PROFILE_DIR"

if cdp_http_ready "$CDP_PORT"; then
  cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "startup" || exit 1
  echo "CDP Chrome already running on port $CDP_PORT with profile $CDP_PROFILE_DIR"
  exit 0
fi

# Fail fast if a non-CDP process already owns the configured port.
cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "startup" || exit 1

# Clean stale lock files from previous crashes in this configured profile only.
for lock in SingletonLock SingletonSocket SingletonCookie; do
  rm -f "$CDP_PROFILE_DIR/$lock" 2>/dev/null
done

touch "$CDP_PROFILE_DIR/First Run" 2>/dev/null

if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif command -v google-chrome >/dev/null 2>&1; then
  CHROME_BIN="$(command -v google-chrome)"
elif command -v chromium >/dev/null 2>&1; then
  CHROME_BIN="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME_BIN="$(command -v chromium-browser)"
else
  echo "ERROR: Google Chrome/Chromium executable not found." >&2
  exit 1
fi

echo "Starting CDP Chrome on port $CDP_PORT with profile $CDP_PROFILE_DIR..."

"$CHROME_BIN" \
  --remote-debugging-port="$CDP_PORT" \
  --user-data-dir="$CDP_PROFILE_DIR" \
  --remote-allow-origins=* \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-background-networking \
  --disable-default-apps \
  --disable-component-extensions-with-background-pages \
  >/dev/null 2>&1 &
chrome_pid=$!

# Wait for Chrome to start (try both IPv4 and IPv6 via cdp_http_ready).
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if cdp_http_ready "$CDP_PORT"; then
    cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "startup" || exit 1
    echo "CDP Chrome started on port $CDP_PORT (PID $chrome_pid)"
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: CDP Chrome failed to start within 10 seconds" >&2
exit 1
