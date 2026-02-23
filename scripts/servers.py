#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
List running repo-map MCP servers with diagnostics.

Shows PID, uptime, memory, project root, index status, cache info,
indexing subprocesses, and recent logs for each server.

Usage:
    uv run scripts/servers.py
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def run_cmd(cmd: list[str], timeout: int = 5) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def find_server_pids() -> list[dict]:
    """Find all running repo-map-server.py processes.

    Returns only the actual Python server processes, skipping the parent
    `uv run` wrappers (which also match the pattern).
    """
    # pgrep -fl: -f matches full command, -l shows process name + pid
    # On macOS, -a means "include ancestors" (not "show args" like Linux)
    output = run_cmd(["pgrep", "-f", "repo-map-server\\.py"])
    if not output:
        return []

    my_pid = os.getpid()
    pids = []
    for line in output.splitlines():
        line = line.strip()
        if not line.isdigit():
            continue
        pid = int(line)
        if pid == my_pid:
            continue
        pids.append(pid)

    if not pids:
        return []

    # Get full command lines via ps (portable across macOS/Linux)
    pid_list = ",".join(str(p) for p in pids)
    ps_output = run_cmd(["ps", "-p", pid_list, "-o", "pid=,command="])
    if not ps_output:
        return []

    servers = []
    seen_uv_pids: set[int] = set()
    entries: list[tuple[int, str]] = []

    for line in ps_output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid = int(parts[0])
        cmdline = parts[1]
        if "repo-map-server.py" not in cmdline:
            continue
        entries.append((pid, cmdline))
        # Track uv wrapper PIDs so we can skip them
        if cmdline.startswith("uv run") or cmdline.startswith("uv run "):
            seen_uv_pids.add(pid)

    # Prefer the actual python process over the uv wrapper
    for pid, cmdline in entries:
        if pid in seen_uv_pids:
            continue
        servers.append({"pid": pid, "cmdline": cmdline})

    # If only uv wrappers found (shouldn't happen normally), include them
    if not servers:
        for pid, cmdline in entries:
            servers.append({"pid": pid, "cmdline": cmdline})

    return servers


def get_process_info(pid: int) -> dict:
    """Get process info (uptime, RSS) from ps."""
    # ps -o etime=,rss= gives elapsed time and RSS in KB
    output = run_cmd(["ps", "-p", str(pid), "-o", "etime=,rss="])
    if not output:
        return {"uptime": "unknown", "rss_kb": 0}

    parts = output.split()
    if len(parts) < 2:
        return {"uptime": output.strip(), "rss_kb": 0}

    return {"uptime": parts[0].strip(), "rss_kb": int(parts[1])}


def format_rss(rss_kb: int) -> str:
    """Format RSS in human-readable form."""
    if rss_kb == 0:
        return "unknown"
    if rss_kb < 1024:
        return f"{rss_kb} KB"
    return f"{rss_kb / 1024:.1f} MB"


def get_project_root_from_env(pid: int) -> str | None:
    """Extract PROJECT_ROOT from process environment (macOS)."""
    # On macOS, use ps eww to get environment variables
    output = run_cmd(["ps", "eww", "-p", str(pid), "-o", "command="])
    if not output:
        return None

    # Look for PROJECT_ROOT= in the environment
    for part in output.split():
        if part.startswith("PROJECT_ROOT="):
            return part.split("=", 1)[1]
    return None


def get_project_root_from_cwd(pid: int) -> str | None:
    """Get the current working directory of a process via lsof."""
    output = run_cmd(["lsof", "-p", str(pid), "-Fn", "-a", "-d", "cwd"])
    if not output:
        return None
    for line in output.splitlines():
        if line.startswith("n/"):
            return line[1:]
    return None


def find_project_root(pid: int, cmdline: str) -> str | None:
    """Try multiple methods to find the project root for a server."""
    # Method 1: from process environment
    root = get_project_root_from_env(pid)
    if root:
        return root

    # Method 2: from process cwd
    root = get_project_root_from_cwd(pid)
    if root:
        return root

    # Method 3: infer from script path in cmdline
    # cmdline might contain something like /path/to/project/.claude-plugin/servers/repo-map-server.py
    for part in cmdline.split():
        if "repo-map-server.py" in part:
            server_path = Path(part)
            # servers/ is inside .claude-plugin/ or the plugin dir
            # Walk up to find a directory with .claude/
            candidate = server_path.parent.parent.parent
            if (candidate / ".claude").is_dir():
                return str(candidate)
            # The server might serve a different project - check cwd
            break

    return None


