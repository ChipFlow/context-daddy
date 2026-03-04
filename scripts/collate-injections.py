# /// script
# requires-python = ">=3.10"
# ///
"""Collate and summarize context injection sizes from hook-runner.sh logs.

Usage:
    uv run scripts/collate-injections.py              # Summary of all injections
    uv run scripts/collate-injections.py --detail      # Per-event detail
    uv run scripts/collate-injections.py --by-session  # Group by session
    uv run scripts/collate-injections.py --since 24h   # Last 24 hours only
    uv run scripts/collate-injections.py --tail 20     # Last 20 events
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


LOG_FILE = Path.home() / ".claude" / "logs" / "context-injection.tsv"

DURATION_MAP = {"h": "hours", "d": "days", "m": "minutes", "w": "weeks"}


def parse_duration(s: str) -> timedelta:
    """Parse '24h', '7d', '30m', '1w' into timedelta."""
    s = s.strip()
    for suffix, kwarg in DURATION_MAP.items():
        if s.endswith(suffix):
            return timedelta(**{kwarg: int(s[:-len(suffix)])})
    # Try parsing as hours by default
    return timedelta(hours=int(s))


def read_log(since: timedelta | None = None) -> list[dict]:
    if not LOG_FILE.exists():
        print(f"No log file found at {LOG_FILE}", file=sys.stderr)
        print("Run some Claude sessions with context-daddy installed to generate data.", file=sys.stderr)
        sys.exit(1)

    cutoff = None
    if since:
        cutoff = datetime.now(timezone.utc) - since

    rows = []
    with open(LOG_FILE) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                ts = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                if cutoff and ts < cutoff:
                    continue
                row["_ts"] = ts
                row["bytes"] = int(row["bytes"])
                row["est_tokens"] = int(row["est_tokens"])
                rows.append(row)
            except (ValueError, KeyError):
                continue
    return rows


def fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f}KB"
    return f"{b / (1024 * 1024):.1f}MB"


def fmt_tokens(t: int) -> str:
    if t < 1000:
        return str(t)
    return f"{t / 1000:.1f}k"


def print_summary(rows: list[dict]) -> None:
    if not rows:
        print("No injection events found.")
        return

    by_hook: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_hook[r["hook"]].append(r)

    total_bytes = sum(r["bytes"] for r in rows)
    total_tokens = sum(r["est_tokens"] for r in rows)

    print(f"{'Hook':<25} {'Count':>6} {'Tot Bytes':>10} {'Tot Tokens':>11} {'Avg Tokens':>11} {'Max Tokens':>11}")
    print("-" * 80)

    for hook in sorted(by_hook, key=lambda h: sum(r["bytes"] for r in by_hook[h]), reverse=True):
        events = by_hook[hook]
        count = len(events)
        tot_b = sum(r["bytes"] for r in events)
        tot_t = sum(r["est_tokens"] for r in events)
        avg_t = tot_t // count
        max_t = max(r["est_tokens"] for r in events)
        print(f"{hook:<25} {count:>6} {fmt_bytes(tot_b):>10} {fmt_tokens(tot_t):>11} {fmt_tokens(avg_t):>11} {fmt_tokens(max_t):>11}")

    print("-" * 80)
    print(f"{'TOTAL':<25} {len(rows):>6} {fmt_bytes(total_bytes):>10} {fmt_tokens(total_tokens):>11}")

    # Per-session average
    sessions = set(r["session"] for r in rows)
    if len(sessions) > 1:
        avg_per_session = total_tokens // len(sessions)
        print(f"\n{len(sessions)} sessions, avg {fmt_tokens(avg_per_session)} tokens/session")

    # Top projects
    by_project: dict[str, int] = defaultdict(int)
    for r in rows:
        by_project[r["project"]] += r["est_tokens"]
    if len(by_project) > 1:
        print("\nBy project:")
        for proj in sorted(by_project, key=by_project.get, reverse=True)[:5]:
            short = proj.replace(str(Path.home()), "~")
            print(f"  {short:<50} {fmt_tokens(by_project[proj]):>8} tokens")


def print_detail(rows: list[dict], tail: int | None = None) -> None:
    if tail:
        rows = rows[-tail:]
    if not rows:
        print("No injection events found.")
        return

    print(f"{'Timestamp':<22} {'Hook':<25} {'Bytes':>8} {'Tokens':>8} {'Project'}")
    print("-" * 95)
    for r in rows:
        ts = r["_ts"].strftime("%Y-%m-%d %H:%M:%S")
        project = r["project"].replace(str(Path.home()), "~")
        # Truncate project to 30 chars
        if len(project) > 30:
            project = "..." + project[-27:]
        print(f"{ts:<22} {r['hook']:<25} {fmt_bytes(r['bytes']):>8} {fmt_tokens(r['est_tokens']):>8} {project}")


def print_by_session(rows: list[dict]) -> None:
    if not rows:
        print("No injection events found.")
        return

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_session[r["session"]].append(r)

    print(f"{'Session':<20} {'Events':>7} {'Tot Tokens':>11} {'Biggest Hook':<25} {'Biggest':>8}")
    print("-" * 80)

    for sid in sorted(by_session, key=lambda s: by_session[s][0]["_ts"]):
        events = by_session[sid]
        tot_t = sum(r["est_tokens"] for r in events)
        biggest = max(events, key=lambda r: r["est_tokens"])
        sid_short = sid[:18] if len(sid) > 18 else sid
        print(
            f"{sid_short:<20} {len(events):>7} {fmt_tokens(tot_t):>11} "
            f"{biggest['hook']:<25} {fmt_tokens(biggest['est_tokens']):>8}"
        )


def main():
    parser = argparse.ArgumentParser(description="Collate context injection sizes")
    parser.add_argument("--detail", action="store_true", help="Show per-event detail")
    parser.add_argument("--by-session", action="store_true", help="Group by session")
    parser.add_argument("--since", type=str, help="Filter to events within duration (e.g. 24h, 7d)")
    parser.add_argument("--tail", type=int, help="Show last N events (with --detail)")
    args = parser.parse_args()

    since = parse_duration(args.since) if args.since else None
    rows = read_log(since=since)

    if args.by_session:
        print_by_session(rows)
    elif args.detail:
        print_detail(rows, tail=args.tail)
    else:
        print_summary(rows)


if __name__ == "__main__":
    main()
