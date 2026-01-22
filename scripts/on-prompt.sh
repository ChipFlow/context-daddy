#!/usr/bin/env bash
# UserPromptSubmit hook - injects context after plan mode clears context
# Detects SessionEnd -> UserPromptSubmit pattern (no SessionStart in between)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
MARKER_FILE="${CLAUDE_DIR}/session-ended"

# Check if this is a post-plan prompt (marker exists)
if [[ -f "${MARKER_FILE}" ]]; then
    # Remove marker so we don't inject twice
    rm -f "${MARKER_FILE}"

    # Log for debugging
    if [[ -x "${SCRIPT_DIR}/log-hook.sh" ]]; then
        "${SCRIPT_DIR}/log-hook.sh" "PostPlanContextInjection" "triggered" 2>/dev/null || true
    fi

    # Extract key context using helper script (same as Stop hook)
    CONTEXT_DATA=$(uv run "${SCRIPT_DIR}/extract-context.py" "${PROJECT_ROOT}" 2>/dev/null || echo "{}")

    # Build context refresh message (similar to stop-reorient.sh)
    CONTEXT="🔄 **Context Refresh After Compaction**"

    # Add project structure
    DIR_TREE=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dir_tree', ''))" 2>/dev/null || true)
    if [[ -n "${DIR_TREE}" ]]; then
        CONTEXT="${CONTEXT}

**Project Structure**:
\`\`\`
${DIR_TREE}
\`\`\`"
    fi

    # Inject narrative sections
    HAS_NARRATIVE=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_narrative', False))" 2>/dev/null || echo "False")

    if [[ "${HAS_NARRATIVE}" == "True" ]]; then
        NARRATIVE_SUMMARY=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_summary', ''))" 2>/dev/null || true)
        NARRATIVE_FOCI=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_foci', ''))" 2>/dev/null || true)
        NARRATIVE_DRAGONS=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_dragons', ''))" 2>/dev/null || true)

        if [[ -n "${NARRATIVE_SUMMARY}" ]]; then
            CONTEXT="${CONTEXT}

📖 **Project Summary**: ${NARRATIVE_SUMMARY}"
        fi
        if [[ -n "${NARRATIVE_FOCI}" ]]; then
            CONTEXT="${CONTEXT}

🎯 **Current Foci**:
${NARRATIVE_FOCI}"
        fi
        if [[ -n "${NARRATIVE_DRAGONS}" ]]; then
            CONTEXT="${CONTEXT}

🐉 **Dragons & Gotchas**:
${NARRATIVE_DRAGONS}"
        fi
    fi

    # Add action instructions
    CONTEXT="${CONTEXT}

---
**Actions Required:**

1. **Read ${CLAUDE_DIR}/CLAUDE.md** (if exists) - Project rules
2. **Read ${CLAUDE_DIR}/learnings.md** (if exists) - Recent discoveries
3. **Update narrative** (if significant learning): Run \`/context-daddy:refresh\`

Then continue with the current task."

    # Output JSON with context to inject
    python3 -c "
import json
import sys
context = sys.stdin.read()
print(json.dumps({'context': context}))
" <<< "${CONTEXT}"
else
    # Normal prompt, no injection needed
    echo '{"continue": true}'
fi
