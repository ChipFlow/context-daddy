#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Discover project dev tools and generate .claude/TOOLS.md.

Scans common locations for scripts, build targets, and dev commands
so Claude remembers what tools exist across sessions and after compaction.
"""

import json
import re
import sys
from pathlib import Path


def extract_description_from_file(filepath: Path) -> str:
    """Extract a short description from a script file's first comment or docstring."""
    try:
        text = filepath.read_text(errors="replace")
        lines = text.splitlines()
    except (OSError, UnicodeDecodeError):
        return ""

    # Skip shebang, blank lines, and PEP 723 metadata blocks
    start = 0
    in_metadata = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#!") or stripped == "":
            start = i + 1
            continue
        # PEP 723 inline script metadata: # /// script ... # ///
        if stripped == "# /// script":
            in_metadata = True
            start = i + 1
            continue
        if in_metadata:
            if stripped == "# ///":
                in_metadata = False
            start = i + 1
            continue
        break

    if start >= len(lines):
        return ""

    # For Python files: check for docstring
    if filepath.suffix == ".py":
        for i in range(start, min(start + 10, len(lines))):
            stripped = lines[i].strip()
            # Skip blank lines and import lines before docstring
            if stripped == "" or stripped.startswith("import ") or stripped.startswith("from "):
                continue
            # Skip comment lines
            if stripped.startswith("#"):
                match = re.match(r'^#\s*(.+)', stripped)
                if match and not match.group(1).startswith(("///", "!")):
                    return match.group(1).rstrip(".")
                continue
            # Triple-quote docstring
            for quote in ('"""', "'''"):
                if stripped.startswith(quote):
                    content = stripped[3:]
                    # Single-line docstring: """text"""
                    end_idx = content.find(quote)
                    if end_idx >= 0:
                        return content[:end_idx].strip().rstrip(".")
                    # Multi-line docstring: grab this line or next
                    content = content.strip()
                    if content:
                        return content.rstrip(".")
                    if i + 1 < len(lines):
                        return lines[i + 1].strip().rstrip(".")
                    return ""
            break

    # For shell/other: first comment line after shebang
    for i in range(start, min(start + 5, len(lines))):
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            match = re.match(r'^#\s*(.+)', stripped)
            if match:
                desc = match.group(1).strip()
                # Skip metadata-like comments
                if desc.startswith(("!", "///", "-*-")):
                    continue
                return desc.rstrip(".")
        elif stripped == "":
            continue
        else:
            break

    return ""


def discover_script_dirs(root: Path) -> list[tuple[str, str]]:
    """Discover scripts in common directories. Returns [(relative_path, description)]."""
    results = []
    script_dirs = ["scripts", "tools", "bin", "dev"]

    for dirname in script_dirs:
        dirpath = root / dirname
        if not dirpath.is_dir():
            continue

        for filepath in sorted(dirpath.iterdir()):
            if filepath.is_dir():
                continue
            if filepath.name.startswith(".") or filepath.name.startswith("_"):
                continue
            # Skip common non-tool files
            if filepath.suffix in (".pyc", ".pyo", ".class", ".o"):
                continue

            desc = extract_description_from_file(filepath)
            rel = filepath.relative_to(root)
            results.append((str(rel), desc))

    return results


def discover_makefile_targets(root: Path) -> list[tuple[str, str]]:
    """Parse Makefile for target names + inline comments."""
    results = []
    makefile = root / "Makefile"
    if not makefile.exists():
        return results

    try:
        text = makefile.read_text(errors="replace")
    except OSError:
        return results

    for line in text.splitlines():
        # Match targets like: target: deps  ## description
        # or: target: deps  # description
        match = re.match(r'^([a-zA-Z_][\w.-]*)\s*:(?!=)', line)
        if match:
            target = match.group(1)
            # Skip internal/phony targets that look private
            if target.startswith("_"):
                continue
            # Look for ## or # comment after the line
            desc_match = re.search(r'##?\s+(.+)$', line)
            desc = desc_match.group(1).strip() if desc_match else ""
            results.append((f"make {target}", desc))

    return results


def discover_package_json_scripts(root: Path) -> list[tuple[str, str]]:
    """Extract scripts from package.json."""
    results = []
    pkg = root / "package.json"
    if not pkg.exists():
        return results

    try:
        data = json.loads(pkg.read_text())
    except (OSError, json.JSONDecodeError):
        return results

    scripts = data.get("scripts", {})
    # Detect package manager
    pm = "npm run"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        pm = "bun run"
    elif (root / "pnpm-lock.yaml").exists():
        pm = "pnpm run"
    elif (root / "yarn.lock").exists():
        pm = "yarn"

    for name, cmd in scripts.items():
        # Truncate long commands
        desc = cmd if len(cmd) <= 60 else cmd[:57] + "..."
        results.append((f"{pm} {name}", desc))

    return results


def discover_pyproject_scripts(root: Path) -> list[tuple[str, str]]:
    """Extract scripts from pyproject.toml [project.scripts] and [tool.pdm.scripts]."""
    results = []
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return results

    try:
        text = pyproject.read_text()
    except OSError:
        return results

    # Simple TOML parsing for [project.scripts] section
    in_section = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]").strip()
            in_section = section
            continue

        if in_section in ("project.scripts", "tool.pdm.scripts"):
            match = re.match(r'^(\w[\w-]*)\s*=\s*["\'](.+?)["\']', stripped)
            if match:
                name, value = match.group(1), match.group(2)
                if in_section == "tool.pdm.scripts":
                    results.append((f"pdm run {name}", value))
                else:
                    results.append((name, value))

    return results


