# TODO: Future Enhancements

## String Literals and Comments Indexing

**Status**: Planned for future release

**Goal**: Extend repo-map indexing to capture string literals and comments, making it a comprehensive search tool that eliminates most Grep usage.

### Use Cases

**String Literals:**
- Find error messages: `search_strings("connection failed")`
- Find API endpoints: `search_strings("/api/users")`
- Find log messages: `search_strings("Starting server")`
- Find config keys: `search_strings("DATABASE_URL")`

**Comments:**
- Find TODOs: `search_comments(tags="TODO")`
- Find FIXMEs: `search_comments(tags="FIXME")`
- Find architecture notes: `search_comments("design pattern")`
- Find explanatory comments: `search_comments("this function")`

### Schema Extensions

```sql
-- New: String literals table
CREATE TABLE string_literals (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,      -- The literal value
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    context TEXT,               -- Function/class containing this literal
    kind TEXT                   -- single, double, triple, f-string, raw, etc.
);

-- New: Comments table
CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    content TEXT NOT NULL,      -- Comment text (without # or // or /* */)
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    kind TEXT,                  -- line, block, docstring
    tags TEXT                   -- TODO, FIXME, NOTE, BUG, HACK, XXX, etc.
);

-- Indexes for fast searching
CREATE INDEX idx_string_content ON string_literals(content);
CREATE INDEX idx_string_file ON string_literals(file_path);
CREATE INDEX idx_comment_content ON comments(content);
CREATE INDEX idx_comment_file ON comments(file_path);
CREATE INDEX idx_comment_tags ON comments(tags);
```

### New MCP Tools

- `search_strings(pattern, file?)` - Find string literals matching pattern
- `search_comments(pattern?, tags?, file?)` - Find comments, optionally filtered by tags
- `get_todos()` - Shorthand for `search_comments(tags="TODO")`
- `get_fixmes()` - Shorthand for `search_comments(tags="FIXME")`

### Implementation Tasks

1. **Python Support** (Easiest - use AST):
   - Extract `ast.Constant` nodes with string values
   - Extract comment nodes (use `tokenize` module)
   - Detect comment tags (TODO, FIXME, etc.) with regex

2. **C++ Support** (tree-sitter):
   - Extend tree-sitter query for `string_literal` nodes
   - Extract `comment` nodes from parse tree
   - Handle different comment styles: `//`, `/**/`, docstrings

3. **Rust Support** (tree-sitter):
   - Extract `string_literal` and `raw_string_literal` nodes
   - Extract `line_comment` and `block_comment` nodes
   - Handle doc comments `///` and `//!`

4. **MCP Server Updates**:
   - Add `search_strings` tool
   - Add `search_comments` tool
   - Add convenience tools (`get_todos`, `get_fixmes`)

5. **Database Migration**:
   - Bump `CACHE_VERSION` to trigger reindex
   - Create new tables with proper indexes
   - Update `write_symbols_to_sqlite` to handle new tables

### Considerations

**Performance:**
- Database size will increase (many more entries)
- Consider limiting string literal length (exclude very long strings)
- Consider excluding common/boring strings ("", " ", etc.)

**Memory:**
- Current single-threaded indexing should handle this fine
- Might need to batch writes to SQLite for large projects

**Configuration:**
- Add option to disable string/comment indexing (for very large repos)
- Add option to configure which comment tags to index

### Breaking Changes

- Requires database schema change (CACHE_VERSION bump)
- Users will need to wait for full reindex on first use
- Old repo-map.db files won't be compatible

### Benefits

- **Eliminates ~80% of Grep usage** for code searches
- Find error messages without reading whole codebase
- Track TODOs/FIXMEs systematically
- Fast API endpoint discovery
- Understand logging patterns across project

### Estimated Effort

- Python implementation: 4-6 hours
- C++/Rust implementation: 6-8 hours
- MCP tools: 2-3 hours
- Testing: 3-4 hours
- **Total: ~20 hours**

---

## Other Future Ideas

### Multi-Repository Support
Track symbols across multiple related repositories (monorepo support).

### Symbol References
Track where symbols are used, not just where they're defined (call graph).

### Import/Include Tracking
Index all imports/includes to understand dependencies.

### Type Information
Enhanced type tracking beyond just signatures (full type hierarchies).

### AI-Powered Similar Code Detection
Use embeddings to find semantically similar code beyond just name matching.
