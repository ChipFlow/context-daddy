#!/usr/bin/env bash
# PostToolUse hook for goals MCP tools
# Shows updated goal status as a transient message after goal changes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
PROJECT_ROOT="${PWD}"

# Get updated status
GOAL_STATUS=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" --status "${PROJECT_ROOT}" 2>/dev/null || true)

if [[ -n "${GOAL_STATUS}" ]]; then
    STATUS_ESCAPED=$(echo -n "${GOAL_STATUS}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
    cat << EOF
{
  "systemMessage": "${STATUS_ESCAPED}"
}
EOF
else
    echo '{}'
fi
