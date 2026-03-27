#!/bin/bash
# Launch Claude Code agent in a tmux session/window.
# Each invocation creates a fresh window with a timestamped name.
#
# Usage: clean-cron-send.sh --session NAME --window NAME --dir PATH --agent AGENT
#
# The agent's initialPrompt (defined in agent frontmatter) is auto-submitted.
# No need to pass a prompt — just specify which agent to run.
#
# Telegram notification: if ~/.claude/channels/telegram/.env contains a bot token,
# sends a startup notification via Telegram Bot API (pure HTTP, no MCP dependency).

set -euo pipefail

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -s|--session) SESSION="$2"; shift 2;;
    -w|--window)  WINDOW="$2";  shift 2;;
    -d|--dir)     DIR="$2";     shift 2;;
    -a|--agent)   AGENT="$2";   shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

# Validate
if [[ -z "${SESSION:-}" || -z "${WINDOW:-}" || -z "${DIR:-}" || -z "${AGENT:-}" ]]; then
  echo "Usage: $0 --session NAME --window NAME --dir DIR --agent AGENT"
  exit 1
fi

# Expand ~ in DIR
DIR="${DIR/#\~/$HOME}"

# Append timestamp to window name to ensure uniqueness
TIMESTAMP=$(date +%y%m%d-%H%M)
WINDOW="${WINDOW}-${TIMESTAMP}"

# --- Telegram notification (best-effort, non-blocking) ---
TG_ENV="$HOME/.claude/channels/telegram/.env"
TG_ACCESS="$HOME/.claude/channels/telegram/access.json"
if [[ -f "$TG_ENV" && -f "$TG_ACCESS" ]]; then
    TG_TOKEN=$(grep -m1 'TELEGRAM_BOT_TOKEN=' "$TG_ENV" | cut -d= -f2-)
    TG_CHAT=$(python3 -c "import json; print(json.load(open('$TG_ACCESS'))['allowFrom'][0])" 2>/dev/null || true)
    if [[ -n "${TG_TOKEN:-}" && -n "${TG_CHAT:-}" ]]; then
        curl -sf "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
          -d chat_id="$TG_CHAT" \
          -d text="⏰ clean-cron: ${WINDOW} started" \
          >/dev/null 2>&1 &
    fi
fi

# Create session if it doesn't exist
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-session -d -s "$SESSION" -n "$WINDOW" -c "$DIR"
else
    tmux new-window -t "$SESSION" -n "$WINDOW" -c "$DIR"
fi

# Start Claude with agent (initialPrompt auto-submitted by agent frontmatter)
tmux send-keys -t "${SESSION}:${WINDOW}" \
  "cd '$DIR' && claude --agent '$AGENT' --dangerously-skip-permissions" Enter

# Wait for trust dialog and accept
sleep 5
tmux send-keys -t "${SESSION}:${WINDOW}" Enter

echo "$(date): started claude --agent $AGENT in ${SESSION}:${WINDOW} (dir: $DIR)"
