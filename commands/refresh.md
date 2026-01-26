# Update Project Narrative

Update the project's living narrative based on git history and session learnings.

## IMPORTANT: This is an executable skill

When invoked, you MUST execute the update process below. Don't just explain it - DO it.

## Step 1: Check Prerequisites

Verify the narrative exists:
```bash
ls -la .claude/narrative.md
```

If the file doesn't exist, tell the user to run `/context-daddy:story` first and stop.

## Step 2: Gather Context

Build a session summary from TWO sources:

### A. Your Session Understanding

Reflect on what you know from the current session:
- What tasks did we work on?
- What decisions were made?
- What did we learn or discover?
- Any gotchas or dragons encountered?
- Did focus shift during the session?

### B. User Input (Optional)

If the user provided a summary with the command (e.g., `/context-daddy:refresh "we fixed the auth bug"`), incorporate that.

If you're unsure about key context, ask:
> Is there anything specific from this session I should include in the narrative update?

## Step 3: Run the Update Script

Execute with `--git-history` flag to include recent commits, plus your session context:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/update-narrative.py --git-history "SESSION_CONTEXT_HERE"
```

Replace `SESSION_CONTEXT_HERE` with a concise summary combining:
- Your understanding from the session (Step 2A)
- Any user-provided context (Step 2B)

Example:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/update-narrative.py --git-history "Made refresh skill executable, added CI workflow for narrative freshness. Key insight: skills need to be prescriptive not just documentation."
```

The `--git-history` flag automatically extracts commits since the last narrative update.

**If the script fails** (e.g., missing ANTHROPIC_API_KEY), fall back to Step 4.

## Step 4: Manual Fallback (only if script fails)

If the automated script isn't available:

1. Get git history since last update:
   ```bash
   git log --oneline $(git log -1 --format=%H -- .claude/narrative.md)..HEAD
   ```

2. Read `.claude/narrative.md`

3. Revise it based on:
   - The git commits (what changed)
   - Your session understanding (why it changed, what we learned)

4. Write the updated content back

**CRITICAL RULES for manual update:**
- **REVISE existing sections** - don't append to end
- **Keep the SAME structure** (Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, Open Questions)
- **Maintain "we" voice** throughout
- **Be concise** - integrate, don't bloat

**Section guidance:**
- **Current Foci**: Update if focus shifted. Remove completed, add new.
- **The Story So Far**: Only add for significant epochs.
- **Dragons & Gotchas**: Add discoveries, remove fixed ones.
- **Open Questions**: Remove answered, add new.

**LENGTH LIMITS** (auto-truncated when injected):
- Summary: ~2-3 sentences, under 300 chars
- Current Foci: 2-4 bullets, under 400 chars
- Dragons: Key warnings, under 300 chars

## Step 5: Confirm Success

After the update completes, tell the user:
- Narrative has been updated
- Brief summary of what changed

## When to Skip

If the session was just exploration/reading with no significant learnings, it's OK to skip. Tell the user:
> "Nothing significant to update - narrative is still current."
