---
description: Mark the current goal step as complete and advance to the next
allowed-tools: [Bash, Read]
---

# Complete Current Goal Step

Quick step completion for the active goal.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Show Current Goal

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py show
```

If no current goal is set, tell the user and suggest `/context-daddy:goal` to select one.

## Step 2: Identify Current Step

Find the step marked with `← current` in the output.

## Step 3: Confirm and Complete

Tell the user which step will be marked complete and ask for confirmation.

If confirmed:
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py update-step <id> <step-num> --complete
```

## Step 4: Optionally Add a Learning

Ask if there's anything worth recording about this step (approaches tried, gotchas):

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py add-learning <id> "LEARNING_TEXT"
```

## Step 5: Show Updated State

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/goals.py show
```

Summarize: what was completed and what the next step is.
