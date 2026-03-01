#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp>=1.0.0",
# ]
# ///
"""
MCP server for cross-session goal tracking.

Exposes goal management tools that import pure functions from scripts/goals.py.
Provides clean tool invocation without Bash noise.
"""

import asyncio
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import goal functions from scripts/goals.py
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import goals  # noqa: E402

# Configuration
PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())

# Logging
LOG_DIR = Path(PROJECT_ROOT) / ".claude" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("goals-server")
logger.setLevel(logging.INFO)

handler = logging.handlers.RotatingFileHandler(
    LOG_DIR / "goals-server.log",
    maxBytes=1_000_000,
    backupCount=3,
)
handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

app = Server("goals")


def _text(content: str) -> list[TextContent]:
    """Helper to wrap string in TextContent list."""
    return [TextContent(type="text", text=content)]


def _error(msg: str) -> list[TextContent]:
    """Helper for error responses."""
    return [TextContent(type="text", text=f"Error: {msg}")]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available goal management tools."""
    return [
        Tool(
            name="goal_create",
            description="Create a new cross-session goal with title and objective.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short descriptive title for the goal"
                    },
                    "objective": {
                        "type": "string",
                        "description": "1-3 sentence description of what success looks like"
                    },
                    "slug": {
                        "type": "string",
                        "description": "Optional human-readable slug (auto-generated from title if omitted)"
                    },
                },
                "required": ["title", "objective"]
            }
        ),
        Tool(
            name="goal_list",
            description="List goals for the current project, or all goals with all=true.",
            inputSchema={
                "type": "object",
                "properties": {
                    "all": {
                        "type": "boolean",
                        "default": False,
                        "description": "Show all goals across all projects"
                    },
                },
            }
        ),
        Tool(
            name="goal_show",
            description="Show the full markdown content of a goal. Defaults to current goal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug. Omit for current goal."
                    },
                },
            }
        ),
        Tool(
            name="goal_switch",
            description="Set the active goal for this project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug to switch to"
                    },
                },
                "required": ["id"]
            }
        ),
        Tool(
            name="goal_unset",
            description="Remove the current goal marker (stop tracking without archiving).",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        Tool(
            name="goal_focus",
            description="Set the focused step for the current goal by step ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "string",
                        "description": "Step ID to focus on (e.g. 'add-src-location')"
                    },
                    "id": {
                        "type": "string",
                        "description": "Goal UUID/slug. Omit for current goal."
                    },
                },
                "required": ["step"]
            }
        ),
        Tool(
            name="goal_update_step",
            description="Mark a step done and/or advance the current marker.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug"
                    },
                    "step": {
                        "type": "string",
                        "description": "Step ID or 1-based step number"
                    },
                    "complete": {
                        "type": "boolean",
                        "default": False,
                        "description": "Mark the step as completed (advances to next)"
                    },
                },
                "required": ["id", "step"]
            }
        ),
        Tool(
            name="goal_add_learning",
            description="Record a learning/insight for a goal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug"
                    },
                    "text": {
                        "type": "string",
                        "description": "Learning text to record"
                    },
                },
                "required": ["id", "text"]
            }
        ),
        Tool(
            name="goal_add_step",
            description="Add a new plan step to a goal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug"
                    },
                    "description": {
                        "type": "string",
                        "description": "Step description text"
                    },
                    "step_id": {
                        "type": "string",
                        "description": "Optional custom step ID (auto-generated if omitted)"
                    },
                    "after": {
                        "type": "string",
                        "description": "Insert after this step ID or 1-based position number"
                    },
                },
                "required": ["id", "description"]
            }
        ),
        Tool(
            name="goal_link_project",
            description="Link a project directory to a goal.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug"
                    },
                    "path": {
                        "type": "string",
                        "description": "Project directory path to link"
                    },
                    "role": {
                        "type": "string",
                        "enum": ["primary", "dependency"],
                        "default": "primary",
                        "description": "Role of this project in the goal"
                    },
                },
                "required": ["id", "path"]
            }
        ),
        Tool(
            name="goal_archive",
            description="Archive a goal (mark as finished/abandoned, move to .archive).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Goal UUID, partial UUID, or slug"
                    },
                },
                "required": ["id"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls by delegating to pure functions."""
    logger.info("Tool called: %s with args: %s", name, arguments)

    try:
        if name == "goal_create":
            result = goals.goal_create(
                title=arguments["title"],
                objective=arguments["objective"],
                project_path=PROJECT_ROOT,
                slug=arguments.get("slug"),
            )

        elif name == "goal_list":
            result = goals.goal_list(
                show_all=arguments.get("all", False),
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_show":
            result = goals.goal_show(
                goal_ref=arguments.get("id"),
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_switch":
            result = goals.goal_switch(
                goal_ref=arguments["id"],
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_unset":
            result = goals.goal_unset(project_path=PROJECT_ROOT)

        elif name == "goal_focus":
            result = goals.goal_focus(
                goal_ref=arguments.get("id"),
                step_id=arguments["step"],
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_update_step":
            step_ref: str | int = arguments["step"]
            try:
                step_ref = int(step_ref)
            except (ValueError, TypeError):
                pass
            result = goals.goal_update_step(
                goal_ref=arguments["id"],
                step_ref=step_ref,
                complete=arguments.get("complete", False),
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_add_learning":
            result = goals.goal_add_learning(
                goal_ref=arguments["id"],
                text=arguments["text"],
            )

        elif name == "goal_add_step":
            after = arguments.get("after")
            if after is not None:
                try:
                    after = int(after)
                except (ValueError, TypeError):
                    pass
            result = goals.goal_add_step(
                goal_ref=arguments["id"],
                description=arguments["description"],
                step_id=arguments.get("step_id"),
                after=after,
                project_path=PROJECT_ROOT,
            )

        elif name == "goal_link_project":
            result = goals.goal_link_project(
                goal_ref=arguments["id"],
                link_path=arguments["path"],
                role=arguments.get("role", "primary"),
            )

        elif name == "goal_archive":
            result = goals.goal_archive(
                goal_ref=arguments["id"],
                project_path=PROJECT_ROOT,
            )

        else:
            logger.warning("Unknown tool: %s", name)
            return _error(f"Unknown tool: {name}")

        logger.info("Tool %s succeeded: %s", name, result[:100] if result else "")
        return _text(result)

    except ValueError as e:
        logger.warning("Tool %s ValueError: %s", name, e)
        return _error(str(e))
    except Exception as e:
        logger.exception("Tool %s unexpected error", name)
        return _error(f"Unexpected error: {e}")


async def main():
    logger.info("Goals MCP server starting (project: %s)", PROJECT_ROOT)

    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    except Exception:
        logger.exception("Goals MCP server error")
        raise
    finally:
        logger.info("Goals MCP server shutting down")


if __name__ == "__main__":
    asyncio.run(main())
