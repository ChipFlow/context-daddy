#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Cross-session goal tracking for context-daddy.
Goals persist across sessions and projects, tracking plans, approaches tried,
and current progress on multi-step objectives.

Storage:
  ~/.claude/goals/<uuid>.md     - Goal files (global, can span projects)
  <project>/.claude/active-goals.json - Project index (fast startup cache)
  <project>/.claude/.current-goal     - Active goal ref for this project

Storage format v2:
  - Goals have a **Slug** field (auto-generated from title, used as alias)
  - Steps have IDs: `- [ ] [step-id] Step description`
  - .current-goal format: `UUID:step-id` (bare UUID for backwards compat)
"""

import json
import logging
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

GOALS_DIR = Path.home() / ".claude" / "goals"
ARCHIVE_DIR = GOALS_DIR / ".archive"
STORAGE_VERSION = 2


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def ensure_dirs():
    """Create goals directories if they don't exist."""
    GOALS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def get_claude_dir(project_path: str | None = None) -> Path:
    """Get the .claude directory for a project."""
    root = Path(project_path) if project_path else Path.cwd()
    claude_dir = root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    return claude_dir


def generate_id() -> str:
    """Generate a short UUID (first 8 chars of uuid4)."""
    return uuid.uuid4().hex[:8]


def slugify(text: str, max_len: int = 40) -> str:
    """Generate a URL-safe slug from text.

    >>> slugify("Add source annotation tracking")
    'add-source-annotation-tracking'
    >>> slugify("Fix the  weird---bug!!!  now")
    'fix-the-weird-bug-now'
    """
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    s = s.strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s


def step_id_from_text(text: str) -> str:
    """Generate a step ID from step description text.

    >>> step_id_from_text("Add source location to ABC network nodes")
    'add-src-location'
    >>> step_id_from_text("Define plan steps")
    'define-plan-steps'
    """
    slug = slugify(text, max_len=30)
    # Shorten common words for brevity
    for long, short in [("annotation", "ann"), ("source", "src"),
                        ("implementation", "impl"), ("configuration", "config"),
                        ("integration", "integ"), ("network", "net"),
                        ("location", "loc")]:
        slug = slug.replace(long, short)
    # Trim to 3-4 words max
    parts = slug.split("-")
    if len(parts) > 4:
        parts = parts[:4]
    return "-".join(parts)


