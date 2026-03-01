#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Add context-daddy MCP tool permissions to ~/.claude/settings.json.

Adds wildcard allow rules so all repo-map and goals MCP tools work without
per-call approval. Idempotent - safe to run multiple times.
"""

import json
import sys
from pathlib import Path

PERMISSION_PATTERNS = [
    "mcp__plugin_context-daddy_repo-map__*",
    "mcp__plugin_context-daddy_goals__*",
]


def setup_permissions() -> bool:
    """Add MCP tool permissions to user settings. Returns True if changed."""
    settings_path = Path.home() / ".claude" / "settings.json"

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {settings_path}: {e}", file=sys.stderr)
            return False
    else:
        settings = {}

    # Navigate to permissions.allow, creating structure if needed
    permissions = settings.setdefault("permissions", {})
    allow_list = permissions.setdefault("allow", [])

    added = []
    for pattern in PERMISSION_PATTERNS:
        if pattern not in allow_list:
            allow_list.append(pattern)
            added.append(pattern)

    if not added:
        print("All permissions already configured, nothing to do.", file=sys.stderr)
        return False

    # Write back with consistent formatting
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    for p in added:
        print(f"Added '{p}' to {settings_path}", file=sys.stderr)
    return True


if __name__ == "__main__":
    changed = setup_permissions()
    # Exit 0 on success (changed or already present), 1 on error
    sys.exit(0)
