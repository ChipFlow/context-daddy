#!/usr/bin/env bash
# Spawns a separate claude instance to update narrative and learnings.
# This runs outside the main session - no dependency on Claude "choosing" to do it.
#
# Usage:
#   update-context.sh --create   # Generate initial narrative from git history
#   update-context.sh --update   # Update existing narrative + learnings
#   update-context.sh --background --create  # Run in background (for hooks)
#   update-context.sh --background --update  # Run in background (for hooks)
#   update-context.sh --create --project /path/to/repo  # Operate on a different project

set -euo pipefail

PROJECT_ROOT="${PWD}"

# Parse arguments
MODE=""
BACKGROUND=false
MODEL="haiku"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --create) MODE="create"; shift ;;
        --update) MODE="update"; shift ;;
        --background) BACKGROUND=true; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        --project) PROJECT_ROOT="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "${MODE}" ]]; then
    echo "Error: Must specify --create or --update" >&2
    exit 1
fi

# Resolve PROJECT_ROOT to absolute path
PROJECT_ROOT=$(cd "${PROJECT_ROOT}" && pwd)

# Derive paths from PROJECT_ROOT (after argument parsing so --project takes effect)
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
NARRATIVE_FILE="${CLAUDE_DIR}/narrative.md"
LEARNINGS_FILE="${CLAUDE_DIR}/learnings.md"
LOCKFILE="${CLAUDE_DIR}/.update-context.lock"
LOGFILE="${CLAUDE_DIR}/logs/update-context.log"

# Ensure directories exist
mkdir -p "${CLAUDE_DIR}/logs"

# Lockfile to prevent concurrent updates (checked before claude binary so we bail early)
if [[ -f "${LOCKFILE}" ]]; then
    # Check if lock is stale (older than 5 minutes)
    if [[ "$(uname)" == "Darwin" ]]; then
        LOCK_AGE=$(( $(date +%s) - $(stat -f %m "${LOCKFILE}") ))
    else
        LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "${LOCKFILE}") ))
    fi
    if [[ ${LOCK_AGE} -lt 300 ]]; then
        echo "Update already in progress (lock age: ${LOCK_AGE}s)" >&2
        exit 0
    fi
    # Stale lock, remove it
    rm -f "${LOCKFILE}"
fi

# Create lock
echo $$ > "${LOCKFILE}"
trap 'rm -f "${LOCKFILE}"' EXIT

run_update() {
    # Find claude binary
    local CLAUDE_BIN
    CLAUDE_BIN=$(command -v claude 2>/dev/null || echo "")
    if [[ -z "${CLAUDE_BIN}" ]]; then
        echo "Error: claude CLI not found in PATH" >&2
        return 1
    fi

    local prompt=""

    if [[ "${MODE}" == "create" ]]; then
        prompt='You are a background agent updating project documentation. Do NOT respond conversationally.

TASK: Generate the initial project narrative from git history.

STEPS:
1. Run: git log --oneline -50 --no-merges
2. Run: git log --oneline -10 --stat
3. Read CLAUDE.md if it exists
4. Read .claude/learnings.md if it exists

Then create .claude/narrative.md with this EXACT structure:

# Project Narrative: [project name]

## Summary
<!-- 2-3 sentences elevator pitch -->

## Current Foci
<!-- 2-4 active work areas based on recent commits -->
- **[Focus]**: description

## How It Works
<!-- Architecture overview, main subsystems -->

## The Story So Far
<!-- Narrative of major epochs, not a changelog -->

## Dragons & Gotchas
<!-- Non-obvious behavior, fragile areas -->

## Open Questions
<!-- Uncertainties, technical debt -->

RULES:
- Write in "we" voice throughout
- Be concise but capture the essential narrative
- Include hunches ("we suspect...", "probably because...")
- This helps future-us understand not just WHAT but WHY
- Write the file using the Write tool'

    elif [[ "${MODE}" == "update" ]]; then
        # Check narrative exists
        if [[ ! -f "${NARRATIVE_FILE}" ]]; then
            echo "No narrative found, switching to create mode" >&2
            MODE="create"
            run_update
            return
        fi

        prompt='You are a background agent updating project documentation. Do NOT respond conversationally.

TASK: Update the project narrative and learnings based on recent changes.

STEPS:
1. Read .claude/narrative.md (the current narrative)
2. Read .claude/learnings.md if it exists
3. Run: git log --oneline -20 --no-merges (to see recent commits)
4. Run: git diff HEAD~5..HEAD --stat (to see what changed recently)

Then do BOTH:

A) UPDATE .claude/narrative.md:
   - REVISE existing sections, do not just append
   - Keep the SAME structure (Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, Open Questions)
   - Update Current Foci if focus shifted
   - Add to Story So Far only if a significant epoch completed
   - Update Dragons if new gotchas discovered or old ones fixed
   - Remove answered Open Questions, add new ones
   - If nothing significant changed, leave mostly as-is

B) UPDATE .claude/learnings.md:
   - Look at recent commits for non-obvious patterns, debugging insights, or API quirks
   - If there are genuine new learnings, append them in this format:
     ### [Title] (YYYY-MM-DD)
     **Insight**: What was discovered
     **Context**: When this matters
   - Do NOT add trivial entries (typos, renames, obvious changes)
   - If no genuine learnings, do not modify the file

RULES:
- Write in "we" voice in the narrative
- Be concise - integrate information, do not bloat
- Use the Edit tool for surgical updates, or Write for full rewrites
- Only update files if there are meaningful changes to record'
    fi

    echo "[$(date -Iseconds)] Starting ${MODE} (model: ${MODEL}) in ${PROJECT_ROOT}" >> "${LOGFILE}"

    # Run claude in print mode from the project directory
    # CLAUDECODE="" allows nested invocation (we're a separate process)
    # CONTEXT_DADDY_UPDATING=1 prevents the spawned instance's session-start.sh
    # from recursively spawning more update agents (infinite loop prevention)
    cd "${PROJECT_ROOT}"
    CLAUDECODE="" CONTEXT_DADDY_UPDATING=1 "${CLAUDE_BIN}" -p \
        --model "${MODEL}" \
        --dangerously-skip-permissions \
        --allowedTools "Read Edit Write Bash" \
        --no-session-persistence \
        "${prompt}" 2>>"${LOGFILE}" | tail -5 >> "${LOGFILE}" || true

    echo "[$(date -Iseconds)] Finished ${MODE}" >> "${LOGFILE}"
}

if [[ "${BACKGROUND}" == "true" ]]; then
    run_update &
    disown
    echo "Background update started (PID: $!)" >&2
else
    run_update
fi