def atomic_write(path: Path, content: str):
    """Write content atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def find_goal(goal_ref: str) -> Path:
    """Find a goal file by UUID, partial UUID (4+ chars), or slug.

    Raises ValueError if not found or ambiguous.
    """
    if len(goal_ref) < 3:
        raise ValueError(f"ID/slug must be at least 3 characters, got '{goal_ref}'")

    # Check active goals first, then archive
    for directory in [GOALS_DIR, ARCHIVE_DIR]:
        if not directory.exists():
            continue

        # Try UUID match first (filename-based)
        matches = [f for f in directory.glob("*.md") if f.stem.startswith(goal_ref)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous ID '{goal_ref}' matches: {', '.join(m.stem for m in matches)}")

    # Try slug match (must read files)
    slug_matches: list[Path] = []
    for directory in [GOALS_DIR, ARCHIVE_DIR]:
        if not directory.exists():
            continue
        for gf in directory.glob("*.md"):
            content = gf.read_text()
            m = re.search(r"^\*\*Slug\*\*:\s*(.+)$", content, re.MULTILINE)
            if m and m.group(1).strip() == goal_ref:
                slug_matches.append(gf)

    if len(slug_matches) == 1:
        return slug_matches[0]
    if len(slug_matches) > 1:
        raise ValueError(
            f"Ambiguous slug '{goal_ref}' matches: {', '.join(m.stem for m in slug_matches)}")

    raise ValueError(f"No goal found matching '{goal_ref}'")


# Backwards-compatible wrapper (used by CLI)
def find_goal_by_id(goal_id: str) -> Path | None:
    """Find a goal file by full or partial UUID (4+ chars). Returns None on error."""
    try:
        return find_goal(goal_id)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Parsing & Rendering
# ---------------------------------------------------------------------------

def parse_goal(path: Path) -> dict:
    """Parse a goal markdown file into a dict."""
    content = path.read_text()
    goal = {"path": str(path), "raw": content}

    # Parse header fields
    for key in ["ID", "Slug", "Status", "Created", "Updated"]:
        m = re.search(rf"^\*\*{key}\*\*:\s*(.+)$", content, re.MULTILINE)
        if m:
            goal[key.lower()] = m.group(1).strip()

    # Parse title
    m = re.search(r"^# Goal:\s*(.+)$", content, re.MULTILINE)
    if m:
        goal["title"] = m.group(1).strip()

    # Parse plan steps (with optional [step-id] prefix)
    steps = []
    in_plan = False
    for line in content.split("\n"):
        if re.match(r"^## Plan\s*$", line):
            in_plan = True
            continue
        if in_plan and re.match(r"^## ", line):
            break
        if in_plan:
            m = re.match(r"^- \[([ x])\]\s*(.+)$", line)
            if m:
                text = m.group(2).strip()
                is_current = "← current" in text
                text_clean = re.sub(r"\s*← current\s*$", "", text)
                # Extract step ID if present: [step-id] rest of text
                step_id_match = re.match(r"^\[([a-z0-9-]+)\]\s*(.+)$", text_clean)
                if step_id_match:
                    sid = step_id_match.group(1)
                    text_clean = step_id_match.group(2)
                else:
                    sid = None
                steps.append({
                    "id": sid,
                    "done": m.group(1) == "x",
                    "text": text_clean,
                    "current": is_current,
                })
    goal["steps"] = steps

    # Detect storage version
    goal["_version"] = 2 if goal.get("slug") else 1

    # Parse projects
    projects = []
    in_projects = False
    for line in content.split("\n"):
        if re.match(r"^## Projects\s*$", line):
            in_projects = True
            continue
        if in_projects and re.match(r"^## ", line):
            break
        if in_projects:
            m = re.match(r"^- (.+?)(?:\s*\((\w+)\))?\s*$", line)
            if m:
                projects.append({"path": m.group(1).strip(), "role": m.group(2) or "primary"})
    goal["projects"] = projects

    # Parse learnings
    learnings = []
    in_learnings = False
    for line in content.split("\n"):
        if re.match(r"^## Approaches & Learnings\s*$", line):
            in_learnings = True
            continue
        if in_learnings and re.match(r"^## ", line):
            break
        if in_learnings:
            learnings.append(line)
    goal["learnings_raw"] = "\n".join(learnings).strip()

    # Parse recent activity
    activity = []
    in_activity = False
    for line in content.split("\n"):
        if re.match(r"^## Recent Activity\s*$", line):
            in_activity = True
            continue
        if in_activity and re.match(r"^## ", line):
            break
        if in_activity and line.startswith("- "):
            activity.append(line)
    goal["activity"] = activity

    return goal


def _render_step_line(step: dict) -> str:
    """Render a single step as a markdown checkbox line."""
    check = "x" if step.get("done") else " "
    marker = "  ← current" if step.get("current") else ""
    sid = step.get("id")
    id_prefix = f"[{sid}] " if sid else ""
    return f"- [{check}] {id_prefix}{step['text']}{marker}"


def render_goal(goal_id: str, title: str, objective: str, slug: str = "",
                status: str = "active",
                created: str | None = None, updated: str | None = None,
                projects: list[dict] | None = None, steps: list[dict] | None = None,
                learnings: str = "", activity: str = "") -> str:
    """Render a goal dict back to markdown (v2 format with slug and step IDs)."""
    now = datetime.now().strftime("%Y-%m-%d")
    created = created or now
    updated = updated or now
    if not slug:
        slug = slugify(title)

    lines = [
        f"# Goal: {title}",
        "",
        f"**ID**: {goal_id}",
        f"**Slug**: {slug}",
        f"**Status**: {status}",
        f"**Created**: {created}",
        f"**Updated**: {updated}",
        "",
        "## Objective",
        "",
        objective,
        "",
        "## Projects",
        "",
    ]

    if projects:
        for p in projects:
            role = f" ({p['role']})" if p.get("role") else ""
            lines.append(f"- {p['path']}{role}")
    else:
        lines.append(f"- {Path.cwd()} (primary)")

    lines.extend(["", "## Plan", ""])

    if steps:
        for s in steps:
            lines.append(_render_step_line(s))
    else:
        default_step = {"id": "define-plan", "done": False,
                        "text": "Define plan steps", "current": True}
        lines.append(_render_step_line(default_step))

    lines.extend(["", "## Approaches & Learnings", ""])
    if learnings:
        lines.append(learnings)

    lines.extend(["", "## Recent Activity", ""])
    if activity:
        lines.append(activity)

    lines.append("")
    return "\n".join(lines)


def _rebuild_plan_section(content: str, steps: list[dict]) -> str:
    """Replace the Plan section in goal markdown content with updated steps."""
    plan_lines = [_render_step_line(s) for s in steps]
    plan_block = "\n".join(plan_lines)
    # Match plan section with 0 or more existing step lines
    m = re.search(r"(## Plan\n\n)((?:- \[[ x]\].+\n?)*)", content)
    if m:
        content = content[:m.start()] + m.group(1) + plan_block + "\n" + content[m.end():]
    return content


def _extract_section(content: str, heading: str) -> str:
    """Safely extract text between ## heading and the next ## heading."""
    m = re.search(rf"^## {re.escape(heading)}\s*\n\n?(.*?)(?=\n## |\Z)",
                  content, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _update_timestamp(content: str) -> str:
    """Update the **Updated** field to today."""
    now = datetime.now().strftime("%Y-%m-%d")
    return re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def needs_migration(goal: dict) -> bool:
    """Check if a goal file needs migration to v2 format."""
    return goal.get("_version", 1) < STORAGE_VERSION


def migrate_goal(path: Path) -> dict:
    """Migrate a v1 goal to v2 format in-place. Returns updated goal dict."""
    goal = parse_goal(path)
    if not needs_migration(goal):
        return goal

    content = path.read_text()

    # Add Slug field after ID if missing
    if not goal.get("slug"):
        title = goal.get("title", "untitled")
        slug = slugify(title)
        content = re.sub(
            r"(\*\*ID\*\*:\s*.+)$",
            rf"\1\n**Slug**: {slug}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    # Add step IDs to steps that don't have them
    steps = goal.get("steps", [])
    used_ids: set[str] = set()
    for step in steps:
        if step.get("id"):
            used_ids.add(step["id"])

    new_step_lines = []
    for step in steps:
        if not step.get("id"):
            candidate = step_id_from_text(step["text"])
            # Ensure unique
            final_id = candidate
            counter = 2
            while final_id in used_ids:
                final_id = f"{candidate}-{counter}"
                counter += 1
            used_ids.add(final_id)
            step["id"] = final_id

    # Rebuild plan section with step IDs
    content = _rebuild_plan_section(content, steps)
    content = _update_timestamp(content)

    atomic_write(path, content)
    logger.info("Migrated goal %s to v2 format", path.stem)
    return parse_goal(path)


# ---------------------------------------------------------------------------
# .current-goal format helpers
# ---------------------------------------------------------------------------

def parse_current_goal(raw: str) -> tuple[str, str | None]:
    """Parse .current-goal content into (goal_uuid, step_id | None).

    Formats:
      - "a1b2c3d4"           -> ("a1b2c3d4", None)        # v1 compat
      - "a1b2c3d4:step-id"   -> ("a1b2c3d4", "step-id")   # v2
    """
    raw = raw.strip()
    if ":" in raw:
        parts = raw.split(":", 1)
        return parts[0], parts[1]
    return raw, None


def format_current_goal(goal_uuid: str, step_id: str | None = None) -> str:
    """Format .current-goal content."""
    if step_id:
        return f"{goal_uuid}:{step_id}\n"
    return f"{goal_uuid}\n"


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def update_index(project_path: str | None = None, goals_to_include: list[dict] | None = None):
    """Rebuild active-goals.json for a project from goal files."""
    claude_dir = get_claude_dir(project_path)
    project_root = str(Path(project_path).resolve()) if project_path else str(Path.cwd().resolve())

    if goals_to_include is None:
        # Scan all goal files for ones that reference this project
        goals_to_include = []
        if GOALS_DIR.exists():
            for gf in GOALS_DIR.glob("*.md"):
                goal = parse_goal(gf)
                for p in goal.get("projects", []):
                    if Path(p["path"]).resolve() == Path(project_root).resolve():
                        steps = goal.get("steps", [])
                        current_step = next((s for s in steps if s.get("current")), None)
                        current_idx = next((i for i, s in enumerate(steps) if s.get("current")), 0)
                        goals_to_include.append({
                            "id": goal.get("id", gf.stem),
                            "slug": goal.get("slug", ""),
                            "name": goal.get("title", "Untitled"),
                            "role": p.get("role", "primary"),
                            "current_step": current_idx + 1,
                            "current_step_id": current_step.get("id", "") if current_step else "",
                            "current_step_text": current_step["text"] if current_step else "",
                            "total_steps": len(steps),
                            "updated": goal.get("updated", ""),
                        })
                        break

    index = {
        "version": STORAGE_VERSION,
        "goals": goals_to_include,
    }
    atomic_write(claude_dir / "active-goals.json", json.dumps(index, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Pure functions (importable by MCP server, return strings or raise)
# ---------------------------------------------------------------------------

def goal_create(title: str, objective: str, project_path: str | None = None,
                slug: str | None = None) -> str:
    """Create a new goal. Returns confirmation string."""
    goal_id = generate_id()
    ensure_dirs()

    if not slug:
        slug = slugify(title)

    default_step = {"id": "define-plan", "done": False,
                    "text": "Define plan steps", "current": True}
    content = render_goal(goal_id, title, objective, slug=slug,
                          steps=[default_step])
    goal_path = GOALS_DIR / f"{goal_id}.md"
    atomic_write(goal_path, content)

    # Set as current goal
    claude_dir = get_claude_dir(project_path)
    atomic_write(claude_dir / ".current-goal",
                 format_current_goal(goal_id, "define-plan"))

    # Update project index
    update_index(project_path=project_path, goals_to_include=[{
        "id": goal_id,
        "slug": slug,
        "name": title,
        "role": "primary",
        "current_step": 1,
        "current_step_id": "define-plan",
        "current_step_text": "Define plan steps",
        "total_steps": 1,
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }])

    return f"Created goal: {goal_id} ({slug})\n  Title: {title}\n  File: {goal_path}"


def goal_list(show_all: bool = False, project_path: str | None = None) -> str:
    """List goals. Returns formatted string."""
    lines = []

    if show_all:
        if not GOALS_DIR.exists():
            return "No goals found."
        for gf in sorted(GOALS_DIR.glob("*.md")):
            goal = parse_goal(gf)
            steps = goal.get("steps", [])
            done = sum(1 for s in steps if s["done"])
            status = goal.get("status", "?")
            slug = goal.get("slug", "")
            slug_str = f" ({slug})" if slug else ""
            lines.append(
                f"  {gf.stem}{slug_str}  [{status}]  "
                f"{goal.get('title', 'Untitled')}  ({done}/{len(steps)} steps)")
        return "\n".join(lines) if lines else "No goals found."

    claude_dir = get_claude_dir(project_path)
    index_path = claude_dir / "active-goals.json"
    current_path = claude_dir / ".current-goal"
    current_id = ""
    if current_path.exists():
        current_id, _ = parse_current_goal(current_path.read_text())

    if not index_path.exists():
        return "No goals linked to this project. Use 'goal create' or 'goal sync'."

    index = json.loads(index_path.read_text())
    goals = index.get("goals", [])
    if not goals:
        return "No goals linked to this project."

    for g in goals:
        marker = " *" if g["id"] == current_id else "  "
        slug = g.get("slug", "")
        slug_str = f" ({slug})" if slug else ""
        step_id = g.get("current_step_id", "")
        step_str = f" [{step_id}]" if step_id else ""
        lines.append(
            f"{marker}{g['id']}{slug_str}  {g['name']}  "
            f"({g['current_step']}/{g['total_steps']}){step_str} "
            f"{g.get('current_step_text', '')}")

    return "\n".join(lines)


def goal_show(goal_ref: str | None = None, project_path: str | None = None) -> str:
    """Show a goal file content. Returns the markdown content."""
    if not goal_ref:
        claude_dir = get_claude_dir(project_path)
        current_path = claude_dir / ".current-goal"
        if not current_path.exists():
            raise ValueError("No current goal set. Use 'goal switch <id>' or 'goal create'.")
        goal_ref, _ = parse_current_goal(current_path.read_text())

    path = find_goal(goal_ref)
    return path.read_text()


def goal_switch(goal_ref: str, project_path: str | None = None) -> str:
    """Set the current goal for this project. Returns confirmation."""
    path = find_goal(goal_ref)
    goal = parse_goal(path)

    # Find current step ID
    current_step = next((s for s in goal.get("steps", []) if s.get("current")), None)
    step_id = current_step.get("id") if current_step else None

    claude_dir = get_claude_dir(project_path)
    atomic_write(claude_dir / ".current-goal",
                 format_current_goal(path.stem, step_id))

    # Ensure goal is in the project index
    update_index(project_path=project_path)

    return f"Switched to: {goal.get('title', path.stem)}"


def goal_unset(project_path: str | None = None) -> str:
    """Remove the current goal marker. Returns confirmation."""
    claude_dir = get_claude_dir(project_path)
    current_path = claude_dir / ".current-goal"
    if current_path.exists():
        current_path.unlink()
        return "Current goal unset."
    return "No current goal was set."


def goal_focus(goal_ref: str | None, step_id: str,
               project_path: str | None = None) -> str:
    """Set the focused step for the current goal. Returns confirmation."""
    if not goal_ref:
        claude_dir = get_claude_dir(project_path)
        current_path = claude_dir / ".current-goal"
        if not current_path.exists():
            raise ValueError("No current goal set.")
        goal_ref, _ = parse_current_goal(current_path.read_text())

    path = find_goal(goal_ref)
    goal = parse_goal(path)
    steps = goal.get("steps", [])

    # Find the step by ID
    target = None
    for i, s in enumerate(steps):
        if s.get("id") == step_id:
            target = (i, s)
            break

    if target is None:
        available = [s.get("id", f"(no id, index {i})") for i, s in enumerate(steps)]
        raise ValueError(
            f"Step '{step_id}' not found. Available: {', '.join(available)}")

    target_idx, target_step = target

    # Move current marker
    for s in steps:
        s["current"] = False
    target_step["current"] = True

    # Rebuild file
    content = path.read_text()
    content = _rebuild_plan_section(content, steps)
    content = _update_timestamp(content)
    atomic_write(path, content)

    # Update .current-goal
    claude_dir = get_claude_dir(project_path)
    atomic_write(claude_dir / ".current-goal",
                 format_current_goal(path.stem, step_id))

    # Sync index
    update_index(project_path=project_path)

    return (f"Focused on step [{step_id}]: {target_step['text']} "
            f"(step {target_idx + 1}/{len(steps)})")


def goal_update_step(goal_ref: str, step_ref: str | int,
                     complete: bool = False,
                     project_path: str | None = None) -> str:
    """Mark a step done and/or advance the current marker.

    step_ref can be a step ID string or 1-based step number (int).
    Returns confirmation.
    """
    path = find_goal(goal_ref)
    goal = parse_goal(path)
    steps = goal.get("steps", [])

    # Resolve step reference
    if isinstance(step_ref, int):
        idx = step_ref - 1
        if idx < 0 or idx >= len(steps):
            raise ValueError(f"Step {step_ref} out of range (1-{len(steps)})")
    else:
        idx = None
        for i, s in enumerate(steps):
            if s.get("id") == step_ref:
                idx = i
                break
        if idx is None:
            raise ValueError(f"Step '{step_ref}' not found")

    if complete:
        steps[idx]["done"] = True
        steps[idx]["current"] = False
        # Advance current to next incomplete step
        next_idx = next(
            (i for i in range(idx + 1, len(steps)) if not steps[i]["done"]),
            None)
        if next_idx is not None:
            steps[next_idx]["current"] = True
    else:
        # Just move the current marker
        for s in steps:
            s["current"] = False
        steps[idx]["current"] = True

    # Rebuild the file
    content = path.read_text()
    content = _rebuild_plan_section(content, steps)
    content = _update_timestamp(content)
    atomic_write(path, content)

    # Update .current-goal with new step ID (or clear step if all done)
    current_step = next((s for s in steps if s.get("current")), None)
    claude_dir = get_claude_dir(project_path)
    atomic_write(claude_dir / ".current-goal",
                 format_current_goal(path.stem, current_step.get("id") if current_step else None))

    # Sync the project index
    update_index(project_path=project_path)

    step_name = steps[idx].get("id") or str(idx + 1)
    if current_step:
        return (f"Step [{step_name}] {'completed' if complete else 'set as current'}. "
                f"Current: [{current_step.get('id', '?')}] {current_step['text']}")
    return f"Step [{step_name}] {'completed' if complete else 'updated'}. All steps done!"


def goal_add_learning(goal_ref: str, text: str) -> str:
    """Append a learning to a goal. Returns confirmation."""
    path = find_goal(goal_ref)

    now = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n### {now}\n{text}\n"

    content = path.read_text()

    # Insert before "## Recent Activity"
    m = re.search(r"^## Recent Activity", content, re.MULTILINE)
    if m:
        content = (content[:m.start()].rstrip("\n") + "\n" + entry +
                   "\n" + content[m.start():])
    else:
        content = content.rstrip() + "\n" + entry

    content = _update_timestamp(content)
    atomic_write(path, content)
    return f"Learning added to {path.stem}."


def goal_add_commit(goal_ref: str, commit_hash: str, message: str,
                    project_name: str | None = None) -> str:
    """Add a commit to Recent Activity, trim to 10 entries. Returns confirmation."""
    path = find_goal(goal_ref)

    now = datetime.now().strftime("%Y-%m-%d")
    if not project_name:
        project_name = Path.cwd().name
    entry = f"- `{commit_hash}` ({project_name}) {now}: {message}"

    content = path.read_text()

    m = re.search(r"^## Recent Activity\n\n?((?:- .+\n?)*)", content, re.MULTILINE)
    if m:
        existing = [line for line in m.group(1).strip().split("\n") if line.strip()]
        existing.insert(0, entry)
        existing = existing[:10]
        activity_block = "\n".join(existing) + "\n"
        content = content[:m.start()] + "## Recent Activity\n\n" + activity_block + content[m.end():]
    else:
        content = content.rstrip() + "\n\n## Recent Activity\n\n" + entry + "\n"

    content = _update_timestamp(content)
    atomic_write(path, content)
    return f"Commit tracked in {path.stem}."


def goal_add_step(goal_ref: str, description: str,
                  step_id: str | None = None,
                  after: str | int | None = None,
                  project_path: str | None = None) -> str:
    """Insert a plan step. Returns confirmation.

    after: step ID or 1-based position number to insert after.
    """
    path = find_goal(goal_ref)
    goal = parse_goal(path)
    steps = goal.get("steps", [])

    # Generate step ID if not provided
    if not step_id:
        used_ids = {s.get("id") for s in steps if s.get("id")}
        step_id = step_id_from_text(description)
        candidate = step_id
        counter = 2
        while candidate in used_ids:
            candidate = f"{step_id}-{counter}"
            counter += 1
        step_id = candidate

    new_step = {"id": step_id, "done": False, "text": description, "current": False}

    # Resolve insertion position
    insert_idx = len(steps)  # default: append
    if after is not None:
        if isinstance(after, int):
            if 1 <= after <= len(steps):
                insert_idx = after
        else:
            # after is a step ID
            for i, s in enumerate(steps):
                if s.get("id") == after:
                    insert_idx = i + 1
                    break

    steps.insert(insert_idx, new_step)

    # If no current marker exists, set on new step
    if not any(s.get("current") for s in steps):
        new_step["current"] = True

    content = path.read_text()
    content = _rebuild_plan_section(content, steps)
    content = _update_timestamp(content)
    atomic_write(path, content)

    update_index(project_path=project_path)
    return f"Step added: [{step_id}] {description}"


def goal_link_project(goal_ref: str, link_path: str,
                      role: str = "primary") -> str:
    """Add a project to a goal. Returns confirmation."""
    path = find_goal(goal_ref)
    project_path = str(Path(link_path).resolve())

    content = path.read_text()

    # Check for exact project path match (not substring)
    goal = parse_goal(path)
    for p in goal.get("projects", []):
        if Path(p["path"]).resolve() == Path(project_path).resolve():
            return f"Project already linked: {project_path}"

    m = re.search(r"(## Projects\n\n)((?:- .+\n?)*)", content, re.MULTILINE)
    if m:
        existing = m.group(2).rstrip("\n")
        new_entry = f"- {project_path} ({role})"
        content = (content[:m.start()] + m.group(1) + existing +
                   "\n" + new_entry + "\n" + content[m.end():])
    else:
        content = content.rstrip() + f"\n\n## Projects\n\n- {project_path} ({role})\n"

    content = _update_timestamp(content)
    atomic_write(path, content)

    # Update index for the linked project
    update_index(project_path=link_path)

    return f"Linked project: {project_path} ({role})"


def goal_archive(goal_ref: str, project_path: str | None = None) -> str:
    """Archive a goal. Returns confirmation."""
    path = find_goal(goal_ref)
    ensure_dirs()

    content = path.read_text()
    content = re.sub(r"(\*\*Status\*\*:\s*).+", r"\1archived", content)
    content = _update_timestamp(content)

    dest = ARCHIVE_DIR / path.name
    atomic_write(dest, content)
    path.unlink()

    # Clear current goal if it was this one
    claude_dir = get_claude_dir(project_path)
    current_path = claude_dir / ".current-goal"
    if current_path.exists():
        current_id, _ = parse_current_goal(current_path.read_text())
        if current_id == path.stem:
            current_path.unlink()

    update_index(project_path=project_path)
    return f"Archived: {path.stem}"


def goal_sync(project_path: str | None = None) -> str:
    """Rebuild active-goals.json from goal files. Returns confirmation."""
    update_index(project_path=project_path)
    claude_dir = get_claude_dir(project_path)
    index = json.loads((claude_dir / "active-goals.json").read_text())
    count = len(index.get("goals", []))
    return f"Synced: {count} goal(s) linked to this project."


def goal_context(project_path: str | None = None) -> dict:
    """Get project-scoped goal context for injection.

    Returns a dict with rich context about the current goal from this project's
    perspective, including focused step, plan summary, recent activity filtered
    to this project, and recent learnings.

    Returns empty dict if no current goal.
    """
    claude_dir = get_claude_dir(project_path)
    current_path = claude_dir / ".current-goal"
    if not current_path.exists():
        return {}

    goal_uuid, focused_step_id = parse_current_goal(current_path.read_text())

    try:
        path = find_goal(goal_uuid)
    except ValueError:
        return {}

    goal = parse_goal(path)
    steps = goal.get("steps", [])
    project_root = str(Path(project_path).resolve()) if project_path else str(Path.cwd().resolve())
    project_name = Path(project_root).name

    # Find this project's role
    role = "primary"
    for p in goal.get("projects", []):
        if Path(p["path"]).resolve() == Path(project_root).resolve():
            role = p.get("role", "primary")
            break

    # Determine focused step
    focused_step = None
    focused_idx = 0
    if focused_step_id:
        for i, s in enumerate(steps):
            if s.get("id") == focused_step_id:
                focused_step = s
                focused_idx = i
                break
    if focused_step is None:
        # Fall back to ← current marker
        for i, s in enumerate(steps):
            if s.get("current"):
                focused_step = s
                focused_idx = i
                break

    # Build plan summary
    plan_lines = []
    for i, s in enumerate(steps):
        check = "x" if s["done"] else " "
        sid = f"[{s['id']}] " if s.get("id") else ""
        focused_marker = " ← focused" if (focused_step and i == focused_idx) else ""
        plan_lines.append(f"- [{check}] {sid}{s['text']}{focused_marker}")

    # Filter activity to this project
    recent_activity = []
    for entry in goal.get("activity", []):
        if f"({project_name})" in entry:
            recent_activity.append(entry.lstrip("- "))

    # Get last 2-3 learnings
    learnings_raw = goal.get("learnings_raw", "")
    learning_sections = re.split(r"(?=^### )", learnings_raw, flags=re.MULTILINE)
    recent_learnings = "\n".join(learning_sections[-3:]).strip()

    return {
        "goal_id": goal_uuid,
        "slug": goal.get("slug", ""),
        "name": goal.get("title", "Untitled"),
        "objective": _extract_section(goal.get("raw", ""), "Objective"),
        "role": role,
        "focused_step_id": focused_step.get("id") if focused_step else None,
        "focused_step_num": focused_idx + 1 if focused_step else None,
        "focused_step_text": focused_step["text"] if focused_step else None,
        "total_steps": len(steps),
        "completed_steps": sum(1 for s in steps if s["done"]),
        "plan_summary": "\n".join(plan_lines),
        "recent_activity": recent_activity[:5],
        "recent_learnings": recent_learnings,
        "goal_file": f"~/.claude/goals/{goal_uuid}.md",
    }


# ---------------------------------------------------------------------------
# CLI wrappers (print + sys.exit)
# ---------------------------------------------------------------------------

def cmd_create(args: list[str]):
    """Create a new goal."""
    if len(args) < 2:
        print("Usage: goals.py create \"Title\" \"Objective\"", file=sys.stderr)
        sys.exit(1)
    print(goal_create(args[0], args[1]))


def cmd_list(args: list[str]):
    """List goals for this project (or all with --all)."""
    print(goal_list(show_all="--all" in args))


def cmd_show(args: list[str]):
    """Print a goal file."""
    try:
        print(goal_show(args[0] if args else None))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_switch(args: list[str]):
    """Set the current goal for this project."""
    if not args:
        print("Usage: goals.py switch <id>", file=sys.stderr)
        sys.exit(1)
    try:
        print(goal_switch(args[0]))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_unset(args: list[str]):
    """Remove the current goal marker."""
    print(goal_unset())


def cmd_focus(args: list[str]):
    """Set focused step for current goal."""
    if len(args) < 1:
        print("Usage: goals.py focus <step-id> [goal-id]", file=sys.stderr)
        sys.exit(1)
    step_id = args[0]
    goal_ref = args[1] if len(args) > 1 else None
    try:
        print(goal_focus(goal_ref, step_id))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_update_step(args: list[str]):
    """Mark a step done and/or advance the current marker."""
    if len(args) < 2:
        print("Usage: goals.py update-step <id> <step-id-or-num> [--complete]", file=sys.stderr)
        sys.exit(1)
    goal_ref = args[0]
    # Try to parse as int (backwards compat), otherwise treat as step ID
    try:
        step_ref: str | int = int(args[1])
    except ValueError:
        step_ref = args[1]
    complete = "--complete" in args
    try:
        print(goal_update_step(goal_ref, step_ref, complete=complete))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_add_learning(args: list[str]):
    """Append a learning to a goal."""
    if len(args) < 2:
        print("Usage: goals.py add-learning <id> \"text\"", file=sys.stderr)
        sys.exit(1)
    try:
        print(goal_add_learning(args[0], args[1]))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_add_commit(args: list[str]):
    """Add a commit to Recent Activity, trim to 10 entries."""
    if len(args) < 3:
        print("Usage: goals.py add-commit <id> <hash> \"message\"", file=sys.stderr)
        sys.exit(1)
    try:
        print(goal_add_commit(args[0], args[1], args[2]))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_add_step(args: list[str]):
    """Insert a plan step."""
    if len(args) < 2:
        print("Usage: goals.py add-step <id> \"description\" [--id step-id] [--after N|step-id]",
              file=sys.stderr)
        sys.exit(1)

    goal_ref = args[0]
    description = args[1]
    step_id = None
    after: str | int | None = None

    if "--id" in args:
        id_idx = args.index("--id")
        if id_idx + 1 < len(args):
            step_id = args[id_idx + 1]

    if "--after" in args:
        after_idx = args.index("--after")
        if after_idx + 1 < len(args):
            val = args[after_idx + 1]
            try:
                after = int(val)
            except ValueError:
                after = val

    try:
        print(goal_add_step(goal_ref, description, step_id=step_id, after=after))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_link_project(args: list[str]):
    """Add a project to a goal."""
    if len(args) < 2:
        print("Usage: goals.py link-project <id> <path> [--role primary|dependency]",
              file=sys.stderr)
        sys.exit(1)
    role = "primary"
    if "--role" in args:
        role_idx = args.index("--role")
        if role_idx + 1 < len(args):
            role = args[role_idx + 1]
    try:
        print(goal_link_project(args[0], args[1], role=role))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_archive(args: list[str]):
    """Archive a goal."""
    if not args:
        print("Usage: goals.py archive <id>", file=sys.stderr)
        sys.exit(1)
    try:
        print(goal_archive(args[0]))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_sync(args: list[str]):
    """Rebuild active-goals.json from goal files."""
    project_path = None
    if "--project" in args:
        proj_idx = args.index("--project")
        if proj_idx + 1 < len(args):
            project_path = args[proj_idx + 1]
    print(goal_sync(project_path=project_path))


def cmd_migrate(args: list[str]):
    """Migrate all v1 goals to v2 format."""
    if not GOALS_DIR.exists():
        print("No goals directory found.")
        return
    migrated = 0
    for gf in GOALS_DIR.glob("*.md"):
        goal = parse_goal(gf)
        if needs_migration(goal):
            migrate_goal(gf)
            print(f"  Migrated: {gf.stem} -> {goal.get('title', 'Untitled')}")
            migrated += 1
    if migrated:
        print(f"Migrated {migrated} goal(s) to v2 format.")
    else:
        print("All goals already at v2 format.")


def cmd_context(args: list[str]):
    """Print project-scoped goal context as JSON."""
    project_path = None
    if "--project" in args:
        proj_idx = args.index("--project")
        if proj_idx + 1 < len(args):
            project_path = args[proj_idx + 1]
    ctx = goal_context(project_path=project_path)
    print(json.dumps(ctx, indent=2))


COMMANDS = {
    "create": cmd_create,
    "list": cmd_list,
    "show": cmd_show,
    "switch": cmd_switch,
    "unset": cmd_unset,
    "focus": cmd_focus,
    "update-step": cmd_update_step,
    "add-learning": cmd_add_learning,
    "add-commit": cmd_add_commit,
    "add-step": cmd_add_step,
    "link-project": cmd_link_project,
    "archive": cmd_archive,
    "sync": cmd_sync,
    "migrate": cmd_migrate,
    "context": cmd_context,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: goals.py <command> [args...]")
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(1)

    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
