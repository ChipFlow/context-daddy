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
Spawns indexing subprocess - watchdog can kill hung processes.

Exposes tools to search symbols by name/pattern, get file symbols, and trigger reindex.
"""

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import resource
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
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
SESSION_START_DIR = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
STALENESS_CHECK_INTERVAL = 60  # seconds between automatic staleness checks

# Dynamic paths based on current working directory
def get_project_root() -> Path:
    """Get current project root (current working directory)."""
    return Path.cwd()

def get_claude_dir() -> Path:
    """Get .claude directory for current project."""
    return get_project_root() / ".claude"

def get_db_path() -> Path:
    """Get database path for current project."""
    return get_claude_dir() / "repo-map.db"

def get_cache_path() -> Path:
    """Get cache path for current project."""
    return get_claude_dir() / "repo-map-cache.json"

def get_progress_path() -> Path:
    """Get progress file path for current project."""
    return get_claude_dir() / "repo-map-progress.json"

# Logging setup with rotating file handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler (stderr)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

# File handler (rotating log) - always in session start directory
try:
    from logging.handlers import RotatingFileHandler
    log_dir = SESSION_START_DIR / ".claude" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "repo-map-server.log"

    # 1MB per file, keep 3 backups (3MB total)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,  # 1MB
        backupCount=3
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s"
    ))
    logger.addHandler(file_handler)
    logger.info(f"Logging to {log_file}")
except Exception as e:
    logger.warning(f"Failed to setup file logging: {e}")

app = Server("context-tools-repo-map")

# Indexing state - now using subprocess instead of threads
_indexing_lock = threading.Lock()
_indexing_process: subprocess.Popen | None = None  # Current indexing subprocess
_last_index_time = 0
_index_error: str | None = None


def set_subprocess_limits():
    """
    Set resource limits for indexing subprocess (Unix only).
    Called via preexec_fn in subprocess.Popen.
    """
    try:
        # Limit memory to 4GB (generous, catches runaway allocations)
        # RLIMIT_AS = virtual memory address space
        memory_limit = 4 * 1024 * 1024 * 1024  # 4GB in bytes
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    except (ValueError, OSError, AttributeError) as e:
        # May fail on some systems or if resource module unavailable
        pass

    try:
        # Limit CPU time to 20 minutes (watchdog catches at 10 min wall-clock time)
        cpu_time_limit = 1200  # 20 minutes in seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit))
    except (ValueError, OSError, AttributeError):
        pass


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    db_path = get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Repo map database not found at {db_path}. Use reindex_repo_map tool.")
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary."""
    return {key: row[key] for key in row.keys()}


def check_subprocess_exit_status():
    """
    Check if indexing subprocess has exited and log resource limit issues.
    Called periodically to detect and log resource limit exceeded conditions.
    """
    global _indexing_process

    with _indexing_lock:
        if _indexing_process is None:
            return

        proc = _indexing_process
        if proc.poll() is None:
            # Still running
            return

        # Process has exited - check exit status
        returncode = proc.returncode

        # Exit code 0 = success (or concurrent indexer - SQLite handles concurrency)
        if returncode == 0:
            logger.info(f"Indexing subprocess completed successfully (PID: {proc.pid})")
            _indexing_process = None
            return

        # Check for resource limit signals (Unix)
        if returncode < 0:
            signal_num = -returncode
            if signal_num == signal.SIGXCPU:
                logger.error(f"Indexing subprocess (PID: {proc.pid}) exceeded CPU time limit (SIGXCPU)")
            elif signal_num == signal.SIGSEGV:
                # SIGSEGV can be caused by RLIMIT_AS exceeded
                logger.error(f"Indexing subprocess (PID: {proc.pid}) crashed (SIGSEGV) - possibly memory limit exceeded")
            elif signal_num == signal.SIGKILL:
                logger.warning(f"Indexing subprocess (PID: {proc.pid}) was killed (SIGKILL)")
            else:
                logger.warning(f"Indexing subprocess (PID: {proc.pid}) exited with signal {signal_num}")
        elif returncode > 0:
            logger.error(f"Indexing subprocess (PID: {proc.pid}) exited with error code {returncode}")

        # Clean up reference
        _indexing_process = None


