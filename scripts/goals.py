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
  <project>/.claude/.current-goal     - Active goal UUID for this project
"""

import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path


GOALS_DIR = Path.home() / ".claude" / "goals"
ARCHIVE_DIR = GOALS_DIR / ".archive"


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


def atomic_write(path: Path, content: str):
    """Write content atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def find_goal_by_id(goal_id: str) -> Path | None:
    """Find a goal file by full or partial UUID (4+ chars)."""
    if len(goal_id) < 4:
        print(f"Error: ID must be at least 4 characters, got '{goal_id}'", file=sys.stderr)
        return None

    # Check active goals first, then archive
    for directory in [GOALS_DIR, ARCHIVE_DIR]:
        if not directory.exists():
            continue
        matches = [f for f in directory.glob("*.md") if f.stem.startswith(goal_id)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Error: Ambiguous ID '{goal_id}' matches: {', '.join(m.stem for m in matches)}",
                  file=sys.stderr)
            return None

    print(f"Error: No goal found matching '{goal_id}'", file=sys.stderr)
    return None


def parse_goal(path: Path) -> dict:
    """Parse a goal markdown file into a dict."""
    content = path.read_text()
    goal = {"path": str(path), "raw": content}

    # Parse header fields
    for key in ["ID", "Status", "Created", "Updated"]:
        m = re.search(rf"^\*\*{key}\*\*:\s*(.+)$", content, re.MULTILINE)
        if m:
            goal[key.lower()] = m.group(1).strip()

    # Parse title
    m = re.search(r"^# Goal:\s*(.+)$", content, re.MULTILINE)
    if m:
        goal["title"] = m.group(1).strip()

    # Parse plan steps
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
                steps.append({
                    "done": m.group(1) == "x",
                    "text": text_clean,
                    "current": is_current,
                })
    goal["steps"] = steps

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

    return goal


