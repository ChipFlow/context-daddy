#!/usr/bin/env bash
# PostToolUse hook for goals MCP tools
# Shows updated goal status as a transient message after goal changes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
PROJECT_ROOT="${PWD}"

# Read hook input from stdin to detect which tool was called
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || true)
TOOL_OUTPUT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_result',''))" 2>/dev/null || true)

# Get updated status
GOAL_STATUS=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" --status "${PROJECT_ROOT}" 2>/dev/null || true)

if [[ -n "${GOAL_STATUS}" ]]; then
    # Add continuation nudge when a step was just completed
    NUDGE=""
    if [[ "${TOOL_NAME}" == *"goal_update_step"* ]] && echo "${TOOL_OUTPUT}" | grep -q "completed"; then
        NUDGE=" | Continue to the next step."
    fi
    MSG="${GOAL_STATUS}${NUDGE}"
    STATUS_ESCAPED=$(echo -n "${MSG}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
    cat << EOF
{
  "systemMessage": "${STATUS_ESCAPED}"
}
EOF
else
    echo '{}'
fi