def check_indexing_watchdog():
    """Check if indexing is stuck and KILL the hung subprocess."""
    global _indexing_process

    db_path = get_db_path()
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT key, value FROM metadata")
        metadata = {row["key"]: row["value"] for row in cursor.fetchall()}

        status = metadata.get("status")
        if status == "indexing":
            # Check how long it's been indexing
            start_time_str = metadata.get("index_start_time")
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                    elapsed = (datetime.now() - start_time).total_seconds()

                    # If indexing for > 10 minutes, kill the subprocess
                    if elapsed > 600:
                        logger.warning(f"Indexing stuck for {elapsed}s, killing subprocess")

                        # Mark database as failed
                        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ["status", "failed"])
                        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                                   ["error_message", f"Watchdog killed hung indexer after {elapsed:.0f}s"])
                        conn.commit()

                        # KILL the hung subprocess (key improvement!)
                        with _indexing_lock:
                            if _indexing_process and _indexing_process.poll() is None:
                                # Process still running - kill it
                                pid = _indexing_process.pid
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                    logger.warning(f"Killed hung indexer subprocess PID {pid}")
                                    _indexing_process.wait(timeout=5)  # Clean up zombie
                                except (ProcessLookupError, subprocess.TimeoutExpired):
                                    pass  # Already dead or still zombie
                                finally:
                                    _indexing_process = None
                except ValueError:
                    pass  # Invalid timestamp format

        conn.close()
    except Exception as e:
        logger.error(f"Watchdog check failed: {e}")


def is_stale() -> tuple[bool, str]:
    """
    Check if the repo map needs reindexing.
    Returns (is_stale, reason).
    """
    indexer = get_indexer()
    db_path = get_db_path()
    cache_path = get_cache_path()
    project_root = get_project_root()

    # No DB yet
    if not db_path.exists():
        return True, "database does not exist"

    # No cache file
    if not cache_path.exists():
        return True, "cache file missing"

    # Check cache version
    try:
        cache_data = json.loads(cache_path.read_text())
        if cache_data.get("version") != indexer.CACHE_VERSION:
            return True, f"cache version mismatch"
    except (json.JSONDecodeError, IOError):
        return True, "cache file corrupt"

    # Count files in cache vs current
    cached_count = len(cache_data.get("files", {}))

    # Quick file count check
    current_files = []
    for ext in [".py", ".rs", ".cpp", ".cc", ".cxx", ".hpp", ".h", ".hxx"]:
        current_files.extend(indexer.find_files(project_root, {ext}))
    current_count = len(current_files)

    if current_count != cached_count:
        return True, f"file count changed ({cached_count} cached, {current_count} found)"

    # Check if any file is newer than DB
    db_mtime = db_path.stat().st_mtime
    for f in current_files[:100]:  # Sample check for speed
        if f.stat().st_mtime > db_mtime:
            return True, "files modified since last index"

    return False, "up to date"


