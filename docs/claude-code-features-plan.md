# Claude Code Features Integration Plan

Leverage new Claude Code 2.1.x features to improve context-daddy.

## Overview

| Feature | Priority | Effort | Impact |
|---------|----------|--------|--------|
| `context: fork` for skills | High | Low | Cleaner sessions |
| PreToolUse `additionalContext` | High | Medium | Better MCP adoption |
| Hooks in skill frontmatter | Medium | Low | Simpler config |
| `${CLAUDE_SESSION_ID}` tracking | Medium | Low | Better metadata |
| SubagentStart hook | Medium | Medium | Context for subagents |
| MCP `list_changed` notifications | Low | Medium | Dynamic tools |
| Task management integration | Low | High | Advanced workflows |
| `--add-dir` exploration | Low | Low | Research only |
| Background tasks with `&` | Low | Low | Nice to have |

---

## Phase 1: Quick Wins (This Week)

### 1.1 Add `context: fork` to Skills

**Goal:** Run narrative commands in isolated context so they don't pollute main session.

**Files to modify:**
- `commands/story.md`
- `commands/refresh.md`
- `commands/readme.md`

**Implementation:**
```yaml
---
context: fork
allowed-tools: [Bash, Read, Write]
---
# Generate Project Narrative
...
```

**Test:** Run `/context-daddy:story`, verify main session context unchanged.

---

### 1.2 Add `${CLAUDE_SESSION_ID}` to Narrative Metadata

**Goal:** Track which session created/updated narratives for debugging and history.

**Files to modify:**
- `scripts/story.py` - Add session ID to narrative-data.json
- `commands/refresh.md` - Include session ID in updates

**Implementation:**
```python
# In story.py extract_git_data()
import os
data = {
    "session_id": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
    "project_name": project_root.name,
    ...
}
```

```markdown
<!-- In narrative.md footer -->
_Last updated: 2026-01-20 by session abc123_
```

**Test:** Generate narrative, verify session ID captured.

---

### 1.3 Hooks in Skill Frontmatter

**Goal:** Move skill-specific hooks into the skill files themselves for cleaner organization.

**Files to modify:**
- `commands/story.md` - Add any pre/post hooks
- `commands/map.md` - Add hooks for indexing

**Example:**
```yaml
---
context: fork
allowed-tools: [Bash, Read, Write]
hooks:
  - type: PostToolUse
    matcher: Write(.claude/narrative.md)
    run: echo "Narrative updated"
---
```

**Note:** Evaluate if this is cleaner than centralized `hooks/hooks.json`. May keep both.

---

## Phase 2: MCP Tool Nudging (Next Week)

### 2.1 PreToolUse Hook with `additionalContext`

**Goal:** When Claude tries to use Grep/Search/Glob for code, inject a reminder about MCP tools.

**New file:** `hooks/nudge-mcp.sh`

```bash
#!/usr/bin/env bash
# PreToolUse hook that returns additionalContext when Claude uses search tools

TOOL_NAME="$1"

# Check if it's a search-related tool
case "$TOOL_NAME" in
  Grep|Search|Glob)
    # Return additionalContext to nudge toward MCP
    cat << 'EOF'
{
  "decision": "approve",
  "additionalContext": "💡 Reminder: For code symbols, MCP tools are 10-100x faster:\n• search_symbols(\"pattern\") for functions/classes\n• get_symbol_content(\"name\") for source code\n• list_files(\"*.py\") for file discovery"
}
EOF
    ;;
  *)
    echo '{"decision": "approve"}'
    ;;
esac
```

**Update `hooks/hooks.json`:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Grep|Search|Glob",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/nudge-mcp.sh"
          }
        ]
      }
    ]
  }
}
```

**Test:** Use Grep in a session, verify nudge message appears in context.

---

### 2.2 SubagentStart Hook

**Goal:** Inject context-daddy context when subagents (Task tool) spawn.

**New file:** `hooks/subagent-context.sh`

```bash
#!/usr/bin/env bash
# SubagentStart hook - inject key context for subagents

CLAUDE_DIR="${PWD}/.claude"

# Build minimal context for subagent
CONTEXT=""

