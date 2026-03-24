#!/bin/bash
# Dispatcher: scan ~/.config/claude-cron/*.sh, run tasks whose schedule matches now
# Called by launchd every minute
#
# Schedule formats (declared in script header as "# claude-cron: <schedule>"):
#   daily HH:MM    — once a day at that time
#   every Nh       — every N hours (at minute 0, starting from hour 0)

# launchd runs with minimal PATH — add Homebrew and user bin
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

TASK_DIR="$HOME/.config/claude-cron"
CURRENT_H=$(date +%-H)   # no leading zero
CURRENT_M=$(date +%-M)   # no leading zero

for script in "$TASK_DIR"/*.sh; do
    [ -f "$script" ] || continue
    [ -x "$script" ] || continue

    schedule=$(grep '^# claude-cron:' "$script" | head -1 | sed 's/^# claude-cron: *//')
    [ -z "$schedule" ] && continue

    run=false

    if [[ "$schedule" =~ ^daily\ ([0-9]{1,2}):([0-9]{2})$ ]]; then
        h=${BASH_REMATCH[1]}
        m=${BASH_REMATCH[2]}
        [ "$CURRENT_H" -eq "$((10#$h))" ] && [ "$CURRENT_M" -eq "$((10#$m))" ] && run=true

    elif [[ "$schedule" =~ ^every\ ([0-9]+)h$ ]]; then
        n=${BASH_REMATCH[1]}
        [ "$((CURRENT_H % n))" -eq 0 ] && [ "$CURRENT_M" -eq 0 ] && run=true
    fi

    if [ "$run" = true ]; then
        echo "$(date): running $(basename "$script")"
        "$script" &
    fi
done
