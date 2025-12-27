# Context Tools for Claude Code

A Claude Code plugin that helps Claude maintain context awareness in large codebases through automatic project mapping, duplicate detection, and learning retention.

## Features

### Project Manifest
Automatically detects and tracks:
- Programming languages in your project
- Build system and commands (npm, uv, pdm, cargo, cmake, meson, go)
- Entry points and main scripts
- Git activity summary

### Repository Map with Duplicate Detection
Generates a comprehensive map of your codebase:
- Extracts all classes, functions, and methods with their signatures
- Detects potentially similar classes that may have overlapping responsibilities
- Identifies similar functions that could be candidates for consolidation
- Analyzes documentation coverage to highlight gaps

### Learnings System
Helps Claude remember important discoveries:
- Project-specific learnings in `.claude/learnings.md`
- Global learnings in `~/.claude/learnings.md`
- Prompted to save learnings before context compaction

## Installation

### Option 1: Install from GitHub (recommended)

```bash
claude plugins add chipflow/claude-context-tools
```

### Option 2: Install from local directory

```bash
git clone https://github.com/chipflow/claude-context-tools.git
claude plugins add ./claude-context-tools
```

## Requirements

- [uv](https://docs.astral.sh/uv/) - Python package manager (for running scripts)
- Python 3.10+

## How It Works

### Hooks

The plugin registers two hooks:

1. **SessionStart**: When you start a Claude Code session, the plugin:
   - Generates/refreshes the project manifest
   - Displays a summary of project context
   - Shows count of available learnings

2. **PreCompact**: Before context compaction, the plugin:
   - Regenerates the project manifest
   - Updates the repository map
   - Reminds you to save important discoveries

### Slash Commands

- `/context-tools:repo-map` - Regenerate the repository map
- `/context-tools:manifest` - Regenerate the project manifest
- `/context-tools:learnings` - View and manage project learnings

## Generated Files

The plugin creates files in your project's `.claude/` directory:

```
.claude/
├── project-manifest.json   # Build system, languages, entry points
├── repo-map.md             # Code structure with similarity analysis
└── learnings.md            # Project-specific learnings
```

## Example Output

### Repository Map

```markdown
## Documentation Coverage

- **Classes**: 15/18 (83% documented)
- **Functions**: 42/50 (84% documented)

## ⚠️ Potentially Similar Classes

- **ConfigLoader** (src/config/loader.py)
  ↔ **SettingsLoader** (src/settings/loader.py)
  Reason: similar names (80%), similar docstrings (72%)

## Code Structure

### src/models/user.py

**class User**
  A user account in the system.
  - create(name: str, email: str) -> User
      Create a new user account.
  - update(self, **kwargs)
      Update user attributes.
```

### Project Manifest

```json
{
  "project_name": "my-project",
  "languages": ["python", "typescript"],
  "build_system": {
    "type": "uv",
    "commands": {
      "install": "uv sync",
      "build": "uv run build",
      "test": "uv run pytest"
    }
  },
  "entry_points": ["src/main.py", "src/cli.py"]
}
```

## Best Practices

### Recording Learnings

When you discover something important during a session, ask Claude to record it:

> "Add a learning about the database connection pooling optimization we just discovered"

Claude will add an entry to `.claude/learnings.md`:

```markdown
## Database: Connection pooling optimization

**Context**: High-traffic API endpoints with PostgreSQL
**Discovery**: Default pool size of 5 was causing connection exhaustion
**Solution/Pattern**: Increase pool size to 20, add 30s timeout, implement retry with exponential backoff
```

### Addressing Duplicate Detection

When the repo map shows similar classes or functions:
1. Review the flagged pairs to determine if they're truly duplicates
2. If they serve different purposes, improve their docstrings to clarify intent
3. If they're duplicates, consolidate them into a single implementation

## License

MIT
