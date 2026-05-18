#!/bin/bash
# Temporary workaround: trigger context compaction before hitting 20MB API limit.
# Remove once anthropics/claude-code#8092 is officially fixed.
#
# PostToolUse → check transcript file size → at 16MB alert to /compact

set -euo pipefail

TP=$(cat | jq -r '.transcript_path // empty' 2>/dev/null)
[ -z "$TP" ] || [ ! -f "$TP" ] && exit 0

SIZE=$(stat -f%z "$TP" 2>/dev/null || stat -c%s "$TP" 2>/dev/null || echo 0)

if [ "$SIZE" -gt 16777216 ]; then
  MB=$((SIZE / 1048576))
  echo "🛑 [guard-payload] ${MB}MB / 20MB — run /compact now" >&2
  echo "{\"systemMessage\":\"[guard-payload] Context is ${MB}MB, approaching 20MB API limit. Run /compact NOW to avoid Request too large error.\"}"
fi
