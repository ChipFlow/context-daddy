#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic"]
# ///
"""
Generate a project narrative from git history.

This script analyzes git history to produce a narrative document that tells
the story of how a codebase evolved - not a changelog, but a coherent
narrative that helps someone understand WHY things are the way they are.

Usage:
    uv run scripts/generate-narrative.py [project_root]
"""

import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import anthropic

def run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return output."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def get_commit_history(cwd: Path, limit: int = 500) -> list[dict]:
    """Get commit history with details."""
    # Format: hash|author|date|subject
    log = run_git([
        "log",
        f"-{limit}",
        "--pretty=format:%H|%an|%aI|%s",
        "--no-merges"
    ], cwd)

    commits = []
    for line in log.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0][:8],
                "author": parts[1],
                "date": parts[2][:10],
                "subject": parts[3]
            })
    return commits

def get_commit_files(cwd: Path, commit_hash: str) -> list[str]:
    """Get files changed in a commit."""
    output = run_git(["show", "--name-only", "--pretty=format:", commit_hash], cwd)
    return [f for f in output.split("\n") if f.strip()]

def get_file_history(cwd: Path, filepath: str) -> list[dict]:
    """Get commit history for a specific file."""
    log = run_git([
        "log",
        "--pretty=format:%H|%aI|%s",
        "--follow",
        "--", filepath
    ], cwd)

    commits = []
    for line in log.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) >= 3:
            commits.append({
                "hash": parts[0][:8],
                "date": parts[1][:10],
                "subject": parts[2]
            })
    return commits

def get_major_changes(cwd: Path, limit: int = 50) -> list[dict]:
    """Find commits with significant changes (many files)."""
    log = run_git([
        "log",
        f"-{limit * 2}",
        "--pretty=format:%H|%aI|%s",
        "--shortstat",
        "--no-merges"
    ], cwd)

    major = []
    lines = log.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) >= 3:
                commit = {
                    "hash": parts[0][:8],
                    "date": parts[1][:10],
                    "subject": parts[2],
                    "files_changed": 0,
                    "insertions": 0,
                    "deletions": 0
                }
                # Look for stat line
                if i + 2 < len(lines):
                    stat_line = lines[i + 2].strip()
                    if "file" in stat_line:
                        # Parse "X files changed, Y insertions(+), Z deletions(-)"
                        import re
                        files_match = re.search(r"(\d+) file", stat_line)
                        ins_match = re.search(r"(\d+) insertion", stat_line)
                        del_match = re.search(r"(\d+) deletion", stat_line)
                        if files_match:
                            commit["files_changed"] = int(files_match.group(1))
                        if ins_match:
                            commit["insertions"] = int(ins_match.group(1))
                        if del_match:
                            commit["deletions"] = int(del_match.group(1))

                # Consider "major" if touches many files or lots of lines
                if commit["files_changed"] >= 5 or (commit["insertions"] + commit["deletions"]) >= 100:
                    major.append(commit)
        i += 1

    return major[:limit]

def get_directory_structure(cwd: Path) -> dict:
    """Get current directory structure with file counts."""
    structure = defaultdict(lambda: {"files": 0, "extensions": set()})

    # Get tracked files
    files = run_git(["ls-files"], cwd).split("\n")

    for f in files:
        if not f.strip():
            continue
        path = Path(f)
        # Get top-level and second-level directories
        parts = path.parts
        if len(parts) >= 1:
            top = parts[0]
            structure[top]["files"] += 1
            if path.suffix:
                structure[top]["extensions"].add(path.suffix)

    # Convert sets to lists for JSON
    return {k: {"files": v["files"], "extensions": list(v["extensions"])}
            for k, v in structure.items()}

def get_authors(cwd: Path) -> list[dict]:
    """Get contributor summary."""
    log = run_git(["shortlog", "-sne", "HEAD"], cwd)
    authors = []
    for line in log.split("\n"):
        if not line.strip():
            continue
        # Format: "  123\tName <email>"
        parts = line.strip().split("\t", 1)
        if len(parts) >= 2:
            authors.append({
                "commits": int(parts[0].strip()),
                "name": parts[1].split("<")[0].strip()
            })
    return authors[:10]

def get_file_churn(cwd: Path, limit: int = 20) -> list[dict]:
    """Find files that change most frequently."""
    # Get all files changed in recent commits
    log = run_git(["log", "-200", "--name-only", "--pretty=format:"], cwd)

    file_counts = defaultdict(int)
    for line in log.split("\n"):
        if line.strip():
            file_counts[line.strip()] += 1

    # Sort by count
    sorted_files = sorted(file_counts.items(), key=lambda x: -x[1])
    return [{"file": f, "changes": c} for f, c in sorted_files[:limit]]