def do_index() -> tuple[bool, str]:
    """
    Spawn subprocess to perform indexing.
    Returns (success, message).
    """
    global _indexing_process, _last_index_time, _index_error

    with _indexing_lock:
        if _indexing_process and _indexing_process.poll() is None:
            return False, "indexing already in progress"
        _index_error = None

    try:
        project_root = get_project_root()
        claude_dir = get_claude_dir()
        logger.info(f"Starting index subprocess for {project_root}")

        # Ensure .claude directory exists
        claude_dir.mkdir(exist_ok=True)

        # Spawn subprocess to run the indexer with resource limits
        proc = subprocess.Popen(
            ["uv", "run", str(SCRIPT_DIR / "generate-repo-map.py"), str(project_root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=set_subprocess_limits,  # Set resource limits (Unix only)
        )

        with _indexing_lock:
            _indexing_process = proc

        _last_index_time = time.time()
        logger.info(f"Indexing subprocess started (PID: {proc.pid})")

        return True, f"indexing started in subprocess (PID: {proc.pid})"

    except Exception as e:
        logger.exception("Failed to start indexing subprocess")
        with _indexing_lock:
            _index_error = str(e)
        return False, f"failed to start indexing: {e}"


def index_in_background():
    """Start indexing in a background subprocess."""
    do_index()  # Spawns subprocess, no thread needed


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
        Tool(
            name="wait_for_index",
            description="Wait for indexing to complete. Use before other tools if you suspect indexing is in progress.",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout_seconds": {
                        "type": "integer",
                        "default": 60,
                        "description": "How long to wait (default: 60)"
                    }
                }
            }
        ),
        Tool(
            name="list_files",
            description="List all indexed files, optionally filtered by glob pattern. MUCH faster than find/ls for discovering file structure - queries pre-built index instead of filesystem traversal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files. Examples: '*.va' (all Verilog-A), '*psp103*' (PSP103 models), '**/devices/*' (all files under devices/). If not specified, returns all indexed files."
                    },
                    "limit": {
                        "type": "integer",
                        "default": 100,
                        "description": "Maximum number of results to return (default: 100)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="md_outline",
            description="Get hierarchical outline of markdown headings. Returns table of contents showing document structure. Useful for navigating large documentation files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to markdown file. Example: '.claude/learnings.md', 'docs/API.md'"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="md_get_section",
            description="Get content under a specific heading from markdown file. Returns section content until next same-level heading. Case-insensitive flexible matching.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to markdown file"
                    },
                    "heading": {
                        "type": "string",
                        "description": "Heading text to find (case-insensitive). Example: 'Installation', 'API Reference'"
                    }
                },
                "required": ["file_path", "heading"]
            }
        ),
        Tool(
            name="md_list_tables",
            description="List all markdown tables with context. Returns summary showing table location, headers, and surrounding context. Useful for finding specific data tables.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to markdown file"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="md_get_table",
            description="Get full markdown table by index (0-based). Use md_list_tables first to see available tables and their indices.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to markdown file"
                    },
                    "index": {
                        "type": "integer",
                        "description": "Table index (0-based). Get indices from md_list_tables."
                    }
                },
                "required": ["file_path", "index"]
            }
        ),
        Tool(
            name="md_list_figures",
            description="List all images/figures referenced in markdown. Returns image locations with alt text and paths.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative path to markdown file"
                    }
                },
                "required": ["file_path"]
            }
        ),
    ]


