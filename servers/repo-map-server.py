#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
#     "tree-sitter>=0.23.0",
#     "tree-sitter-cpp>=0.23.0",
#     "tree-sitter-rust>=0.23.0",
# ]
# ///
"""
MCP server for querying repo-map symbol data.
Handles indexing internally - no subprocess spawning.

Exposes tools to search symbols by name/pattern, get file symbols, and trigger reindex.
"""

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import parsing functions - add scripts dir to path
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

# Lazy import to avoid loading tree-sitter until needed
_indexer_module = None


def get_indexer():
    """Lazy-load the indexer module to defer tree-sitter initialization."""
    global _indexer_module
    if _indexer_module is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_repo_map",
            SCRIPT_DIR / "generate-repo-map.py"
        )
        _indexer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_indexer_module)
    return _indexer_module


# Configuration
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
CLAUDE_DIR = PROJECT_ROOT / ".claude"
DB_PATH = CLAUDE_DIR / "repo-map.db"
CACHE_PATH = CLAUDE_DIR / "repo-map-cache.json"
STALENESS_CHECK_INTERVAL = 60  # seconds between automatic staleness checks

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Server("context-tools-repo-map")

# Indexing state
_indexing_lock = threading.Lock()
_is_indexing = False
_last_index_time = 0
_index_error: str | None = None


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Repo map database not found at {DB_PATH}. Use reindex_repo_map tool.")
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary."""
    return {key: row[key] for key in row.keys()}


def is_stale() -> tuple[bool, str]:
    """
    Check if the repo map needs reindexing.
    Returns (is_stale, reason).
    """
    indexer = get_indexer()

    # No DB yet
    if not DB_PATH.exists():
        return True, "database does not exist"

    # No cache file
    if not CACHE_PATH.exists():
        return True, "cache file missing"

    # Check cache version
    try:
        cache_data = json.loads(CACHE_PATH.read_text())
        if cache_data.get("version") != indexer.CACHE_VERSION:
            return True, f"cache version mismatch"
    except (json.JSONDecodeError, IOError):
        return True, "cache file corrupt"

    # Count files in cache vs current
    cached_count = len(cache_data.get("files", {}))

    # Quick file count check
    current_files = []
    for ext in [".py", ".rs", ".cpp", ".cc", ".cxx", ".hpp", ".h", ".hxx"]:
        current_files.extend(indexer.find_files(PROJECT_ROOT, {ext}))
    current_count = len(current_files)

    if current_count != cached_count:
        return True, f"file count changed ({cached_count} cached, {current_count} found)"

    # Check if any file is newer than DB
    db_mtime = DB_PATH.stat().st_mtime
    for f in current_files[:100]:  # Sample check for speed
        if f.stat().st_mtime > db_mtime:
            return True, "files modified since last index"

    return False, "up to date"


def do_index() -> tuple[bool, str]:
    """
    Perform indexing synchronously.
    Returns (success, message).
    """
    global _is_indexing, _last_index_time, _index_error

    with _indexing_lock:
        if _is_indexing:
            return False, "indexing already in progress"
        _is_indexing = True
        _index_error = None

    try:
        logger.info(f"Starting index of {PROJECT_ROOT}")
        indexer = get_indexer()

        # Ensure .claude directory exists
        CLAUDE_DIR.mkdir(exist_ok=True)

        # Find all source files
        python_files = indexer.find_python_files(PROJECT_ROOT)
        cpp_files = indexer.find_cpp_files(PROJECT_ROOT)
        rust_files = indexer.find_rust_files(PROJECT_ROOT)

        total_files = len(python_files) + len(cpp_files) + len(rust_files)
        if total_files == 0:
            with _indexing_lock:
                _is_indexing = False
            return False, f"no source files found in {PROJECT_ROOT}"

        # Load symbol cache
        cache = indexer.SymbolCache(CACHE_PATH)

        all_symbols = []
        all_rel_paths = set()

        # Process each language
        for file_path in python_files:
            rel_path = str(file_path.relative_to(PROJECT_ROOT))
            all_rel_paths.add(rel_path)
            symbols, was_cached = cache.get_symbols(file_path, rel_path)
            if was_cached:
                all_symbols.extend(symbols)
            else:
                symbols = indexer.extract_symbols_from_python(file_path, PROJECT_ROOT)
                all_symbols.extend(symbols)
                try:
                    mtime = file_path.stat().st_mtime
                    content_hash = indexer.compute_file_hash(file_path)
                    cache.update(rel_path, mtime, content_hash, symbols)
                except IOError:
                    pass

        for file_path in cpp_files:
            rel_path = str(file_path.relative_to(PROJECT_ROOT))
            all_rel_paths.add(rel_path)
            symbols, was_cached = cache.get_symbols(file_path, rel_path)
            if was_cached:
                all_symbols.extend(symbols)
            else:
                symbols = indexer.extract_symbols_from_cpp(file_path, PROJECT_ROOT)
                all_symbols.extend(symbols)
                try:
                    mtime = file_path.stat().st_mtime
                    content_hash = indexer.compute_file_hash(file_path)
                    cache.update(rel_path, mtime, content_hash, symbols)
                except IOError:
                    pass

        for file_path in rust_files:
            rel_path = str(file_path.relative_to(PROJECT_ROOT))
            all_rel_paths.add(rel_path)
            symbols, was_cached = cache.get_symbols(file_path, rel_path)
            if was_cached:
                all_symbols.extend(symbols)
            else:
                symbols = indexer.extract_symbols_from_rust(file_path, PROJECT_ROOT)
                all_symbols.extend(symbols)
                try:
                    mtime = file_path.stat().st_mtime
                    content_hash = indexer.compute_file_hash(file_path)
                    cache.update(rel_path, mtime, content_hash, symbols)
                except IOError:
                    pass

        # Remove stale entries and save cache
        cache.remove_stale(all_rel_paths)
        cache.save()

        # Write to SQLite
        indexer.write_symbols_to_sqlite(all_symbols, DB_PATH)

        # Also generate the markdown file for reference
        similar_classes = indexer.find_similar_classes(all_symbols)
        similar_functions = indexer.find_similar_functions(all_symbols)
        doc_coverage = indexer.analyze_documentation_coverage(all_symbols)
        repo_map = indexer.format_repo_map(all_symbols, similar_classes, similar_functions, doc_coverage, PROJECT_ROOT)

        md_path = CLAUDE_DIR / "repo-map.md"
        tmp_path = md_path.with_suffix(".md.tmp")
        tmp_path.write_text(repo_map)
        tmp_path.rename(md_path)

        _last_index_time = time.time()
        logger.info(f"Indexed {len(all_symbols)} symbols from {total_files} files")

        with _indexing_lock:
            _is_indexing = False

        return True, f"indexed {len(all_symbols)} symbols from {total_files} files"

    except Exception as e:
        logger.exception("Indexing failed")
        with _indexing_lock:
            _is_indexing = False
            _index_error = str(e)
        return False, f"indexing failed: {e}"


def index_in_background():
    """Start indexing in a background thread."""
    thread = threading.Thread(target=do_index, daemon=True)
    thread.start()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="search_symbols",
            description="Search for symbols (functions, classes, methods) by name pattern. Supports glob patterns like 'get_*' or '*Config*'. FASTER than Grep/Search for symbol lookups - uses pre-built SQLite index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Name pattern to search for. Supports glob wildcards (* and ?). Examples: 'get_*', '*Handler', 'parse_*_file'"
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["class", "function", "method"],
                        "description": "Optional: Filter by symbol type"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results to return (default: 20)"
                    }
                },
                "required": ["pattern"]
            }
        ),
        Tool(
            name="get_file_symbols",
            description="Get all symbols defined in a specific file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Relative file path from project root. Example: 'src/models/user.py'"
                    }
                },
                "required": ["file"]
            }
        ),
        Tool(
            name="get_symbol_content",
            description="Get the source code content of a symbol by exact name. FASTER than Grep/Search+Read - directly retrieves function/class/method source code from pre-indexed line ranges.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Exact symbol name to look up. Example: 'MyClass', 'process_data', 'User.save'"
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["class", "function", "method"],
                        "description": "Optional: Filter by symbol type if name is ambiguous"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="reindex_repo_map",
            description="Trigger a reindex of the repository symbols. Use when files have changed or index seems stale.",
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {
                        "type": "boolean",
                        "default": False,
                        "description": "Force reindex even if cache seems fresh"
                    }
                }
            }
        ),
        Tool(
            name="repo_map_status",
            description="Get the current status of the repo map index.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    try:
        if name == "search_symbols":
            result = search_symbols(
                pattern=arguments["pattern"],
                kind=arguments.get("kind"),
                limit=arguments.get("limit", 20)
            )
        elif name == "get_file_symbols":
            result = get_file_symbols(file=arguments["file"])
        elif name == "get_symbol_content":
            result = get_symbol_content(
                name=arguments["name"],
                kind=arguments.get("kind")
            )
        elif name == "reindex_repo_map":
            result = reindex_repo_map(force=arguments.get("force", False))
        elif name == "repo_map_status":
            result = repo_map_status()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except FileNotFoundError as e:
        # DB doesn't exist - trigger indexing
        stale, reason = is_stale()
        if stale and not _is_indexing:
            index_in_background()
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "status": "indexing started in background" if not _is_indexing else "indexing in progress"
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": f"Tool error: {e}"}))]


def search_symbols(pattern: str, kind: str | None = None, limit: int = 20) -> list[dict]:
    """Search for symbols by name pattern."""
    conn = get_db()
    try:
        # Convert glob pattern to SQL LIKE pattern
        sql_pattern = pattern.replace("*", "%").replace("?", "_")

        query = "SELECT * FROM symbols WHERE name LIKE ?"
        params: list = [sql_pattern]

        if kind:
            query += " AND kind = ?"
            params.append(kind)

        query += " ORDER BY name LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        # If SQL LIKE didn't match well, fall back to fnmatch for proper glob
        results = []
        for row in rows:
            if fnmatch.fnmatch(row["name"], pattern):
                results.append(row_to_dict(row))

        # If no results with strict fnmatch, return SQL results
        if not results:
            results = [row_to_dict(row) for row in rows]

        return results[:limit]
    finally:
        conn.close()


def get_file_symbols(file: str) -> list[dict]:
    """Get all symbols in a specific file."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_number",
            [file]
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_symbol_content(name: str, kind: str | None = None) -> dict:
    """Get the source code content of a symbol by exact name."""
    conn = get_db()
    try:
        # Handle Parent.method format
        if "." in name:
            parent, method_name = name.rsplit(".", 1)
            query = "SELECT * FROM symbols WHERE name = ? AND parent = ?"
            params: list = [method_name, parent]
        else:
            query = "SELECT * FROM symbols WHERE name = ?"
            params = [name]

        if kind:
            query += " AND kind = ?"
            params.append(kind)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            return {"error": f"Symbol '{name}' not found"}

        # If multiple matches, return info about all of them
        if len(rows) > 1 and kind is None:
            matches = [row_to_dict(row) for row in rows]
            return {
                "error": f"Multiple symbols named '{name}' found. Specify 'kind' to disambiguate.",
                "matches": matches
            }

        row = rows[0]
        symbol_info = row_to_dict(row)
        file_path = PROJECT_ROOT / row["file_path"]

        if not file_path.exists():
            return {"error": f"File not found: {row['file_path']}", "symbol": symbol_info}

        # Read file content
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (IOError, UnicodeDecodeError) as e:
            return {"error": f"Could not read file: {e}", "symbol": symbol_info}

        start_line = row["line_number"]
        end_line = row["end_line_number"]

        if end_line is None:
            # Fallback: return just the start line and a few following lines
            end_line = min(start_line + 20, len(lines))

        # Extract content (convert to 0-indexed)
        content_lines = lines[start_line - 1:end_line]
        content = "\n".join(content_lines)

        return {
            "symbol": symbol_info,
            "content": content,
            "location": f"{row['file_path']}:{start_line}-{end_line}"
        }
    finally:
        conn.close()