def get_recent_activity(cwd: Path, days: int = 30) -> dict:
    """Get recent activity summary."""
    since = f"--since={days} days ago"

    commit_count = len(run_git(["log", since, "--oneline"], cwd).split("\n"))

    # Get recently changed files
    files = run_git(["log", since, "--name-only", "--pretty=format:"], cwd)
    recent_files = set(f for f in files.split("\n") if f.strip())

    return {
        "commits_last_30_days": commit_count,
        "files_touched": len(recent_files)
    }

def extract_git_data(project_root: Path) -> dict:
    """Extract all relevant git data for narrative generation."""
    print("Extracting git history...", file=sys.stderr)

    data = {
        "project_name": project_root.name,
        "extracted_at": datetime.now().isoformat(),
        "commits": get_commit_history(project_root, limit=200),
        "major_changes": get_major_changes(project_root, limit=30),
        "structure": get_directory_structure(project_root),
        "authors": get_authors(project_root),
        "file_churn": get_file_churn(project_root, limit=15),
        "recent_activity": get_recent_activity(project_root),
    }

    # Get first and last commit dates
    if data["commits"]:
        data["first_commit"] = data["commits"][-1]["date"]
        data["last_commit"] = data["commits"][0]["date"]
        data["total_commits"] = len(data["commits"])

    return data

def generate_narrative(git_data: dict) -> str:
    """Use Claude to generate a narrative from git data."""
    print("Generating narrative with Claude...", file=sys.stderr)

    client = anthropic.Anthropic()

    prompt = f"""Analyze this git history data and generate a PROJECT NARRATIVE document.

This is NOT a changelog or git log. It's a living narrative that tells the STORY of this codebase -
how it evolved, why things are the way they are, what the team is thinking.

CRITICAL: Write in "we" voice throughout. This is OUR project, OUR narrative.
Not "Rob did X" but "We built X because..."

Be opinionated. Include hunches and intuitions, not just facts.

Git Data:
```json
{json.dumps(git_data, indent=2)}
```

Generate a markdown document with EXACTLY this structure:

# Project Narrative: [name]

## Summary
<!-- 2-3 sentences. The elevator pitch. What is this and why does it matter? -->

## Current Foci
<!-- What we're actively working on NOW. Teams juggle multiple things.
     Based on recent commits, what are the 2-4 active areas of work? -->

- **[Focus area]**: Brief description of what and why

## How It Works
<!-- Current architecture/structure. Main subsystems and their roles.
     Philosophy/approach. Keep it concise but useful for orientation. -->

## The Story So Far
<!-- Narrative of how we got here. Identify major phases/epochs.
     Not a list of commits, but the STORY. What were we trying to do?
     What problems did we hit? How did our understanding evolve?
     Write this as connected narrative, not bullet points. -->

## Dragons & Gotchas
<!-- Warnings for future-us. Areas that are fragile, confusing, or have
     non-obvious behavior. Things that bit us. High-churn areas that
     suggest ongoing pain. -->

## Open Questions
<!-- Things we're still figuring out. Uncertainties. Areas where we
     suspect there might be better approaches. Technical debt we're
     aware of but haven't addressed. -->

Remember:
- "We" voice throughout - this is our team's living document
- Be concise but capture the essential narrative
- Opinions and hunches are valuable ("we suspect...", "probably because...")
- This document should help future-us (or new team members) understand not just WHAT but WHY
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text

def main():
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path.cwd()

    if not (project_root / ".git").exists():
        print(f"Error: {project_root} is not a git repository", file=sys.stderr)
        sys.exit(1)

    # Extract git data
    git_data = extract_git_data(project_root)

    # Save raw data for debugging
    data_file = project_root / ".claude" / "narrative-data.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    with open(data_file, "w") as f:
        json.dump(git_data, f, indent=2)
    print(f"Git data saved to {data_file}", file=sys.stderr)

    # Generate narrative
    narrative = generate_narrative(git_data)

    # Save narrative
    narrative_file = project_root / ".claude" / "narrative.md"
    with open(narrative_file, "w") as f:
        f.write(narrative)

    print(f"Narrative saved to {narrative_file}", file=sys.stderr)
    print(narrative)

if __name__ == "__main__":
    main()
