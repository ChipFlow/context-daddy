#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic"]
# ///
"""
Generate or update a README from the project narrative.

Uses the narrative.md to create a user-focused README with:
- What/Why (quick pitch)
- Quick Start (get running fast)
- Features
- How It Works
- The Journey (from narrative, no version numbers)
- Dragons & Open Questions

Usage:
    uv run scripts/generate-readme.py [project_root]
    uv run scripts/generate-readme.py --update  # Update existing README
"""

import sys
from pathlib import Path
import anthropic
import argparse


def generate_readme(narrative: str, existing_readme: str | None = None) -> str:
    """Use Claude to generate a README from the narrative."""

    client = anthropic.Anthropic()

    if existing_readme:
        context = f"""You are updating a README based on the project narrative.

CURRENT README:
```markdown
{existing_readme}
```

PROJECT NARRATIVE:
```markdown
{narrative}
```

Update the README to reflect the current narrative. Keep the same structure but refresh content.
Preserve any sections that aren't derived from the narrative (like installation instructions specific to the project).
"""
    else:
        context = f"""You are generating a README from a project narrative.

PROJECT NARRATIVE:
```markdown
{narrative}
```

Generate a README with this structure:
"""

    prompt = f"""{context}

README STRUCTURE (use exactly this order):

# [Project Name]

*[Tagline from narrative summary]*

## What
- 3 bullet points: what this does (from narrative summary)

## Why
- 2-3 sentences: why this matters (from narrative)

## Quick Start
```bash
# Simple install/run commands
# Keep it minimal - just enough to try it
```

## Features
### [Feature 1 emoji] [Feature Name]
Brief description with code example if relevant

### [Feature 2 emoji] [Feature Name]
...

## Commands / API
Table or list of main commands/functions

## How It Works
- Architecture in plain language (from narrative "How It Works")
- Keep it brief

## Requirements
- List dependencies

---

## The Journey
- From narrative "The Story So Far"
- NO version numbers - describe what happened and why
- Use bold for key moments: **Memory explosion.** We had to...

## Known Dragons 🐉
- From narrative "Dragons & Gotchas"
- Brief, punchy warnings

## Open Questions
- From narrative "Open Questions"
- Bullet points

## License
[License]

RULES:
1. What/Why/Quick Start come FIRST - people want to use it before reading the story
2. NO version numbers in the Journey - they're meaningless to readers
3. Keep it concise - README should be scannable
4. Use "we" voice in Journey/Dragons/Questions sections
5. Use emojis sparingly for section headers in Features
6. Journey goes AFTER the horizontal rule - it's backstory, not essential

Output ONLY the markdown README, nothing else.
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
    parser = argparse.ArgumentParser(description="Generate README from project narrative")
    parser.add_argument("project", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--update", "-u", action="store_true", help="Update existing README")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Print without saving")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    narrative_file = project_root / ".claude" / "narrative.md"
    readme_file = project_root / "README.md"

    if not narrative_file.exists():
        print(f"Error: No narrative found at {narrative_file}", file=sys.stderr)
        print("Run generate-narrative.py first.", file=sys.stderr)
        sys.exit(1)

    narrative = narrative_file.read_text()

    existing_readme = None
    if args.update and readme_file.exists():
        existing_readme = readme_file.read_text()
        print("Updating existing README...", file=sys.stderr)
    else:
        print("Generating new README...", file=sys.stderr)

    readme = generate_readme(narrative, existing_readme)

    if args.dry_run:
        print("\n--- GENERATED README (dry run) ---\n")
        print(readme)
    else:
        if readme_file.exists():
            backup = project_root / "README.md.bak"
            backup.write_text(readme_file.read_text())
            print(f"Backup saved to {backup}", file=sys.stderr)

        readme_file.write_text(readme)
        print(f"README saved to {readme_file}", file=sys.stderr)
        print(readme)


if __name__ == "__main__":
    main()
