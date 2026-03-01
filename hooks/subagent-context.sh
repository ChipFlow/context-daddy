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

# Add active goal context (project-scoped)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
GOAL_CONTEXT=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" "${PWD}" 2>/dev/null || true)
if [[ -n "${GOAL_CONTEXT}" ]]; then
    CONTEXT="${CONTEXT}
${GOAL_CONTEXT}"
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
