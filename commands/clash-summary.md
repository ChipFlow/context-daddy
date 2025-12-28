# Clash Summary

Show a summary of potential naming clashes detected in the codebase.

```bash
python3 << 'PYSCRIPT'
import re
from pathlib import Path

repo_map = Path(".claude/repo-map.md")
if not repo_map.exists():
    print("No repo map found. Run /repo-map first.")
    exit(0)

content = repo_map.read_text()

# Parse similar classes
class_section = re.search(r'## ⚠️ Potentially Similar Classes\n\n.*?\n\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
similar_classes = []
if class_section:
    for match in re.finditer(r'\*\*([^*]+)\*\* \(([^)]+)\) ↔ \*\*([^*]+)\*\* \(([^)]+)\): (.+)', class_section.group(1)):
        similar_classes.append({
            'name1': match.group(1), 'loc1': match.group(2),
            'name2': match.group(3), 'loc2': match.group(4),
            'reason': match.group(5)
        })

# Parse similar functions
func_section = re.search(r'## ⚠️ Potentially Similar Functions\n\n.*?\n\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
similar_functions = []
if func_section:
    for match in re.finditer(r'\*\*([^*]+)\*\* \(([^)]+)\) ↔ \*\*([^*]+)\*\* \(([^)]+)\): (.+)', func_section.group(1)):
        similar_functions.append({
            'name1': match.group(1), 'loc1': match.group(2),
            'name2': match.group(3), 'loc2': match.group(4),
            'reason': match.group(5)
        })

total = len(similar_classes) + len(similar_functions)
if total == 0:
    print("✅ No naming clashes detected in this codebase.")
    exit(0)

print(f"⚠️  {total} potential naming clash(es) detected\n")

if similar_classes:
    print(f"📦 Similar Classes: {len(similar_classes)}")
    # Group by directory
    by_dir = {}
    for c in similar_classes:
        dir1 = str(Path(c['loc1'].split(':')[0]).parent)
        dir2 = str(Path(c['loc2'].split(':')[0]).parent)
        key = tuple(sorted([dir1, dir2]))
        by_dir.setdefault(key, []).append(c)

    for dirs, clashes in sorted(by_dir.items(), key=lambda x: -len(x[1]))[:5]:
        print(f"   {dirs[0]} ↔ {dirs[1]}: {len(clashes)} clash(es)")
    if len(by_dir) > 5:
        print(f"   ... and {len(by_dir) - 5} more directory pairs")
    print()

if similar_functions:
    print(f"🔧 Similar Functions: {len(similar_functions)}")
    # Group by directory
    by_dir = {}
    for f in similar_functions:
        dir1 = str(Path(f['loc1'].split(':')[0]).parent)
        dir2 = str(Path(f['loc2'].split(':')[0]).parent)
        key = tuple(sorted([dir1, dir2]))
        by_dir.setdefault(key, []).append(f)

    for dirs, clashes in sorted(by_dir.items(), key=lambda x: -len(x[1]))[:5]:
        print(f"   {dirs[0]} ↔ {dirs[1]}: {len(clashes)} clash(es)")
    if len(by_dir) > 5:
        print(f"   ... and {len(by_dir) - 5} more directory pairs")
    print()

print("Use /resolve-clashes to review and resolve these interactively.")
PYSCRIPT
```

This shows:
- Total clash count
- Breakdown by classes vs functions
- Top directories with clashes
- Pointer to `/resolve-clashes` for resolution
