# context daddy 🧔 - Development Guide

## Version Bumping

**IMPORTANT: Always bump the version when making changes!**

Update version in BOTH files:
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Users need to run `claude plugin update` to get changes, and this only works if the version number increases.

## Testing Changes Locally

```bash
# Test with --plugin-dir (no install needed)
claude --plugin-dir /path/to/context-daddy

# Or run scripts directly
uv run scripts/map.py /path/to/test-project
uv run scripts/scan.py /path/to/test-project
```

## Hook Structure

When using matchers in hooks.json, the structure requires a nested `hooks` array:

```json
{
  "matcher": "startup",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/scripts/session-start.sh"
    }
  ]
}
```

## Output Behavior

- **SessionStart hook**: stdout goes to Claude's context, stderr is displayed to user
- Use `>&2` to show messages to the user: `echo "message" >&2`

## MCP Server Logging

The repo-map MCP server maintains rotating logs in `.claude/logs/repo-map-server.log`:

- **Size**: 1MB per file, 3 backups (3MB total)
- **Rotation**: Automatic when file reaches 1MB
- **What's logged**:
  - Server startup/shutdown
  - Tool calls with arguments
  - Tool results (success/error/result count)
  - Indexing events (start, complete, errors)
  - Watchdog actions (hung process detection, SIGKILL)
  - Resource limit violations (SIGXCPU, SIGSEGV)

**Check logs to:**
- See if MCP tools are being used
- Identify common usage patterns
- Debug why tools might not be working
- Verify resource limits are appropriate
- Understand indexing performance

Example:
```bash
tail -f .claude/logs/repo-map-server.log
```

## Goals MCP Server

The goals MCP server (`servers/goals-server.py`) provides 11 tools for goal management. It imports pure functions from `scripts/goals.py`.

- **Logs**: `.claude/logs/goals-server.log` (1MB rotation, 3 backups)
- **Storage**: Goals in `~/.claude/goals/<uuid>.md`, project index in `.claude/active-goals.json`
- **Format v2**: Goals have slugs, steps have IDs (`[step-id]` prefix), `.current-goal` is `UUID:step-id`
- **PostToolUse hook**: `hooks/goals-post-tool.sh` shows transient status after goal changes

```bash
# Test MCP server directly
uv run servers/goals-server.py

# Test goals CLI
uv run scripts/goals.py list --all
uv run scripts/goals.py context

# Run goal tests
uv run tests/test_goals.py
```

## Automatic Narrative Updates

The narrative and learnings are updated automatically by spawning a separate `claude -p` instance (no API key needed):

- **Session start**: If no `.claude/narrative.md` exists, spawns `claude -p --model haiku` in background to create one from git history
- **Pre-compact**: Before context compaction, spawns background update of narrative + learnings
- **Git post-commit**: After each commit, spawns background narrative update

Key script: `scripts/update-context.sh` (orchestrates all of the above)

```bash
# Manual usage
bash scripts/update-context.sh --create   # Generate initial narrative
bash scripts/update-context.sh --update   # Update narrative + learnings
bash scripts/update-context.sh --background --update  # Background update

# Logs
tail -f .claude/logs/update-context.log
```

The git post-commit hook is auto-installed on session start via `scripts/install-git-hooks.sh`.

**Important**: Uses `CLAUDECODE=""` to bypass nested-session detection since it runs as a separate process.

## Context Injection Tracking

All context-injecting hooks are wrapped by `scripts/hook-runner.sh`, which logs output sizes to `~/.claude/logs/context-injection.tsv`.

```bash
# Summary by hook (which hooks inject the most?)
uv run scripts/collate-injections.py

# Per-event detail
uv run scripts/collate-injections.py --detail

# Group by session
uv run scripts/collate-injections.py --by-session

# Last 24 hours
uv run scripts/collate-injections.py --since 24h

# Last 20 events
uv run scripts/collate-injections.py --detail --tail 20
```

## CI

- Main CI validates structure and tests scripts
- E2E tests require `ANTHROPIC_API_KEY` secret (skipped if not set)