def discover_justfile_targets(root: Path) -> list[tuple[str, str]]:
    """Extract targets from Justfile."""
    results = []
    # Try common names
    for name in ("Justfile", "justfile"):
        justfile = root / name
        if justfile.exists():
            break
    else:
        return results

    try:
        text = justfile.read_text(errors="replace")
    except OSError:
        return results

    comment_buffer = ""
    for line in text.splitlines():
        stripped = line.strip()
        # Collect comments above recipes
        if stripped.startswith("#"):
            comment_buffer = stripped.lstrip("#").strip()
            continue
        # Recipe definition
        match = re.match(r'^([a-zA-Z_][\w-]*)\s*(?:\(|:)', stripped)
        if match:
            target = match.group(1)
            results.append((f"just {target}", comment_buffer))
            comment_buffer = ""
        else:
            comment_buffer = ""

    return results


def discover_taskfile_targets(root: Path) -> list[tuple[str, str]]:
    """Extract targets from Taskfile.yml."""
    results = []
    for name in ("Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"):
        taskfile = root / name
        if taskfile.exists():
            break
    else:
        return results

    try:
        text = taskfile.read_text(errors="replace")
    except OSError:
        return results

    # Simple YAML parsing: look for task names under 'tasks:' key
    in_tasks = False
    current_task = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "tasks:":
            in_tasks = True
            continue
        if in_tasks:
            # Top-level task (2 spaces indent, then name:)
            task_match = re.match(r'^  ([a-zA-Z_][\w-]*):', line)
            if task_match:
                current_task = task_match.group(1)
                results.append((f"task {current_task}", ""))
            # Description under task
            if current_task:
                desc_match = re.match(r'^\s+desc:\s*(.+)', line)
                if desc_match and results:
                    # Update last entry with description
                    cmd, _ = results[-1]
                    results[-1] = (cmd, desc_match.group(1).strip().strip('"\''))

    return results


def discover_build_commands(root: Path) -> list[tuple[str, str]]:
    """Pull build commands from project-manifest.json if available."""
    results = []
    manifest = root / ".claude" / "project-manifest.json"
    if not manifest.exists():
        return results

    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return results

    # Extract commands from build systems
    build_systems = data.get("build_systems", [])
    if not build_systems:
        # Legacy format
        build = data.get("build_system", {})
        if build:
            build_systems = [build]

    for bs in build_systems:
        commands = bs.get("commands", {})
        for cmd_name, cmd_value in commands.items():
            if isinstance(cmd_value, str) and cmd_value:
                results.append((cmd_value, cmd_name.replace("_", " ").title()))

    return results


def generate_tools_md(root: Path) -> str:
    """Generate TOOLS.md content from discovered tools."""
    sections = []

    # Build & manifest commands
    build_cmds = discover_build_commands(root)
    if build_cmds:
        lines = ["## Build & Test Commands"]
        for cmd, desc in build_cmds:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # package.json scripts
    pkg_scripts = discover_package_json_scripts(root)
    if pkg_scripts:
        lines = ["## npm/Package Scripts"]
        for cmd, desc in pkg_scripts:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # pyproject.toml scripts
    py_scripts = discover_pyproject_scripts(root)
    if py_scripts:
        lines = ["## Python Scripts (pyproject.toml)"]
        for cmd, desc in py_scripts:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # Makefile targets
    make_targets = discover_makefile_targets(root)
    if make_targets:
        lines = ["## Makefile Targets"]
        for cmd, desc in make_targets:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # Justfile targets
    just_targets = discover_justfile_targets(root)
    if just_targets:
        lines = ["## Just Recipes"]
        for cmd, desc in just_targets:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # Taskfile targets
    task_targets = discover_taskfile_targets(root)
    if task_targets:
        lines = ["## Task Targets"]
        for cmd, desc in task_targets:
            if desc:
                lines.append(f"- `{cmd}` — {desc}")
            else:
                lines.append(f"- `{cmd}`")
        sections.append("\n".join(lines))

    # Script directories
    scripts = discover_script_dirs(root)
    if scripts:
        lines = ["## Scripts"]
        for path, desc in scripts:
            if desc:
                lines.append(f"- `{path}` — {desc}")
            else:
                lines.append(f"- `{path}`")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    header = "# Project Dev Tools\n\n> Auto-discovered by context-daddy. Update this file when you create new scripts or tools.\n"
    return header + "\n\n" + "\n\n".join(sections) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: discover-tools.py <project-root>", file=sys.stderr)
        sys.exit(1)

    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    content = generate_tools_md(root)
    if not content:
        print("No dev tools discovered.", file=sys.stderr)
        sys.exit(0)

    # Write to .claude/TOOLS.md
    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    tools_md = claude_dir / "TOOLS.md"
    tools_md.write_text(content)
    print(f"Wrote {tools_md}", file=sys.stderr)

    # Also print to stdout for inspection
    print(content)


if __name__ == "__main__":
    main()
