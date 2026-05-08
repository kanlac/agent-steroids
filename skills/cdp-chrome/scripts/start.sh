#!/bin/bash
# CDP Chrome shared instance launcher
# Deploy to: ~/.config/cdp-chrome/start.sh
#
# Starts Chrome in GUI mode with remote debugging enabled.
# Key: does NOT use --enable-automation, so navigator.webdriver stays false.

PORT=$(cat ~/.config/cdp-chrome/port)
PROFILE="$HOME/.config/cdp-chrome/profile"

# Check if already running (try IPv4, then IPv6 on macOS)
for endpoint in "http://127.0.0.1:$PORT" "http://[::1]:$PORT"; do
  if curl -s --connect-timeout 2 "$endpoint/json/version" >/dev/null 2>&1; then
    echo "CDP Chrome already running on port $PORT"
    exit 0
  fi
done

# Clean stale lock files from previous crashes
for lock in SingletonLock SingletonSocket SingletonCookie; do
  rm -f "$PROFILE/$lock" 2>/dev/null
done

# Ensure profile directory exists
mkdir -p "$PROFILE"
touch "$PROFILE/First Run" 2>/dev/null

echo "Starting CDP Chrome on port $PORT..."

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --remote-allow-origins=* \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-background-networking \
  --disable-default-apps \
  --disable-component-extensions-with-background-pages \
  &>/dev/null &

# Wait for Chrome to start (try both IPv4 and IPv6)
for i in $(seq 1 20); do
  for endpoint in "http://127.0.0.1:$PORT" "http://[::1]:$PORT"; do
    if curl -s --connect-timeout 1 "$endpoint/json/version" >/dev/null 2>&1; then
      echo "CDP Chrome started on port $PORT (PID $!)"
      exit 0
    fi
  done
  sleep 0.5
done

echo "ERROR: CDP Chrome failed to start within 10 seconds" >&2
exit 1
