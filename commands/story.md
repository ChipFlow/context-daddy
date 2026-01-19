# Generate Project Narrative

Generate a living narrative document for this codebase from git history.

## Step 1: Extract Git Data

Run the extraction script:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/story.py --extract-only
```

This saves git history data to `.claude/narrative-data.json`.

## Step 2: Generate Narrative

Read the extracted data:

```
Read .claude/narrative-data.json
```

Then generate a narrative document with EXACTLY this structure and write it to `.claude/narrative.md`:

```markdown
# Project Narrative: [project_name]

## Summary
<!-- 2-3 sentences. The elevator pitch. What is this and why does it matter? -->

## Current Foci
<!-- What we're actively working on NOW. Based on recent commits, what are the 2-4 active areas? -->

- **[Focus area]**: Brief description of what and why

## How It Works
<!-- Current architecture/structure. Main subsystems and their roles. Keep concise but useful. -->

## The Story So Far
<!-- Narrative of how we got here. Identify major phases/epochs. Not a list of commits, but the STORY. -->

## Dragons & Gotchas
<!-- Warnings for future-us. Fragile areas, non-obvious behavior, things that bit us. -->

## Open Questions
<!-- Things we're still figuring out. Uncertainties. Technical debt we're aware of. -->
```

**Critical rules for generation:**
- Write in "we" voice throughout - this is OUR project, OUR narrative
- Be opinionated - include hunches and intuitions, not just facts
- This is NOT a changelog - it's a story that helps understand WHY things are the way they are
- Look at commit patterns, file churn, and major changes to identify epochs and focus areas
- High-churn files often indicate pain points (dragons)

## When to Use

- **First time**: Bootstrap the narrative for a codebase
- **Fresh start**: If the narrative has drifted too far from reality
- **New team member**: Help them understand the project story

For ongoing updates after sessions, use `/context-daddy:refresh` instead.
