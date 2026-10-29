#!/bin/bash
# Install, remove or inspect the launchd agent that keeps remote-mcp.mjs running (macOS only).
# usage: remote-mcp-launchd.sh install|uninstall|status
# The agent runs remote-mcp.mjs from this script's directory, so install from the checkout that should serve.

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LABEL="dev.steroids.cdp-chrome-remote-mcp"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/cdp-chrome-remote-mcp.log"
DOMAIN="gui/$(id -u)"

[ "$(uname -s)" = "Darwin" ] || { echo "ERROR: launchd install is macOS only." >&2; exit 1; }

case "${1:-}" in
  install)
    NODE="$(command -v node)" || { echo "ERROR: node not found on PATH." >&2; exit 1; }
    major="$("$NODE" -p 'process.versions.node.split(".")[0]')"
    [ "$major" -ge 22 ] || { echo "ERROR: Node >= 22 required, found $("$NODE" -v)." >&2; exit 1; }
    mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$NODE</string>
    <string>$SCRIPT_DIR/remote-mcp.mjs</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>HOME</key><string>$HOME</string><key>PATH</key><string>$(dirname "$NODE"):/usr/bin:/bin</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
    launchctl bootstrap "$DOMAIN" "$PLIST" || exit 1
    echo "Installed $LABEL -> $SCRIPT_DIR/remote-mcp.mjs (log: $LOG)"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
    rm -f "$PLIST"
    echo "Removed $LABEL"
    ;;
  status)
    launchctl print "$DOMAIN/$LABEL" 2>/dev/null | grep -E '^\s*(state|pid|last exit code|program|arguments)' || echo "$LABEL is not loaded"
    tail -n 5 "$LOG" 2>/dev/null
    ;;
  *)
    echo "usage: $0 install|uninstall|status" >&2
    exit 2
    ;;
esac
