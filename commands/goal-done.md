---
description: Mark the current goal step as complete and advance to the next
allowed-tools: [mcp__plugin_context-daddy_goals__goal_show, mcp__plugin_context-daddy_goals__goal_update_step, mcp__plugin_context-daddy_goals__goal_add_learning, mcp__plugin_context-daddy_goals__goal_focus]
---

# Complete Current Goal Step

Quick step completion for the active goal.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Show Current Goal

Use the `goal_show` MCP tool:

```
goal_show()
```

If no current goal is set, tell the user and suggest `/context-daddy:goal` to select one.

## Step 2: Identify Current Step

Find the step marked with `← current` in the output. Note its step ID and description.

## Step 3: Confirm and Complete

Tell the user which step will be marked complete and ask for confirmation.

If confirmed, use the `goal_update_step` MCP tool:

```
goal_update_step(id="<goal-id>", step="<step-id>", complete=true)
```

## Step 4: Optionally Add a Learning

Ask if there's anything worth recording about this step (approaches tried, gotchas):

```
goal_add_learning(id="<goal-id>", text="LEARNING_TEXT")
```

## Step 5: Show Updated State

Use `goal_show()` to display the updated goal.

Summarize: what was completed and what the next step is.
