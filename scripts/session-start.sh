#!/usr/bin/env bash
# Session Start Hook for context-tools plugin
# Runs when a new Claude Code session starts
# Generates project manifest and starts repo map generation in background

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Ensure .claude directory exists
mkdir -p "${CLAUDE_DIR}"

# Generate project manifest (quick, runs synchronously)
uv run "${SCRIPT_DIR}/generate-manifest.py" "${PROJECT_ROOT}" 2>/dev/null || true

# Start repo map generation in background (can take a while for large projects)
# Uses lock file to prevent concurrent runs
# Progress is saved periodically, so safe to interrupt
(
    nohup uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" \
        > "${CLAUDE_DIR}/repo-map-build.log" 2>&1 &
) &

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

# Show repo map status
REPO_MAP="${CLAUDE_DIR}/repo-map.md"
PROGRESS_FILE="${CLAUDE_DIR}/repo-map-progress.json"

if [[ -f "${REPO_MAP}" ]]; then
    SYMBOL_COUNT=$(grep -c "^\*\*" "${REPO_MAP}" 2>/dev/null || echo "0")
    echo "🗺️  Repo map available (${SYMBOL_COUNT} symbols)"
    # Check if we're rebuilding
    if [[ -f "${CLAUDE_DIR}/repo-map-cache.lock" ]]; then
        if [[ -f "${PROGRESS_FILE}" ]]; then
            python3 -c "
import json
with open('${PROGRESS_FILE}') as f:
    p = json.load(f)
status = p.get('status', 'unknown')
if status == 'parsing':
    parsed = p.get('files_parsed', 0)
    to_parse = p.get('files_to_parse', 0)
    if to_parse > 0:
        pct = int(parsed / to_parse * 100)
        print(f'   ⏳ Updating: {parsed}/{to_parse} files ({pct}%)')
    else:
        print('   ⏳ Updating...')
else:
    print('   ⏳ Updating in background...')
" 2>/dev/null || echo "   ⏳ Updating in background..."
        else
            echo "   ⏳ Updating in background..."
        fi
    fi
elif [[ -f "${CLAUDE_DIR}/repo-map-cache.lock" ]]; then
    # Building for first time
    if [[ -f "${PROGRESS_FILE}" ]]; then
        python3 -c "
import json
with open('${PROGRESS_FILE}') as f:
    p = json.load(f)
status = p.get('status', 'unknown')
if status == 'parsing':
    parsed = p.get('files_parsed', 0)
    to_parse = p.get('files_to_parse', 0)
    total = p.get('files_total', 0)
    cached = p.get('files_cached', 0)
    if to_parse > 0:
        pct = int(parsed / to_parse * 100)
        print(f'🗺️  Building repo map: {parsed}/{to_parse} files ({pct}%)')
    else:
        print(f'🗺️  Building repo map ({total} files)...')
else:
    print('🗺️  Building repo map...')
" 2>/dev/null || echo "🗺️  Building repo map in background..."
    else
        echo "🗺️  Building repo map in background..."
    fi
else
    echo "🗺️  Building repo map in background..."
fi

# Hint about checking progress
if [[ -f "${CLAUDE_DIR}/repo-map-cache.lock" ]] && [[ ! -f "${REPO_MAP}" ]]; then
    echo "   Use /context-tools:status to check progress"
fi