async def wait_for_indexing(timeout_seconds: int = 60) -> tuple[bool, str]:
    """
    Wait for indexing to complete.
    Returns (success, message).
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        status = repo_map_status()

        if status.get("index_status") == "completed":
            return True, "indexing completed"

        if status.get("index_status") == "failed":
            error = status.get("error", "unknown error")
            return False, f"indexing failed: {error}"

        await asyncio.sleep(1)  # Poll every second

    return False, "timeout waiting for indexing"


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with args: {arguments}")

    # Log which directory we're querying
    project_root = get_project_root()
    db_path = get_db_path()
    if project_root != SESSION_START_DIR:
        logger.info(f"Directory changed: session started in {SESSION_START_DIR}, now in {project_root}")
        logger.info(f"Will query/index database at: {db_path}")

    # Auto-wait for indexing if needed (reduced timeout for better UX)
    # Markdown tools don't need indexing
    if name not in ["repo_map_status", "reindex_repo_map", "wait_for_index",
                     "md_outline", "md_get_section", "md_list_tables", "md_get_table", "md_list_figures"]:
        try:
            if db_path.exists():
                conn = sqlite3.connect(db_path, timeout=5.0)
                try:
                    cursor = conn.execute("SELECT value FROM metadata WHERE key = 'status'")
                    row = cursor.fetchone()
                    if row and row[0] == "indexing":
                        logger.info("Indexing in progress, waiting up to 15 seconds...")
                        success, msg = await wait_for_indexing(timeout_seconds=15)
                        if not success:
                            # Don't return error - return progress information instead
                            progress = get_indexing_progress()
                            if progress:
                                return [TextContent(type="text", text=json.dumps({
                                    "status": "indexing_in_progress",
                                    "message": "Index is building. Try again in a moment or use repo_map_status to check progress.",
                                    "progress": progress,
                                    "partial_results": []
                                }, indent=2))]
                            else:
                                return [TextContent(type="text", text=json.dumps({
                                    "status": "indexing_in_progress",
                                    "message": "Index is building. Try again in a moment or use repo_map_status to check progress.",
                                    "partial_results": []
                                }, indent=2))]
                except sqlite3.OperationalError:
                    pass  # Metadata table doesn't exist yet
                finally:
                    conn.close()
        except Exception:
            pass  # DB doesn't exist yet

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
        elif name == "wait_for_index":
            timeout = arguments.get("timeout_seconds", 60)
            success, msg = await wait_for_indexing(timeout_seconds=timeout)
            result = {"success": success, "message": msg}
        elif name == "list_files":
            result = list_files(
                pattern=arguments.get("pattern"),
                limit=arguments.get("limit", 100)
            )
        elif name == "md_outline":
            result = md_outline(file_path=arguments["file_path"])
        elif name == "md_get_section":
            result = md_get_section(
                file_path=arguments["file_path"],
                heading=arguments["heading"]
            )
        elif name == "md_list_tables":
            result = md_list_tables(file_path=arguments["file_path"])
        elif name == "md_get_table":
            result = md_get_table(
                file_path=arguments["file_path"],
                index=arguments["index"]
            )
        elif name == "md_list_figures":
            result = md_list_figures(file_path=arguments["file_path"])
        else:
            result = {"error": f"Unknown tool: {name}"}
            logger.error(f"Unknown tool: {name}")

        # Log result summary
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Tool {name} returned error: {result.get('error')}")
        elif isinstance(result, list):
            logger.info(f"Tool {name} returned {len(result)} results")
        elif isinstance(result, str):
            logger.info(f"Tool {name} returned markdown ({len(result)} chars)")
        else:
            logger.info(f"Tool {name} completed successfully")

        # Return markdown strings directly, JSON-encode dicts/lists
        if isinstance(result, str):
            return [TextContent(type="text", text=result)]
        else:
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except FileNotFoundError as e:
        # DB doesn't exist - trigger indexing
        logger.info(f"DB not found, triggering indexing for tool {name}")
        stale, reason = is_stale()
        is_indexing = _indexing_process is not None and _indexing_process.poll() is None
        if stale and not is_indexing:
            index_in_background()
        return [TextContent(type="text", text=json.dumps({
            "error": str(e),
            "status": "indexing started in background" if not is_indexing else "indexing in progress"
        }))]
    except Exception as e:
        logger.exception(f"Tool {name} failed with exception")
        return [TextContent(type="text", text=json.dumps({"error": f"Tool error: {e}"}))]


def search_symbols(pattern: str, kind: str | None = None, limit: int = 20) -> str:
    """Search for symbols by name pattern. Returns markdown."""
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
                results.append(row)

        # If no results with strict fnmatch, return SQL results
        if not results:
            results = list(rows)

        results = results[:limit]

        if not results:
            return f"No symbols found matching pattern: `{pattern}`"

        # Format as markdown
        md = f"## Found {len(results)} symbol(s) matching `{pattern}`\n\n"
        for row in results:
            name = row["name"]
            kind_str = row["kind"]
            path = row["file_path"]
            line = row["line_number"]

            if row["parent"]:
                name = f"{row['parent']}.{name}"

            md += f"- **{name}** ({kind_str}) - `{path}:{line}`\n"

            if row["docstring"]:
                # First line of docstring only
                first_line = row["docstring"].split("\n")[0]
                if len(first_line) > 80:
                    first_line = first_line[:77] + "..."
                md += f"  _{first_line}_\n"

        return md
    finally:
        conn.close()


def get_file_symbols(file: str) -> str:
    """Get all symbols in a specific file. Returns markdown."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_number",
            [file]
        )
        rows = cursor.fetchall()

        if not rows:
            return f"No symbols found in file: `{file}`"

        # Format as markdown
        md = f"## Symbols in `{file}`\n\n"
        md += f"Found {len(rows)} symbol(s):\n\n"

        for row in rows:
            name = row["name"]
            kind = row["kind"]
            line = row["line_number"]

            if row["parent"]:
                name = f"{row['parent']}.{name}"

            md += f"- **{name}** ({kind}) - line {line}\n"

            if row["signature"]:
                md += f"  `{row['signature']}`\n"

            if row["docstring"]:
                # First line of docstring only
                first_line = row["docstring"].split("\n")[0]
                if len(first_line) > 80:
                    first_line = first_line[:77] + "..."
                md += f"  _{first_line}_\n"

        return md
    finally:
        conn.close()


