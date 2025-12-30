#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
# ]
# ///
"""
MCP server for querying repo-map symbol data.
Exposes tools to search symbols by name/pattern and get file symbols.
"""

import fnmatch
import json
import os
import sqlite3
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


# Get project root from environment or use current directory
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", os.getcwd()))
DB_PATH = PROJECT_ROOT / ".claude" / "repo-map.db"

app = Server("context-tools-repo-map")


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Repo map database not found at {DB_PATH}. Run /repo-map first.")
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary."""
    return {key: row[key] for key in row.keys()}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="search_symbols",
            description="Search for symbols (functions, classes, methods) by name pattern. Supports glob patterns like 'get_*' or '*Config*'. FASTER than Grep for symbol lookups - uses pre-built SQLite index.",
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
            description="Get the source code content of a symbol by exact name. FASTER than Grep+Read - directly retrieves function/class/method source code from pre-indexed line ranges. Use this instead of Grep when you know the symbol name.",
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
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except FileNotFoundError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
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


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