def render_goal(goal_id: str, title: str, objective: str, status: str = "active",
                created: str | None = None, updated: str | None = None,
                projects: list[dict] | None = None, steps: list[dict] | None = None,
                learnings: str = "", activity: str = "") -> str:
    """Render a goal dict back to markdown."""
    now = datetime.now().strftime("%Y-%m-%d")
    created = created or now
    updated = updated or now

    lines = [
        f"# Goal: {title}",
        "",
        f"**ID**: {goal_id}",
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
            check = "x" if s.get("done") else " "
            marker = "  ← current" if s.get("current") else ""
            lines.append(f"- [{check}] {s['text']}{marker}")
    else:
        lines.append("- [ ] Define plan steps  ← current")

    lines.extend(["", "## Approaches & Learnings", ""])
    if learnings:
        lines.append(learnings)

    lines.extend(["", "## Recent Activity", ""])
    if activity:
        lines.append(activity)

    lines.append("")
    return "\n".join(lines)


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
                        # Find current step info
                        steps = goal.get("steps", [])
                        current_idx = next((i for i, s in enumerate(steps) if s.get("current")), 0)
                        goals_to_include.append({
                            "id": goal.get("id", gf.stem),
                            "name": goal.get("title", "Untitled"),
                            "role": p.get("role", "primary"),
                            "current_step": current_idx + 1,
                            "total_steps": len(steps),
                            "current_step_text": steps[current_idx]["text"] if steps and current_idx < len(steps) else "",
                            "updated": goal.get("updated", ""),
                        })
                        break

    index = {
        "version": 1,
        "goals": goals_to_include,
    }
    atomic_write(claude_dir / "active-goals.json", json.dumps(index, indent=2) + "\n")


def cmd_create(args: list[str]):
    """Create a new goal."""
    if len(args) < 2:
        print("Usage: goals.py create \"Title\" \"Objective\"", file=sys.stderr)
        sys.exit(1)

    title, objective = args[0], args[1]
    goal_id = generate_id()
    ensure_dirs()

    content = render_goal(goal_id, title, objective)
    goal_path = GOALS_DIR / f"{goal_id}.md"
    atomic_write(goal_path, content)

    # Set as current goal
    claude_dir = get_claude_dir()
    atomic_write(claude_dir / ".current-goal", goal_id + "\n")

    # Update project index
    goal = parse_goal(goal_path)
    steps = goal.get("steps", [])
    current_idx = next((i for i, s in enumerate(steps) if s.get("current")), 0)
    update_index(goals_to_include=[{
        "id": goal_id,
        "name": title,
        "role": "primary",
        "current_step": current_idx + 1,
        "total_steps": len(steps),
        "current_step_text": steps[current_idx]["text"] if steps else "",
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }])

    print(f"Created goal: {goal_id}")
    print(f"  Title: {title}")
    print(f"  File: {goal_path}")


def cmd_list(args: list[str]):
    """List goals for this project (or all with --all)."""
    show_all = "--all" in args

    if show_all:
        if not GOALS_DIR.exists():
            print("No goals found.")
            return
        for gf in sorted(GOALS_DIR.glob("*.md")):
            goal = parse_goal(gf)
            steps = goal.get("steps", [])
            done = sum(1 for s in steps if s["done"])
            status = goal.get("status", "?")
            print(f"  {gf.stem}  [{status}]  {goal.get('title', 'Untitled')}  ({done}/{len(steps)} steps)")
    else:
        claude_dir = get_claude_dir()
        index_path = claude_dir / "active-goals.json"
        current_path = claude_dir / ".current-goal"
        current_id = current_path.read_text().strip() if current_path.exists() else ""

        if not index_path.exists():
            print("No goals linked to this project. Use 'goals.py create' or 'goals.py sync'.")
            return

        index = json.loads(index_path.read_text())
        goals = index.get("goals", [])
        if not goals:
            print("No goals linked to this project.")
            return

        for g in goals:
            marker = " *" if g["id"] == current_id else "  "
            print(f"{marker}{g['id']}  {g['name']}  ({g['current_step']}/{g['total_steps']}) {g.get('current_step_text', '')}")


def cmd_show(args: list[str]):
    """Print a goal file."""
    if not args:
        # Show current goal
        claude_dir = get_claude_dir()
        current_path = claude_dir / ".current-goal"
        if not current_path.exists():
            print("No current goal set. Use 'goals.py switch <id>' or 'goals.py create'.", file=sys.stderr)
            sys.exit(1)
        goal_id = current_path.read_text().strip()
    else:
        goal_id = args[0]

    path = find_goal_by_id(goal_id)
    if not path:
        sys.exit(1)

    print(path.read_text())


def cmd_switch(args: list[str]):
    """Set the current goal for this project."""
    if not args:
        print("Usage: goals.py switch <id>", file=sys.stderr)
        sys.exit(1)

    path = find_goal_by_id(args[0])
    if not path:
        sys.exit(1)

    claude_dir = get_claude_dir()
    atomic_write(claude_dir / ".current-goal", path.stem + "\n")

    # Ensure goal is in the project index
    update_index()

    goal = parse_goal(path)
    print(f"Switched to: {goal.get('title', path.stem)}")


def cmd_unset(args: list[str]):
    """Remove the current goal marker."""
    claude_dir = get_claude_dir()
    current_path = claude_dir / ".current-goal"
    if current_path.exists():
        current_path.unlink()
        print("Current goal unset.")
    else:
        print("No current goal was set.")


def cmd_update_step(args: list[str]):
    """Mark a step done and/or advance the current marker."""
    if len(args) < 2:
        print("Usage: goals.py update-step <id> <step-num> [--complete]", file=sys.stderr)
        sys.exit(1)

    goal_id = args[0]
    step_num = int(args[1])  # 1-based
    complete = "--complete" in args

    path = find_goal_by_id(goal_id)
    if not path:
        sys.exit(1)

    goal = parse_goal(path)
    steps = goal.get("steps", [])

    if step_num < 1 or step_num > len(steps):
        print(f"Error: Step {step_num} out of range (1-{len(steps)})", file=sys.stderr)
        sys.exit(1)

    idx = step_num - 1

    if complete:
        steps[idx]["done"] = True
        steps[idx]["current"] = False
        # Advance current to next incomplete step
        next_idx = next((i for i in range(idx + 1, len(steps)) if not steps[i]["done"]), None)
        if next_idx is not None:
            steps[next_idx]["current"] = True
    else:
        # Just move the current marker
        for s in steps:
            s["current"] = False
        steps[idx]["current"] = True

    # Rebuild the file
    content = path.read_text()

    # Replace the Plan section
    plan_lines = []
    for s in steps:
        check = "x" if s["done"] else " "
        marker = "  ← current" if s["current"] else ""
        plan_lines.append(f"- [{check}] {s['text']}{marker}")
    plan_block = "\n".join(plan_lines)

    # Use regex to replace the plan section
    content = re.sub(
        r"(## Plan\n\n)((?:- \[[ x]\].+\n?)+)",
        rf"\g<1>{plan_block}\n",
        content,
    )

    # Update the Updated date
    now = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)

    atomic_write(path, content)

    # Sync the project index
    update_index()

    current_step = next((s for s in steps if s.get("current")), None)
    if current_step:
        print(f"Step {step_num} {'completed' if complete else 'set as current'}. Current: {current_step['text']}")
    else:
        print(f"Step {step_num} {'completed' if complete else 'updated'}. All steps done!")


