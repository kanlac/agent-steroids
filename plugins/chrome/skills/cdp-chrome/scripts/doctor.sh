#!/bin/bash
# Doctor/setup check for cdp-chrome current-user configuration.

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

cdp_apply_config

status=0

echo "cdp-chrome doctor"
echo "  config:      $CDP_CONFIG_PATH"
echo "  port:        $CDP_PORT"
echo "  profile_dir: $CDP_PROFILE_DIR"
echo "  user:        $(id -un 2>/dev/null || whoami 2>/dev/null || echo unknown)"
echo

case "$CDP_PORT" in
  ''|*[!0-9]*)
    echo "ERROR: cdp-chrome.port must be a number." >&2
    status=1
    ;;
  *)
    if [ "$CDP_PORT" -lt 1 ] || [ "$CDP_PORT" -gt 65535 ]; then
      echo "ERROR: cdp-chrome.port must be between 1 and 65535." >&2
      status=1
    fi
    ;;
esac

if mkdir -p "$CDP_PROFILE_DIR" 2>/dev/null; then
  echo "OK: profile directory exists or was created."
else
  echo "ERROR: cannot create profile directory: $CDP_PROFILE_DIR" >&2
  status=1
fi

if cdp_http_ready "$CDP_PORT"; then
  echo "OK: Chrome DevTools endpoint responds on port $CDP_PORT."
else
  echo "INFO: no Chrome DevTools endpoint responds on port $CDP_PORT."
fi

if ! cdp_validate_listener "$CDP_PORT" "$CDP_PROFILE_DIR" "doctor"; then
  status=1
fi

# Optional remote MCP entry (remote-mcp.mjs); absent is fine.
REMOTE_SOCK="$(python3 -c 'import json,os
base=os.environ.get("APPDATA",os.path.expanduser("~/.config"))
try: s=json.load(open(os.environ.get("CDP_CHROME_CONFIG") or os.path.join(base,"steroids.json"))).get("cdp-chrome",{}).get("remote_mcp_socket")
except Exception: s=None
print(os.path.expanduser(s or os.path.join(base,"cdp-chrome","remote","mcp.sock")))')"
if [ -S "$REMOTE_SOCK" ]; then
  mode="$(stat -f %Lp "$REMOTE_SOCK" 2>/dev/null || stat -c %a "$REMOTE_SOCK" 2>/dev/null)"
  if curl -s --max-time 3 --unix-socket "$REMOTE_SOCK" -H 'Content-Type: application/json' http://localhost/mcp \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | grep -q '"name":"open"'; then
    echo "OK: remote MCP answers on $REMOTE_SOCK (mode $mode)."
  else
    echo "ERROR: remote MCP socket $REMOTE_SOCK exists but does not answer; see remote-mcp-launchd.sh status." >&2
    status=1
  fi
  [ "$mode" = "600" ] || { echo "ERROR: remote MCP socket mode is $mode, expected 600." >&2; status=1; }
else
  echo "INFO: remote MCP not running (optional; see references/remote-mcp.md)."
fi

echo
if [ "$status" -eq 0 ]; then
  if cdp_http_ready "$CDP_PORT"; then
    echo "Doctor passed. MCP can use http://127.0.0.1:$CDP_PORT for this OS user."
  else
    echo "Doctor passed for config/port availability. Start Chrome with:"
    echo "  $SCRIPT_DIR/start.sh"
  fi
else
  echo "Doctor failed. Remediation:"
  echo "  1. Give each OS user a unique cdp-chrome.port in ${APPDATA:-$HOME/.config}/steroids.json."
  echo "  2. Ensure profile_dir is unique per OS user, for example ~/.config/cdp-chrome/profile."
  echo "  3. Stop the conflicting Chrome/process or choose another port, then rerun this doctor."
fi

exit "$status"
