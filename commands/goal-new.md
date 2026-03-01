---
description: Create a new cross-session goal with guided setup
allowed-tools: [mcp__plugin_context-daddy_goals__goal_create, mcp__plugin_context-daddy_goals__goal_add_step, mcp__plugin_context-daddy_goals__goal_link_project, mcp__plugin_context-daddy_goals__goal_show]
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

Use the `goal_create` MCP tool:

```
goal_create(title="TITLE", objective="OBJECTIVE")
```

Note the goal ID and slug from the response.

## Step 3: Add Plan Steps

Ask the user for their plan steps. If they have a rough plan, help refine it into discrete, checkable steps.

For each step, use the `goal_add_step` MCP tool:

```
goal_add_step(id="<goal-id>", description="Step description")
```

The first step created replaces the default "Define plan steps" placeholder.

You can specify a custom step ID with `step_id` or insert at a position with `after`:

```
goal_add_step(id="<goal-id>", description="Step description", step_id="custom-id", after="previous-step-id")
```

## Step 4: Link Related Projects (Optional)

If the goal spans multiple projects, ask which other projects are involved:

```
goal_link_project(id="<goal-id>", path="/path/to/other-project", role="dependency")
```

## Step 5: Confirm

Show the final goal using `goal_show(id="<goal-id>")`.

Tell the user:
- The goal is now active and will appear in future sessions
- Use `/context-daddy:goal-focus` to set which step to work on
- Use `/context-daddy:goal-done` to mark steps complete
- Use `/context-daddy:goal` to manage goals
