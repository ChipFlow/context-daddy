#!/usr/bin/env bash
# Stop Hook for Post-Compaction Reorientation
# Blocks Claude after compaction and forces context restoration by reading files

set -euo pipefail

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

# Check if narrative exists
HAS_NARRATIVE=""
if [[ -f "${CLAUDE_DIR}/narrative.md" ]]; then
    HAS_NARRATIVE="yes"
fi

# Build refresh instructions
INSTRUCTIONS="🔄 **Context Refresh Required After Compaction**

**STEP 1: Capture what we learned this session**"

if [[ -n "${HAS_NARRATIVE}" ]]; then
    INSTRUCTIONS="${INSTRUCTIONS}

📖 **Update the project narrative** (if significant learning occurred):
   Run \`/context-tools:update-narrative\` with a brief summary of:
   • What we worked on and key decisions made
   • New understanding or insights gained
   • Any dragons discovered or questions answered"
fi

INSTRUCTIONS="${INSTRUCTIONS}

📝 **Update ${CLAUDE_DIR}/learnings.md** with:
   • New features/APIs implemented
   • Integration points added (e.g., Python bindings, new modules)
   • Solution approaches discussed and agreed with user
   • Non-obvious design decisions or debugging insights

**STEP 2: Restore context by reading files in order:**

1. **Read ${CLAUDE_DIR}/CLAUDE.md** (if it exists) - Project rules and guidelines"

if [[ -n "${HAS_NARRATIVE}" ]]; then
    INSTRUCTIONS="${INSTRUCTIONS}
2. **Read ${CLAUDE_DIR}/narrative.md** - Project story, current foci, and dragons
3. **Read ${CLAUDE_DIR}/learnings.md** (if it exists) - Recent work and discoveries"
else
    INSTRUCTIONS="${INSTRUCTIONS}
2. **Read ${CLAUDE_DIR}/learnings.md** (if it exists) - Recent work and discoveries"
fi

INSTRUCTIONS="${INSTRUCTIONS}

**STEP 3: Query MCP tools to refresh project structure:**
   - Use \`mcp__plugin_context-tools_repo-map__list_files(\"*.py\")\` to see indexed files
   - Use \`mcp__plugin_context-tools_repo-map__search_symbols(\"*\", limit=10)\` to see key symbols

After completing these steps, you'll have full context restored. Then continue with the current task."

# Escape for JSON
INSTRUCTIONS_ESCAPED=$(echo -n "$INSTRUCTIONS" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

# Return blocking decision
cat << EOF
{
  "decision": "block",
  "reason": "${INSTRUCTIONS_ESCAPED}"
}
EOF
