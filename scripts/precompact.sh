#!/usr/bin/env bash
# PreCompact Hook for context-daddy plugin
# Runs before context compaction to:
# 1. Flag for post-compaction reorientation
# 2. Sync goal index
# 3. Tell Claude to call save_session_context MCP tool
# Note: Narrative updates are now handled by the MCP tool, not background agents

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Set flag for post-compaction reorientation
mkdir -p "${CLAUDE_DIR}"
touch "${CLAUDE_DIR}/needs-reorientation"

# Sync goal index before compaction
if [[ -f "${CLAUDE_DIR}/.current-goal" ]]; then
    uv run "${SCRIPT_DIR}/goals.py" sync --project "${PROJECT_ROOT}" 2>/dev/null || true
fi

# Tell Claude to save session context before compaction via MCP tool
MSG='**BEFORE COMPACTION**: Call `save_session_context` NOW to preserve your session insights.

Extract from your conversation history:
- **current_foci**: What you worked on (2-4 items)
- **learnings**: Non-obvious discoveries [{title, insight, context}]
- **dragons**: Gotchas or fragile areas found
- **narrative_updates**: Brief summary of what happened this session for "The Story So Far"
- **open_questions**: New uncertainties (if any)
- **resolved_questions**: Previously-open questions you answered (if any)
- **tools_update**: If you created any new scripts or dev tools this session, update .claude/TOOLS.md with them before compaction.

This information will be lost after compaction. Save it now.'

MSG_ESCAPED=$(echo "${MSG}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "additionalContext": "${MSG_ESCAPED}"
}
EOF
