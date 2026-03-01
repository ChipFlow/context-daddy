#!/usr/bin/env bash
# SubagentStart hook - inject key context for subagents spawned via Task tool
# Provides project summary and MCP tools reminder so subagents can be effective

set -euo pipefail

CLAUDE_DIR="${PWD}/.claude"
CONTEXT=""

# Add project summary from narrative if available
if [[ -f "${CLAUDE_DIR}/narrative.md" ]]; then
    # Extract just the summary section (first ~300 chars)
    SUMMARY=$(sed -n '/^## Summary/,/^## /p' "${CLAUDE_DIR}/narrative.md" 2>/dev/null | head -10 | tail -n +2 | head -c 300)
    if [[ -n "${SUMMARY}" ]]; then
        CONTEXT="📖 Project: ${SUMMARY}..."
    fi
fi

# Add active goal context
CURRENT_GOAL_FILE="${CLAUDE_DIR}/.current-goal"
ACTIVE_GOALS_FILE="${CLAUDE_DIR}/active-goals.json"
if [[ -f "${CURRENT_GOAL_FILE}" && -f "${ACTIVE_GOALS_FILE}" ]]; then
    GOAL_INFO=$(python3 -c "
import json
try:
    goal_id = open('${CURRENT_GOAL_FILE}').read().strip()
    index = json.load(open('${ACTIVE_GOALS_FILE}'))
    for g in index.get('goals', []):
        if g['id'] == goal_id:
            print(f\"{g['name']}|{g['current_step']}|{g['total_steps']}|{g.get('current_step_text', '')}\")
            break
except Exception:
    pass
" 2>/dev/null || true)

    if [[ -n "${GOAL_INFO}" ]]; then
        GOAL_NAME=$(echo "${GOAL_INFO}" | cut -d'|' -f1)
        GOAL_STEP_TEXT=$(echo "${GOAL_INFO}" | cut -d'|' -f4)
        CONTEXT="${CONTEXT}
🎯 Goal: ${GOAL_NAME} - Current step: ${GOAL_STEP_TEXT}"
    fi
fi

# Add MCP tools reminder
CONTEXT="${CONTEXT}

⚡ MCP tools available for fast code search:
• search_symbols(\"pattern\") - find functions/classes
• get_symbol_content(\"name\") - get source code
• list_files(\"*.py\") - find files
• md_outline/md_get_section - navigate markdown"

# Escape for JSON
CONTEXT_ESCAPED=$(echo -e "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "additionalContext": "${CONTEXT_ESCAPED}"
}
EOF
