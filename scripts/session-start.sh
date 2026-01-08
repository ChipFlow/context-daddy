#!/usr/bin/env bash
# Session Start Hook for context-tools plugin
# Outputs JSON with systemMessage (shown to user) and context for Claude
# NOTE: Indexing is now handled by the MCP server - no subprocess spawning here

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

# Ensure .claude directory exists
mkdir -p "${CLAUDE_DIR}"

# Generate project manifest (quick, runs synchronously)
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" >/dev/null 2>&1 || true

REPO_MAP="${CLAUDE_DIR}/repo-map.md"
DB_FILE="${CLAUDE_DIR}/repo-map.db"

# Determine repo map status message
if [[ -f "${DB_FILE}" ]]; then
    SYMBOL_COUNT=$(sqlite3 "${DB_FILE}" "SELECT COUNT(*) FROM symbols" 2>/dev/null || echo "0")
    STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols (MCP server handles updates)"
elif [[ -f "${REPO_MAP}" ]]; then
    SYMBOL_COUNT=$(grep -c "^\*\*" "${REPO_MAP}" 2>/dev/null || echo "0")
    STATUS_MSG="[context-tools] Repo map: ${SYMBOL_COUNT} symbols"
else
    STATUS_MSG="[context-tools] MCP server will build repo map on first query"
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
if [[ -f "${DB_FILE}" ]]; then
    CONTEXT="${CONTEXT}\n\n⚡ **BEFORE using grep/find/ls for code**: ALWAYS try MCP tools first (mcp__plugin_context-tools_repo-map__*)."
    CONTEXT="${CONTEXT}\n• Finding enum/struct/class definition? → search_symbols(\"TypeName\") then get_symbol_content(\"TypeName\")"
    CONTEXT="${CONTEXT}\n• Finding functions by pattern? → search_symbols(\"setup_*\") or search_symbols(\"*Handler\")"
    CONTEXT="${CONTEXT}\n• What's in a file? → get_file_symbols(\"path/to/file.rs\")"
    CONTEXT="${CONTEXT}\n• Finding files? → list_files(\"*.va\") or list_files(\"*psp103*\") - faster than find/ls"
    CONTEXT="${CONTEXT}\n• 10-100x faster than grep/find/ls. Use grep only for text/comments. /context-tools:mcp-help for more."
elif [[ -f "${REPO_MAP}" ]]; then
    CONTEXT="${CONTEXT}\nRepo map available with ${SYMBOL_COUNT} symbols in .claude/repo-map.md"
fi

# Output JSON with systemMessage for user display
STATUS_MSG_ESCAPED=$(echo -n "$STATUS_MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
CONTEXT_ESCAPED=$(echo -e "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "systemMessage": "${STATUS_MSG_ESCAPED}",
  "additionalContext": "${CONTEXT_ESCAPED}",
  "continue": true
}
EOF
