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


def extract_section(content: str, section_name: str, max_chars: int = 500) -> str:
    """Extract a section from markdown by heading, with truncation."""
    # Match ## Section Name through next ## or end
    pattern = rf"^## {re.escape(section_name)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        text = match.group(1).strip()
        if len(text) > max_chars:
            # Truncate at word boundary
            truncated = text[:max_chars].rsplit(' ', 1)[0]
            return truncated + "..."
        return text
    return ""


def get_dir_tree(project_root: Path, max_depth: int = 2) -> str:
    """Get directory tree with depth limit, similar to `tree -L 2`."""
    lines = []

    def walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            # Filter hidden, cache dirs, and common noise
            skip_names = {'.', '__pycache__', 'node_modules', '.git', 'venv', '.venv',
                         'dist', 'build', '.tox', '.pytest_cache', '.mypy_cache',
                         'target', '.cargo', '*.egg-info'}
            items = [i for i in items if not i.name.startswith('.')
                     and i.name not in skip_names
                     and not i.name.endswith('.egg-info')]
            if len(items) > 10 and depth > 0:
                items = items[:8]
                items.append(None)  # Marker for "..."

            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "

                if item is None:
                    lines.append(f"{prefix}{connector}...")
                    continue

                if item.is_dir():
                    lines.append(f"{prefix}{connector}{item.name}/")
                    extension = "    " if is_last else "│   "
                    walk(item, prefix + extension, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{item.name}")
        except:
            pass

    lines.append(f"{project_root.name}/")
    walk(project_root, "", 0)

    # Limit total lines
    if len(lines) > 30:
        lines = lines[:28] + ["...", f"({len(lines) - 28} more items)"]

    return "\n".join(lines)


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
        "dir_tree": get_dir_tree(project_root, max_depth=3),
    }

    if narrative_file.exists():
        content = narrative_file.read_text()
        # Truncate sections to prevent context bloat
        # Summary: concise overview (300 chars)
        # Foci: current work areas (400 chars)
        # Dragons: key warnings only (300 chars)
        result["narrative_summary"] = extract_section(content, "Summary", max_chars=300)
        result["narrative_foci"] = extract_section(content, "Current Foci", max_chars=400)
        result["narrative_dragons"] = extract_section(content, "Dragons & Gotchas", max_chars=300)
        result["has_narrative"] = True
    else:
        result["has_narrative"] = False

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
