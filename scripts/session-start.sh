#!/usr/bin/env bash
# Session Start Hook for context-tools plugin
# Runs when a new Claude Code session starts
# Generates project manifest and displays context summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"

# Generate project manifest
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" 2>/dev/null || true

# Display project context if manifest exists
MANIFEST="${PROJECT_ROOT}/.claude/project-manifest.json"
if [[ -f "${MANIFEST}" ]]; then
    echo "=== Project Context ==="

    # Extract key info using python for JSON parsing
    python3 -c "
import json
import sys
try:
    with open('${MANIFEST}') as f:
        m = json.load(f)
    print(f\"Project: {m.get('project_name', 'unknown')}\")
    langs = m.get('languages', [])
    if langs:
        print(f\"Languages: {', '.join(langs)}\")
    build = m.get('build_system', {})
    if build.get('type'):
        print(f\"Build: {build['type']}\")
        if build.get('commands'):
            cmds = build['commands']
            if cmds.get('build'):
                print(f\"  Build: {cmds['build']}\")
            if cmds.get('test'):
                print(f\"  Test: {cmds['test']}\")
    entries = m.get('entry_points', [])
    if entries:
        print(f\"Entry points: {', '.join(entries[:3])}\")
except Exception as e:
    pass
" 2>/dev/null || true

    echo "========================"
fi

# Check for project learnings
LEARNINGS="${PROJECT_ROOT}/.claude/learnings.md"
if [[ -f "${LEARNINGS}" ]]; then
    LEARNING_COUNT=$(grep -c "^## " "${LEARNINGS}" 2>/dev/null || echo "0")
    if [[ "${LEARNING_COUNT}" -gt 0 ]]; then
        echo ""
        echo "📚 ${LEARNING_COUNT} project learning(s) available in .claude/learnings.md"
    fi
fi

# Check for global learnings
GLOBAL_LEARNINGS="${HOME}/.claude/learnings.md"
if [[ -f "${GLOBAL_LEARNINGS}" ]]; then
    GLOBAL_COUNT=$(grep -c "^## " "${GLOBAL_LEARNINGS}" 2>/dev/null || echo "0")
    if [[ "${GLOBAL_COUNT}" -gt 0 ]]; then
        echo "🌍 ${GLOBAL_COUNT} global learning(s) available in ~/.claude/learnings.md"
    fi
fi
