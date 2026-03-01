#!/usr/bin/env bash
# Session Start Hook for context-daddy plugin
# Outputs JSON with systemMessage (shown to user) and context for Claude
# NOTE: Indexing is now handled by the MCP server - no subprocess spawning here

set -euo pipefail

# Guard against recursive spawning: if we're a background update agent,
# skip session-start entirely to prevent infinite claude -p loops.
if [[ -n "${CONTEXT_DADDY_UPDATING:-}" ]]; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PWD}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

# Ensure .claude directory exists
mkdir -p "${CLAUDE_DIR}"

# Clear session-ended marker (normal session start, not post-plan resume)
rm -f "${CLAUDE_DIR}/session-ended"

# Generate project manifest (quick, runs synchronously)
uv run "${SCRIPT_DIR}/scan.py" "${PROJECT_ROOT}" >/dev/null 2>&1 || true

# Install git hooks (idempotent, silent)
bash "${SCRIPT_DIR}/install-git-hooks.sh" "${PROJECT_ROOT}" 2>/dev/null || true

REPO_MAP="${CLAUDE_DIR}/repo-map.md"
DB_FILE="${CLAUDE_DIR}/repo-map.db"
PROGRESS_FILE="${CLAUDE_DIR}/repo-map-progress.json"

# Check if MCP tool permissions are configured
MCP_PERMS_MISSING=""
MCP_PERMS_MISSING=$(python3 -c "
import json
from pathlib import Path
settings_path = Path.home() / '.claude' / 'settings.json'
if not settings_path.exists():
    print('missing')
else:
    try:
        settings = json.loads(settings_path.read_text())
        allow = settings.get('permissions', {}).get('allow', [])
        needed = ['mcp__plugin_context-daddy_repo-map', 'mcp__plugin_context-daddy_goals']
        if not all(any(n in str(e) for e in allow) for n in needed):
            print('missing')
    except Exception:
        pass
" 2>/dev/null || true)

# Install statusline with goal tracking (if no existing statusLine configured)
STATUSLINE_STATUS=""
STATUSLINE_STATUS=$(python3 -c "
import json, shutil
from pathlib import Path

settings_path = Path.home() / '.claude' / 'settings.json'
source = Path('${SCRIPT_DIR}/statusline.sh')
dest = Path.home() / '.claude' / 'statusline.sh'

if not settings_path.exists():
    print('no-settings')
else:
    try:
        settings = json.loads(settings_path.read_text())
        existing = settings.get('statusLine')
        if existing:
            # Check if it's our script
            cmd = existing.get('command', '') if isinstance(existing, dict) else str(existing)
            if 'statusline.sh' in cmd and (dest.exists()):
                # Our script - update it silently
                if source.exists():
                    shutil.copy2(str(source), str(dest))
                    dest.chmod(0o755)
                print('updated')
            else:
                print('existing')
        else:
            # No statusLine - install ours
            if source.exists():
                shutil.copy2(str(source), str(dest))
                dest.chmod(0o755)
                settings['statusLine'] = {'type': 'command', 'command': '~/.claude/statusline.sh'}
                settings_path.write_text(json.dumps(settings, indent=2) + '\n')
                print('installed')
            else:
                print('no-source')
    except Exception as e:
        print(f'error:{e}')
" 2>/dev/null || true)

# Determine repo map status message (check indexing status)
INDEXING_STATUS=""
if [[ -f "${DB_FILE}" ]]; then
    # Check if indexing is in progress
    INDEXING_STATUS=$(sqlite3 "${DB_FILE}" "SELECT value FROM metadata WHERE key = 'status'" 2>/dev/null || echo "")
fi

if [[ "${INDEXING_STATUS}" == "indexing" && -f "${PROGRESS_FILE}" ]]; then
    # Indexing in progress - show progress
    PROGRESS_INFO=$(python3 -c "
import json
try:
    with open('${PROGRESS_FILE}') as f:
        p = json.load(f)
    parsed = p.get('files_parsed', 0)
    to_parse = p.get('files_to_parse', p.get('files_total', 0))
    total = p.get('files_total', 0)
    pct = int((parsed / to_parse) * 100) if to_parse > 0 else 0
    remaining = max(0, to_parse - parsed)
    est_sec = max(0, int(remaining * 0.05))
    if est_sec < 60:
        time_str = f'{est_sec}s'
    else:
        time_str = f'{int(est_sec / 60)}m'
    print(f'{pct}% ({parsed}/{to_parse} files, ~{time_str} remaining)')
except:
    print('in progress')
" 2>/dev/null || echo "in progress")
    STATUS_MSG="[context-daddy] ⏳ Indexing: ${PROGRESS_INFO}"
elif [[ -f "${DB_FILE}" ]]; then
    # Index exists and ready
    SYMBOL_COUNT=$(sqlite3 "${DB_FILE}" "SELECT COUNT(*) FROM symbols" 2>/dev/null || echo "0")
    STATUS_MSG="[context-daddy] ✅ Repo map ready: ${SYMBOL_COUNT} symbols indexed"
elif [[ -f "${REPO_MAP}" ]]; then
    SYMBOL_COUNT=$(grep -c "^\*\*" "${REPO_MAP}" 2>/dev/null || echo "0")
    STATUS_MSG="[context-daddy] Repo map: ${SYMBOL_COUNT} symbols"
else
    STATUS_MSG="[context-daddy] MCP server will build repo map on first query"
fi

# Build context for Claude (goes to stdout, added to Claude's context)
CONTEXT=""

# Add manifest info
MANIFEST="${CLAUDE_DIR}/project-manifest.json"
if [[ -f "${MANIFEST}" ]]; then
    MANIFEST_INFO=$(python3 -c "
import json
try:
    with open('${MANIFEST}') as f:
        m = json.load(f)
    lines = []
    lines.append(f\"Project: {m.get('project_name', 'unknown')}\")
    langs = m.get('languages', [])
    if langs:
        lines.append(f\"Languages: {', '.join(langs)}\")
    build = m.get('build_system', {})
    if build.get('type'):
        lines.append(f\"Build: {build['type']}\")
    print('\\n'.join(lines))
except:
    pass
" 2>/dev/null || true)
    if [[ -n "${MANIFEST_INFO}" ]]; then
        CONTEXT="${MANIFEST_INFO}"
    fi
fi

# Extract and inject key context (narrative sections, directory structure)
CONTEXT_DATA=$(uv run "${SCRIPT_DIR}/extract-context.py" "${PROJECT_ROOT}" 2>/dev/null || echo "{}")

# Add project root and directory tree
DIR_TREE=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dir_tree', ''))" 2>/dev/null || true)

if [[ -n "${DIR_TREE}" ]]; then
    CONTEXT="${CONTEXT}\n\n**Project Structure**:\n\`\`\`\n${DIR_TREE}\n\`\`\`"
fi

# Inject narrative sections if they exist
HAS_NARRATIVE=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('has_narrative', False))" 2>/dev/null || echo "False")

if [[ "${HAS_NARRATIVE}" != "True" ]]; then
    # No narrative exists - spawn background agent to create one
    # Create lockfile SYNCHRONOUSLY before forking to prevent race conditions
    # where multiple session-start.sh invocations each spawn their own agent
    LOCKFILE="${CLAUDE_DIR}/.update-context.lock"
    if [[ ! -f "${LOCKFILE}" ]] && [[ -f "${SCRIPT_DIR}/update-context.sh" ]]; then
        echo $$ > "${LOCKFILE}"
        bash "${SCRIPT_DIR}/update-context.sh" --background --create 2>/dev/null &
        STATUS_MSG="${STATUS_MSG} | Generating narrative in background..."
    fi
fi

if [[ "${HAS_NARRATIVE}" == "True" ]]; then
    NARRATIVE_SUMMARY=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_summary', ''))" 2>/dev/null || true)
    NARRATIVE_FOCI=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_foci', ''))" 2>/dev/null || true)
    NARRATIVE_DRAGONS=$(echo "${CONTEXT_DATA}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('narrative_dragons', ''))" 2>/dev/null || true)

    if [[ -n "${NARRATIVE_SUMMARY}" ]]; then
        CONTEXT="${CONTEXT}\n\n📖 **Project Summary**: ${NARRATIVE_SUMMARY}"
    fi
    if [[ -n "${NARRATIVE_FOCI}" ]]; then
        CONTEXT="${CONTEXT}\n\n🎯 **Current Foci**:\n${NARRATIVE_FOCI}"
    fi
    if [[ -n "${NARRATIVE_DRAGONS}" ]]; then
        CONTEXT="${CONTEXT}\n\n🐉 **Dragons & Gotchas**:\n${NARRATIVE_DRAGONS}"
    fi
    CONTEXT="${CONTEXT}\n\n(Full narrative in .claude/narrative.md)"
fi

# Add learnings count
LEARNINGS="${CLAUDE_DIR}/learnings.md"
if [[ -f "${LEARNINGS}" ]]; then
    LEARNING_COUNT=$(grep -c "^## " "${LEARNINGS}" 2>/dev/null || echo "0")
    if [[ "${LEARNING_COUNT}" -gt 0 ]]; then
        CONTEXT="${CONTEXT}\n${LEARNING_COUNT} project learning(s) in .claude/learnings.md"
    fi
fi

# Goal context injection (project-scoped, reads goal files directly)
GOAL_CONTEXT=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" "${PROJECT_ROOT}" 2>/dev/null || true)
if [[ -n "${GOAL_CONTEXT}" ]]; then
    CONTEXT="${CONTEXT}\n\n${GOAL_CONTEXT}"
    GOAL_STATUS=$(bash "${SCRIPT_DIR}/goal-context-helper.sh" --status "${PROJECT_ROOT}" 2>/dev/null || true)
    if [[ -n "${GOAL_STATUS}" ]]; then
        STATUS_MSG="${STATUS_MSG} | ${GOAL_STATUS}"
    fi
fi

# Add repo map summary and MCP tools info
if [[ "${INDEXING_STATUS}" == "indexing" ]]; then
    # Indexing in progress
    CONTEXT="${CONTEXT}\n\n⏳ **Repo map indexing in progress** (${PROGRESS_INFO})"
    CONTEXT="${CONTEXT}\n• MCP tools will work once indexing completes"
    CONTEXT="${CONTEXT}\n• Use repo_map_status to check progress"
    CONTEXT="${CONTEXT}\n• Most tools auto-wait up to 15 seconds, then return progress info"
elif [[ -f "${DB_FILE}" ]]; then
    # Ready to use
    CONTEXT="${CONTEXT}\n\n✅ **Repo map ready: ${SYMBOL_COUNT} symbols indexed** - context-daddy MCP guaranteed to work!"
    CONTEXT="${CONTEXT}\n\n🎯 **MANDATORY FIRST ACTION**: Verify MCP tools work by running ONE of these NOW:"
    CONTEXT="${CONTEXT}\n   • mcp__plugin_context-daddy_repo-map__list_files(pattern=\"*.py\") - see indexed Python files"
    CONTEXT="${CONTEXT}\n   • mcp__plugin_context-daddy_repo-map__search_symbols(pattern=\"*\", limit=5) - see available symbols"
    CONTEXT="${CONTEXT}\n   This takes <1 second and proves the tools work in THIS project. Do it before any other work."
    CONTEXT="${CONTEXT}\n\n⚡ **BEFORE using Search/Grep/Glob/find/ls for code**: ALWAYS try MCP tools first."
    CONTEXT="${CONTEXT}\n• Finding enum/struct/class definition? → search_symbols(\"TypeName\") then get_symbol_content(\"TypeName\")"
    CONTEXT="${CONTEXT}\n• Finding functions by pattern? → search_symbols(\"setup_*\") or search_symbols(\"*Handler\")"
    CONTEXT="${CONTEXT}\n• What's in a file? → get_file_symbols(\"path/to/file.rs\")"
    CONTEXT="${CONTEXT}\n• Finding files? → list_files(\"*.py\") or list_files(\"*ring*\") - faster than Search/find/ls"
    CONTEXT="${CONTEXT}\n• 10-100x faster than Search/Grep/find/ls. Use MCP tools for code, grep only for text/comments."
    CONTEXT="${CONTEXT}\n\n📄 **Large markdown files?** Use md_* tools instead of Read:"
    CONTEXT="${CONTEXT}\n• md_outline(\"docs/API.md\") - Get table of contents"
    CONTEXT="${CONTEXT}\n• md_get_section(\"docs/API.md\", \"Installation\") - Read specific section"
    CONTEXT="${CONTEXT}\n• md_list_tables/md_get_table - Navigate tables"
elif [[ -f "${REPO_MAP}" ]]; then
    CONTEXT="${CONTEXT}\nRepo map available with ${SYMBOL_COUNT} symbols in .claude/repo-map.md"
fi

# Add permission warning if MCP tools aren't auto-allowed
if [[ "${MCP_PERMS_MISSING}" == "missing" ]]; then
    STATUS_MSG="${STATUS_MSG} | ⚠️ MCP tools need permission setup"
    CONTEXT="${CONTEXT}\n\n⚠️ **MCP tool permissions not configured**"
    CONTEXT="${CONTEXT}\ncontext-daddy's MCP tools require per-call approval right now."
    CONTEXT="${CONTEXT}\nAsk the user: \"context-daddy's MCP tools need permission approval on every use. Would you like me to auto-allow them? They're all read-only code search tools.\""
    CONTEXT="${CONTEXT}\nIf user agrees, run: uv run ${SCRIPT_DIR}/setup-permissions.py"
    CONTEXT="${CONTEXT}\nThen tell them to restart the session for changes to take effect."
fi

# Statusline integration guidance
if [[ "${STATUSLINE_STATUS}" == "existing" ]]; then
    CONTEXT="${CONTEXT}\n\n⚠️ **StatusLine: existing config detected**"
    CONTEXT="${CONTEXT}\ncontext-daddy can show goal tracking in the status bar, but you already have a statusLine configured."
    CONTEXT="${CONTEXT}\nIf the user wants goal info in their status bar, help them integrate it into their existing script."
    CONTEXT="${CONTEXT}\nThe goal status snippet is in: ${SCRIPT_DIR}/statusline.sh (the goal tracking section)"
fi

# Output JSON with systemMessage for user display
STATUS_MSG_ESCAPED=$(echo -n "$STATUS_MSG" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')
CONTEXT_ESCAPED=$(echo -e "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "systemMessage": "${STATUS_MSG_ESCAPED}",
  "additionalContext": "${CONTEXT_ESCAPED}",
  "continue": true
}
EOF
