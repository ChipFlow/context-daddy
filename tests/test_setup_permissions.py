#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Tests for setup-permissions.py and session-start.sh permission check.
Validates the script correctly manages MCP tool permissions in settings.json
and that session-start.sh warns when permissions are missing.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SETUP_SCRIPT = SCRIPTS_DIR / "setup-permissions.py"
SESSION_START_SCRIPT = SCRIPTS_DIR / "session-start.sh"

PERMISSION_PATTERN = "mcp__plugin_context-daddy_repo-map__*"


def run_setup(home_dir: str) -> subprocess.CompletedProcess:
    """Run setup-permissions.py with a custom HOME."""
    env = {**os.environ, "HOME": home_dir}
    return subprocess.run(
        ["uv", "run", str(SETUP_SCRIPT)],
        capture_output=True, text=True, env=env, timeout=30,
    )


def run_session_start(home_dir: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run session-start.sh with a custom HOME, return result."""
    env = {**os.environ, "HOME": home_dir}
    return subprocess.run(
        ["bash", str(SESSION_START_SCRIPT)],
        capture_output=True, text=True, env=env, timeout=60,
        cwd=cwd or str(PROJECT_ROOT),
    )


def test_script_exists():
    """setup-permissions.py exists."""
    print("\n" + "=" * 60)
    print("TEST 1: setup-permissions.py exists")
    print("=" * 60)

    if not SETUP_SCRIPT.exists():
        print(f"❌ FAIL: {SETUP_SCRIPT} not found")
        return False

    print(f"✅ PASS: Script exists at {SETUP_SCRIPT}")
    return True


def test_creates_settings_from_scratch():
    """Creates settings.json when none exists."""
    print("\n" + "=" * 60)
    print("TEST 2: Creates settings.json from scratch")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_setup(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: Script exited with {result.returncode}")
            print(f"  stderr: {result.stderr}")
            return False

        settings_path = Path(tmpdir) / ".claude" / "settings.json"
        if not settings_path.exists():
            print("❌ FAIL: settings.json was not created")
            return False

        settings = json.loads(settings_path.read_text())
        allow = settings.get("permissions", {}).get("allow", [])
        if PERMISSION_PATTERN not in allow:
            print(f"❌ FAIL: Permission pattern not in allow list: {allow}")
            return False

        print("✅ PASS: Created settings.json with correct permission")
        return True


def test_adds_to_existing_settings():
    """Adds permission to existing settings without clobbering."""
    print("\n" + "=" * 60)
    print("TEST 3: Adds to existing settings")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        existing = {
            "permissions": {"allow": ["Read(**)", "Edit(**)"]},
            "other_key": "preserved",
        }
        settings_path.write_text(json.dumps(existing, indent=2))

        result = run_setup(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: Script exited with {result.returncode}")
            return False

        settings = json.loads(settings_path.read_text())
        allow = settings.get("permissions", {}).get("allow", [])

        if "Read(**)" not in allow or "Edit(**)" not in allow:
            print(f"❌ FAIL: Existing permissions were lost: {allow}")
            return False

        if PERMISSION_PATTERN not in allow:
            print(f"❌ FAIL: New permission not added: {allow}")
            return False

        if settings.get("other_key") != "preserved":
            print("❌ FAIL: Non-permission settings were clobbered")
            return False

        print(f"✅ PASS: Permission added, existing settings preserved ({len(allow)} entries)")
        return True


def test_idempotent():
    """Running twice doesn't duplicate the permission."""
    print("\n" + "=" * 60)
    print("TEST 4: Idempotent (no duplicates)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Run twice
        run_setup(tmpdir)
        result = run_setup(tmpdir)

        if result.returncode != 0:
            print(f"❌ FAIL: Second run exited with {result.returncode}")
            return False

        settings_path = Path(tmpdir) / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        allow = settings.get("permissions", {}).get("allow", [])

        count = allow.count(PERMISSION_PATTERN)
        if count != 1:
            print(f"❌ FAIL: Permission appears {count} times (expected 1)")
            return False

        if "already configured" not in result.stderr.lower():
            print(f"❌ FAIL: Expected 'already configured' message, got: {result.stderr}")
            return False

        print("✅ PASS: Idempotent - single entry after two runs")
        return True


def test_handles_empty_permissions():
    """Works when settings exists but has no permissions key."""
    print("\n" + "=" * 60)
    print("TEST 5: Handles missing permissions key")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        settings_path = Path(tmpdir) / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"theme": "dark"}, indent=2))

        result = run_setup(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: Script exited with {result.returncode}")
            return False

        settings = json.loads(settings_path.read_text())
        allow = settings.get("permissions", {}).get("allow", [])

        if PERMISSION_PATTERN not in allow:
            print(f"❌ FAIL: Permission not added: {allow}")
            return False

        if settings.get("theme") != "dark":
            print("❌ FAIL: Existing non-permission settings were lost")
            return False

        print("✅ PASS: Created permissions structure, preserved other settings")
        return True


def test_session_start_warns_when_perms_missing():
    """session-start.sh includes permission warning when no allow rule exists."""
    print("\n" + "=" * 60)
    print("TEST 6: session-start.sh warns when permissions missing")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a HOME with no MCP permission
        claude_home = Path(tmpdir) / ".claude"
        claude_home.mkdir(parents=True)
        settings_path = claude_home / "settings.json"
        settings_path.write_text(json.dumps({"permissions": {"allow": ["Read(**)"]}}, indent=2))

        result = run_session_start(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: session-start.sh exited with {result.returncode}")
            print(f"  stderr: {result.stderr[:500]}")
            return False

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ FAIL: Invalid JSON output: {result.stdout[:300]}")
            return False

        system_msg = data.get("systemMessage", "")
        context = data.get("additionalContext", "")

        if "permission" not in system_msg.lower():
            print(f"❌ FAIL: systemMessage missing permission warning: {system_msg}")
            return False

        if "MCP tool permissions not configured" not in context:
            print(f"❌ FAIL: additionalContext missing permission guidance")
            return False

        if "setup-permissions.py" not in context:
            print(f"❌ FAIL: additionalContext missing setup script reference")
            return False

        print("✅ PASS: Permission warning present in both systemMessage and additionalContext")
        return True


def test_session_start_no_warning_when_perms_present():
    """session-start.sh omits permission warning when allow rule exists."""
    print("\n" + "=" * 60)
    print("TEST 7: session-start.sh no warning when permissions present")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a HOME with the MCP permission already set
        claude_home = Path(tmpdir) / ".claude"
        claude_home.mkdir(parents=True)
        settings_path = claude_home / "settings.json"
        settings_path.write_text(json.dumps({
            "permissions": {"allow": ["Read(**)", PERMISSION_PATTERN]}
        }, indent=2))

        result = run_session_start(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: session-start.sh exited with {result.returncode}")
            print(f"  stderr: {result.stderr[:500]}")
            return False

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ FAIL: Invalid JSON output: {result.stdout[:300]}")
            return False

        system_msg = data.get("systemMessage", "")
        context = data.get("additionalContext", "")

        if "permission" in system_msg.lower() and "setup" in system_msg.lower():
            print(f"❌ FAIL: systemMessage should NOT contain permission warning: {system_msg}")
            return False

        if "MCP tool permissions not configured" in context:
            print(f"❌ FAIL: additionalContext should NOT contain permission warning")
            return False

        print("✅ PASS: No permission warning when permissions are configured")
        return True


def test_session_start_no_warning_with_no_settings_file():
    """session-start.sh warns when ~/.claude/settings.json doesn't exist."""
    print("\n" + "=" * 60)
    print("TEST 8: session-start.sh warns when no settings.json")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # HOME with no .claude/settings.json at all
        result = run_session_start(tmpdir)
        if result.returncode != 0:
            print(f"❌ FAIL: session-start.sh exited with {result.returncode}")
            print(f"  stderr: {result.stderr[:500]}")
            return False

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ FAIL: Invalid JSON output: {result.stdout[:300]}")
            return False

        context = data.get("additionalContext", "")

        if "MCP tool permissions not configured" not in context:
            print(f"❌ FAIL: Should warn when settings.json doesn't exist")
            return False

        print("✅ PASS: Warning present when no settings.json exists")
        return True


if __name__ == "__main__":
    tests = [
        test_script_exists,
        test_creates_settings_from_scratch,
        test_adds_to_existing_settings,
        test_idempotent,
        test_handles_empty_permissions,
        test_session_start_warns_when_perms_missing,
        test_session_start_no_warning_when_perms_present,
        test_session_start_no_warning_with_no_settings_file,
    ]

    print("\n" + "=" * 60)
    print("SETUP-PERMISSIONS TESTS")
    print("=" * 60)

    results = [test() for test in tests]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print(f"❌ {total - passed} test(s) failed")
        sys.exit(1)
