#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic"]
# ///
"""
Update the project narrative based on a session summary.

This script takes the current narrative and a summary of what happened
in a session, then asks Claude to REVISE (not append to) the narrative
to incorporate the new understanding.

Usage:
    # With session summary from stdin
    echo "We fixed the hooks bug and added validation tests" | uv run scripts/update-narrative.py

    # With session summary as argument
    uv run scripts/update-narrative.py "We fixed the hooks bug and added validation tests"

    # With session summary from file
    uv run scripts/update-narrative.py --file session-notes.txt
"""

import sys
from pathlib import Path
import anthropic
import argparse


def update_narrative(current_narrative: str, session_summary: str) -> str:
    """Use Claude to update the narrative based on session activity."""

    client = anthropic.Anthropic()

    prompt = f"""You are updating a project narrative document based on what happened in a recent session.

CURRENT NARRATIVE:
```markdown
{current_narrative}
```

SESSION SUMMARY (what we worked on):
```
{session_summary}
```

Your task: UPDATE the narrative to incorporate what we learned/did this session.

CRITICAL RULES:
1. REVISE existing sections - don't just append new text at the end
2. Keep the SAME structure (Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, Open Questions)
3. Maintain "we" voice throughout
4. Be concise - integrate information, don't bloat

Specific guidance:
- **Current Foci**: Update if our focus shifted. Remove completed foci, add new ones.
- **The Story So Far**: Only add if we completed a significant epoch. Don't add minor updates.
- **Dragons & Gotchas**: Add new discoveries. Can also remove if we fixed a dragon.
- **Open Questions**: Update based on what we learned. Remove answered questions, add new ones.
- **How It Works**: Update if architecture/structure changed significantly.
- **Summary**: Rarely needs updating unless the project's core purpose evolved.

If the session didn't change much about our understanding, it's OK for the narrative to be mostly the same.
The goal is a LIVING DOCUMENT that reflects our current understanding, not a log of everything that happened.

Output ONLY the updated markdown document, nothing else.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.content[0].text

    # Strip markdown code fences if Claude wrapped the output
    if result.startswith("```markdown"):
        result = result[len("```markdown"):].lstrip("\n")
    if result.startswith("```"):
        result = result[3:].lstrip("\n")
    if result.endswith("```"):
        result = result[:-3].rstrip("\n")

    return result


def main():
    parser = argparse.ArgumentParser(description="Update project narrative based on session activity")
    parser.add_argument("summary", nargs="?", help="Session summary (what we worked on)")
    parser.add_argument("--file", "-f", help="Read session summary from file")
    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Print updated narrative without saving")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    narrative_file = project_root / ".claude" / "narrative.md"

    # Get current narrative
    if not narrative_file.exists():
        print(f"Error: No narrative found at {narrative_file}", file=sys.stderr)
        print("Run story.py first to create initial narrative.", file=sys.stderr)
        sys.exit(1)

    current_narrative = narrative_file.read_text()

    # Get session summary
    if args.file:
        session_summary = Path(args.file).read_text()
    elif args.summary:
        session_summary = args.summary
    elif not sys.stdin.isatty():
        session_summary = sys.stdin.read()
    else:
        print("Error: No session summary provided.", file=sys.stderr)
        print("Provide as argument, --file, or pipe to stdin.", file=sys.stderr)
        sys.exit(1)

    if not session_summary.strip():
        print("Error: Session summary is empty.", file=sys.stderr)
        sys.exit(1)

    print(f"Updating narrative based on session summary...", file=sys.stderr)
    print(f"Session: {session_summary[:100]}{'...' if len(session_summary) > 100 else ''}", file=sys.stderr)

    updated_narrative = update_narrative(current_narrative, session_summary)

    if args.dry_run:
        print("\n--- UPDATED NARRATIVE (dry run) ---\n")
        print(updated_narrative)
    else:
        # Backup current narrative
        backup_file = project_root / ".claude" / "narrative.md.bak"
        backup_file.write_text(current_narrative)
        print(f"Backup saved to {backup_file}", file=sys.stderr)

        # Save updated narrative
        narrative_file.write_text(updated_narrative)
        print(f"Narrative updated at {narrative_file}", file=sys.stderr)
        print(updated_narrative)


if __name__ == "__main__":
    main()
