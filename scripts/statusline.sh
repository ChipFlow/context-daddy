#!/usr/bin/env bash
# Claude Code statusline with goal tracking
# Receives JSON on stdin with session info

input=$(cat)

# Model and context
MODEL=$(echo "$input" | jq -r '.model.display_name // "?"')
PCT=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
COST=$(printf "%.2f" "$(echo "$input" | jq -r '.cost.total_cost_usd // 0')")

# Goal status (fast: just read files, no subprocess)
GOAL_STATUS=""
CWD=$(echo "$input" | jq -r '.cwd // ""')
CURRENT_GOAL_FILE="${CWD}/.claude/.current-goal"
GOALS_DIR="${HOME}/.claude/goals"

if [[ -f "${CURRENT_GOAL_FILE}" ]]; then
    RAW=$(tr -d '\n\r' < "${CURRENT_GOAL_FILE}")
    GOAL_UUID="${RAW%%:*}"
    GOAL_FILE="${GOALS_DIR}/${GOAL_UUID}.md"

    if [[ -f "${GOAL_FILE}" ]]; then
        # Extract slug (line looks like: **Slug**: goal-tracking-functionality)
        SLUG=$(sed -n 's/^\*\*Slug\*\*: *//p' "${GOAL_FILE}" | head -1 | tr -d '\r')
        TOTAL=$(grep -c '^- \[' "${GOAL_FILE}" 2>/dev/null || echo 0)
        DONE=$(grep -c '^- \[x\]' "${GOAL_FILE}" 2>/dev/null || echo 0)

        # Get focused step ID from .current-goal
        STEP_ID="${RAW#*:}"
        if [[ "${STEP_ID}" == "${RAW}" ]]; then
            # No step ID in .current-goal, try ← current
            STEP_ID=$(grep '← current' "${GOAL_FILE}" | head -1 | grep -o '\[[a-z0-9-]*\]' | tr -d '[]')
        fi

        if [[ -n "${SLUG}" ]]; then
            if [[ -n "${STEP_ID}" ]]; then
                GOAL_STATUS=" | 🎯 Goal: ${SLUG} - ${STEP_ID} (${DONE}/${TOTAL})"
            else
                GOAL_STATUS=" | 🎯 Goal: ${SLUG} (${DONE}/${TOTAL})"
            fi
        fi
    fi
fi

# Context bar
BAR_WIDTH=8
FILLED=$((PCT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && BAR=$(printf "%${FILLED}s" | tr ' ' '▓')
[ "$EMPTY" -gt 0 ] && BAR="${BAR}$(printf "%${EMPTY}s" | tr ' ' '░')"

printf "[%s] %s %s%% \$%s%s" "$MODEL" "$BAR" "$PCT" "$COST" "$GOAL_STATUS"
