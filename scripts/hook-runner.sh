#!/usr/bin/env bash
# hook-runner.sh — Wraps hook execution to log context injection sizes
#
# Usage: hook-runner.sh <hook-label> <real-script> [args...]
#
# Passes stdin through to the real script, captures its stdout (the JSON
# output that Claude Code reads), logs the byte/token count, and then
# outputs the JSON. Stderr passes through unchanged.
#
# Log file: ~/.claude/logs/context-injection.tsv

set -eo pipefail

HOOK_LABEL="${1:?Usage: hook-runner.sh <label> <script> [args...]}"
shift
SCRIPT="$1"
shift

# Pass stdin to the real script, capture stdout
STDIN_DATA=$(cat)
OUTPUT=$(echo "${STDIN_DATA}" | bash "${SCRIPT}" "$@") || true
# Note: we swallow the exit code because a hook failure shouldn't
# be masked by the wrapper. The real hook's stderr still reaches the user.

# Pass output to Claude Code
echo -n "${OUTPUT}"

# Log if non-trivial (skip {}, {"continue":true}, {"decision":"approve"}, etc.)
BYTES=${#OUTPUT}
if [ "${BYTES}" -gt 40 ]; then
    LOG_DIR="${HOME}/.claude/logs"
    LOG_FILE="${LOG_DIR}/context-injection.tsv"
    {
        mkdir -p "${LOG_DIR}"
        EST_TOKENS=$(( BYTES * 10 / 35 ))
        TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
        SID="${CLAUDE_SESSION_ID:-${CLAUDE_CONVERSATION_ID:-unknown}}"
        PROJECT="${PWD}"

        # Write header if new file
        if [ ! -f "${LOG_FILE}" ]; then
            printf 'timestamp\thook\tproject\tbytes\test_tokens\tsession\n' >> "${LOG_FILE}"
        fi

        printf '%s\t%s\t%s\t%d\t%d\t%s\n' \
            "${TS}" "${HOOK_LABEL}" "${PROJECT}" "${BYTES}" "${EST_TOKENS}" "${SID}" \
            >> "${LOG_FILE}"
    } 2>/dev/null &
    disown 2>/dev/null || true
fi
