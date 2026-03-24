#!/bin/bash
# Generic script: send a prompt to Claude Code running in a tmux session/window
# Auto-creates session/window and launches Claude if needed
#
# Usage: claude-tmux-send.sh --session NAME --window NAME --dir PATH --prompt "TEXT"

set -euo pipefail

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -s|--session) SESSION="$2"; shift 2;;
    -w|--window)  WINDOW="$2";  shift 2;;
    -d|--dir)     DIR="$2";     shift 2;;
    -p|--prompt)  PROMPT="$2";  shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

# Validate
if [[ -z "${SESSION:-}" || -z "${WINDOW:-}" || -z "${DIR:-}" || -z "${PROMPT:-}" ]]; then
  echo "Usage: $0 --session NAME --window NAME --dir DIR --prompt PROMPT"
  exit 1
fi

NEEDS_STARTUP=false

# Create session if it doesn't exist
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-session -d -s "$SESSION" -n "$WINDOW" -c "$DIR" -e "DISABLE_AUTO_UPDATE=true"
    NEEDS_STARTUP=true
fi

# Create window if it doesn't exist (session exists but window was closed)
if ! tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -q "^${WINDOW}$"; then
    tmux new-window -t "$SESSION" -n "$WINDOW" -c "$DIR"
    NEEDS_STARTUP=true
fi

# Start Claude if this is a fresh window
if [ "$NEEDS_STARTUP" = true ]; then
    tmux send-keys -t "${SESSION}:${WINDOW}" "cd '$DIR' && claude --dangerously-skip-permissions" Enter
    sleep 5   # wait for trust prompt
    tmux send-keys -t "${SESSION}:${WINDOW}" Enter  # accept trust
    sleep 15  # wait for Claude to fully start
    echo "$(date): started Claude in ${SESSION}:${WINDOW} (dir: $DIR)"
fi

# Clear any pending input, then send prompt
tmux send-keys -t "${SESSION}:${WINDOW}" Escape
sleep 1
tmux send-keys -t "${SESSION}:${WINDOW}" "$PROMPT" Enter
echo "$(date): sent prompt to ${SESSION}:${WINDOW}"
