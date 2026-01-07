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

## Using MCP Tools

**IMPORTANT**: Before attempting to use MCP tools (mcp__plugin_context-tools_repo-map__*), check if `.claude/repo-map.db` exists:
- If YES: Try the MCP tool. If it fails (not available), use sqlite3 fallback.
- If NO: The project hasn't been indexed yet. Either wait for indexing or run `/context-tools:repo-map` to generate it.

**Preferred approach when MCP tools are available:**
1. Try MCP tool first
2. If tool not found, explain that session needs restart to load MCP server
3. Use sqlite3 fallback to still answer the question

## First Time Setup

**IMPORTANT**: If the user has just installed this plugin:

> "I see you've installed the context-tools plugin. The MCP server should auto-configure on restart. After restarting Claude Code, run `/mcp` to verify the `repo-map` server is loaded.
>
> If it doesn't load automatically, let me know and I can help troubleshoot using `/context-tools:setup-mcp`."

The MCP server auto-configures from the plugin manifest. Only if auto-config fails should you run `/context-tools:setup-mcp` for troubleshooting.

## Included Components

### Hooks
- **SessionStart**: Generates project manifest and displays status
- **PreCompact**: Refreshes context before compaction
- **SessionEnd**: Cleanup operations

Note: Indexing is now handled by the MCP server itself (no PreToolUse hook needed).

### MCP Server (repo-map)

**Database Schema (.claude/repo-map.db):**
```sql
symbols table columns:
- name (TEXT): Symbol name (function/class/method name)
- kind (TEXT): "function", "class", or "method"
- signature (TEXT): Full function/method signature with parameters and type hints
  Examples:
  - "extract_symbols_from_python(file_path: Path, relative_to: Path) -> list[Symbol]"
  - "analyze_files(files: list[Path], extractor, language: str, root: Path)"
- docstring (TEXT): First line of docstring or full docstring
- file_path (TEXT): Relative path from project root
- line_number (INTEGER): Start line (1-indexed)
- end_line_number (INTEGER): End line (1-indexed)
- parent (TEXT): For methods, the class name
```

**Available MCP Tools:**
- `mcp__plugin_context-tools_repo-map__search_symbols` - Search symbols by pattern (supports glob wildcards)
  - Returns: name, kind, signature, file_path, line_number, docstring, parent
- `mcp__plugin_context-tools_repo-map__get_file_symbols` - Get all symbols in a specific file
  - Returns: All symbols with full metadata
- `mcp__plugin_context-tools_repo-map__get_symbol_content` - Get full source code of a symbol by exact name
  - Returns: symbol metadata + content (source code text) + location
- `mcp__plugin_context-tools_repo-map__reindex_repo_map` - Trigger manual reindex
- `mcp__plugin_context-tools_repo-map__repo_map_status` - Check indexing status and staleness

**Fallback when MCP tools unavailable:**
Use sqlite3 directly on `.claude/repo-map.db`:
```bash
# Search symbols
sqlite3 .claude/repo-map.db "SELECT name, kind, signature, file_path, line_number FROM symbols WHERE name LIKE 'pattern%' LIMIT 20"

# Get symbol with source
sqlite3 .claude/repo-map.db "SELECT * FROM symbols WHERE name = 'function_name'"
# Then read file_path lines line_number to end_line_number
```

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
