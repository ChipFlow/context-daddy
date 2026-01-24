# Update Project Narrative

Update the project's living narrative based on what we learned this session.

## IMPORTANT: This is an executable skill

When invoked, you MUST execute the update process below. Don't just explain it - DO it.

## Step 1: Check Prerequisites

First, verify the narrative exists:
```bash
ls -la .claude/narrative.md
```

If the file doesn't exist, tell the user to run `/context-daddy:story` first and stop.

## Step 2: Get Session Summary

If the user provided a summary with the command (e.g., `/context-daddy:refresh "we fixed the auth bug"`), use that.

Otherwise, ask the user:
> What did we work on this session? (Key tasks, decisions, discoveries, or gotchas)

Wait for their response before proceeding.

## Step 3: Run the Update Script

Execute the update script with the user's summary:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/update-narrative.py "<USER_SUMMARY_HERE>"
```

Replace `<USER_SUMMARY_HERE>` with the actual summary from Step 2.

**If the script fails** (e.g., missing ANTHROPIC_API_KEY), fall back to manual update in Step 4.

## Step 4: Manual Fallback (only if script fails)

If the automated script isn't available, do a manual update:

1. Read `.claude/narrative.md`
2. Revise it based on the session summary
3. Write the updated content back

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
- Brief summary of what changed (if visible from script output)

## When to Skip

If the session was just exploration/reading with no significant learnings, it's OK to skip the update. Tell the user:
> "Nothing significant to update - narrative is still current."