def get_symbol_content(name: str, kind: str | None = None) -> str:
    """Get the source code content of a symbol by exact name. Returns markdown."""
    conn = get_db()
    project_root = get_project_root()
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
            return f"❌ Symbol `{name}` not found"

        # If multiple matches, return info about all of them
        if len(rows) > 1 and kind is None:
            md = f"❌ Multiple symbols named `{name}` found. Specify 'kind' to disambiguate.\n\n"
            md += f"Found {len(rows)} matches:\n\n"
            for row in rows:
                display_name = f"{row['parent']}.{row['name']}" if row["parent"] else row["name"]
                md += f"- **{display_name}** ({row['kind']}) - `{row['file_path']}:{row['line_number']}`\n"
            return md

        row = rows[0]
        file_path = project_root / row["file_path"]

        if not file_path.exists():
            return f"❌ File not found: `{row['file_path']}`"

        # Read file content
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (IOError, UnicodeDecodeError) as e:
            return f"❌ Could not read file: {e}"

        start_line = row["line_number"]
        end_line = row["end_line_number"]

        if end_line is None:
            # Fallback: return just the start line and a few following lines
            end_line = min(start_line + 20, len(lines))

        # Extract content (convert to 0-indexed)
        content_lines = lines[start_line - 1:end_line]
        content = "\n".join(content_lines)

        # Detect language for syntax highlighting
        file_ext = Path(row["file_path"]).suffix.lstrip(".")
        lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "rs": "rust", "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp"}
        lang = lang_map.get(file_ext, file_ext)

        # Build markdown
        display_name = f"{row['parent']}.{row['name']}" if row["parent"] else row["name"]
        md = f"## {display_name} ({row['kind']})\n\n"
        md += f"**Location:** `{row['file_path']}:{start_line}-{end_line}`\n\n"

        if row["signature"]:
            md += f"**Signature:** `{row['signature']}`\n\n"

        if row["docstring"]:
            md += f"**Documentation:**\n```\n{row['docstring']}\n```\n\n"

        md += f"**Source Code:**\n```{lang}\n{content}\n```\n"

        return md
    finally:
        conn.close()


def reindex_repo_map(force: bool = False) -> dict:
    """Trigger a reindex of the repository."""
    is_indexing = _indexing_process is not None and _indexing_process.poll() is None

    if is_indexing:
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
    is_indexing = _indexing_process is not None and _indexing_process.poll() is None
    project_root = get_project_root()
    db_path = get_db_path()
    status = {
        "project_root": str(project_root),
        "database_exists": db_path.exists(),
        "is_indexing": is_indexing,
    }

    if _index_error:
        status["last_error"] = _index_error

    if _last_index_time > 0:
        status["last_index_time"] = _last_index_time
        status["last_index_ago_seconds"] = int(time.time() - _last_index_time)

    if db_path.exists():
        try:
            conn = get_db()

            # Get metadata
            try:
                cursor = conn.execute("SELECT key, value FROM metadata")
                metadata = {row["key"]: row["value"] for row in cursor.fetchall()}

                status["index_status"] = metadata.get("status", "unknown")
                status["last_indexed"] = metadata.get("last_indexed")

                symbol_count_str = metadata.get("symbol_count")
                if symbol_count_str:
                    status["symbol_count"] = int(symbol_count_str)
                else:
                    # Fallback to counting
                    cursor = conn.execute("SELECT COUNT(*) FROM symbols")
                    status["symbol_count"] = cursor.fetchone()[0]

                if metadata.get("status") == "indexing":
                    start_time_str = metadata.get("index_start_time")
                    if start_time_str:
                        try:
                            start_time = datetime.fromisoformat(start_time_str)
                            elapsed = (datetime.now() - start_time).total_seconds()
                            status["indexing_duration_seconds"] = int(elapsed)
                        except ValueError:
                            pass

                if metadata.get("status") == "failed":
                    status["error"] = metadata.get("error_message")

            except sqlite3.OperationalError:
                # Metadata table doesn't exist yet (old DB format)
                cursor = conn.execute("SELECT COUNT(*) FROM symbols")
                status["symbol_count"] = cursor.fetchone()[0]
                status["index_status"] = "unknown (old DB format)"

            conn.close()
        except Exception as e:
            status["db_error"] = str(e)

    stale, reason = is_stale()
    status["is_stale"] = stale
    status["staleness_reason"] = reason

    return status