def get_index_status(project_root: str) -> dict:
    """Read index status from repo-map.db metadata table."""
    db_path = Path(project_root) / ".claude" / "repo-map.db"
    if not db_path.exists():
        return {"status": "no database"}

    try:
        conn = sqlite3.connect(str(db_path), timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT key, value FROM metadata")
            metadata = {row["key"]: row["value"] for row in cursor.fetchall()}
        except sqlite3.OperationalError:
            return {"status": "db exists but no metadata table"}

        result = {
            "status": metadata.get("status", "unknown"),
            "last_indexed": metadata.get("last_indexed"),
            "symbol_count": metadata.get("symbol_count"),
        }

        if metadata.get("status") == "indexing":
            start = metadata.get("index_start_time")
            if start:
                try:
                    started = datetime.fromisoformat(start)
                    elapsed = datetime.now() - started
                    result["indexing_for"] = str(timedelta(seconds=int(elapsed.total_seconds())))
                except ValueError:
                    pass

        if metadata.get("status") == "failed":
            result["error"] = metadata.get("error_message")

        conn.close()
        return result
    except sqlite3.Error as e:
        return {"status": f"db error: {e}"}


def get_cache_info(project_root: str) -> dict | None:
    """Read cache info from repo-map-cache.json."""
    cache_path = Path(project_root) / ".claude" / "repo-map-cache.json"
    if not cache_path.exists():
        return None

    try:
        data = json.loads(cache_path.read_text())
        return {
            "found_file_count": data.get("found_file_count"),
            "cached_file_count": len(data.get("files", {})),
        }
    except (json.JSONDecodeError, OSError):
        return None


def find_child_processes(pid: int) -> list[dict]:
    """Find child processes (e.g. map.py indexing subprocesses)."""
    output = run_cmd(["pgrep", "-lP", str(pid)])
    if not output:
        return []

    children = []
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) >= 2:
            children.append({"pid": int(parts[0]), "name": parts[1]})
        elif len(parts) == 1:
            children.append({"pid": int(parts[0]), "name": "unknown"})
    return children


def get_recent_logs(project_root: str, lines: int = 20) -> list[str]:
    """Get recent log lines from repo-map-server.log."""
    log_path = Path(project_root) / ".claude" / "logs" / "repo-map-server.log"
    if not log_path.exists():
        return []

    try:
        all_lines = log_path.read_text().splitlines()
        return all_lines[-lines:]
    except OSError:
        return []


def print_server(server: dict, index: int) -> None:
    """Print diagnostics for one server."""
    pid = server["pid"]
    cmdline = server["cmdline"]

    proc_info = get_process_info(pid)
    project_root = find_project_root(pid, cmdline)

    print(f"{'=' * 70}")
    print(f"Server #{index + 1}")
    print(f"  PID:      {pid}")
    print(f"  Uptime:   {proc_info['uptime']}")
    print(f"  Memory:   {format_rss(proc_info['rss_kb'])}")
    print(f"  Project:  {project_root or 'unknown'}")

    if project_root:
        # Index status
        idx = get_index_status(project_root)
        status_line = idx["status"]
        if idx.get("symbol_count"):
            status_line += f" ({idx['symbol_count']} symbols)"
        if idx.get("last_indexed"):
            status_line += f", last indexed: {idx['last_indexed']}"
        if idx.get("indexing_for"):
            status_line += f", running for {idx['indexing_for']}"
        if idx.get("error"):
            status_line += f"\n            ERROR: {idx['error']}"
        print(f"  Index:    {status_line}")

        # Cache info
        cache = get_cache_info(project_root)
        if cache:
            found = cache.get("found_file_count") or "?"
            cached = cache.get("cached_file_count", 0)
            print(f"  Cache:    {cached} cached / {found} found files")
        else:
            print(f"  Cache:    no cache file")

    # Child processes
    children = find_child_processes(pid)
    if children:
        print(f"  Children:")
        for child in children:
            child_info = get_process_info(child["pid"])
            print(f"    PID {child['pid']}: {child['name']} "
                  f"(up {child_info['uptime']}, {format_rss(child_info['rss_kb'])})")

    # Recent logs (filtered to current instance)
    if project_root:
        logs = get_recent_logs(project_root)
        if logs:
            print(f"  Logs ({len(logs)} lines):")
            for log_line in logs:
                print(f"    {log_line}")
        else:
            print(f"  Logs: no log file found")

    print()


def main() -> None:
    servers = find_server_pids()

    if not servers:
        print("No repo-map servers running.")
        return

    print(f"Found {len(servers)} repo-map server(s)\n")

    for i, server in enumerate(servers):
        print_server(server, i)


if __name__ == "__main__":
    main()
