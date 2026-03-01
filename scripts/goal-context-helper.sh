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
        GOAL_COUNT=$(python3 -c "
import json
try:
    index = json.load(open('${ACTIVE_GOALS_FILE}'))
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
python3 -c "
import json
import re
from pathlib import Path

mode = '${MODE}'
project_root = '${PROJECT_ROOT}'
project_name = Path(project_root).name

# Parse .current-goal
raw = open('${CURRENT_GOAL_FILE}').read().strip()
if ':' in raw:
    goal_uuid, focused_step_id = raw.split(':', 1)
else:
    goal_uuid, focused_step_id = raw, None

# Find and read goal file
goal_path = Path('${GOALS_DIR}') / f'{goal_uuid}.md'
if not goal_path.exists():
    exit(0)

content = goal_path.read_text()

# Parse fields
title = ''
slug = ''
m = re.search(r'^# Goal:\s*(.+)$', content, re.MULTILINE)
if m: title = m.group(1).strip()
m = re.search(r'^\*\*Slug\*\*:\s*(.+)$', content, re.MULTILINE)
if m: slug = m.group(1).strip()

# Parse objective
objective = ''
if '## Objective' in content:
    objective = content.split('## Objective\n\n')[1].split('\n\n## ')[0].strip()

# Parse role for this project
role = 'primary'
in_projects = False
for line in content.split('\n'):
    if re.match(r'^## Projects', line):
        in_projects = True; continue
    if in_projects and re.match(r'^## ', line): break
    if in_projects and project_root in line:
        m = re.match(r'^- .+\((\w+)\)', line)
        if m: role = m.group(1)

# Parse steps
steps = []
in_plan = False
for line in content.split('\n'):
    if re.match(r'^## Plan', line):
        in_plan = True; continue
    if in_plan and re.match(r'^## ', line): break
    if in_plan:
        m = re.match(r'^- \[([ x])\]\s*(.+)$', line)
        if m:
            text = m.group(2).strip()
            is_current = '← current' in text
            text_clean = re.sub(r'\s*← current\s*$', '', text)
            sid_match = re.match(r'^\[([a-z0-9-]+)\]\s*(.+)$', text_clean)
            sid = sid_match.group(1) if sid_match else None
            desc = sid_match.group(2) if sid_match else text_clean
            steps.append({'id': sid, 'done': m.group(1) == 'x', 'text': desc, 'current': is_current})

# Find focused step
focused = None
focused_idx = 0
if focused_step_id:
    for i, s in enumerate(steps):
        if s.get('id') == focused_step_id:
            focused = s; focused_idx = i; break
if not focused:
    for i, s in enumerate(steps):
        if s.get('current'):
            focused = s; focused_idx = i; break

total = len(steps)
done = sum(1 for s in steps if s['done'])

if mode == 'status':
    # Short status line
    step_info = f'({focused_idx + 1}/{total})' if focused else f'({done}/{total})'
    print(f'Goal: {title} {step_info}')
    exit(0)

# Full context mode
slug_str = f' ({slug})' if slug else ''
lines = []
lines.append(f'🎯 **Active Goal**: {title}{slug_str}')
lines.append(f'   Role: {role} | Step {focused_idx + 1}/{total}: {focused[\"text\"]}' if focused else f'   {done}/{total} steps completed')

# Plan summary
lines.append('')
for i, s in enumerate(steps):
    check = 'x' if s['done'] else ' '
    sid = f'[{s[\"id\"]}] ' if s.get('id') else ''
    marker = ' ← focused' if (focused and i == focused_idx) else ''
    lines.append(f'   - [{check}] {sid}{s[\"text\"]}{marker}')

# Recent activity filtered to this project
in_activity = False
activity = []
for line in content.split('\n'):
    if re.match(r'^## Recent Activity', line):
        in_activity = True; continue
    if in_activity and re.match(r'^## ', line): break
    if in_activity and line.startswith('- ') and f'({project_name})' in line:
        activity.append(line.lstrip('- '))

if activity:
    lines.append('')
    lines.append('   Recent activity (this project):')
    for a in activity[:3]:
        lines.append(f'   - {a}')

# Recent learnings (last entry)
in_learnings = False
learnings = []
current_learning = []
for line in content.split('\n'):
    if re.match(r'^## Approaches & Learnings', line):
        in_learnings = True; continue
    if in_learnings and re.match(r'^## ', line): break
    if in_learnings:
        if line.startswith('### '):
            if current_learning:
                learnings.append('\n'.join(current_learning))
            current_learning = [line]
        elif in_learnings and current_learning:
            current_learning.append(line)
if current_learning:
    learnings.append('\n'.join(current_learning))

if learnings:
    last = learnings[-1].strip()
    if last:
        lines.append('')
        lines.append(f'   Last learning: {last[:200]}')

lines.append(f'   Full goal: ~/.claude/goals/{goal_uuid}.md')
lines.append(f'   Commands: /context-daddy:goal (manage) | /context-daddy:goal-done (complete step) | /context-daddy:goal-focus (change step)')

print('\n'.join(lines))
" 2>/dev/null || true
