#!/usr/bin/env bash
# Session Start Hook for context-tools plugin
# Outputs JSON with systemMessage (shown to user) and context for Claude

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# --- Cleanup old plugin versions ---
# CLAUDE_PLUGIN_ROOT is set by Claude Code and points to the current version
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    PLUGIN_CACHE_DIR="$(dirname "${CLAUDE_PLUGIN_ROOT}")"
    CURRENT_VERSION="$(basename "${CLAUDE_PLUGIN_ROOT}")"

    # Remove old cached versions (keep only current)
    if [[ -d "${PLUGIN_CACHE_DIR}" ]]; then
        for OLD_VERSION in "${PLUGIN_CACHE_DIR}"/*; do
            if [[ -d "${OLD_VERSION}" && "$(basename "${OLD_VERSION}")" != "${CURRENT_VERSION}" ]]; then
                rm -rf "${OLD_VERSION}" 2>/dev/null || true
            fi
        done
    fi
fi

# --- Kill ALL stale indexing processes for this project ---
PIDS=$(pgrep -f "generate-repo-map.py.*${PROJECT_ROOT}" 2>/dev/null || true)
if [[ -n "${PIDS}" ]]; then
    # SIGTERM first
    echo "${PIDS}" | xargs kill 2>/dev/null || true
    sleep 0.5
    # SIGKILL any survivors
    PIDS=$(pgrep -f "generate-repo-map.py.*${PROJECT_ROOT}" 2>/dev/null || true)
    if [[ -n "${PIDS}" ]]; then
        echo "${PIDS}" | xargs kill -9 2>/dev/null || true
        sleep 0.2
    fi
fi

# Ensure .claude directory exists
mkdir -p "${CLAUDE_DIR}"

# Generate project manifest (quick, runs synchronously)
# Redirect stdout to avoid mixing with our JSON output
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" >/dev/null 2>&1 || true

REPO_MAP="${CLAUDE_DIR}/repo-map.md"
CACHE_FILE="${CLAUDE_DIR}/repo-map-cache.json"

# Check cache version - must match CACHE_VERSION in generate-repo-map.py
EXPECTED_CACHE_VERSION=3
if [[ -f "${CACHE_FILE}" ]]; then
    CACHE_VERSION=$(python3 -c "import json; print(json.load(open('${CACHE_FILE}')).get('version', 0))" 2>/dev/null || echo "0")
    if [[ "${CACHE_VERSION}" != "${EXPECTED_CACHE_VERSION}" ]]; then
        # Cache is outdated, delete it to force full reindex
        rm -f "${CACHE_FILE}" "${REPO_MAP}"
    fi
fi
# Update last check timestamp so PreToolUse doesn't immediately re-check
touch "${CLAUDE_DIR}/.last-cache-check"

# Check if repo-map process is already running (use pgrep, not lock file)
is_running() {
    pgrep -f "generate-repo-map.py.*${PROJECT_ROOT}" >/dev/null 2>&1
}

# Determine repo map status message
if [[ -f "${REPO_MAP}" ]]; then
    SYMBOL_COUNT=$(grep -c "^\*\*" "${REPO_MAP}" 2>/dev/null || echo "0")
    # Count naming clashes (similar classes + similar functions)
    CLASH_COUNT=$(python3 -c "
import re
from pathlib import Path
content = Path('${REPO_MAP}').read_text()
classes = len(re.findall(r'\*\*[^*]+\*\* \([^)]+\) ↔', content))
print(classes)
" 2>/dev/null || echo "0")
    if is_running; then
        STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols (updating in background)"
    elif [[ "${CLASH_COUNT}" -gt 0 ]]; then
        STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols, ${CLASH_COUNT} naming clash(es)"
    else
        STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols"
    fi
    # Start background update if not already running
    if ! is_running; then
        (
            nohup uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" \
                > "${CLAUDE_DIR}/repo-map-build.log" 2>&1 &
        ) &
    fi
elif is_running; then
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

# Add repo map summary and MCP tools info
DB_FILE="${CLAUDE_DIR}/repo-map.db"
if [[ -f "${DB_FILE}" ]]; then
    CONTEXT="${CONTEXT}\n\n**PREFER these MCP tools over Grep/Search for code symbol lookups:**"
    CONTEXT="${CONTEXT}\n- mcp__plugin_context-tools_repo-map__search_symbols: Find functions/classes/methods by pattern (e.g., 'get_*', '*Handler')"
    CONTEXT="${CONTEXT}\n- mcp__plugin_context-tools_repo-map__get_file_symbols: List all symbols in a file"
    CONTEXT="${CONTEXT}\n- mcp__plugin_context-tools_repo-map__get_symbol_content: Get full source code of a symbol by name"
    CONTEXT="${CONTEXT}\n"
    CONTEXT="${CONTEXT}\nThese use a pre-built SQLite index - much faster than Grep for finding definitions."
    CONTEXT="${CONTEXT}\nUse these FIRST when looking for code symbols. Use Grep only for arbitrary text searches."
elif [[ -f "${REPO_MAP}" ]]; then
    CONTEXT="${CONTEXT}\nRepo map available with ${SYMBOL_COUNT} symbols in .claude/repo-map.md"
fi

if [[ -f "${REPO_MAP}" && "${CLASH_COUNT}" -gt 0 ]]; then
    CONTEXT="${CONTEXT}\n${CLASH_COUNT} potential naming clash(es) detected. Use /clash-summary or /resolve-clashes to review."
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
