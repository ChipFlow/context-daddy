#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Pure functions for saving session context to narrative.md and learnings.md.

Called by the repo-map MCP server's save_session_context tool.
Handles concurrent writes from multiple sessions via lockfile.
"""

import json
import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

@contextmanager
def acquire_lock(lock_path: Path, timeout: float = 10.0):
    """Lockfile with PID, stale detection, auto-cleanup.

    Uses atomic file creation (O_CREAT | O_EXCL) for race-free locking.
    Stale locks (PID no longer running or older than timeout) are broken.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    acquired = False

    while time.monotonic() < deadline:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}\n".encode())
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            # Check if lock is stale
            try:
                content = lock_path.read_text().strip()
                pid = int(content)
                # Check if process is alive
                try:
                    os.kill(pid, 0)
                except OSError:
                    # Process is dead, break lock
                    logger.info(f"Breaking stale lock (dead PID {pid})")
                    lock_path.unlink(missing_ok=True)
                    continue

                # Check if lock is too old
                age = time.time() - lock_path.stat().st_mtime
                if age > timeout:
                    logger.info(f"Breaking stale lock (age {age:.1f}s > {timeout}s)")
                    lock_path.unlink(missing_ok=True)
                    continue
            except (ValueError, OSError):
                # Corrupt lock file, break it
                logger.info("Breaking corrupt lock file")
                lock_path.unlink(missing_ok=True)
                continue

            time.sleep(0.1)

    if not acquired:
        raise TimeoutError(f"Could not acquire lock {lock_path} within {timeout}s")

    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Narrative merging
# ---------------------------------------------------------------------------

def _read_sections(text: str) -> dict[str, str]:
    """Parse markdown into {heading: content} dict.

    Only parses ## level headings. Content includes everything until the next
    ## heading or end of file.
    """
    sections: dict[str, str] = {}
    current_heading = "__preamble__"
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            sections[current_heading] = "\n".join(current_lines)
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_heading] = "\n".join(current_lines)
    return sections


def _rebuild_narrative(sections: dict[str, str], heading_order: list[str]) -> str:
    """Rebuild narrative.md from sections dict, preserving heading order."""
    lines: list[str] = []

    # Preamble (# title etc.)
    if "__preamble__" in sections:
        preamble = sections["__preamble__"].strip()
        if preamble:
            lines.append(preamble)
            lines.append("")

    for heading in heading_order:
        if heading in sections and heading != "__preamble__":
            lines.append(f"## {heading}")
            content = sections[heading].rstrip()
            if content:
                lines.append(content)
            lines.append("")

    # Any sections not in heading_order (append at end)
    for heading, content in sections.items():
        if heading not in heading_order and heading != "__preamble__":
            lines.append(f"## {heading}")
            content_stripped = content.rstrip()
            if content_stripped:
                lines.append(content_stripped)
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# The expected section order in narrative.md
NARRATIVE_HEADING_ORDER = [
    "Summary",
    "Current Foci",
    "How It Works",
    "The Story So Far",
    "Dragons & Gotchas",
    "Open Questions",
]


def _merge_narrative(
    path: Path,
    current_foci: list[str] | None = None,
    narrative_updates: str | None = None,
    dragons: list[str] | None = None,
    open_questions: list[str] | None = None,
    resolved_questions: list[str] | None = None,
) -> str:
    """Read existing narrative, merge updates, return summary of changes."""
    changes: list[str] = []

    if not path.exists():
        # No narrative yet — create minimal one
        lines = ["# Project Narrative\n"]
        if current_foci:
            lines.append("## Current Foci\n")
            for focus in current_foci:
                lines.append(f"- {focus}")
            lines.append("")
        if narrative_updates:
            lines.append("## The Story So Far\n")
            lines.append(narrative_updates)
            lines.append("")
        if dragons:
            lines.append("## Dragons & Gotchas\n")
            for d in dragons:
                lines.append(f"- {d}")
                lines.append("")
        if open_questions:
            lines.append("## Open Questions\n")
            for q in open_questions:
                lines.append(f"- {q}")
                lines.append("")

        _atomic_write(path, "\n".join(lines))
        changes.append("Created new narrative.md")
        return "; ".join(changes)

    text = path.read_text()
    sections = _read_sections(text)

    # Current Foci: replace entirely
    if current_foci:
        foci_text = "\n" + "\n".join(f"- {f}" for f in current_foci) + "\n"
        sections["Current Foci"] = foci_text
        changes.append(f"Updated foci ({len(current_foci)} items)")

    # Story So Far: append new paragraph
    if narrative_updates:
        story = sections.get("The Story So Far", "")
        # Add separator and new content
        new_paragraph = f"\n**{datetime.now().strftime('%b %d')} – Session update**: {narrative_updates}\n"
        sections["The Story So Far"] = story.rstrip() + "\n" + new_paragraph
        changes.append("Appended to Story So Far")

    # Dragons & Gotchas: append new, dedup by substring
    if dragons:
        existing = sections.get("Dragons & Gotchas", "")
        existing_lower = existing.lower()
        added = 0
        for dragon in dragons:
            # Basic dedup: skip if a substantial substring already exists
            # Use first 40 chars as key (enough to identify duplicates)
            key = dragon[:40].lower().strip("- *")
            if key and key in existing_lower:
                continue
            existing = existing.rstrip() + f"\n\n- {dragon}\n"
            added += 1
        if added > 0:
            sections["Dragons & Gotchas"] = existing
            changes.append(f"Added {added} dragon(s)")

    # Open Questions: add new, remove resolved
    if open_questions or resolved_questions:
        existing = sections.get("Open Questions", "")

        # Remove resolved questions
        if resolved_questions:
            removed = 0
            for resolved in resolved_questions:
                key = resolved[:40].lower().strip("- *")
                if not key:
                    continue
                # Try to find and remove matching lines
                new_lines = []
                skip_until_next = False
                for line in existing.split("\n"):
                    if skip_until_next:
                        if line.startswith("- ") or line.startswith("## ") or not line.strip():
                            skip_until_next = False
                        else:
                            continue
                    if key in line.lower():
                        skip_until_next = True
                        removed += 1
                        continue
                    new_lines.append(line)
                existing = "\n".join(new_lines)
            if removed > 0:
                changes.append(f"Resolved {removed} question(s)")

        # Add new questions
        if open_questions:
            existing_lower = existing.lower()
            added = 0
            for q in open_questions:
                key = q[:40].lower().strip("- *")
                if key and key in existing_lower:
                    continue
                existing = existing.rstrip() + f"\n\n- {q}\n"
                added += 1
            if added > 0:
                changes.append(f"Added {added} open question(s)")

        sections["Open Questions"] = existing

    if changes:
        result = _rebuild_narrative(sections, NARRATIVE_HEADING_ORDER)
        _atomic_write(path, result)

    return "; ".join(changes) if changes else "No narrative changes"