def cmd_add_learning(args: list[str]):
    """Append a learning to a goal."""
    if len(args) < 2:
        print("Usage: goals.py add-learning <id> \"text\"", file=sys.stderr)
        sys.exit(1)

    path = find_goal_by_id(args[0])
    if not path:
        sys.exit(1)

    text = args[1]
    now = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n### {now}\n{text}\n"

    content = path.read_text()

    # Insert before "## Recent Activity"
    m = re.search(r"^## Recent Activity", content, re.MULTILINE)
    if m:
        content = content[:m.start()] + content[content.rindex("\n", 0, m.start()):m.start()].lstrip("\n") + entry + "\n" + content[m.start():]
        # Clean up: ensure Approaches section ends with the new entry before Recent Activity
        content = re.sub(r"(## Approaches & Learnings\n(?:.*\n)*?)" + re.escape(entry.strip()) + r"\n*## Recent Activity",
                         r"\1" + entry.strip() + "\n\n## Recent Activity", content)
    else:
        # Append at end
        content = content.rstrip() + "\n" + entry

    # Update date
    now_str = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now_str}", content)

    atomic_write(path, content)
    print(f"Learning added to {path.stem}.")


def cmd_add_commit(args: list[str]):
    """Add a commit to Recent Activity, trim to 10 entries."""
    if len(args) < 3:
        print("Usage: goals.py add-commit <id> <hash> \"message\"", file=sys.stderr)
        sys.exit(1)

    path = find_goal_by_id(args[0])
    if not path:
        sys.exit(1)

    commit_hash = args[1]
    message = args[2]
    now = datetime.now().strftime("%Y-%m-%d")

    # Determine project name from cwd
    project_name = Path.cwd().name

    entry = f"- `{commit_hash}` ({project_name}) {now}: {message}"

    content = path.read_text()

    # Find Recent Activity section and parse existing entries
    m = re.search(r"^## Recent Activity\n\n?((?:- .+\n?)*)", content, re.MULTILINE)
    if m:
        existing = [line for line in m.group(1).strip().split("\n") if line.strip()]
        existing.insert(0, entry)
        existing = existing[:10]  # Trim to 10
        activity_block = "\n".join(existing) + "\n"
        content = content[:m.start()] + "## Recent Activity\n\n" + activity_block + content[m.end():]
    else:
        content = content.rstrip() + "\n\n## Recent Activity\n\n" + entry + "\n"

    # Update date
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)

    atomic_write(path, content)
    print(f"Commit tracked in {path.stem}.")