def get_indexing_progress() -> dict | None:
    """
    Get current indexing progress from progress file.
    Returns dict with progress info, or None if no progress file.
    """
    progress_path = get_progress_path()
    if not progress_path.exists():
        return None

    try:
        data = json.loads(progress_path.read_text())

        # Calculate percentage if we have the data
        status = data.get("status", "unknown")
        files_parsed = data.get("files_parsed", 0)
        files_to_parse = data.get("files_to_parse", 0)
        files_total = data.get("files_total", 0)
        symbols_found = data.get("symbols_found", 0)

        percentage = 0
        if files_to_parse > 0:
            percentage = int((files_parsed / files_to_parse) * 100)

        # Estimate time remaining (very rough)
        # Assume average 50ms per file
        files_remaining = files_to_parse - files_parsed
        estimated_seconds = max(0, int(files_remaining * 0.05))  # 50ms per file

        if estimated_seconds < 60:
            time_remaining = f"{estimated_seconds} seconds"
        else:
            time_remaining = f"{int(estimated_seconds / 60)} minutes"

        return {
            "status": status,
            "percentage": percentage,
            "files_parsed": files_parsed,
            "files_to_parse": files_to_parse,
            "files_total": files_total,
            "symbols_found": symbols_found,
            "estimated_time_remaining": time_remaining if files_remaining > 0 else "completing..."
        }
    except (json.JSONDecodeError, IOError, KeyError):
        return None


def list_files(pattern: str | None = None, limit: int = 100) -> str:
    """
    List all indexed files, optionally filtered by glob pattern.
    Much faster than find/ls - queries pre-built index. Returns markdown.
    """
    conn = get_db()
    try:
        # Get distinct file paths from symbols table
        query = "SELECT DISTINCT file_path FROM symbols"
        params: list = []

        # Apply glob pattern filtering if provided
        if pattern:
            # Convert glob pattern to SQL LIKE pattern
            sql_pattern = pattern.replace("*", "%").replace("?", "_")
            query += " WHERE file_path LIKE ?"
            params.append(sql_pattern)

        query += " ORDER BY file_path LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        files = [row["file_path"] for row in rows]

        if not files:
            pattern_str = f" matching `{pattern}`" if pattern else ""
            return f"No files found{pattern_str}"

        # Format as markdown
        pattern_str = f" matching `{pattern}`" if pattern else ""
        md = f"## Found {len(files)} file(s){pattern_str}\n\n"

        # Group by directory for better readability
        dirs = {}
        for file in files:
            if "/" in file:
                dir_name = file.rsplit("/", 1)[0]
                file_name = file.rsplit("/", 1)[1]
            else:
                dir_name = "."
                file_name = file

            if dir_name not in dirs:
                dirs[dir_name] = []
            dirs[dir_name].append(file_name)

        # Output grouped by directory
        for dir_name in sorted(dirs.keys()):
            if dir_name == ".":
                md += "**Root directory:**\n"
            else:
                md += f"**`{dir_name}/`:**\n"

            for file_name in sorted(dirs[dir_name]):
                md += f"- {file_name}\n"

            md += "\n"

        if len(files) >= limit:
            md += f"\n*Showing first {limit} files. Use `limit` parameter to see more.*\n"

        return md
    finally:
        conn.close()


# ============================================================================
# Markdown Navigation Tools
# ============================================================================

