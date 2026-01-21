#!/usr/bin/env bash
# SessionEnd hook - kills indexing processes when Claude Code session ends

set -euo pipefail

PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Kill all repo-map processes for this project
PIDS=$(pgrep -f "map.py.*${PROJECT_ROOT}" 2>/dev/null || true)
if [[ -n "${PIDS}" ]]; then
    echo "${PIDS}" | xargs kill 2>/dev/null || true
fi

# Create marker for post-plan context injection
# UserPromptSubmit will check for this and inject context if present
mkdir -p "${CLAUDE_DIR}"
touch "${CLAUDE_DIR}/session-ended"

# Output valid JSON for hook
echo '{"continue": true}'
