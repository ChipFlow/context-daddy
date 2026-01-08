# Changelog

All notable changes to the context-tools plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.3] - 2026-01-08

### Changed
- **Session start context**: Embedded SKILL.md guidance directly in session-start.sh additionalContext
- Claude now receives dynamic directory support and restart requirement instructions at session start
- Alternative approach since plugin manifest doesn't support automatic context loading via skills field

## [0.8.2] - 2026-01-08

### Fixed
- **Plugin validation error**: Removed `skills` field from plugin.json - not supported in current plugin manifest format
- Plugin now loads correctly without validation errors

## [0.8.1] - 2026-01-08 [YANKED]

### Fixed
- **Attempted skill registration**: Added `skills` field to plugin.json (YANKED - caused validation errors)

## [0.8.0] - 2026-01-08

### Added
- **Multiprocess architecture**: MCP server spawns indexing subprocess instead of using threads
- **Resource limits**: 4GB memory (RLIMIT_AS) and 20 min CPU time (RLIMIT_CPU) for indexing subprocess
- **Dynamic directory support**: MCP tools automatically query current working directory, not session start directory
- **Rotating logs**: Comprehensive logging to `.claude/logs/repo-map-server.log` (1MB per file, 3 backups)
- **Exit status detection**: Logs specific resource limit violations (SIGXCPU, SIGSEGV, SIGKILL)
- **SKILL.md**: Usage instructions for Claude with session restart guidance
- **PROCESS-ARCHITECTURE.md**: Documents architecture evolution and design decisions
- **TESTING.md**: Comprehensive test documentation with 18 test cases

### Changed
- **Simplified database writes**: Removed tmp file + rename pattern, rely on SQLite WAL mode + transactions
- **Removed file locking**: SQLite's built-in locking is sufficient for concurrent access
- **Watchdog can kill subprocess**: Using SIGKILL on subprocess doesn't affect MCP server
- **MCP server stays responsive**: Even during indexing or hung processes
- **Better logging**: Tool calls, results, indexing events, and errors all logged

### Fixed
- **Multi-project support**: Can now switch between projects in one session without restart
- **Concurrent indexing**: Multiple MCP servers can safely coexist, SQLite handles coordination
- **Resource leak detection**: Logs when subprocess exceeds memory or CPU limits

## [0.7.1] - 2026-01-07

### Fixed
- **Critical data corruption fix**: Wrap all database writes in single BEGIN IMMEDIATE / COMMIT transaction
- **Race condition protection**: Safety check prevents hung processes from overwriting after watchdog intervention
- **Transaction safety**: Rollback on exception, all-or-nothing writes

### Changed
- `set_metadata()` no longer commits internally - caller must commit
- Database writes are atomic (single transaction for all changes)

## [0.7.0] - 2026-01-07

### Added
- **Indexing status tracking**: Metadata table tracks status (idle/indexing/completed/failed)
- **Auto-wait behavior**: Tools automatically wait up to 60s if indexing in progress
- **Watchdog**: Detects hung indexing (>10 min) and resets status to 'failed'
- **Periodic watchdog**: Runs every 60 seconds to detect stuck processes
- **New MCP tool**: `wait_for_index` to explicitly wait for indexing completion
- **Status reporting**: `repo_map_status` shows indexing progress and duration

### Changed
- Bumped CACHE_VERSION from 3 to 4 (metadata table added)
- Tools "just work" on first use - auto-wait for indexing to complete

## [0.6.1] - 2026-01-06

### Changed
- Simplified MCP server configuration in plugin.json

## [0.6.0] - 2026-01-06

### Added
- **MCP server architecture**: Moved from PreToolUse hook to persistent MCP server
- Single long-running process per Claude Code session
- Background thread for indexing (replaced nohup subprocess)

### Fixed
- **Memory leak**: Eliminated "hundreds of gigs" memory usage from multiple background processes
- No more subprocess accumulation from hook calls

### Removed
- PreToolUse hook (replaced by MCP server)
- nohup subprocess spawning

## [0.5.x and earlier]

Initial releases with PreToolUse hook architecture.

[0.8.0]: https://github.com/ChipFlow/claude-context-tools/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/ChipFlow/claude-context-tools/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/ChipFlow/claude-context-tools/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/ChipFlow/claude-context-tools/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/ChipFlow/claude-context-tools/releases/tag/v0.6.0
