#!/usr/bin/env bash
# Shared helper: outputs rich goal context for injection into Claude's context.
# Uses python3 stdlib only (no uv needed) for fast execution.
#
# Usage:
#   GOAL_CONTEXT=$(bash scripts/goal-context-helper.sh [project_root])
#   GOAL_STATUS_MSG=$(bash scripts/goal-context-helper.sh --status [project_root])

set -euo pipefail

MODE="context"
if [[ "${1:-}" == "--status" ]]; then
    MODE="status"
    shift
fi

PROJECT_ROOT="${1:-${PWD}}"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"
CURRENT_GOAL_FILE="${CLAUDE_DIR}/.current-goal"
ACTIVE_GOALS_FILE="${CLAUDE_DIR}/active-goals.json"
GOALS_DIR="${HOME}/.claude/goals"

# Quick exit if no goal data
if [[ ! -f "${CURRENT_GOAL_FILE}" ]]; then
    if [[ -f "${ACTIVE_GOALS_FILE}" && "${MODE}" == "context" ]]; then
        GOAL_COUNT=$(ACTIVE_GOALS_FILE="${ACTIVE_GOALS_FILE}" python3 -c "
import json, os
try:
    index = json.load(open(os.environ['ACTIVE_GOALS_FILE']))
    print(len(index.get('goals', [])))
except Exception:
    print(0)
" 2>/dev/null || echo "0")
        if [[ "${GOAL_COUNT}" -gt 0 ]]; then
            echo "📋 ${GOAL_COUNT} active goal(s) linked to this project - run /context-daddy:goal to select one"
        fi
    fi
    exit 0
fi

# Read goal context using python3 stdlib
# Pass all paths via env vars to avoid shell injection
export _GCH_MODE="${MODE}"
export _GCH_PROJECT_ROOT="${PROJECT_ROOT}"
export _GCH_CURRENT_GOAL_FILE="${CURRENT_GOAL_FILE}"
export _GCH_GOALS_DIR="${GOALS_DIR}"

python3 -c '
import json
import os
import re
from pathlib import Path

mode = os.environ["_GCH_MODE"]
project_root = os.environ["_GCH_PROJECT_ROOT"]
current_goal_file = os.environ["_GCH_CURRENT_GOAL_FILE"]
goals_dir = os.environ["_GCH_GOALS_DIR"]
project_name = Path(project_root).name

# Parse .current-goal
raw = open(current_goal_file).read().strip()
if ":" in raw:
    goal_uuid, focused_step_id = raw.split(":", 1)
else:
    goal_uuid, focused_step_id = raw, None

# Find and read goal file
goal_path = Path(goals_dir) / f"{goal_uuid}.md"
if not goal_path.exists():
    exit(0)

content = goal_path.read_text()

# Parse fields
title = ""
slug = ""
m = re.search(r"^# Goal:\s*(.+)$", content, re.MULTILINE)
if m: title = m.group(1).strip()
m = re.search(r"^\*\*Slug\*\*:\s*(.+)$", content, re.MULTILINE)
if m: slug = m.group(1).strip()

# Parse objective
objective = ""
m = re.search(r"^## Objective\s*\n\n?(.*?)(?=\n## |\Z)", content, re.MULTILINE | re.DOTALL)
if m: objective = m.group(1).strip()

# Parse role for this project
role = "primary"
in_projects = False
for line in content.split("\n"):
    if re.match(r"^## Projects", line):
        in_projects = True; continue
    if in_projects and re.match(r"^## ", line): break
    if in_projects and project_root in line:
        m = re.match(r"^- .+\((\w+)\)", line)
        if m: role = m.group(1)

# Parse steps
steps = []
in_plan = False
for line in content.split("\n"):
    if re.match(r"^## Plan", line):
        in_plan = True; continue
    if in_plan and re.match(r"^## ", line): break
    if in_plan:
        m = re.match(r"^- \[([ x])\]\s*(.+)$", line)
        if m:
            text = m.group(2).strip()
            is_current = "\u2190 current" in text
            text_clean = re.sub(r"\s*\u2190 current\s*$", "", text)
            sid_match = re.match(r"^\[([a-z0-9-]+)\]\s*(.+)$", text_clean)
            sid = sid_match.group(1) if sid_match else None
            desc = sid_match.group(2) if sid_match else text_clean
            steps.append({"id": sid, "done": m.group(1) == "x", "text": desc, "current": is_current})

# Find focused step
focused = None
focused_idx = 0
if focused_step_id:
    for i, s in enumerate(steps):
        if s.get("id") == focused_step_id:
            focused = s; focused_idx = i; break
if not focused:
    for i, s in enumerate(steps):
        if s.get("current"):
            focused = s; focused_idx = i; break

total = len(steps)
done = sum(1 for s in steps if s.get("done"))

if mode == "status":
    # Short status line
    step_info = f"({focused_idx + 1}/{total})" if focused else f"({done}/{total})"
    print(f"Goal: {title} {step_info}")
    exit(0)

# Full context mode
slug_str = f" ({slug})" if slug else ""
lines = []
lines.append(f"\U0001f3af **Active Goal**: {title}{slug_str}")
if focused:
    ft = focused.get("text", "")
    lines.append(f"   Role: {role} | Step {focused_idx + 1}/{total}: {ft}")
else:
    lines.append(f"   {done}/{total} steps completed")

# Plan summary
lines.append("")
for i, s in enumerate(steps):
    check = "x" if s.get("done") else " "
    step_id = s.get("id", "")
    step_text = s.get("text", "")
    sid = f"[{step_id}] " if step_id else ""
    marker = " \u2190 focused" if (focused and i == focused_idx) else ""
    lines.append(f"   - [{check}] {sid}{step_text}{marker}")

# Recent activity filtered to this project
in_activity = False
activity = []
for line in content.split("\n"):
    if re.match(r"^## Recent Activity", line):
        in_activity = True; continue
    if in_activity and re.match(r"^## ", line): break
    if in_activity and line.startswith("- ") and f"({project_name})" in line:
        activity.append(line.lstrip("- "))

if activity:
    lines.append("")
    lines.append("   Recent activity (this project):")
    for a in activity[:3]:
        lines.append(f"   - {a}")

# Recent learnings (last entry)
in_learnings = False
learnings = []
current_learning = []
for line in content.split("\n"):
    if re.match(r"^## Approaches & Learnings", line):
        in_learnings = True; continue
    if in_learnings and re.match(r"^## ", line): break
    if in_learnings:
        if line.startswith("### "):
            if current_learning:
                learnings.append("\n".join(current_learning))
            current_learning = [line]
        elif in_learnings and current_learning:
            current_learning.append(line)
if current_learning:
    learnings.append("\n".join(current_learning))

if learnings:
    last = learnings[-1].strip()
    if last:
        lines.append("")
        lines.append(f"   Last learning: {last[:200]}")

lines.append(f"   Full goal: ~/.claude/goals/{goal_uuid}.md")
lines.append("   Commands: /context-daddy:goal (manage) | /context-daddy:goal-done (complete step) | /context-daddy:goal-focus (change step)")

# Behavioral guidance
lines.append("")
lines.append("   **IMPORTANT - Goal-driven workflow:**")
lines.append("   - When the user asks for a large multi-step task, prefer the goal system (goal_create + goal_add_step) over EnterPlanMode. If you do use EnterPlanMode, the plan steps will be auto-captured as goal steps.")
lines.append("   - After completing a step, use goal_update_step to mark it done, then CONTINUE to the next step without waiting to be asked.")
lines.append("   - Only stop between steps if you need user input or clarification.")
lines.append("   - To reorder or remove steps: edit the goal file directly (rearrange/delete the `- [ ] [step-id]` lines). Step IDs, not positions, identify steps.")

print("\n".join(lines))
' 2>/dev/null || true