def md_outline(file_path: str) -> str:
    """
    Get hierarchical outline of markdown headings.
    Returns markdown-formatted table of contents.
    """
    project_root = get_project_root()
    full_path = project_root / file_path

    if not full_path.exists():
        return f"❌ File not found: `{file_path}`"

    try:
        content = full_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError) as e:
        return f"❌ Could not read file: {e}"

    # Extract headings
    headings = []
    for line_num, line in enumerate(content.splitlines(), 1):
        if line.startswith("#"):
            # Count heading level
            level = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip()
            if heading_text:
                headings.append((level, heading_text, line_num))

    if not headings:
        return f"No headings found in `{file_path}`"

    # Format as markdown outline
    md = f"## Outline: `{file_path}`\n\n"
    for level, text, line_num in headings:
        indent = "  " * (level - 1)
        md += f"{indent}- **{text}** (line {line_num})\n"

    return md


def md_get_section(file_path: str, heading: str) -> str:
    """
    Get content under a specific heading (until next same-level heading).
    Returns markdown with the section content.
    """
    project_root = get_project_root()
    full_path = project_root / file_path

    if not full_path.exists():
        return f"❌ File not found: `{file_path}`"

    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
    except (IOError, UnicodeDecodeError) as e:
        return f"❌ Could not read file: {e}"

    # Find the heading (case-insensitive, flexible matching)
    heading_lower = heading.lower().strip()
    start_line = None
    heading_level = None

    for i, line in enumerate(lines):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip().lower()
            if heading_lower in text or text in heading_lower:
                start_line = i
                heading_level = level
                break

    if start_line is None:
        return f"❌ Heading not found: `{heading}` in `{file_path}`"

    # Find end of section (next same-level or higher heading)
    end_line = len(lines)
    if heading_level is not None:
        for i in range(start_line + 1, len(lines)):
            if lines[i].startswith("#"):
                level = len(lines[i]) - len(lines[i].lstrip("#"))
                if level <= heading_level:
                    end_line = i
                    break

    # Extract section content
    section_lines = lines[start_line:end_line]
    content = "\n".join(section_lines)

    md = f"## Section from `{file_path}`\n\n"
    md += f"```markdown\n{content}\n```\n"

    return md


def md_list_tables(file_path: str) -> str:
    """
    List all markdown tables with context (surrounding text).
    Returns summary of each table.
    """
    project_root = get_project_root()
    full_path = project_root / file_path

    if not full_path.exists():
        return f"❌ File not found: `{file_path}`"

    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
    except (IOError, UnicodeDecodeError) as e:
        return f"❌ Could not read file: {e}"

    # Find tables (look for separator lines with |---|)
    tables = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Table separator line pattern
        if "|" in line and ("-" in line or ":" in line):
            # Check if previous line is table header
            if i > 0 and "|" in lines[i - 1]:
                header_line = lines[i - 1].strip()
                # Find preceding context (heading or text)
                context = ""
                for j in range(i - 1, max(0, i - 10), -1):
                    if lines[j].startswith("#"):
                        context = lines[j].lstrip("#").strip()
                        break
                    elif lines[j].strip():
                        context = lines[j].strip()[:50] + "..." if len(lines[j].strip()) > 50 else lines[j].strip()

                tables.append({
                    "index": len(tables),
                    "line": i + 1,
                    "header": header_line,
                    "context": context or "(no context)"
                })
        i += 1

    if not tables:
        return f"No tables found in `{file_path}`"

    # Format as markdown
    md = f"## Found {len(tables)} table(s) in `{file_path}`\n\n"
    for table in tables:
        md += f"{table['index'] + 1}. **Line {table['line']}** - {table['context']}\n"
        md += f"   Header: `{table['header']}`\n\n"

    md += "\nUse `md_get_table(file_path, index)` to get full table content.\n"

    return md


