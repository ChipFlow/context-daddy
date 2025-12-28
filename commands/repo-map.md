# Regenerate Repository Map

Regenerate the repo map for this project to understand the code structure, find similar classes/functions, and identify documentation gaps.

Run this command to regenerate with progress display:

```bash
# Start regeneration in background (clears old cache first)
rm -f .claude/repo-map-cache.json .claude/repo-map.md
nohup uv run ${CLAUDE_PLUGIN_ROOT}/scripts/generate-repo-map.py > .claude/repo-map-build.log 2>&1 &

# Show progress until complete
echo "Regenerating repo map..."
while true; do
    if [[ -f .claude/repo-map-progress.json ]]; then
        PROGRESS=$(python3 -c "
import json
try:
    with open('.claude/repo-map-progress.json') as f:
        p = json.load(f)
    status = p.get('status', 'unknown')
    if status == 'complete':
        print(f\"Complete: {p.get('symbols_found', 0)} symbols found\")
    elif status == 'indexing':
        total = p.get('files_total', 0)
        done = p.get('files_cached', 0) + p.get('files_parsed', 0)
        pct = (done / total * 100) if total > 0 else 0
        print(f\"Indexing: {pct:.0f}% ({done}/{total} files)\")
    else:
        print(f\"Status: {status}\")
except Exception as e:
    print(f'Starting...')
" 2>/dev/null)
        echo -ne "\r\033[K${PROGRESS}"
        if [[ "${PROGRESS}" == Complete* ]]; then
            echo ""
            break
        fi
    fi
    sleep 1
done

# Show summary
if [[ -f .claude/repo-map.md ]]; then
    CLASSES=$(grep -c "^## ⚠️ Potentially Similar Classes" .claude/repo-map.md 2>/dev/null && grep -A1000 "^## ⚠️ Potentially Similar Classes" .claude/repo-map.md | grep -c "^\*\*" || echo "0")
    FUNCS=$(grep -c "^## ⚠️ Potentially Similar Functions" .claude/repo-map.md 2>/dev/null && grep -A1000 "^## ⚠️ Potentially Similar Functions" .claude/repo-map.md | grep -c "^\*\*" || echo "0")
    echo "Repo map saved to .claude/repo-map.md"
fi
```

After running, review the output for:
- **Similar classes**: May indicate overlapping responsibilities or duplicate implementations (same-language only)
- **Similar functions**: May be candidates for consolidation (same-language only)
- **Undocumented code**: Opportunities to improve codebase understanding

Note: Cross-language similarities (e.g., Python and Rust) are not flagged as they're typically intentional (bindings, ports).
