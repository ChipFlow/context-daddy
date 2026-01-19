# Generate README from Narrative

Generate or update the project README based on the narrative document.

## Prerequisites

You need a narrative first. If `.claude/narrative.md` doesn't exist:

```bash
/context-daddy:story
```

## Generating README

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/readme.py
```

This creates a README with:
- **What/Why** - Quick pitch from narrative summary
- **Quick Start** - Minimal install/run commands
- **Features** - From narrative
- **How It Works** - Architecture in plain language
- **The Journey** - Story from narrative (no version numbers)
- **Dragons & Open Questions** - Warnings and uncertainties

## Updating Existing README

To update while preserving project-specific content:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/readme.py --update
```

## Dry Run

Preview without saving:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/readme.py --dry-run
```

## Structure

The generated README follows this order:

1. **What/Why/Quick Start** - People want to use it first
2. **Features/Commands/How It Works** - Reference material
3. **--- (separator)** - Backstory below
4. **Journey/Dragons/Questions** - For the curious

This structure prioritizes action over story while still capturing the narrative.