def md_get_table(file_path: str, index: int) -> str:
    """
    Get full markdown table by index (0-based).
    Returns the complete table in markdown.
    """
    project_root = get_project_root()
    full_path = project_root / file_path

    if not full_path.exists():
        return f"❌ File not found: `{file_path}`"

    try:
        lines = full_path.read_text(encoding="utf-8").splitlines()
    except (IOError, UnicodeDecodeError) as e:
        return f"❌ Could not read file: {e}"

    # Find tables
    table_starts = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" in line and ("-" in line or ":" in line):
            if i > 0 and "|" in lines[i - 1]:
                # Found table separator, header is at i-1
                table_starts.append(i - 1)
        i += 1

    if not table_starts:
        return f"No tables found in `{file_path}`"

    if index < 0 or index >= len(table_starts):
        return f"❌ Table index {index} out of range (found {len(table_starts)} tables)"

    # Extract table (from header until non-table line)
    start = table_starts[index]
    end = start
    for i in range(start, len(lines)):
        if "|" in lines[i]:
            end = i + 1
        else:
            break

    table_lines = lines[start:end]
    table_content = "\n".join(table_lines)

    md = f"## Table {index + 1} from `{file_path}` (line {start + 1})\n\n"
    md += table_content + "\n"

    return md


def md_list_figures(file_path: str) -> str:
    """
    List all images/figures referenced in markdown.
    Returns list with alt text and paths.
    """
    project_root = get_project_root()
    full_path = project_root / file_path

    if not full_path.exists():
        return f"❌ File not found: `{file_path}`"

    try:
        content = full_path.read_text(encoding="utf-8")
    except (IOError, UnicodeDecodeError) as e:
        return f"❌ Could not read file: {e}"

    # Find markdown images: ![alt](path)
    import re
    figures = []
    for line_num, line in enumerate(content.splitlines(), 1):
        # Pattern: ![alt text](image/path.png)
        matches = re.findall(r'!\[([^\]]*)\]\(([^\)]+)\)', line)
        for alt_text, img_path in matches:
            figures.append({
                "line": line_num,
                "alt": alt_text or "(no alt text)",
                "path": img_path
            })

    if not figures:
        return f"No figures/images found in `{file_path}`"

    # Format as markdown
    md = f"## Found {len(figures)} figure(s) in `{file_path}`\n\n"
    for i, fig in enumerate(figures, 1):
        md += f"{i}. **Line {fig['line']}**: {fig['alt']}\n"
        md += f"   Path: `{fig['path']}`\n\n"

    return md


async def periodic_staleness_check():
    """Periodically check if reindexing is needed."""
    while True:
        await asyncio.sleep(STALENESS_CHECK_INTERVAL)
        try:
            is_indexing = _indexing_process is not None and _indexing_process.poll() is None
            if not is_indexing:
                stale, reason = is_stale()
                if stale:
                    logger.info(f"Index is stale ({reason}), starting background reindex")
                    index_in_background()
        except Exception as e:
            logger.warning(f"Staleness check failed: {e}")


async def periodic_watchdog_check():
    """Run watchdog every 60 seconds to detect hung indexing and resource limit issues."""
    while True:
        await asyncio.sleep(60)
        try:
            # Check for completed subprocess and log resource limit issues
            check_subprocess_exit_status()
            # Check for hung processes
            check_indexing_watchdog()
        except Exception as e:
            logger.warning(f"Watchdog check failed: {e}")


async def main():
    """Run the MCP server."""
    logger.info("=" * 60)
    logger.info(f"MCP Server starting in directory: {SESSION_START_DIR}")
    logger.info(f"MCP tools will dynamically query current working directory")
    logger.info(f"Python: {sys.version}")
    logger.info("=" * 60)

    # Run watchdog on startup to detect any stuck state
    try:
        check_subprocess_exit_status()
        check_indexing_watchdog()
    except Exception as e:
        logger.warning(f"Startup watchdog check failed: {e}")

    # Check if indexing needed on startup
    try:
        stale, reason = is_stale()
        if stale:
            logger.info(f"Index is stale on startup ({reason}), starting background reindex")
            index_in_background()
    except Exception as e:
        logger.warning(f"Startup staleness check failed: {e}")

    # Start periodic checks
    asyncio.create_task(periodic_staleness_check())
    asyncio.create_task(periodic_watchdog_check())

    logger.info("MCP Server ready, waiting for tool calls...")

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    except Exception as e:
        logger.exception("MCP Server error")
        raise
    finally:
        logger.info("MCP Server shutting down")


if __name__ == "__main__":
    asyncio.run(main())
