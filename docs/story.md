# The Story So Far

This page captures the evolving narrative of context-daddy - not just what it does, but why it exists and what we've learned building it.

## The Vision

We started with a simple observation: Claude struggles with large codebases. It either drowns in context trying to understand everything at once, or makes blind guesses without sufficient understanding. There had to be a better way.

The solution: give Claude a structured way to explore code semantically. Instead of reading files randomly, it could query for symbols by name, understand the codebase structure through maps, and dive into specific implementations only when needed.

## Evolution

### v0.1-v0.3: The Naive Approach

Our first attempt was straightforward - use tree-sitter to parse code and generate repository maps. It worked fine for small projects but failed catastrophically on anything substantial. Memory would explode as we tried to parse everything simultaneously.

**Lesson learned**: You can't just load an entire codebase into memory. Even with tree-sitter's efficiency, large repos require incremental processing.

### v0.4-v0.5: MCP Server Architecture

Static repository maps weren't enough. Claude needed fast, targeted access to specific symbols. This led us to build an MCP server - a live query interface for code exploration rather than just generated static files.

**Lesson learned**: The real value isn't in the map itself, but in the ability to query it dynamically.

### v0.6-v0.8: Process Management Nightmares

This era was dominated by resource management issues:
- Indexing processes hanging after Claude sessions ended
- Memory leaks from multiple tree-sitter instances
- Lock file conflicts between concurrent sessions

We went through multiple iterations:
1. **PreToolUse hooks** - Spawned too many background processes
2. **Thread-based indexing** - Hung tree-sitter froze entire MCP server
3. **Multiprocess architecture** - Finally isolated indexing properly

**Lesson learned**: Process isolation is worth the complexity. A hung parser shouldn't take down the whole system.

### v0.9: Database Versioning

As the schema evolved, users hit compatibility issues between plugin versions. We added database versioning and learned that multiple Claude sessions can coexist with different plugin versions - we just need to handle schema mismatches gracefully.

**Lesson learned**: Schema versioning isn't optional. Plan for it from the start.

### v0.10: Documentation & Narrative

A philosophical shift: understanding codebases isn't just about parsing syntax. It's about capturing the stories, decisions, and hard-won insights that accumulate around projects.

Traditional documentation captures *what* code does. Narratives capture *why* it exists and what we've learned building it.

**Lesson learned**: Tribal knowledge is valuable and worth preserving systematically.

## Dragons & Gotchas

Hard-won lessons that aren't obvious from reading the code:

### Hooks Autodiscovery

The hooks system is more fragile than it appears. Declaring hooks in both `plugin.json` and `hooks/hooks.json` causes validation failures. The fix: only use `hooks/hooks.json` - Claude Code autodiscovers them.

### Tree-sitter Memory

Tree-sitter memory usage is unpredictable and can spike dramatically with certain file types or parsing errors. Our subprocess isolation helps, but resource limits are essential.

### SQLite Concurrency

WAL mode saves us from many concurrency issues, but database migrations still require care. We moved away from process locks (which caused deadlocks) to graceful cleanup based on process detection.

### MCP Server Lifecycle

The MCP server lifecycle is tightly coupled to Claude Code's session management in ways that aren't well-documented. We've reverse-engineered expected behaviors through trial and error - particularly around when servers start, stop, and restart.

## Open Questions

Things we're still figuring out:

- **Cache invalidation**: The current mtime+hash approach works but feels heavyweight. Filesystem watching or git hooks might be more elegant.

- **Narrative maintenance**: How do we keep tribal knowledge current without it becoming a maintenance burden? When should narratives be version-controlled?

- **FTS utilization**: The full-text search infrastructure exists but we haven't found the right UX patterns to make it genuinely useful in Claude's workflow.

- **Validation**: How do we measure whether narratives are actually useful? Technical metrics like indexing speed are easy; the value of tribal knowledge is harder to quantify.

## Philosophy

A few principles that have emerged:

1. **Structure before detail** - Help Claude understand the map before exploring the territory
2. **Fail gracefully** - A hung process shouldn't corrupt data or block the session
3. **Context is precious** - Return markdown, not JSON; be concise, not comprehensive
4. **Stories matter** - The "why" is often more valuable than the "what"
