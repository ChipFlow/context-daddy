# context daddy 🧔

*Your codebase's context needs a responsible adult.*

[![CI](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml/badge.svg)](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml)

## What

A Claude Code plugin for understanding large codebases:
- **Fast symbol search** - 10-100x faster than grep via MCP tools
- **Living narratives** - Capture the "why", not just the "what"
- **Tribal knowledge** - Dragons, gotchas, and hard-won insights that survive context compaction

## Why

Understanding code isn't just about parsing syntax. It's about the *stories* - "here be dragons", "we did X because Y", "this is WTF but it works". That knowledge lives in people's heads and gets lost.

**context daddy** captures both: fast code exploration AND the narrative that makes codebases actually understandable.

## Quick Start

```bash
# Install
claude plugin marketplace add chipflow/context-daddy
claude plugin install context-daddy

# Verify MCP tools work
claude mcp list  # Should show: repo-map: ✓ Connected

# Generate a narrative for your project
cd /path/to/your-project
/context-daddy:generate-narrative
```

Or load directly without installing:
```bash
claude --plugin-dir /path/to/context-daddy
```

## Features

### 🔍 Fast Symbol Search

```
search_symbols("*Handler")         → Find all handler classes
get_symbol_content("AuthService")  → Full source with docstrings
get_file_symbols("src/api.py")     → Everything in a file
list_files("*.py")                 → Find files by pattern
```

Pre-built SQLite index with FTS5. Claude explores your codebase without drowning in context.

### 📖 Living Narratives

Not changelogs. **Stories**:

- **Summary** - What and why
- **Current Foci** - What we're working on now
- **How It Works** - Architecture in plain language
- **The Story So Far** - How we got here
- **Dragons & Gotchas** - Warnings for future-us
- **Open Questions** - Things we're still figuring out

```bash
/context-daddy:generate-narrative  # Bootstrap from git history
/context-daddy:update-narrative    # Revise after sessions
```

Written in "we" voice. Opinionated. Updated after context compaction.

### 🧠 Learnings

Hard-won insights that persist:
- `.claude/learnings.md` - Project-specific
- `~/.claude/learnings.md` - Global
- Prompted to save before compaction

## Commands

| Command | Purpose |
|---------|---------|
| `/context-daddy:generate-narrative` | Bootstrap narrative from git |
| `/context-daddy:update-narrative` | Update after a session |
| `/context-daddy:mcp-help` | MCP tools guide |
| `/context-daddy:repo-map` | Regenerate repo map |
| `/context-daddy:status` | Indexing status |
| `/context-daddy:learnings` | Manage learnings |

## How It Works

**Three components:**
1. **Tree-sitter indexing** → Semantic symbols from Python, C++, Rust
2. **SQLite + FTS5** → Fast retrieval and search
3. **MCP server** → Tools Claude can query

**Multiprocess design:** Indexing runs in isolated subprocesses (4GB memory, 20 min CPU limit, watchdog). MCP server stays responsive.

**Hooks:** SessionStart loads context, Stop hook guides reorientation after compaction.

**Generated files:**
```
.claude/
├── narrative.md           # Project story
├── project-manifest.json  # Build system, languages
├── repo-map.db            # Symbol index
├── learnings.md           # Your insights
└── logs/repo-map-server.log
```

## Requirements

- [uv](https://docs.astral.sh/uv/) for Python
- Python 3.10+
- `ANTHROPIC_API_KEY` for narrative generation

---

## The Journey

We started simple: parse code with tree-sitter, generate repo maps. Then reality hit.

**Memory explosion.** Large codebases broke everything. We moved to incremental caching and parallel parsing with resource limits.

**Static maps weren't enough.** Claude needed fast, targeted access. We built an MCP server - a live query interface, not just generated docs.

**Process management nightmares.** Zombie processes, resource leaks, conflicts. Multiple iterations before landing on isolated subprocesses with watchdog monitoring.

**User experience matters.** Database versioning for seamless upgrades. Simpler hook patterns. Progressive feedback during indexing.

**The philosophical shift.** We realized understanding codebases isn't just parsing - it's capturing stories, decisions, and hard-won insights. Traditional docs capture what code does; narratives capture why it exists.

Throughout: balancing comprehensive understanding against context overload. That tension shapes everything.

## Known Dragons 🐉

**Hooks are fragile.** Autodiscovery doesn't always match expectations. We've been bitten in CI.

**SQLite WAL helps but isn't magic.** We moved away from heavy locking after deadlocks.

**Tree-sitter memory spikes.** Subprocess isolation is our safety net.

**MCP lifecycle is underdocumented.** We've reverse-engineered start/stop behavior.

## Open Questions

- Cache invalidation feels heavyweight. Filesystem watching?
- How do we keep narratives from going stale?
- Is multiprocess architecture over-engineered?
- FTS5 search is underutilized - what's the right UX?

## License

MIT