def cmd_add_step(args: list[str]):
    """Insert a plan step."""
    if not args:
        print("Usage: goals.py add-step <id> \"description\" [--after N]", file=sys.stderr)
        sys.exit(1)

    goal_id = args[0]
    description = args[1] if len(args) > 1 else None
    if not description:
        print("Usage: goals.py add-step <id> \"description\" [--after N]", file=sys.stderr)
        sys.exit(1)

    after = None
    if "--after" in args:
        after_idx = args.index("--after")
        if after_idx + 1 < len(args):
            after = int(args[after_idx + 1])

    path = find_goal_by_id(goal_id)
    if not path:
        sys.exit(1)

    goal = parse_goal(path)
    steps = goal.get("steps", [])

    new_step = {"done": False, "text": description, "current": False}

    if after is not None and 1 <= after <= len(steps):
        steps.insert(after, new_step)
    else:
        steps.append(new_step)

    # If no current marker exists, set on new step
    if not any(s.get("current") for s in steps):
        new_step["current"] = True

    # Rebuild plan section
    plan_lines = []
    for s in steps:
        check = "x" if s["done"] else " "
        marker = "  ← current" if s["current"] else ""
        plan_lines.append(f"- [{check}] {s['text']}{marker}")
    plan_block = "\n".join(plan_lines)

    content = path.read_text()
    content = re.sub(
        r"(## Plan\n\n)((?:- \[[ x]\].+\n?)+)",
        rf"\g<1>{plan_block}\n",
        content,
    )

    # Update date
    now = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)

    atomic_write(path, content)
    update_index()
    print(f"Step added: {description}")


def cmd_link_project(args: list[str]):
    """Add a project to a goal."""
    if len(args) < 2:
        print("Usage: goals.py link-project <id> <path> [--role primary|dependency]", file=sys.stderr)
        sys.exit(1)

    goal_id = args[0]
    project_path = str(Path(args[1]).resolve())
    role = "primary"
    if "--role" in args:
        role_idx = args.index("--role")
        if role_idx + 1 < len(args):
            role = args[role_idx + 1]

    path = find_goal_by_id(goal_id)
    if not path:
        sys.exit(1)

    content = path.read_text()

    # Check if project already listed
    if project_path in content:
        print(f"Project already linked: {project_path}")
        return

    # Insert into Projects section
    m = re.search(r"(## Projects\n\n)((?:- .+\n?)*)", content, re.MULTILINE)
    if m:
        existing = m.group(2).rstrip("\n")
        new_entry = f"- {project_path} ({role})"
        content = content[:m.start()] + m.group(1) + existing + "\n" + new_entry + "\n" + content[m.end():]
    else:
        # No Projects section - add one
        content = content.rstrip() + f"\n\n## Projects\n\n- {project_path} ({role})\n"

    # Update date
    now = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)

    atomic_write(path, content)

    # Update index for the linked project
    update_index(project_path=project_path)

    print(f"Linked project: {project_path} ({role})")


def cmd_archive(args: list[str]):
    """Archive a goal."""
    if not args:
        print("Usage: goals.py archive <id>", file=sys.stderr)
        sys.exit(1)

    path = find_goal_by_id(args[0])
    if not path:
        sys.exit(1)

    ensure_dirs()

    # Update status in file
    content = path.read_text()
    content = re.sub(r"(\*\*Status\*\*:\s*).+", r"\1archived", content)
    now = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"(\*\*Updated\*\*:\s*).+", rf"\g<1>{now}", content)

    # Move to archive
    dest = ARCHIVE_DIR / path.name
    atomic_write(dest, content)
    path.unlink()

    # Clear current goal if it was this one
    claude_dir = get_claude_dir()
    current_path = claude_dir / ".current-goal"
    if current_path.exists() and current_path.read_text().strip() == path.stem:
        current_path.unlink()

    # Update index
    update_index()

    print(f"Archived: {path.stem}")


def cmd_sync(args: list[str]):
    """Rebuild active-goals.json from goal files."""
    project_path = None
    if "--project" in args:
        proj_idx = args.index("--project")
        if proj_idx + 1 < len(args):
            project_path = args[proj_idx + 1]

    update_index(project_path=project_path)
    claude_dir = get_claude_dir(project_path)
    index = json.loads((claude_dir / "active-goals.json").read_text())
    count = len(index.get("goals", []))
    print(f"Synced: {count} goal(s) linked to this project.")


COMMANDS = {
    "create": cmd_create,
    "list": cmd_list,
    "show": cmd_show,
    "switch": cmd_switch,
    "unset": cmd_unset,
    "update-step": cmd_update_step,
    "add-learning": cmd_add_learning,
    "add-commit": cmd_add_commit,
    "add-step": cmd_add_step,
    "link-project": cmd_link_project,
    "archive": cmd_archive,
    "sync": cmd_sync,
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
