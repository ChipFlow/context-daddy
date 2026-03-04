#!/usr/bin/env bash
# PostToolUse hook for goals MCP tools
# Shows updated goal status after goal changes.
# When a step is completed, injects the next step details and a strong
# continuation directive so Claude doesn't stop and wait.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
PROJECT_ROOT="${PWD}"

# Read hook input from stdin to detect which tool was called
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || true)
TOOL_OUTPUT=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_result',''))" 2>/dev/null || true)

# Get updated status
GOAL_STATUS=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" --status "${PROJECT_ROOT}" 2>/dev/null || true)

if [[ -z "${GOAL_STATUS}" ]]; then
    echo '{}'
    exit 0
fi

# When a step was just completed, inject strong continuation context
if [[ "${TOOL_NAME}" == *"goal_update_step"* ]] && echo "${TOOL_OUTPUT}" | grep -q "completed"; then
    # Check if all steps are done
    if echo "${TOOL_OUTPUT}" | grep -q "All steps done"; then
        STATUS_ESCAPED=$(echo -n "${GOAL_STATUS} | All steps complete!" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
        cat << EOF
{
  "systemMessage": "${STATUS_ESCAPED}"
}
EOF
    else
        # Get full goal context with next step details
        GOAL_CONTEXT=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" "${PROJECT_ROOT}" 2>/dev/null || true)
        CONTINUATION="✅ Step completed. Here is your updated goal context:\n\n${GOAL_CONTEXT}\n\n**ACTION REQUIRED**: Continue immediately with the next step shown above. Do NOT stop to ask the user — they expect you to keep working through the goal steps. Only pause if you need user input or clarification for the NEXT step."
        CONTEXT_ESCAPED=$(echo -e "${CONTINUATION}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
        STATUS_ESCAPED=$(echo -n "${GOAL_STATUS}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
        cat << EOF
{
  "systemMessage": "${STATUS_ESCAPED}",
  "additionalContext": "${CONTEXT_ESCAPED}"
}
EOF
    fi
else
    STATUS_ESCAPED=$(echo -n "${GOAL_STATUS}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
    cat << EOF
{
  "systemMessage": "${STATUS_ESCAPED}"
}
EOF
fi
