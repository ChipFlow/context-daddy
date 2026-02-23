#!/usr/bin/env bash
# PostToolUse hook: detect when Edit/Write targets a different git repo
# and inject that project's context into the conversation.
#
# On project switch:
# 1. Spawns background repo-map generation (map.py) for code indexing
# 2. Spawns background narrative creation if none exists
# 3. Injects project context (structure, narrative, repo-map summary)
# 4. Warns that MCP tools are bound to the original project
#
# IMPORTANT: This hook must NOT write to ~/.claude/ or any .claude/ directory
# synchronously, as Claude Code watches those directories for config changes
# and writes there can trigger plugin reloads → new MCP server launches → loops.
# The marker file lives in /tmp and all .claude/ writes are deferred to
# background processes.

set -euo pipefail

# Exit cleanly on any error — a PostToolUse hook failure shows as an error
# to the user but doesn't provide useful info. Better to silently no-op.
trap 'exit 0' ERR

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# Marker file in /tmp to avoid triggering Claude Code's ~/.claude/ file watcher.
# Namespaced by UID to avoid collisions on shared machines.
MARKER_FILE="/tmp/.claude-project-root-$(id -u)"

# Read stdin (PostToolUse hook receives JSON with tool_input)
INPUT=$(cat)

# Extract file_path from tool_input
FILE_PATH=$(echo "${INPUT}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # PostToolUse provides tool_input with the tool's parameters
    tool_input = data.get('tool_input', {})
    print(tool_input.get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)

if [[ -z "${FILE_PATH}" ]]; then
    # No file_path in tool input - nothing to do
    exit 0
fi

# Resolve to directory
if [[ -f "${FILE_PATH}" ]]; then
    FILE_DIR=$(dirname "${FILE_PATH}")
elif [[ -d "${FILE_PATH}" ]]; then
    FILE_DIR="${FILE_PATH}"
else
    # File might not exist yet (Write creates it) - use parent dir
    FILE_DIR=$(dirname "${FILE_PATH}")
fi

# Bail if directory doesn't exist
if [[ ! -d "${FILE_DIR}" ]]; then
    exit 0
fi

# Find git root for the file's directory
NEW_ROOT=$(git -C "${FILE_DIR}" rev-parse --show-toplevel 2>/dev/null || echo "")
if [[ -z "${NEW_ROOT}" ]]; then
    # Not in a git repo - nothing to do
    exit 0
fi

# Read current tracked project root
CURRENT_ROOT=""
if [[ -f "${MARKER_FILE}" ]]; then
    CURRENT_ROOT=$(cat "${MARKER_FILE}")
fi

# If no marker yet, set it to this project and exit (first use)
if [[ -z "${CURRENT_ROOT}" ]]; then
    echo "${NEW_ROOT}" > "${MARKER_FILE}"
    exit 0
fi

# Same project - no-op
if [[ "${NEW_ROOT}" == "${CURRENT_ROOT}" ]]; then
    exit 0
fi

# --- Project switch detected! ---

# Update marker (in /tmp, safe from file watchers)
echo "${NEW_ROOT}" > "${MARKER_FILE}"

NEW_CLAUDE_DIR="${NEW_ROOT}/.claude"

# Spawn ALL .claude/ directory writes in a single background process
# to avoid triggering Claude Code's file watcher during hook execution.
(
    mkdir -p "${NEW_CLAUDE_DIR}/logs"

    # 1. Generate repo-map for the new project
    if command -v uv &>/dev/null && [[ -f "${PLUGIN_ROOT}/scripts/map.py" ]]; then
        uv run "${PLUGIN_ROOT}/scripts/map.py" "${NEW_ROOT}" \
            >"${NEW_CLAUDE_DIR}/logs/map-switch.log" 2>&1 || true
    fi

    # 2. Create narrative if none exists
    if [[ ! -f "${NEW_CLAUDE_DIR}/narrative.md" ]]; then
        bash "${PLUGIN_ROOT}/scripts/update-context.sh" \
            --background --create --project "${NEW_ROOT}" 2>/dev/null || true
    fi

    # 3. Generate project manifest
    if command -v uv &>/dev/null && [[ -f "${PLUGIN_ROOT}/scripts/scan.py" ]]; then
        uv run "${PLUGIN_ROOT}/scripts/scan.py" "${NEW_ROOT}" >/dev/null 2>&1 || true
    fi
) &
disown

# Extract context from the new project (read-only, no writes to .claude/)
CONTEXT=""
if command -v uv &>/dev/null; then
    CONTEXT=$(uv run "${PLUGIN_ROOT}/scripts/extract-context.py" "${NEW_ROOT}" 2>/dev/null || echo "")
fi

# Check if repo-map DB exists (read-only)
REPO_MAP_INFO=""
DB_FILE="${NEW_CLAUDE_DIR}/repo-map.db"
if [[ -f "${DB_FILE}" ]]; then
    SYMBOL_COUNT=$(sqlite3 "${DB_FILE}" "SELECT COUNT(*) FROM symbols" 2>/dev/null || echo "0")
    if [[ "${SYMBOL_COUNT}" -gt 0 ]]; then
        REPO_MAP_INFO="Repo map: ${SYMBOL_COUNT} symbols previously indexed"
    fi
fi

# Build additionalContext message
SUMMARY=$(echo "${CONTEXT}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    parts = []
    root = data.get('project_root', '')
    parts.append(f'PROJECT SWITCH DETECTED: Now working in {root}')
    parts.append('')
    if data.get('narrative_summary'):
        parts.append(f\"Summary: {data['narrative_summary']}\")
    if data.get('narrative_foci'):
        parts.append(f\"Current foci: {data['narrative_foci']}\")
    if data.get('narrative_dragons'):
        parts.append(f\"Dragons: {data['narrative_dragons']}\")
    if data.get('dir_tree'):
        parts.append(f\"Project structure:\n{data['dir_tree']}\")
    print('\n'.join(parts))
except Exception:
    print('PROJECT SWITCH DETECTED: Now working in ${NEW_ROOT}')
" 2>/dev/null)

# Fallback if python parsing failed
if [[ -z "${SUMMARY}" ]]; then
    SUMMARY="PROJECT SWITCH DETECTED: Now working in ${NEW_ROOT}"
fi

# Add repo-map and background generation status
if [[ -n "${REPO_MAP_INFO}" ]]; then
    SUMMARY="${SUMMARY}

${REPO_MAP_INFO} (repo-map DB exists but MCP tools are bound to the original project)"
fi

SUMMARY="${SUMMARY}

BACKGROUND TASKS STARTED:
- Repo-map generation (map.py) running in background for ${NEW_ROOT}
- Narrative creation spawned if not already present

IMPORTANT: repo-map MCP tools (search_symbols, get_symbol_content, list_files) are indexed for the ORIGINAL project and will NOT work for this project. Use Grep/Glob/Read for code navigation here."

# Escape for JSON output
CONTEXT_ESCAPED=$(echo -e "${SUMMARY}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "additionalContext": "${CONTEXT_ESCAPED}"
}
EOF
