#!/bin/bash
# Log hook invocations for debugging
# Usage: log-hook.sh <hook_name> [extra_info]

HOOK_NAME="${1:-unknown}"
EXTRA_INFO="${2:-}"
LOG_FILE="${PROJECT_ROOT:-.}/.claude/hook-trace.log"

mkdir -p "$(dirname "$LOG_FILE")"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TIMESTAMP] $HOOK_NAME $EXTRA_INFO" >> "$LOG_FILE"

# Also echo to stderr so user sees it
echo "🪝 Hook fired: $HOOK_NAME $EXTRA_INFO" >&2