def reindex_repo_map(force: bool = False) -> dict:
    """Trigger a reindex of the repository."""
    global _is_indexing

    if _is_indexing:
        return {"status": "indexing already in progress"}

    if not force:
        stale, reason = is_stale()
        if not stale:
            return {"status": "index is fresh", "reason": reason}

    # Do indexing in background
    index_in_background()
    return {"status": "indexing started in background"}


def repo_map_status() -> dict:
    """Get current index status."""
    status = {
        "project_root": str(PROJECT_ROOT),
        "database_exists": DB_PATH.exists(),
        "is_indexing": _is_indexing,
    }

    if _index_error:
        status["last_error"] = _index_error

    if _last_index_time > 0:
        status["last_index_time"] = _last_index_time
        status["last_index_ago_seconds"] = int(time.time() - _last_index_time)

    if DB_PATH.exists():
        try:
            conn = get_db()
            cursor = conn.execute("SELECT COUNT(*) FROM symbols")
            status["symbol_count"] = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            status["db_error"] = str(e)

    stale, reason = is_stale()
    status["is_stale"] = stale
    status["staleness_reason"] = reason

    return status


async def periodic_staleness_check():
    """Periodically check if reindexing is needed."""
    while True:
        await asyncio.sleep(STALENESS_CHECK_INTERVAL)
        try:
            if not _is_indexing:
                stale, reason = is_stale()
                if stale:
                    logger.info(f"Index is stale ({reason}), starting background reindex")
                    index_in_background()
        except Exception as e:
            logger.warning(f"Staleness check failed: {e}")


async def main():
    """Run the MCP server."""
    # Check if indexing needed on startup
    try:
        stale, reason = is_stale()
        if stale:
            logger.info(f"Index is stale on startup ({reason}), starting background reindex")
            index_in_background()
    except Exception as e:
        logger.warning(f"Startup staleness check failed: {e}")

    # Start periodic staleness checker
    asyncio.create_task(periodic_staleness_check())

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
