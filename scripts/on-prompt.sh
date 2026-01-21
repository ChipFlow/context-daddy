#!/usr/bin/env bash
# UserPromptSubmit hook - injects context after plan mode clears context
# Detects SessionEnd -> UserPromptSubmit pattern (no SessionStart in between)

set -euo pipefail

PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
MARKER_FILE="${CLAUDE_DIR}/session-ended"
CONTEXT_FILE="${CLAUDE_DIR}/post-plan-context.md"

# Check if this is a post-plan prompt (marker exists)
if [[ -f "${MARKER_FILE}" ]]; then
    # Remove marker so we don't inject twice
    rm -f "${MARKER_FILE}"

    # Log for debugging
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [[ -x "${SCRIPT_DIR}/log-hook.sh" ]]; then
        "${SCRIPT_DIR}/log-hook.sh" "PostPlanContextInjection" "triggered" 2>/dev/null || true
    fi

    # Build context to inject
    CONTEXT=""

    # Include post-plan context file if it exists
    if [[ -f "${CONTEXT_FILE}" ]]; then
        CONTEXT=$(cat "${CONTEXT_FILE}")
    fi

    # Include narrative if it exists
    NARRATIVE_FILE="${CLAUDE_DIR}/narrative.md"
    if [[ -f "${NARRATIVE_FILE}" ]]; then
        if [[ -n "${CONTEXT}" ]]; then
            CONTEXT="${CONTEXT}"$'\n\n---\n\n'
        fi
        CONTEXT="${CONTEXT}$(cat "${NARRATIVE_FILE}")"
    fi

    # Include CLAUDE.md if it exists
    CLAUDE_MD="${PROJECT_ROOT}/CLAUDE.md"
    if [[ -f "${CLAUDE_MD}" ]]; then
        if [[ -n "${CONTEXT}" ]]; then
            CONTEXT="${CONTEXT}"$'\n\n---\n\n'
        fi
        CONTEXT="${CONTEXT}$(cat "${CLAUDE_MD}")"
    fi

    if [[ -n "${CONTEXT}" ]]; then
        # Output JSON with context to inject
        # Using python to safely JSON-encode the context
        python3 -c "
import json
import sys
context = sys.stdin.read()
print(json.dumps({'context': context}))
" <<< "${CONTEXT}"
    else
        echo '{"continue": true}'
    fi
else
    # Normal prompt, no injection needed
    echo '{"continue": true}'
fi
