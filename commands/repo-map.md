# Regenerate Repository Map

Regenerate the repo map for this project to understand the code structure, find similar classes/functions, and identify documentation gaps.

Run this command:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/generate-repo-map.py
```

After running, review the output for:
- **Similar classes**: May indicate overlapping responsibilities or duplicate implementations
- **Similar functions**: May be candidates for consolidation
- **Undocumented code**: Opportunities to improve codebase understanding

The repo map is saved to `.claude/repo-map.md` for future reference.
