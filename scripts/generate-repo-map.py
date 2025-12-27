#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Generate a repo map showing functions, classes, and their documentation.
Helps Claude Code understand what already exists before implementing new features.

Usage:
    uv run generate-repo-map.py [directory]
"""

import ast
import sys
from pathlib import Path
from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import defaultdict


@dataclass
class Symbol:
    """A code symbol (function, class, method)."""
    name: str
    kind: str  # "function", "class", "method"
    signature: str
    docstring: str | None
    file_path: str
    line_number: int
    parent: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.parent}.{self.name}" if self.parent else self.name

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.line_number}"


def get_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract function signature including arguments and return type."""
    args = []
    for arg in node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {ast.unparse(arg.annotation)}"
        args.append(arg_str)

    if node.args.vararg:
        arg_str = f"*{node.args.vararg.arg}"
        if node.args.vararg.annotation:
            arg_str += f": {ast.unparse(node.args.vararg.annotation)}"
        args.append(arg_str)

    if node.args.kwarg:
        arg_str = f"**{node.args.kwarg.arg}"
        if node.args.kwarg.annotation:
            arg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
        args.append(arg_str)

    sig = f"{node.name}({', '.join(args)})"
    if node.returns:
        sig += f" -> {ast.unparse(node.returns)}"
    return sig


def get_first_line_of_docstring(docstring: str | None) -> str | None:
    """Get just the first line of a docstring for the summary."""
    if not docstring:
        return None
    first_line = docstring.strip().split('\n')[0].strip()
    return first_line[:97] + "..." if len(first_line) > 100 else first_line


def extract_symbols_from_python(file_path: Path, relative_to: Path) -> list[Symbol]:
    """Extract all functions and classes from a Python file."""
    symbols = []

    try:
        source = file_path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    rel_path = str(file_path.relative_to(relative_to))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(Symbol(
                name=node.name,
                kind="class",
                signature=node.name,
                docstring=get_first_line_of_docstring(ast.get_docstring(node)),
                file_path=rel_path,
                line_number=node.lineno,
            ))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(Symbol(
                        name=item.name,
                        kind="method",
                        signature=get_function_signature(item),
                        docstring=get_first_line_of_docstring(ast.get_docstring(item)),
                        file_path=rel_path,
                        line_number=item.lineno,
                        parent=node.name,
                    ))

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(Symbol(
                name=node.name,
                kind="function",
                signature=get_function_signature(node),
                docstring=get_first_line_of_docstring(ast.get_docstring(node)),
                file_path=rel_path,
                line_number=node.lineno,
            ))

    return symbols


def similarity(a: str, b: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower().replace('_', ''), b.lower().replace('_', '')).ratio()


def find_similar_classes(symbols: list[Symbol], name_threshold: float = 0.75, doc_threshold: float = 0.65) -> list[tuple[Symbol, Symbol, str]]:
    """Find classes with similar names or docstrings."""
    similar = []
    classes = [s for s in symbols if s.kind == "class" and not s.name.startswith("Test")]
    compared = set()

    for i, cls1 in enumerate(classes):
        for cls2 in classes[i+1:]:
            if cls1.file_path == cls2.file_path:
                continue
            pair_key = tuple(sorted([cls1.location, cls2.location]))
            if pair_key in compared:
                continue
            compared.add(pair_key)

            reasons = []
            name_sim = similarity(cls1.name, cls2.name)
            if name_sim >= name_threshold:
                reasons.append(f"similar names ({name_sim:.0%})")

            if cls1.docstring and cls2.docstring and len(cls1.docstring) >= 30 and len(cls2.docstring) >= 30:
                doc_sim = similarity(cls1.docstring, cls2.docstring)
                if doc_sim >= doc_threshold:
                    reasons.append(f"similar docstrings ({doc_sim:.0%})")

            if reasons:
                similar.append((cls1, cls2, ", ".join(reasons)))

    return similar


