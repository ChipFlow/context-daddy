---
description: Manage cross-session goals - list, show, switch, archive
allowed-tools: [mcp__plugin_context-daddy_goals__goal_list, mcp__plugin_context-daddy_goals__goal_show, mcp__plugin_context-daddy_goals__goal_switch, mcp__plugin_context-daddy_goals__goal_unset, mcp__plugin_context-daddy_goals__goal_archive]
---

# Goal Management

Manage cross-session goals that persist across sessions and projects.

## IMPORTANT: This is an executable skill

When invoked, execute the steps below. Don't just explain - DO it.

## Step 1: Show Current State

Use the `goal_list` MCP tool to see goals for the current project:

```
goal_list()
```

And show the current goal details:

```
goal_show()
```

If no current goal is set, note that and continue to Step 2.

## Step 2: Offer Actions

Based on the output, offer the user these options:

- **Switch goal**: If multiple goals exist, ask which to activate
  - Use the `goal_switch` MCP tool with the goal's UUID or slug

- **Show all goals** (including other projects):
  - Use `goal_list(all=true)`

- **Create new goal**: Point them to `/context-daddy:goal-new`

- **Focus on a step**: Point them to `/context-daddy:goal-focus`

- **Complete current step**: Point them to `/context-daddy:goal-done`

- **Archive a goal** (mark as finished/abandoned):
  - Use `goal_archive(id="<goal-id>")`

- **Unset current goal** (stop tracking without archiving):
  - Use `goal_unset()`

- **Reorder plan steps**: To move steps around:
  1. Use `goal_show()` to see current plan
  2. Read the goal file directly (path shown in output, e.g. `~/.claude/goals/<id>.md`)
  3. Rearrange the `- [ ] [step-id] Description` lines in the `## Plan` section
  4. Write the file back. Steps are identified by `[step-id]`, not position, so reordering is safe.
  5. Use `goal_focus(step="<step-id>")` to set the current step if needed

- **Remove a plan step**: Edit the goal file directly and delete the line

## Step 3: Execute User Choice

Run the appropriate MCP tool based on the user's selection.

After any change, show the updated state using `goal_show()`.
