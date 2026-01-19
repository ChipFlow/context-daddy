#!/usr/bin/env bash
# Stop Hook for Post-Compaction Reorientation
# Blocks Claude after compaction and injects key context for orientation

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
MARKER_FILE="${CLAUDE_DIR}/needs-reorientation"

# Check if marker exists and is recent (within 5 minutes)
if [[ ! -f "${MARKER_FILE}" ]]; then
    # No reorientation needed
    echo '{"decision": "approve"}'
    exit 0
fi

# Check if marker is recent (within 5 minutes)
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS
    MARKER_AGE=$(( $(date +%s) - $(stat -f %m "${MARKER_FILE}") ))
else
    # Linux
    MARKER_AGE=$(( $(date +%s) - $(stat -c %Y "${MARKER_FILE}") ))
fi

if [[ ${MARKER_AGE} -gt 300 ]]; then
    # Marker is older than 5 minutes - ignore it
    rm -f "${MARKER_FILE}"
    echo '{"decision": "approve"}'
    exit 0
fi

# Remove marker immediately (so we only do this once)
rm -f "${MARKER_FILE}"

# Extract key context using helper script
CONTEXT_DATA=$(uv run "${SCRIPT_DIR}/extract-context.py" "${PROJECT_ROOT}" 2>/dev/null || echo "{}")

# Build refresh instructions with injected context
INSTRUCTIONS="🔄 **Context Refresh After Compaction**

**Project Root**: ${PROJECT_ROOT}"

# Add top-level structure
TOP_DIRS=$(echo "${CONTEXT_DATA}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    dirs = data.get('top_dirs', [])
    if dirs:
        parts = []
        for d in dirs[:12]:
            if d['type'] == 'dir':
                parts.append(f\"{d['name']}/ ({d.get('files', '?')} files)\")
            else:
                parts.append(d['name'])
        print(', '.join(parts))
except:
    pass
" 2>/dev/null || true)

if [[ -n "${TOP_DIRS}" ]]; then
    INSTRUCTIONS="${INSTRUCTIONS}
**Structure**: ${TOP_DIRS}"
fi

# Inject narrative sections
HAS_NARRATIVE=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_narrative', False))" 2>/dev/null || echo "False")

if [[ "${HAS_NARRATIVE}" == "True" ]]; then
    NARRATIVE_SUMMARY=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_summary', ''))" 2>/dev/null || true)
    NARRATIVE_FOCI=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_foci', ''))" 2>/dev/null || true)
    NARRATIVE_DRAGONS=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_dragons', ''))" 2>/dev/null || true)

    if [[ -n "${NARRATIVE_SUMMARY}" ]]; then
        INSTRUCTIONS="${INSTRUCTIONS}

📖 **Project Summary**: ${NARRATIVE_SUMMARY}"
    fi
    if [[ -n "${NARRATIVE_FOCI}" ]]; then
        INSTRUCTIONS="${INSTRUCTIONS}

🎯 **Current Foci**:
${NARRATIVE_FOCI}"
    fi
    if [[ -n "${NARRATIVE_DRAGONS}" ]]; then
        INSTRUCTIONS="${INSTRUCTIONS}

🐉 **Dragons & Gotchas**:
${NARRATIVE_DRAGONS}"
    fi
fi

INSTRUCTIONS="${INSTRUCTIONS}

---
**Actions Required:**

1. **Read ${CLAUDE_DIR}/CLAUDE.md** (if exists) - Project rules
2. **Read ${CLAUDE_DIR}/learnings.md** (if exists) - Recent discoveries
3. **Update narrative** (if significant learning): Run \`/context-daddy:refresh\`

Then continue with the current task."

# Escape for JSON
INSTRUCTIONS_ESCAPED=$(echo -n "$INSTRUCTIONS" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

# Return blocking decision
cat << EOF
{
  "decision": "block",
  "reason": "${INSTRUCTIONS_ESCAPED}"
}
EOF
