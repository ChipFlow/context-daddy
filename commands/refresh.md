# Update Project Narrative

Update the project's living narrative based on what we learned this session.

## Step 1: Check Narrative Exists

Read `.claude/narrative.md`. If it doesn't exist, run `/context-daddy:story` first.

## Step 2: Get Session Summary

Ask the user (or recall from the session) what we worked on:
- Main focus/task of this session
- Key decisions or approaches
- New understanding or gotchas discovered
- Any focus shifts

## Step 3: Update the Narrative

Read the current narrative, then write an updated version to `.claude/narrative.md`.

**CRITICAL RULES:**
1. **REVISE existing sections** - don't just append new text at the end
2. **Keep the SAME structure** (Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, Open Questions)
3. **Maintain "we" voice** throughout
4. **Be concise** - integrate information, don't bloat

**Section-specific guidance:**
- **Current Foci**: Update if focus shifted. Remove completed foci, add new ones.
- **The Story So Far**: Only add if we completed a significant epoch. Don't add minor updates.
- **Dragons & Gotchas**: Add new discoveries. Remove if we fixed a dragon.
- **Open Questions**: Remove answered questions, add new ones.
- **How It Works**: Update if architecture/structure changed significantly.
- **Summary**: Rarely needs updating unless project's core purpose evolved.

**LENGTH LIMITS** (sections are auto-truncated when injected):
- **Summary**: ~2-3 sentences, under 300 chars
- **Current Foci**: 2-4 bullets, under 400 chars
- **Dragons**: Key warnings, under 300 chars

If the session didn't change much about our understanding, the narrative can stay mostly the same.
The goal is a **living document** that reflects current understanding, not a log of everything.

## When to Update

**Update when:**
- Completed significant work
- Discovered something non-obvious
- Understanding of the project shifted
- Hit a "dragon" that future-us should know about
- Answered a long-standing question

**Skip if:**
- Session was just exploration/reading
- Changes were trivial (typos, minor tweaks)
- Nothing changed about understanding
