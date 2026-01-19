# Generate Project Narrative

Generate a living narrative document for this codebase from git history.

## What This Does

This creates `.claude/narrative.md` - a living document that tells the **story** of the codebase:

- **Summary**: What this project is and why it matters
- **Current Foci**: What we're actively working on
- **How It Works**: Architecture and key subsystems
- **The Story So Far**: How we got here (the journey, not a changelog)
- **Dragons & Gotchas**: Warnings for future-us
- **Open Questions**: Things we're still figuring out

## Running Generation

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/story.py
```

This will:
1. Extract git history (commits, file churn, authors, structure)
2. Save raw data to `.claude/narrative-data.json`
3. Use Claude to synthesize a narrative from the history
4. Save the narrative to `.claude/narrative.md`

## When to Use

- **First time**: Run once to bootstrap the narrative for a codebase
- **Fresh start**: If the narrative has drifted too far from reality
- **New team member**: Generate a narrative to help them understand the project

For ongoing updates after sessions, use `/context-tools:update-narrative` instead.

## Requirements

- Git repository with commit history
- `ANTHROPIC_API_KEY` environment variable set

## Output

The narrative is written in "we" voice - it's OUR project, OUR story. It captures not just facts but opinions, hunches, and tribal knowledge that help understand WHY things are the way they are.
