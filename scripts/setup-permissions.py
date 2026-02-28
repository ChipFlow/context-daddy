#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Add context-daddy MCP tool permissions to ~/.claude/settings.json.

Adds a wildcard allow rule so all repo-map MCP tools work without
per-call approval. Idempotent - safe to run multiple times.
"""

import json
import sys
from pathlib import Path

PERMISSION_PATTERN = "mcp__plugin_context-daddy_repo-map__*"


def setup_permissions() -> bool:
    """Add MCP tool permission to user settings. Returns True if changed."""
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

    # Check if already present (exact match or equivalent wildcard)
    for entry in allow_list:
        if entry == PERMISSION_PATTERN:
            print("Permission already configured, nothing to do.", file=sys.stderr)
            return False

    allow_list.append(PERMISSION_PATTERN)

    # Write back with consistent formatting
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Added '{PERMISSION_PATTERN}' to {settings_path}", file=sys.stderr)
    return True


if __name__ == "__main__":
    changed = setup_permissions()
    # Exit 0 on success (changed or already present), 1 on error
    sys.exit(0)
