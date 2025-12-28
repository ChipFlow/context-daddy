#!/usr/bin/env bash
# Lightweight cache version check for PreToolUse hook
# Checks if cache needs invalidation and triggers reindex if needed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
CACHE_FILE="${CLAUDE_DIR}/repo-map-cache.json"
LOCK_FILE="${CLAUDE_DIR}/repo-map-cache.lock"
REPO_MAP="${CLAUDE_DIR}/repo-map.md"
CHECK_MARKER="${CLAUDE_DIR}/.cache-checked-v2"

# Quick exit if we've already checked this session (marker exists and is recent)
if [[ -f "${CHECK_MARKER}" ]]; then
    # Marker exists - skip check (already validated this session)
    exit 0
fi

# Expected cache version - must match CACHE_VERSION in generate-repo-map.py
EXPECTED_CACHE_VERSION=2

# Check if cache exists and has wrong version
if [[ -f "${CACHE_FILE}" ]]; then
    CACHE_VERSION=$(python3 -c "import json; print(json.load(open('${CACHE_FILE}')).get('version', 0))" 2>/dev/null || echo "0")
    if [[ "${CACHE_VERSION}" != "${EXPECTED_CACHE_VERSION}" ]]; then
        # Cache is outdated - delete and trigger reindex
        rm -f "${CACHE_FILE}" "${REPO_MAP}"

        # Start background reindex if not already running
        if [[ ! -f "${LOCK_FILE}" ]]; then
            (
                nohup uv run "${SCRIPT_DIR}/generate-repo-map.py" "${PROJECT_ROOT}" \
                    > "${CLAUDE_DIR}/repo-map-build.log" 2>&1 &
            ) &
        fi
    fi
fi

# Create marker so we don't check again this session
mkdir -p "${CLAUDE_DIR}"
touch "${CHECK_MARKER}"

exit 0
