#!/usr/bin/env bash
# PreCompact Hook for context-tools plugin
# Runs before context compaction to ensure context is refreshed
# Regenerates project manifest and repo map

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"

echo "=== Refreshing Project Context (PreCompact) ==="

# Regenerate project manifest
echo "Updating project manifest..."
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" 2>/dev/null || true

# Regenerate repo map for Python projects
if [[ -f "${PROJECT_ROOT}/pyproject.toml" ]] || [[ -d "${PROJECT_ROOT}" && $(find "${PROJECT_ROOT}" -maxdepth 2 -name "*.py" 2>/dev/null | head -1) ]]; then
    echo "Updating repo map..."
    uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" 2>/dev/null | tail -10 || true
fi

echo ""
echo "💡 Reminder: Record important discoveries in .claude/learnings.md"
echo "================================================"
