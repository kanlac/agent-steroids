#!/bin/bash
# CDP Chrome shared instance launcher
# Deploy to: ~/.config/cdp-chrome/start.sh
#
# Starts Chrome in GUI mode with remote debugging enabled.
# Key: does NOT use --enable-automation, so navigator.webdriver stays false.

PORT=$(cat ~/.config/cdp-chrome/port)
PROFILE="$HOME/.config/cdp-chrome/profile"

# Check if already running
if curl -s --connect-timeout 2 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "CDP Chrome already running on port $PORT"
  exit 0
fi

echo "Starting CDP Chrome on port $PORT..."

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --no-default-browser-check \
  --disable-sync \
  --disable-background-networking \
  --disable-default-apps \
  --disable-component-extensions-with-background-pages \
  &>/dev/null &

# Wait for Chrome to start
for i in $(seq 1 10); do
  if curl -s --connect-timeout 1 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
    echo "CDP Chrome started on port $PORT (PID $!)"
    exit 0
  fi
  sleep 1
done

echo "ERROR: CDP Chrome failed to start within 10 seconds" >&2
exit 1
