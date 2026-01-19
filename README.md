# context daddy 🧔

*Your codebase's context needs a responsible adult.*

[![CI](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml/badge.svg)](https://github.com/ChipFlow/context-daddy/actions/workflows/ci.yml)

A Claude Code plugin that gives Claude superpowers for understanding your codebase:
- **Fast code exploration** via MCP tools (10-100x faster than grep for symbols)
- **Living project narratives** that capture the "why", not just the "what"
- **Tribal knowledge retention** that survives context compaction

## What's New in v0.10.0: Narrative Documentation

Teams build up stories about their codebases - "here be dragons", "we did X because Y", "this is WTF but works". That knowledge usually lives in people's heads and gets lost.

**context daddy** now captures and evolves these narratives:

```bash
# Bootstrap a narrative from git history
/context-daddy:generate-narrative

# Update after a session with significant learning
/context-daddy:update-narrative
```

The narrative is a living document with: Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, and Open Questions. Written in "we" voice. Opinionated. Useful.

## Features

### 🔍 Fast Symbol Search (MCP Tools)

Once installed, Claude has lightning-fast code exploration:

```
search_symbols("*Handler")     → Find all handler classes
get_symbol_content("AuthService")  → Get full source code
get_file_symbols("src/api.py")     → List everything in a file
list_files("*.py")             → Find files by pattern
```

These use a pre-built SQLite index. Way faster than grep for finding code.

### 📖 Living Narratives

Not changelogs. Not API docs. **Stories** about your codebase:

- What we're working on now (Current Foci)
- How we got here (The Story So Far)
- Where the dragons lurk (Dragons & Gotchas)
- What we're still figuring out (Open Questions)

Updated automatically after context compaction, or manually via slash command.

### 🧠 Learning Retention

Discoveries persist across sessions:
- Project learnings in `.claude/learnings.md`
- Global learnings in `~/.claude/learnings.md`
- Prompted to save before context compaction

### 📊 Project Awareness

Auto-detects your stack:
- Languages, build system, entry points
- Git activity summary
- Multi-language support (Python, C++, Rust)

## Installation

### From GitHub (recommended)

```bash
claude plugin marketplace add chipflow/context-daddy
claude plugin install context-daddy
```

### From local directory

```bash
git clone https://github.com/chipflow/context-daddy.git
claude plugin marketplace add ./context-daddy
claude plugin install context-daddy
```

### One-off use

```bash
claude --plugin-dir ./context-daddy
```

### Verify it's working

```bash
claude mcp list
# Should show: repo-map: ... - ✓ Connected
```

## Slash Commands

| Command | What it does |
|---------|--------------|
| `/context-daddy:generate-narrative` | Bootstrap narrative from git history |
| `/context-daddy:update-narrative` | Update narrative after a session |
| `/context-daddy:mcp-help` | Guide for using MCP tools effectively |
| `/context-daddy:repo-map` | Regenerate the repository map |
| `/context-daddy:status` | Check indexing status |
| `/context-daddy:learnings` | View and manage project learnings |

## How It Works

### Hooks

- **SessionStart**: Loads context, shows status, connects MCP tools
- **PreCompact**: Creates marker for post-compaction reorientation
- **Stop**: After compaction, guides Claude to restore context and update narrative

### Generated Files

```
.claude/
├── narrative.md           # Living project story
├── narrative-data.json    # Git data for narrative generation
├── project-manifest.json  # Build system, languages, entry points
├── repo-map.db            # SQLite index for fast symbol lookup
├── learnings.md           # Project-specific learnings
└── logs/
    └── repo-map-server.log  # MCP server logs
```

## Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager
- Python 3.10+
- `ANTHROPIC_API_KEY` environment variable (for narrative generation)

## Development

```bash
# Test locally without installing
claude --plugin-dir .

# Run scripts directly
uv run scripts/generate-narrative.py
uv run scripts/generate-repo-map.py /path/to/project
```

## Uninstalling

```bash
claude plugin uninstall context-daddy
```

To clean up generated files (optional):
```bash
rm -rf .claude/repo-map.* .claude/project-manifest.json .claude/narrative*
```

Note: Keep `.claude/learnings.md` - that's your project's hard-won knowledge!

## License

MIT
