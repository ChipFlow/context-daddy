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
uv run scripts/generate-repo-map.py /path/to/test-project
uv run scripts/generate-manifest.py /path/to/test-project
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

## CI

- Main CI validates structure and tests scripts
- E2E tests require `ANTHROPIC_API_KEY` secret (skipped if not set)
