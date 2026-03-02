#!/usr/bin/env bash
# PostToolUse hook for ExitPlanMode
# When a plan is approved and an active goal exists, nudges Claude to
# capture the plan's steps as goal steps so they persist across sessions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
CURRENT_GOAL_FILE="${CLAUDE_DIR}/.current-goal"
PLANS_DIR="${HOME}/.claude/plans"

# Quick exit if no active goal or no plans directory
if [[ ! -f "${CURRENT_GOAL_FILE}" ]] || [[ ! -d "${PLANS_DIR}" ]]; then
    echo '{}'
    exit 0
fi

# Find the most recently modified plan file (modified in the last 60 seconds)
PLAN_FILE=$(find "${PLANS_DIR}" -name '*.md' -not -name '*.backup-*' -mmin -1 -print0 2>/dev/null \
    | xargs -0 ls -t 2>/dev/null \
    | head -1)

if [[ -z "${PLAN_FILE}" ]]; then
    echo '{}'
    exit 0
fi

# Extract numbered steps from the plan (### N. Title pattern)
# Also handles ## Changes / ### N. Title patterns
export _PC_PLAN_FILE="${PLAN_FILE}"
STEPS=$(python3 -c '
import os
import re
from pathlib import Path

plan_file = os.environ["_PC_PLAN_FILE"]
content = Path(plan_file).read_text()

steps = []
for m in re.finditer(r"^###\s+(\d+)\.\s+(.+)$", content, re.MULTILINE):
    num = m.group(1)
    title = m.group(2).strip()
    # Clean up markdown formatting from title
    title = re.sub(r"`([^`]+)`", r"\1", title)
    # Truncate long titles
    if len(title) > 80:
        title = title[:77] + "..."
    steps.append(f"  {num}. {title}")

if steps:
    print("\n".join(steps))
' 2>/dev/null || true)

if [[ -z "${STEPS}" ]]; then
    echo '{}'
    exit 0
fi

# Get current goal info for the message
GOAL_STATUS=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" --status "${PROJECT_ROOT}" 2>/dev/null || true)

# Build the nudge message
MSG="📋 Plan approved with steps that should be tracked in your active goal.

Plan steps detected:
${STEPS}

**ACTION**: Use goal_add_step to add these as goal steps (skip any that duplicate existing steps). Use short kebab-case step IDs derived from the titles."

MSG_ESCAPED=$(echo -n "${MSG}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
cat << EOF
{
  "systemMessage": "${MSG_ESCAPED}"
}
EOF
