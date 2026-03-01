---
description: Set the focused step for your current goal
allowed-tools: [mcp__plugin_context-daddy_goals__goal_show, mcp__plugin_context-daddy_goals__goal_focus]
---

# Focus on a Goal Step

Set which step you're actively working on for the current goal.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Show Current Goal

Use the `goal_show` MCP tool to display the current goal with its plan steps:

```
goal_show()
```

If no current goal is set, tell the user and suggest `/context-daddy:goal` to select one.

## Step 2: Show Numbered Steps

Parse the plan steps from the output and display them clearly with their step IDs:

```
1. [define-plan] Define plan steps
2. [add-src-location] Add source location to ABC network nodes  <- current
3. [test-annotations] Write annotation tests
```

## Step 3: Ask Which Step to Focus On

Ask the user which step they want to focus on. They can specify by:
- Step ID (e.g., `add-src-location`)
- Step number (e.g., `2`)

Default to the next incomplete step if user doesn't specify.

## Step 4: Set Focus

Use the `goal_focus` MCP tool:

```
goal_focus(step="<step-id>")
```

## Step 5: Confirm

Show the updated focus:
- Which step is now focused
- Step position (e.g., "step 2/5")
- The step description

Tell the user that this step will appear in their session context going forward.
