---
name: context-tools
description: Context management tools for Claude Code - provides intelligent codebase mapping with Python, Rust, and C++ parsing, duplicate detection, and MCP-powered symbol queries. Use this skill when working with large codebases that need automated indexing and context management.
---

# Context Tools for Claude Code

This skill provides intelligent context management for large codebases through:

- **Repository Mapping**: Parses Python, Rust, and C++ code to extract classes, functions, and methods
- **Duplicate Detection**: Identifies similar code patterns using fuzzy matching
- **MCP Symbol Server**: Enables fast symbol search via `search_symbols` and `get_file_symbols` tools
- **Automatic Indexing**: Background incremental updates as files change

## First Time Setup

**IMPORTANT**: If the user has just installed this plugin, inform them about MCP server configuration:

> "I see you've installed the context-tools plugin. Note that this plugin requires the MCP server to be configured for fast symbol search tools to work. Would you like me to guide you through the setup, or would you prefer to configure it manually?
>
> If you'd like guidance, I can run `/context-tools:setup-mcp` which will show you the commands to add the repo-map server to your Claude Code configuration."

If they want guidance, run `/context-tools:setup-mcp` and explain the steps. After configuration, ask them to restart Claude Code.

## Included Components

### Hooks
- **SessionStart**: Generates project manifest and displays status
- **PreCompact**: Refreshes context before compaction
- **SessionEnd**: Cleanup operations

Note: Indexing is now handled by the MCP server itself (no PreToolUse hook needed).

### MCP Server (repo-map)
- `search_symbols(pattern, kind?, limit?)` - Search symbols by name pattern (supports glob wildcards)
- `get_file_symbols(file)` - Get all symbols in a specific file
- `get_symbol_content(name, kind?)` - Get full source code of a symbol by exact name
- `reindex_repo_map(force?)` - Trigger manual reindex
- `repo_map_status()` - Check indexing status and staleness

### Slash Commands
- `/context-tools:repo-map` - Regenerate repository map
- `/context-tools:manifest` - Refresh project manifest
- `/context-tools:learnings` - Manage project learnings
- `/context-tools:status` - Show plugin status

## Language Support

| Language | Parser | File Extensions |
|----------|--------|-----------------|
| Python | AST | `.py` |
| Rust | tree-sitter-rust | `.rs` |
| C++ | tree-sitter-cpp | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.h`, `.hxx` |
