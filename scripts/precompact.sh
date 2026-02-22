#!/usr/bin/env bash
# PreCompact Hook for context-daddy plugin
# Runs before context compaction to:
# 1. Flag for post-compaction reorientation
# 2. Spawn a background agent to update narrative + learnings
# Note: Repo map is maintained by MCP server, no need to regenerate here

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Set flag for post-compaction reorientation
mkdir -p "${CLAUDE_DIR}"
touch "${CLAUDE_DIR}/needs-reorientation"

# Spawn background agent to update narrative + learnings before compaction
# This runs independently - the compaction proceeds without waiting
if [[ -f "${SCRIPT_DIR}/update-context.sh" ]]; then
    bash "${SCRIPT_DIR}/update-context.sh" --background --update 2>/dev/null &
fi

echo "=== PreCompact Hook (context-daddy) ==="
echo ""
echo "Narrative and learnings update started in background."
echo "Context will be refreshed after compaction."
echo "================================================"
