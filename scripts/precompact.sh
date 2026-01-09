#!/usr/bin/env bash
# PreCompact Hook for context-tools plugin
# Runs before context compaction to ensure context is refreshed
# Note: Repo map is maintained by MCP server, no need to regenerate here

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"

echo "=== PreCompact Hook (context-tools) ==="
echo ""
echo "💡 Reminder: Record important discoveries in .claude/learnings.md"
echo "================================================"