if [[ -f "${CLAUDE_DIR}/narrative.md" ]]; then
    # Extract just the summary
    SUMMARY=$(sed -n '/^## Summary/,/^## /p' "${CLAUDE_DIR}/narrative.md" | head -5)
    CONTEXT="Project context: ${SUMMARY}"
fi

# Add MCP tools reminder
CONTEXT="${CONTEXT}\n\nMCP tools available: search_symbols, get_symbol_content, list_files"

# Return as additionalContext
CONTEXT_ESCAPED=$(echo -e "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" | sed 's/^"//;s/"$//')

cat << EOF
{
  "additionalContext": "${CONTEXT_ESCAPED}"
}
EOF
```

**Update `hooks/hooks.json`:**
```json
{
  "hooks": {
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/subagent-context.sh"
          }
        ]
      }
    ]
  }
}
```

**Test:** Spawn a Task agent, verify it receives context.

---

## Phase 3: Advanced Features (Future)

### 3.1 MCP `list_changed` Notifications

**Goal:** Dynamically update available MCP tools without session restart.

**Use cases:**
- Add new markdown files → update md_* tool suggestions
- Reindex completes → notify tools are ready
- New symbols detected → update search suggestions

**Implementation approach:**
1. Research MCP notification protocol
2. Add notification capability to `repo-map-server.py`
3. Trigger on reindex completion

**Files to modify:**
- `servers/repo-map-server.py`

**Effort:** Medium - requires understanding MCP notification protocol.

---

### 3.2 Task Management Integration

**Goal:** Integrate with Claude Code's built-in task management for narrative updates.

**Use cases:**
- Auto-create task "Update narrative" after significant work
- Track narrative freshness as a task
- Dependencies: "Complete feature X" blocks "Update narrative"

**Implementation approach:**
1. Research TaskCreate/TaskUpdate tool APIs
2. Add task creation to stop-reorient hook
3. Mark narrative update as task completion

**Effort:** High - requires understanding task system deeply.

---

### 3.3 `--add-dir` Exploration

**Goal:** Understand if `--add-dir` can help load narrative context automatically.

**Research questions:**
- Can we point `--add-dir` to `.claude/` to auto-load narrative?
- Does it work with plugin-generated content?
- Any conflicts with existing CLAUDE.md loading?

**Action:** Test manually, document findings.

---

### 3.4 Background Tasks with `&` Prefix

**Goal:** Allow users to send narrative generation to claude.ai in background.

**Use case:**
```
& /context-daddy:story
```

User continues working while narrative generates on claude.ai.

**Implementation:** Mostly documentation - feature exists, we just need to tell users about it.

**Add to README/docs:**
```markdown
## Background Generation

For long narratives, prefix with `&` to run on claude.ai:
```
& /context-daddy:story
```
```

---

## Implementation Checklist

### Phase 1 (This Week)
- [ ] Add `context: fork` to story.md
- [ ] Add `context: fork` to refresh.md
- [ ] Add `context: fork` to readme.md
- [ ] Add session ID capture to story.py
- [ ] Add session ID to narrative footer
- [ ] Test forked context behavior
- [ ] Evaluate hooks-in-frontmatter vs centralized

### Phase 2 (Next Week)
- [ ] Create `hooks/nudge-mcp.sh`
- [ ] Add PreToolUse hook to hooks.json
- [ ] Test MCP nudging behavior
- [ ] Create `hooks/subagent-context.sh`
- [ ] Add SubagentStart hook to hooks.json
- [ ] Test subagent context injection

### Phase 3 (Future)
- [ ] Research MCP list_changed protocol
- [ ] Prototype dynamic tool updates
- [ ] Research task management APIs
- [ ] Test `--add-dir` behavior
- [ ] Document background task usage

---

## Success Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| `context: fork` | Session cleanliness | No narrative artifacts in main context |
| PreToolUse nudge | MCP tool usage | 50% reduction in Grep for code lookups |
| SubagentStart | Subagent effectiveness | Subagents use MCP tools without prompting |
| Session ID tracking | Debuggability | Can trace narrative history |

---

## Notes

- All changes should be backward compatible
- Test on both fresh sessions and resumed sessions
- Monitor context window usage - don't bloat with nudges
- Version bump after each phase completion
