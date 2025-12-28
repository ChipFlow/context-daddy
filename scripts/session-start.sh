#!/usr/bin/env bash
# Session Start Hook for context-tools plugin
# Outputs JSON with systemMessage (shown to user) and context for Claude

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Ensure .claude directory exists
mkdir -p "${CLAUDE_DIR}"

# Generate project manifest (quick, runs synchronously)
# Redirect stdout to avoid mixing with our JSON output
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" >/dev/null 2>&1 || true

REPO_MAP="${CLAUDE_DIR}/repo-map.md"
LOCK_FILE="${CLAUDE_DIR}/repo-map-cache.lock"
CACHE_FILE="${CLAUDE_DIR}/repo-map-cache.json"

# Check cache version - must match CACHE_VERSION in generate-repo-map.py
EXPECTED_CACHE_VERSION=2
CHECK_MARKER="${CLAUDE_DIR}/.cache-checked-v2"
if [[ -f "${CACHE_FILE}" ]]; then
    CACHE_VERSION=$(python3 -c "import json; print(json.load(open('${CACHE_FILE}')).get('version', 0))" 2>/dev/null || echo "0")
    if [[ "${CACHE_VERSION}" != "${EXPECTED_CACHE_VERSION}" ]]; then
        # Cache is outdated, delete it to force full reindex
        rm -f "${CACHE_FILE}" "${REPO_MAP}"
    fi
fi
# Mark as checked so PreToolUse hook can skip redundant checks
touch "${CHECK_MARKER}"

# Determine repo map status message
if [[ -f "${REPO_MAP}" ]]; then
    SYMBOL_COUNT=$(grep -c "^\*\*" "${REPO_MAP}" 2>/dev/null || echo "0")
    if [[ -f "${LOCK_FILE}" ]]; then
        STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols (updating in background)"
    else
        STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols"
    fi
    # Start background update if not already running
    if [[ ! -f "${LOCK_FILE}" ]]; then
        (
            nohup uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" \
                > "${CLAUDE_DIR}/repo-map-build.log" 2>&1 &
        ) &
    fi
elif [[ -f "${LOCK_FILE}" ]]; then
    STATUS_MSG="[context-tools] Building repo map in background..."
else
    STATUS_MSG="[context-tools] Starting repo map generation..."
    # Start repo map generation
    (
        nohup uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" \
            > "${CLAUDE_DIR}/repo-map-build.log" 2>&1 &
    ) &
fi

# Build context for Claude (goes to stdout, added to Claude's context)
CONTEXT=""

# Add manifest info
MANIFEST="${CLAUDE_DIR}/project-manifest.json"
if [[ -f "${MANIFEST}" ]]; then
    MANIFEST_INFO=$(python3 -c "
import json
try:
    with open('${MANIFEST}') as f:
        m = json.load(f)
    lines = []
    lines.append(f\"Project: {m.get('project_name', 'unknown')}\")
    langs = m.get('languages', [])
    if langs:
        lines.append(f\"Languages: {', '.join(langs)}\")
    build = m.get('build_system', {})
    if build.get('type'):
        lines.append(f\"Build: {build['type']}\")
    print('\\n'.join(lines))
except:
    pass
" 2>/dev/null || true)
    if [[ -n "${MANIFEST_INFO}" ]]; then
        CONTEXT="${MANIFEST_INFO}"
    fi
fi

# Add learnings count
LEARNINGS="${CLAUDE_DIR}/learnings.md"
if [[ -f "${LEARNINGS}" ]]; then
    LEARNING_COUNT=$(grep -c "^## " "${LEARNINGS}" 2>/dev/null || echo "0")
    if [[ "${LEARNING_COUNT}" -gt 0 ]]; then
        CONTEXT="${CONTEXT}\n${LEARNING_COUNT} project learning(s) in .claude/learnings.md"
    fi
fi

# Add repo map summary
if [[ -f "${REPO_MAP}" ]]; then
    CONTEXT="${CONTEXT}\nRepo map available with ${SYMBOL_COUNT} symbols in .claude/repo-map.md"
fi

# Output JSON with systemMessage for user display
# Escape special characters for JSON
STATUS_MSG_ESCAPED=$(echo -n "$STATUS_MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
CONTEXT_ESCAPED=$(echo -e "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "systemMessage": "${STATUS_MSG_ESCAPED}",
  "additionalContext": "${CONTEXT_ESCAPED}",
  "continue": true
}
EOF