# ---------------------------------------------------------------------------
# Learnings
# ---------------------------------------------------------------------------

def _append_learnings(path: Path, learnings: list[dict]) -> int:
    """Append new learnings to learnings.md. Returns count added.

    Each learning is: {title: str, insight: str, context?: str}
    """
    if not learnings:
        return 0

    existing = ""
    if path.exists():
        existing = path.read_text()

    existing_lower = existing.lower()
    today = datetime.now().strftime("%Y-%m-%d")
    added = 0
    new_entries: list[str] = []

    for learning in learnings:
        title = learning.get("title", "Untitled")
        insight = learning.get("insight", "")
        context = learning.get("context", "")

        # Basic dedup: skip if title substring already exists
        title_key = title[:40].lower()
        if title_key and title_key in existing_lower:
            continue

        entry = f"\n### {title} ({today})\n"
        entry += f"**Insight**: {insight}\n"
        if context:
            entry += f"\n**Context**: {context}\n"

        new_entries.append(entry)
        added += 1

    if new_entries:
        content = existing.rstrip() + "\n" + "\n".join(new_entries) + "\n"
        _atomic_write(path, content)

    return added


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str):
    """Write content atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, str(path))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Trigger file
# ---------------------------------------------------------------------------

def trigger_git_update(claude_dir: Path):
    """Write trigger file for background git-based narrative update."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    trigger = claude_dir / ".update-narrative-trigger"
    trigger.write_text(f"{os.getpid()}\n{time.time()}\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def save_session_context(
    project_root: str,
    current_foci: list[str] | None = None,
    learnings: list[dict] | None = None,
    dragons: list[str] | None = None,
    narrative_updates: str | None = None,
    open_questions: list[str] | None = None,
    resolved_questions: list[str] | None = None,
) -> dict:
    """Merge session insights into narrative.md and learnings.md.

    Returns a summary of what was changed.
    """
    root = Path(project_root)
    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    narrative_path = claude_dir / "narrative.md"
    learnings_path = claude_dir / "learnings.md"
    lock_path = claude_dir / ".context-write.lock"

    result = {
        "status": "ok",
        "narrative_changes": "",
        "learnings_added": 0,
        "trigger_created": False,
    }

    try:
        with acquire_lock(lock_path):
            # Merge narrative
            result["narrative_changes"] = _merge_narrative(
                narrative_path,
                current_foci=current_foci,
                narrative_updates=narrative_updates,
                dragons=dragons,
                open_questions=open_questions,
                resolved_questions=resolved_questions,
            )

            # Append learnings
            if learnings:
                result["learnings_added"] = _append_learnings(
                    learnings_path, learnings
                )

        # Drop trigger for git-based update (outside lock — trigger is append-only)
        trigger_git_update(claude_dir)
        result["trigger_created"] = True

    except TimeoutError:
        result["status"] = "lock_timeout"
        result["error"] = "Could not acquire write lock (another session may be writing)"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        logger.exception("save_session_context failed")

    return result


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: context_saver.py <project_root> [--test]")
        print("  --test: Run with sample data")
        sys.exit(1)

    project_root = sys.argv[1]

    if "--test" in sys.argv:
        result = save_session_context(
            project_root=project_root,
            current_foci=[
                "Testing save_session_context tool",
                "Verifying narrative merge logic",
            ],
            learnings=[
                {
                    "title": "Test learning from CLI",
                    "insight": "context_saver.py CLI works correctly",
                    "context": "Manual testing via command line",
                },
            ],
            dragons=["Test dragon: CLI testing is important for MCP tools"],
            narrative_updates="Tested save_session_context via CLI. Everything works.",
            open_questions=["Does the trigger file get picked up?"],
        )
        print(json.dumps(result, indent=2))
    else:
        print("Pass --test to run with sample data")
