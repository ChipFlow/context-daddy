#!/usr/bin/env bash
# SessionEnd hook - kills indexing processes when Claude Code session ends

set -euo pipefail

PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Kill all context-daddy background processes for this project
# (map.py indexing, update-context.sh agents)
for pattern in "map.py.*${PROJECT_ROOT}" "update-context.sh.*${PROJECT_ROOT}" "update-context.*--project.*${PROJECT_ROOT}"; do
    PIDS=$(pgrep -f "${pattern}" 2>/dev/null || true)
    if [[ -n "${PIDS}" ]]; then
        echo "${PIDS}" | xargs kill 2>/dev/null || true
    fi
done

# Create marker for post-plan context injection
# UserPromptSubmit will check for this and inject context if present
mkdir -p "${CLAUDE_DIR}"
touch "${CLAUDE_DIR}/session-ended"

# Output valid JSON for hook
echo '{"continue": true}'
