# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Process guardian for context-daddy background processes.

Watches the parent Claude Code process and kills all registered child
processes when the parent exits. This prevents orphaned MCP servers,
map.py indexers, and update-context.sh agents from accumulating.

Usage:
    # Spawned by session-start.sh, runs in background
    uv run process-guardian.py --parent-pid 12345 --pidfile /path/to/.claude/.guardian-pids

The guardian:
1. Reads PIDs from the pidfile (one per line, format: PID:label)
2. Polls the parent process every 10 seconds
3. When parent dies, kills all registered children
4. Also kills children that are already zombies/orphans

Other scripts register processes by appending to the pidfile:
    echo "54321:repo-map-server" >> .claude/.guardian-pids
"""

import argparse
import os
import signal
import sys
import time
from pathlib import Path


def is_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_process(pid: int, label: str = "") -> None:
    """Kill a process, escalating from SIGTERM to SIGKILL."""
    if not is_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly for clean shutdown
        for _ in range(10):
            time.sleep(0.5)
            if not is_alive(pid):
                return
        # Force kill
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def read_pids(pidfile: Path) -> list[tuple[int, str]]:
    """Read registered PIDs from the pidfile."""
    if not pidfile.exists():
        return []
    pids = []
    for line in pidfile.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":", 1)
        try:
            pid = int(parts[0])
            label = parts[1] if len(parts) > 1 else "unknown"
            pids.append((pid, label))
        except ValueError:
            continue
    return pids


def cleanup_all(pidfile: Path) -> None:
    """Kill all registered processes and clean up pidfile."""
    pids = read_pids(pidfile)
    for pid, label in pids:
        if is_alive(pid):
            kill_process(pid, label)
    # Clean up
    pidfile.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Process guardian for context-daddy")
    parser.add_argument("--parent-pid", type=int, required=True,
                        help="PID of the parent Claude Code process to watch")
    parser.add_argument("--pidfile", type=str, required=True,
                        help="Path to the pidfile listing child PIDs")
    parser.add_argument("--poll-interval", type=int, default=10,
                        help="Seconds between parent process checks (default: 10)")
    args = parser.parse_args()

    pidfile = Path(args.pidfile)
    parent_pid = args.parent_pid

    # Verify parent exists
    if not is_alive(parent_pid):
        # Parent already dead — clean up immediately
        cleanup_all(pidfile)
        return

    # Register self for cleanup on signals
    def handle_signal(signum, frame):
        cleanup_all(pidfile)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Poll loop
    while True:
        time.sleep(args.poll_interval)

        if not is_alive(parent_pid):
            # Parent died — clean up all children
            cleanup_all(pidfile)
            break

        # Also prune dead entries from pidfile (keeps it tidy)
        pids = read_pids(pidfile)
        alive = [(pid, label) for pid, label in pids if is_alive(pid)]
        if len(alive) < len(pids) and pidfile.exists():
            pidfile.write_text(
                "\n".join(f"{pid}:{label}" for pid, label in alive) + "\n"
            )

        # If no children left to watch, exit
        if not alive:
            pidfile.unlink(missing_ok=True)
            break


if __name__ == "__main__":
    main()
