#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic"]
# ///
"""
Update project narrative based on session summary and git history.

This script revises an existing narrative document to incorporate new learnings
from a development session. It uses Claude to intelligently merge new information
into the existing structure rather than just appending.

Usage:
    uv run scripts/update-narrative.py "Session summary here"
    uv run scripts/update-narrative.py --git-history  # Auto-extract from git
    uv run scripts/update-narrative.py --git-history "Additional context"
    uv run scripts/update-narrative.py --file session-notes.txt
    echo "summary" | uv run scripts/update-narrative.py --stdin
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime
import anthropic


def backup_narrative(narrative_file: Path) -> Path:
    """Create a backup of the current narrative."""
    backup_file = narrative_file.with_suffix(".md.bak")
    shutil.copy2(narrative_file, backup_file)
    return backup_file


def get_git_history_since_narrative(project_root: Path, narrative_file: Path, max_commits: int = 30) -> str:
    """Extract git commit history since the narrative was last updated."""
    try:
        # Get the last commit that modified the narrative
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H %aI", "--", str(narrative_file)],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            # Narrative not in git, get last 2 weeks of commits
            since_date = (datetime.now() - __import__('datetime').timedelta(days=14)).isoformat()
            last_commit = None
        else:
            parts = result.stdout.strip().split(" ", 1)
            last_commit = parts[0]
            since_date = parts[1] if len(parts) > 1 else None

        # Get commits since that point
        cmd = ["git", "log", f"--max-count={max_commits}", "--format=%h %s (%an, %ar)"]
        if last_commit:
            cmd.append(f"{last_commit}..HEAD")
        elif since_date:
            cmd.extend([f"--since={since_date}"])

        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        if result.returncode != 0:
            return ""

        commits = result.stdout.strip()
        if not commits:
            return "No new commits since last narrative update."

        # Also get files changed
        cmd_files = ["git", "diff", "--stat", "--name-only"]
        if last_commit:
            cmd_files.append(f"{last_commit}..HEAD")

        result_files = subprocess.run(cmd_files, cwd=project_root, capture_output=True, text=True)
        files_changed = result_files.stdout.strip() if result_files.returncode == 0 else ""

        output = f"## Recent Commits (since last narrative update)\n\n{commits}"
        if files_changed:
            # Summarize files changed
            file_list = [f for f in files_changed.split("\n") if f and not f.startswith(".")][:15]
            if file_list:
                output += f"\n\n## Files Changed\n\n" + "\n".join(f"- {f}" for f in file_list)
                if len(files_changed.split("\n")) > 15:
                    output += f"\n- ... and {len(files_changed.split(chr(10))) - 15} more files"

        return output
    except Exception as e:
        print(f"Warning: Could not extract git history: {e}", file=sys.stderr)
        return ""


def update_narrative(current_narrative: str, session_summary: str) -> str:
    """Use Claude to revise the narrative with session learnings."""
    print("Updating narrative with Claude...", file=sys.stderr)

    client = anthropic.Anthropic()

    prompt = f"""You are updating a living project narrative document. Your task is to REVISE
the existing narrative to incorporate new learnings from a development session.

CRITICAL RULES:
1. **REVISE existing sections** - don't just append new text at the end
2. **Keep the SAME structure** (Summary, Current Foci, How It Works, The Story So Far, Dragons & Gotchas, Open Questions)
3. **Maintain "we" voice** throughout
4. **Be concise** - integrate information, don't bloat the document

Section-specific guidance:
- **Summary**: Rarely needs updating unless project's core purpose evolved
- **Current Foci**: Update if focus shifted. Remove completed foci, add new ones.
- **How It Works**: Update if architecture/structure changed significantly
- **The Story So Far**: Only add if we completed a significant epoch. Don't add minor updates.
- **Dragons & Gotchas**: Add new discoveries. Remove if we fixed a dragon.
- **Open Questions**: Remove answered questions, add new ones.

If the session didn't significantly change our understanding, the narrative can stay mostly the same.
The goal is a **living document** that reflects current understanding, not a log of everything.

CURRENT NARRATIVE:
```markdown
{current_narrative}
```

SESSION SUMMARY (what we worked on, learned, discovered):
```
{session_summary}
```

Output ONLY the updated narrative markdown document. No explanations or commentary.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
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
    import argparse
    parser = argparse.ArgumentParser(description="Update project narrative with session summary")
    parser.add_argument("summary", nargs="?", help="Session summary text")
    parser.add_argument("--file", "-f", help="Read session summary from file")
    parser.add_argument("--stdin", action="store_true", help="Read session summary from stdin")
    parser.add_argument("--git-history", "-g", action="store_true",
                        help="Include git history since last narrative update")
    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Print updated narrative without saving")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    narrative_file = project_root / ".claude" / "narrative.md"

    # Check narrative exists
    if not narrative_file.exists():
        print(f"Error: No narrative found at {narrative_file}", file=sys.stderr)
        print("Run /context-daddy:story first to create initial narrative.", file=sys.stderr)
        sys.exit(1)

    # Get session summary from various sources
    session_summary_parts = []

    # Add git history if requested
    if args.git_history:
        git_history = get_git_history_since_narrative(project_root, narrative_file)
        if git_history:
            session_summary_parts.append(git_history)
            print(f"Extracted git history since last update", file=sys.stderr)

    # Add user-provided summary
    if args.stdin:
        user_summary = sys.stdin.read().strip()
        if user_summary:
            session_summary_parts.append(f"## Session Context\n\n{user_summary}")
    elif args.file:
        with open(args.file) as f:
            user_summary = f.read().strip()
            if user_summary:
                session_summary_parts.append(f"## Session Context\n\n{user_summary}")
    elif args.summary:
        session_summary_parts.append(f"## Session Context\n\n{args.summary}")

    # Build final summary
    if not session_summary_parts:
        print("Error: No session summary provided.", file=sys.stderr)
        print("Usage: uv run scripts/update-narrative.py \"What we worked on...\"", file=sys.stderr)
        print("   or: uv run scripts/update-narrative.py --git-history", file=sys.stderr)
        sys.exit(1)

    session_summary = "\n\n".join(session_summary_parts)

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    # Read current narrative
    current_narrative = narrative_file.read_text()

    # Update narrative
    updated_narrative = update_narrative(current_narrative, session_summary)

    if args.dry_run:
        print(updated_narrative)
        return

    # Backup and save
    backup = backup_narrative(narrative_file)
    print(f"Backup saved to {backup}", file=sys.stderr)

    narrative_file.write_text(updated_narrative)
    print(f"Narrative updated: {narrative_file}", file=sys.stderr)

    # Print summary of changes
    old_lines = len(current_narrative.split("\n"))
    new_lines = len(updated_narrative.split("\n"))
    print(f"Lines: {old_lines} -> {new_lines} ({new_lines - old_lines:+d})", file=sys.stderr)


if __name__ == "__main__":
    main()
