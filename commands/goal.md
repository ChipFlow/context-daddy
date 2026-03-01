---
description: Manage cross-session goals - list, show, switch, archive
allowed-tools: [Bash, Read]
---

# Goal Management

Manage cross-session goals that persist across sessions and projects.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Show Current State

Run this to see goals for the current project:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py list
```

And check if there's a current goal:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py show 2>/dev/null || echo "No current goal set."
```

## Step 2: Offer Actions

Based on the output, offer the user these options:

- **Switch goal**: If multiple goals exist, ask which to activate
  ```bash
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py switch <id>
  ```

- **Show all goals** (including other projects):
  ```bash
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py list --all
  ```

- **Create new goal**: Point them to `/context-daddy:goal-new`

- **Complete current step**: Point them to `/context-daddy:goal-done`

- **Archive a goal** (mark as finished/abandoned):
  ```bash
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py archive <id>
  ```

- **Unset current goal** (stop tracking without archiving):
  ```bash
  uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py unset
  ```

## Step 3: Execute User Choice

Run the appropriate command based on the user's selection.

After any change, show the updated state:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py show 2>/dev/null
```