def find_similar_functions(symbols: list[Symbol], name_threshold: float = 0.75, doc_threshold: float = 0.65) -> list[tuple[Symbol, Symbol, str]]:
    """Find top-level functions with similar names or docstrings."""
    similar = []
    functions = [s for s in symbols if s.kind == "function" and not s.name.startswith('_') and not s.name.startswith('test_')]
    compared = set()

    for i, fn1 in enumerate(functions):
        for fn2 in functions[i+1:]:
            if fn1.file_path == fn2.file_path:
                continue
            pair_key = tuple(sorted([fn1.location, fn2.location]))
            if pair_key in compared:
                continue
            compared.add(pair_key)

            reasons = []
            name_sim = similarity(fn1.name, fn2.name)
            if name_sim >= name_threshold:
                reasons.append(f"similar names ({name_sim:.0%})")

            if fn1.docstring and fn2.docstring and len(fn1.docstring) >= 20 and len(fn2.docstring) >= 20:
                doc_sim = similarity(fn1.docstring, fn2.docstring)
                if doc_sim >= doc_threshold:
                    reasons.append(f"similar docstrings ({doc_sim:.0%})")

            if reasons:
                similar.append((fn1, fn2, ", ".join(reasons)))

    return similar


def analyze_documentation_coverage(symbols: list[Symbol]) -> dict:
    """Analyze docstring coverage and identify documentation gaps."""
    stats = {
        "classes": {"total": 0, "documented": 0, "undocumented": []},
        "functions": {"total": 0, "documented": 0, "undocumented": []},
        "methods": {"total": 0, "documented": 0, "undocumented": []},
    }

    for sym in symbols:
        if sym.kind == "class":
            stats["classes"]["total"] += 1
            if sym.docstring:
                stats["classes"]["documented"] += 1
            else:
                stats["classes"]["undocumented"].append(sym)
        elif sym.kind == "function" and not sym.name.startswith('_'):
            stats["functions"]["total"] += 1
            if sym.docstring:
                stats["functions"]["documented"] += 1
            else:
                stats["functions"]["undocumented"].append(sym)
        elif sym.kind == "method" and not sym.name.startswith('_'):
            stats["methods"]["total"] += 1
            if sym.docstring:
                stats["methods"]["documented"] += 1
            else:
                stats["methods"]["undocumented"].append(sym)

    return stats


