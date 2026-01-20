# Testing

## Running Tests

```bash
# Run all unit tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_plugin_config.py

# Run plugin config validation (standalone)
uv run tests/test_plugin_config.py
```

## Test Files

| File | Purpose |
|------|---------|
| `tests/test_plugin_config.py` | Plugin configuration validation (7 tests) |
| `tests/test_mcp_tools.py` | MCP tool functionality |
| `tests/test_list_files.py` | File listing with glob patterns |

## CI Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | push, PR | Structure validation, script tests |
| `test-hooks.yml` | push to main | E2E hook execution |
| `e2e-test.yml` | manual | Full E2E testing with Claude |
| `pages.yml` | push to main | Deploy documentation |
| `preview-docs.yml` | PR | Documentation preview |

**Note**: E2E tests require `ANTHROPIC_API_KEY` secret.

## Plugin Configuration Tests

`test_plugin_config.py` validates:

1. **Required fields** - plugin.json has name, version, description, author, keywords, repository
2. **Hooks discovery** - hooks/hooks.json exists (autodiscovered by Claude Code)
3. **Hook types** - All hook types are valid (SessionStart, PreCompact, Stop, etc.)
4. **Script existence** - All referenced scripts in hooks.json exist
5. **Version format** - Version follows semver (X.Y.Z)
6. **MCP servers** - Referenced server scripts exist
7. **Version consistency** - plugin.json and marketplace.json versions match

## E2E Hook Tests

`.github/workflows/test-hooks.yml` tests:

- **SessionStart hook** - Creates .claude directory and manifest
- **PreCompact + Stop hooks** - Verifies compaction flow via turn limits
- **Artifact verification** - Checks repo-map.db creation and MCP logs

## Test Guarantees

### Transaction Safety

- All database writes in single BEGIN IMMEDIATE / COMMIT block
- WAL mode enabled for crash safety
- Atomic rename only after successful commit
- Rollback on exception (no partial state)

### Watchdog

- Detects indexing hung >10 minutes
- Sets status='failed' with error message
- Prevents hung process from overwriting after intervention
- Runs on server startup and every 60 seconds

### Data Integrity

- Safety check before rename prevents watchdog race condition
- Concurrent reads during indexing handled by SQLite WAL
- Recovery from failed/crashed indexing supported
