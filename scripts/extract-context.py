#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Extract key context from narrative and project structure for Claude orientation.

Outputs JSON with:
- project_root: absolute path
- top_dirs: top-level directory structure
- narrative_summary: Summary section from narrative.md
- narrative_foci: Current Foci section
- narrative_dragons: Dragons & Gotchas section
"""

import json
import re
import sys
from pathlib import Path


def extract_section(content: str, section_name: str) -> str:
    """Extract a section from markdown by heading."""
    # Match ## Section Name through next ## or end
    pattern = rf"^## {re.escape(section_name)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def get_top_dirs(project_root: Path) -> list[dict]:
    """Get top-level directory structure."""
    dirs = []
    try:
        for item in sorted(project_root.iterdir()):
            if item.name.startswith('.'):
                continue
            if item.is_dir():
                # Count files in dir
                try:
                    file_count = sum(1 for _ in item.rglob('*') if _.is_file())
                except:
                    file_count = 0
                dirs.append({"name": item.name, "type": "dir", "files": file_count})
            elif item.is_file():
                dirs.append({"name": item.name, "type": "file"})
    except:
        pass
    return dirs[:20]  # Limit to 20 entries


def main():
    if len(sys.argv) > 1:
        project_root = Path(sys.argv[1]).resolve()
    else:
        project_root = Path.cwd().resolve()

    claude_dir = project_root / ".claude"
    narrative_file = claude_dir / "narrative.md"

    result = {
        "project_root": str(project_root),
        "project_name": project_root.name,
        "top_dirs": get_top_dirs(project_root),
    }

    if narrative_file.exists():
        content = narrative_file.read_text()
        result["narrative_summary"] = extract_section(content, "Summary")
        result["narrative_foci"] = extract_section(content, "Current Foci")
        result["narrative_dragons"] = extract_section(content, "Dragons & Gotchas")
        result["has_narrative"] = True
    else:
        result["has_narrative"] = False

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