def format_repo_map(symbols: list[Symbol], similar_classes: list, similar_functions: list, doc_coverage: dict, root: Path) -> str:
    """Format symbols as a hierarchical repo map with analysis."""
    output = [
        "# Repository Map", "",
        f"Generated from: {root}",
        f"Total symbols: {len(symbols)}", "",
        "## Documentation Coverage", ""
    ]

    for kind in ["classes", "functions", "methods"]:
        stats = doc_coverage[kind]
        if stats["total"] > 0:
            pct = stats["documented"] / stats["total"] * 100
            output.append(f"- **{kind.title()}**: {stats['documented']}/{stats['total']} ({pct:.0f}% documented)")
    output.append("")

    if similar_classes:
        output.extend(["## ⚠️ Potentially Similar Classes", "", "These classes may have overlapping responsibilities:", ""])
        for cls1, cls2, reason in similar_classes:
            output.extend([
                f"- **{cls1.name}** ({cls1.file_path})",
                f"  ↔ **{cls2.name}** ({cls2.file_path})",
                f"  Reason: {reason}",
            ])
            if cls1.docstring:
                output.append(f"  Doc 1: {cls1.docstring}")
            if cls2.docstring:
                output.append(f"  Doc 2: {cls2.docstring}")
            output.append("")

    if similar_functions:
        output.extend(["## ⚠️ Potentially Similar Functions", "", "These functions may be duplicates:", ""])
        for fn1, fn2, reason in similar_functions:
            output.extend([
                f"- **{fn1.name}** ({fn1.file_path}:{fn1.line_number})",
                f"  ↔ **{fn2.name}** ({fn2.file_path}:{fn2.line_number})",
                f"  Reason: {reason}",
            ])
            if fn1.docstring:
                output.append(f"  Doc 1: {fn1.docstring}")
            if fn2.docstring:
                output.append(f"  Doc 2: {fn2.docstring}")
            output.append("")

    undoc_classes = doc_coverage["classes"]["undocumented"]
    undoc_functions = doc_coverage["functions"]["undocumented"]
    if undoc_classes or undoc_functions:
        output.extend(["## 📝 Documentation Opportunities", "", "Adding docstrings helps both humans and AI understand your code:", ""])
        if undoc_classes:
            output.append("**Undocumented classes:**")
            for sym in undoc_classes[:10]:
                output.append(f"- {sym.name} ({sym.file_path}:{sym.line_number})")
            if len(undoc_classes) > 10:
                output.append(f"- ... and {len(undoc_classes) - 10} more")
            output.append("")
        if undoc_functions:
            output.append("**Undocumented functions:**")
            for sym in undoc_functions[:10]:
                output.append(f"- {sym.name} ({sym.file_path}:{sym.line_number})")
            if len(undoc_functions) > 10:
                output.append(f"- ... and {len(undoc_functions) - 10} more")
            output.append("")

    output.extend(["## Code Structure", ""])

    by_file: dict[str, list[Symbol]] = defaultdict(list)
    for sym in symbols:
        by_file[sym.file_path].append(sym)

    for file_path in sorted(by_file.keys()):
        file_symbols = by_file[file_path]
        output.extend([f"### {file_path}", ""])

        for cls in sorted([s for s in file_symbols if s.kind == "class"], key=lambda s: s.line_number):
            doc_marker = "" if cls.docstring else " ❌"
            output.append(f"**class {cls.signature}**{doc_marker}")
            if cls.docstring:
                output.append(f"  {cls.docstring}")
            for method in sorted([s for s in file_symbols if s.kind == "method" and s.parent == cls.name], key=lambda s: s.line_number):
                if method.name.startswith('_'):
                    continue
                doc_marker = "" if method.docstring else " ❌"
                output.append(f"  - {method.signature}{doc_marker}")
                if method.docstring:
                    output.append(f"      {method.docstring}")
            output.append("")

        for func in sorted([s for s in file_symbols if s.kind == "function"], key=lambda s: s.line_number):
            if func.name.startswith('_'):
                continue
            doc_marker = "" if func.docstring else " ❌"
            output.append(f"**{func.signature}**{doc_marker}")
            if func.docstring:
                output.append(f"  {func.docstring}")
            output.append("")

    return "\n".join(output)


def find_python_files(root: Path) -> list[Path]:
    """Find all Python files, excluding common non-source directories."""
    exclude_dirs = {"node_modules", ".git", "__pycache__", "venv", ".venv", "target", "build", "dist", ".next", ".cache", "vendor", ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages", "eggs", ".eggs"}
    return sorted([p for p in root.rglob("*.py") if not any(ex in p.parts for ex in exclude_dirs)])


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()

    python_files = find_python_files(root)
    if not python_files:
        print(f"No Python files found in {root}")
        return

    all_symbols = []
    for file_path in python_files:
        all_symbols.extend(extract_symbols_from_python(file_path, root))

    similar_classes = find_similar_classes(all_symbols)
    similar_functions = find_similar_functions(all_symbols)
    doc_coverage = analyze_documentation_coverage(all_symbols)

    repo_map = format_repo_map(all_symbols, similar_classes, similar_functions, doc_coverage, root)

    claude_dir = root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "repo-map.md").write_text(repo_map)

    print(repo_map)
    print("\n---")
    print(f"Repo map saved to: {claude_dir / 'repo-map.md'}")
    print(f"Files scanned: {len(python_files)}")
    print(f"Symbols found: {len(all_symbols)}")
    if similar_classes:
        print(f"Similar classes found: {len(similar_classes)}")
    if similar_functions:
        print(f"Similar functions found: {len(similar_functions)}")

    for kind in ["classes", "functions", "methods"]:
        stats = doc_coverage[kind]
        if stats["total"] > 0:
            print(f"{kind.title()} documented: {stats['documented']}/{stats['total']} ({stats['documented']/stats['total']*100:.0f}%)")


if __name__ == "__main__":
    main()
