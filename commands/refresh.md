# Update Project Narrative

You are updating the project's living narrative document based on what we learned this session.

## If No Narrative Exists

First check if `.claude/narrative.md` exists. If not, generate one first:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/story.py
```

Then proceed with the update.

## Creating the Session Summary

Before running the update script, write a brief session summary (2-5 sentences) capturing:

- **What we worked on**: The main focus/task of this session
- **Key decisions**: Any significant choices or approaches we took
- **What we learned**: New understanding, gotchas discovered, or insights gained
- **Focus shifts**: If our priorities or understanding changed

Example summaries:
- "We fixed a critical bug in the OAuth flow where tokens weren't refreshing correctly. Discovered that the race condition only occurs under high load. Added retry logic with exponential backoff."
- "Refactored the database layer to use connection pooling. This was prompted by production timeouts. We now understand the connection lifecycle much better."
- "Explored options for caching but decided against Redis due to operational complexity. Will revisit if performance becomes critical."

## Running the Update

Once you have a session summary, run:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/refresh.py "YOUR SESSION SUMMARY HERE"
```

The script will:
1. Read the current narrative from `.claude/narrative.md`
2. Ask Claude to revise (not append to) the narrative based on your summary
3. Save the updated narrative (backup at `.claude/narrative.md.bak`)

## What Gets Updated

The narrative has these sections that may change:

- **Current Foci**: Updated if our focus shifted
- **How It Works**: Updated if architecture/structure changed
- **The Story So Far**: Extended if we completed a significant epoch
- **Dragons & Gotchas**: New warnings added, fixed issues removed
- **Open Questions**: Answered questions removed, new ones added
- **Summary**: Rarely changes unless project purpose evolved

## When to Update

Update the narrative when:
- You completed a significant piece of work
- You discovered something non-obvious about the codebase
- Your understanding of the project shifted
- You hit a "dragon" that future-you should know about
- You answered a long-standing question

Skip updating if:
- The session was just exploration/reading
- Changes were trivial (typos, minor tweaks)
- Nothing changed about your understanding
