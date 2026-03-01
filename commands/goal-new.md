---
description: Create a new cross-session goal with guided setup
allowed-tools: [Bash, Read, Write]
---

# Create New Goal

Guided creation of a cross-session goal that persists across sessions.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Gather Info

Ask the user for:
1. **Title** (short, descriptive): e.g., "Add source annotation tracking"
2. **Objective** (1-3 sentences): What does success look like?

If the user provided these with the command (e.g., `/context-daddy:goal-new "Add auth" "Implement OAuth2 login flow"`), skip the questions.

## Step 2: Create the Goal

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py create "TITLE" "OBJECTIVE"
```

Capture the goal ID from the output.

## Step 3: Add Plan Steps

Ask the user for their plan steps. If they have a rough plan, help refine it into discrete, checkable steps.

For each step:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py add-step <id> "Step description"
```

The first step created replaces the default "Define plan steps" placeholder. Use `--after N` to insert steps at specific positions.

## Step 4: Link Related Projects (Optional)

If the goal spans multiple projects, ask which other projects are involved:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py link-project <id> /path/to/other-project --role dependency
```

## Step 5: Confirm

Show the final goal:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py show <id>
```

Tell the user:
- The goal is now active and will appear in future sessions
- Use `/context-daddy:goal-done` to mark steps complete
- Use `/context-daddy:goal` to manage goals
