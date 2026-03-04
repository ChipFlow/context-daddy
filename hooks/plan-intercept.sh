#!/usr/bin/env bash
# PreToolUse hook for EnterPlanMode
#
# When Claude tries to enter plan mode:
# - If NO active goal exists → nudge to create a goal first, then plan
#   individual steps
# - If active goal exists → allow (it's planning a single step)
set -eo pipefail

PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
CURRENT_GOAL_FILE="${CLAUDE_DIR}/.current-goal"

# If there's an active goal, allow plan mode (planning a single step)
if [[ -f "${CURRENT_GOAL_FILE}" ]]; then
    echo '{"decision": "approve"}'
    exit 0
fi

# No active goal — nudge Claude to create a goal first
cat << 'EOF'
{
  "decision": "approve",
  "additionalContext": "⚠️ **No active goal — consider using the goal system instead of a standalone plan.**\n\nFor multi-step tasks:\n1. Create a goal with `goal_create` (title + objective)\n2. Add high-level steps with `goal_add_step` (one per major milestone)\n3. Then use EnterPlanMode for just the CURRENT step's implementation details\n\nGoals persist across sessions and compactions. Plans don't.\n\nIf this is truly a small, single-step task, proceed with the plan. Otherwise, create a goal first."
}
EOF
