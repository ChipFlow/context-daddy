# context daddy 🧔

*Your codebase's context needs a responsible adult.*

[![CI](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml/badge.svg)](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml)

We're building a plugin that fundamentally changes how Claude explores and comprehends large codebases. By combining tree-sitter parsing, intelligent caching, and MCP tools, we provide fast, targeted code retrieval without overwhelming context windows.

But we realized something: understanding code isn't just about parsing syntax. It's about capturing the *stories* - the "here be dragons", the "we did X because Y", the "this is WTF but it works". That tribal knowledge usually lives in people's heads and gets lost.

**context daddy** captures both: fast code exploration AND living project narratives.

## The Journey

We started simple: parse code with tree-sitter, generate repo maps. Then reality hit.

**v0.3 - Memory explosion.** Large codebases broke everything. We moved to incremental caching and parallel parsing with resource limits.

**v0.4 - Static maps weren't enough.** Claude needed fast, targeted access. We built an MCP server - not just generating maps, but a live query interface for code exploration.

**v0.6-v0.8 - Process management nightmares.** Zombie indexing processes, resource leaks, conflicts. Multiple iterations of cleanup strategies before landing on isolated subprocesses with watchdog monitoring.

**v0.9 - User experience focus.** Database versioning for seamless upgrades. Simpler Stop hook pattern for post-compaction guidance.

**v0.10 - Narrative documentation.** The philosophical shift. Capturing not just WHAT code does, but WHY it exists and what we've learned building it.

## Features

### 🔍 Fast Symbol Search

MCP tools that are 10-100x faster than grep for finding code:

```
search_symbols("*Handler")         → Find all handler classes
get_symbol_content("AuthService")  → Get full source with docstrings
get_file_symbols("src/api.py")     → List everything in a file
list_files("*.py")                 → Find files by pattern
```

Pre-built SQLite index with FTS5 full-text search. Claude can explore your codebase without drowning in context.

### 📖 Living Narratives

Not changelogs. Not API docs. **Stories**:

- **Summary** - What this is and why it matters
- **Current Foci** - What we're actively working on
- **How It Works** - Architecture in plain language
- **The Story So Far** - How we got here (the journey, not a commit log)
- **Dragons & Gotchas** - Warnings for future-us
- **Open Questions** - Things we're still figuring out

Bootstrap from git history, update after sessions. Written in "we" voice. Opinionated. Useful.

```bash
/context-daddy:generate-narrative  # Bootstrap from git history
/context-daddy:update-narrative    # Revise after significant sessions
```

### 🧠 Learning Retention

Hard-won insights persist across sessions and context compactions:
- Project learnings in `.claude/learnings.md`
- Global learnings in `~/.claude/learnings.md`
- Prompted to save before compaction wipes context

### 📊 Project Awareness

Auto-detects your stack: languages, build system, entry points, git activity. Supports Python, C++, and Rust via tree-sitter.

## Installation

```bash
# From GitHub
claude plugin marketplace add chipflow/context-daddy
claude plugin install context-daddy

# Or load directly
claude --plugin-dir ./context-daddy
```

Verify it's working:
```bash
claude mcp list
# Should show: repo-map: ... - ✓ Connected
```

## Slash Commands

| Command | What it does |
|---------|--------------|
| `/context-daddy:generate-narrative` | Bootstrap narrative from git history |
| `/context-daddy:update-narrative` | Update narrative after a session |
| `/context-daddy:mcp-help` | Guide for MCP tools vs grep |
| `/context-daddy:repo-map` | Regenerate the repository map |
| `/context-daddy:status` | Check indexing status |
| `/context-daddy:learnings` | View and manage learnings |

## Architecture

Three main components:

1. **Tree-sitter indexing** - Parses code into semantic symbols
2. **SQLite + FTS5** - Fast retrieval and full-text search
3. **MCP server** - Exposes tools for Claude to query

Multiprocess design: heavy indexing runs in isolated subprocesses (4GB memory limit, 20 min CPU limit, watchdog monitoring). MCP server stays responsive.

Hooks into Claude's lifecycle:
- **SessionStart** - Loads context, connects MCP
- **PreCompact** - Marks for post-compaction reorientation
- **Stop** - After compaction, guides context restoration and narrative updates

## Generated Files

```
.claude/
├── narrative.md           # Living project story
├── narrative-data.json    # Git data for narrative generation
├── project-manifest.json  # Build system, languages, entry points
├── repo-map.db            # SQLite index for symbol lookup
├── learnings.md           # Project-specific learnings
└── logs/
    └── repo-map-server.log
```

## Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- Python 3.10+
- `ANTHROPIC_API_KEY` (for narrative generation)

## Known Dragons 🐉

**Hooks are fragile.** Autodiscovery doesn't always match plugin.json expectations. We've been bitten by this in CI.

**SQLite WAL helps but isn't magic.** Database migrations need care. We moved away from heavy locking after deadlock issues.

**Tree-sitter memory spikes.** Certain files cause unpredictable memory usage. Subprocess isolation is our safety net.

**MCP lifecycle is underdocumented.** We've reverse-engineered when servers start/stop through trial and error.

## Open Questions

- Cache invalidation feels heavyweight. Filesystem watching? Git hooks?
- How do we keep narratives from going stale?
- Is our multiprocess architecture over-engineered?
- FTS5 search is underutilized - what's the right UX?

## Development

```bash
# Test locally
claude --plugin-dir .

# Run scripts directly
uv run scripts/generate-narrative.py
uv run scripts/generate-repo-map.py /path/to/project
```

## Uninstalling

```bash
claude plugin uninstall context-daddy
rm -rf .claude/repo-map.* .claude/project-manifest.json .claude/narrative*
```

Keep `.claude/learnings.md` - that's your hard-won knowledge!

## License

MIT
