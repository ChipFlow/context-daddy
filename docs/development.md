# Development

Future plans, design decisions, and development history.

## Planned Features

### String Literals and Comments Indexing

**Status**: Planned

Extend repo-map indexing to capture string literals and comments, enabling concept searches without grep.

**Use Cases:**
- Find error messages: `search_strings("connection failed")`
- Find TODOs: `search_comments(tags="TODO")`
- Find API endpoints: `search_strings("/api/users")`

**Schema Extensions:**

```sql
CREATE TABLE string_literals (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    context TEXT,
    kind TEXT  -- single, double, triple, f-string, raw
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    kind TEXT,  -- line, block, docstring
    tags TEXT   -- TODO, FIXME, NOTE, etc.
);
```

**New MCP Tools:**
- `search_strings(pattern, file?)` - Find string literals
- `search_comments(pattern?, tags?, file?)` - Find comments
- `get_todos()` / `get_fixmes()` - Convenience tools

### Full-Text Search (FTS)

**Status**: Planned

Enable fast, relevance-ranked searches across comments, docstrings, and string literals.

```sql
CREATE VIRTUAL TABLE code_text_fts USING fts5(
    file_path UNINDEXED,
    line_number UNINDEXED,
    element_type UNINDEXED,  -- 'comment', 'docstring', 'string_literal'
    symbol_name UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 2'
);
```

**Search tool:**
```python
search_text(
    query="connection pool",
    element_type="docstring",  # or 'comment', 'string_literal', 'all'
    limit=20
)
```

**Performance**: FTS5 queries <50ms vs grep 100-500ms (10-20x faster).

### Other Ideas

- **Multi-Repository Support** - Track symbols across related repos
- **Symbol References** - Call graph: where symbols are used, not just defined
- **Import/Include Tracking** - Index dependencies
- **AI-Powered Similar Code** - Embeddings for semantic search

---

## Completed Features

### v0.10.x - Documentation & CI

- mdbook documentation with GitHub Pages
- PR preview workflow
- Mermaid diagrams in architecture docs

### v0.9.x - Plugin Stability

- Database versioning for schema compatibility
- Plugin configuration validation tests
- E2E hook testing in CI

### v0.8.0 - Multiprocess Architecture

Changed from thread-based to subprocess-based indexing.

**Why**: Hung tree-sitter parsing would freeze the entire MCP server.

**Solution**:
- `do_index()` spawns subprocess: `uv run scripts/generate-repo-map.py`
- Watchdog can SIGKILL hung subprocess without affecting MCP server
- SQLite WAL handles concurrent read (MCP) / write (subprocess)

**Resource Limits**:
- Memory: 4GB virtual address space
- CPU: 20 minutes timeout
- Watchdog checks every 60 seconds

### v0.7.x - Indexing Status & Watchdog

Added metadata table to track indexing status and detect hung processes.

**Metadata keys**: `status`, `db_version`, `last_indexed`, `symbol_count`

**Watchdog**:
- Detects indexing stuck >10 minutes
- Sets `status='failed'` with error message
- Safety check prevents hung process from overwriting after watchdog intervention
