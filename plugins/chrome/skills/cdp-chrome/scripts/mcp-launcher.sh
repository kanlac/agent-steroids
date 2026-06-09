#!/bin/bash
# Plugin-local MCP launcher for cdp-chrome.
# Reads the current OS user's steroids config, validates the listener when present,
# then execs chrome-devtools-mcp against that user's configured port.

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

cdp_apply_config

if cdp_http_ready "$CDP_PORT"; then
  cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "MCP launcher" || exit 1
else
  # Detect occupied non-CDP ports before chrome-devtools-mcp starts.
  cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "MCP launcher" || exit 1
  echo "ERROR: cdp-chrome is not running on configured port $CDP_PORT." >&2
  echo "Run: $SCRIPT_DIR/start.sh" >&2
  echo "Then run: $SCRIPT_DIR/doctor.sh" >&2
  exit 1
fi

exec npx -y chrome-devtools-mcp@latest \
  --browserUrl "http://127.0.0.1:$CDP_PORT" \
  --no-usage-statistics \
  --no-category-performance \
  --no-category-emulation \
  --no-category-network
