#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Tests for update-context.sh, install-git-hooks.sh, and post-commit hook.
Tests the scaffolding without requiring Claude CLI authentication.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
HOOKS_DIR = PROJECT_ROOT / "hooks"


def run(cmd: list[str], cwd: str | Path | None = None, env: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=full_env, timeout=timeout)


def test_update_context_sh_exists():
    """update-context.sh exists and has valid bash syntax."""
    print("\n" + "=" * 60)
    print("TEST 1: update-context.sh exists and valid syntax")
    print("=" * 60)

    script = SCRIPTS_DIR / "update-context.sh"
    assert script.exists(), f"update-context.sh not found at {script}"

    result = run(["bash", "-n", str(script)])
    assert result.returncode == 0, f"Syntax error: {result.stderr}"

    print("✅ PASS: update-context.sh exists with valid syntax")
    return True


def test_update_context_requires_mode():
    """update-context.sh fails without --create or --update."""
    print("\n" + "=" * 60)
    print("TEST 2: update-context.sh requires --create or --update")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run(
            ["bash", str(SCRIPTS_DIR / "update-context.sh")],
            cwd=tmpdir,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        )
        assert result.returncode != 0, "Should fail without mode flag"
        assert "Must specify" in result.stderr, f"Expected usage error, got: {result.stderr}"

    print("✅ PASS: Correctly requires --create or --update")
    return True


def test_update_context_lockfile():
    """update-context.sh respects lockfile to prevent concurrent runs."""
    print("\n" + "=" * 60)
    print("TEST 3: update-context.sh lockfile mechanism")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()
        lockfile = claude_dir / ".update-context.lock"

        # Create a fresh lockfile (not stale)
        lockfile.write_text("99999")

        # Should exit 0 (silently skip) due to lockfile
        result = run(
            ["bash", str(SCRIPTS_DIR / "update-context.sh"), "--create"],
            cwd=tmpdir,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        )
        assert "already in progress" in result.stderr, f"Expected lockfile message, got: {result.stderr}"

    print("✅ PASS: Lockfile prevents concurrent runs")
    return True


def test_install_git_hooks_creates_hook():
    """install-git-hooks.sh creates post-commit hook in git repo."""
    print("\n" + "=" * 60)
    print("TEST 4: install-git-hooks.sh creates post-commit hook")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize a git repo
        run(["git", "init", tmpdir])
        run(["git", "-C", tmpdir, "config", "user.email", "test@test.com"])
        run(["git", "-C", tmpdir, "config", "user.name", "Test"])

        # Run installer
        result = run(
            ["bash", str(SCRIPTS_DIR / "install-git-hooks.sh"), tmpdir],
            cwd=tmpdir
        )
        assert result.returncode == 0, f"Installer failed: {result.stderr}"

        # Verify hook was created
        hook_path = Path(tmpdir) / ".git" / "hooks" / "post-commit"
        assert hook_path.exists(), "post-commit hook not created"
        assert os.access(hook_path, os.X_OK), "post-commit hook not executable"

        # Verify content
        content = hook_path.read_text()
        assert "context-daddy" in content, "Hook missing context-daddy marker"

        # Verify plugin path marker
        marker = Path(tmpdir) / ".claude" / ".context-daddy-path"
        assert marker.exists(), "Plugin path marker not created"

    print("✅ PASS: post-commit hook installed correctly")
    return True


def test_install_git_hooks_idempotent():
    """install-git-hooks.sh doesn't duplicate when run twice."""
    print("\n" + "=" * 60)
    print("TEST 5: install-git-hooks.sh is idempotent")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        run(["git", "init", tmpdir])
        run(["git", "-C", tmpdir, "config", "user.email", "test@test.com"])
        run(["git", "-C", tmpdir, "config", "user.name", "Test"])

        # Run twice
        run(["bash", str(SCRIPTS_DIR / "install-git-hooks.sh"), tmpdir])
        run(["bash", str(SCRIPTS_DIR / "install-git-hooks.sh"), tmpdir])

        # Count occurrences of marker
        hook_path = Path(tmpdir) / ".git" / "hooks" / "post-commit"
        content = hook_path.read_text()
        marker_count = content.count("context-daddy post-commit hook")
        assert marker_count == 1, f"Hook duplicated! Found marker {marker_count} times"

    print("✅ PASS: Idempotent - no duplication on second run")
    return True


def test_install_git_hooks_appends_to_existing():
    """install-git-hooks.sh appends to existing post-commit hook."""
    print("\n" + "=" * 60)
    print("TEST 6: install-git-hooks.sh appends to existing hook")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        run(["git", "init", tmpdir])
        run(["git", "-C", tmpdir, "config", "user.email", "test@test.com"])
        run(["git", "-C", tmpdir, "config", "user.name", "Test"])

        # Create existing hook
        hook_path = Path(tmpdir) / ".git" / "hooks" / "post-commit"
        hook_path.write_text("#!/usr/bin/env bash\necho 'existing hook'\n")
        hook_path.chmod(0o755)

        # Run installer
        result = run(["bash", str(SCRIPTS_DIR / "install-git-hooks.sh"), tmpdir])
        assert result.returncode == 0, f"Installer failed: {result.stderr}"
        assert "Appended" in result.stderr, f"Expected append message, got: {result.stderr}"

        # Verify both exist
        content = hook_path.read_text()
        assert "existing hook" in content, "Original hook content lost"
        assert "context-daddy" in content, "Our hook not appended"

    print("✅ PASS: Appends to existing hook without clobbering")
    return True


def test_install_git_hooks_skips_non_git():
    """install-git-hooks.sh gracefully skips non-git directories."""
    print("\n" + "=" * 60)
    print("TEST 7: install-git-hooks.sh skips non-git directories")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Not a git repo - should exit 0 (skip, not fail)
        result = run(["bash", str(SCRIPTS_DIR / "install-git-hooks.sh"), tmpdir])
        assert result.returncode == 0, f"Should exit 0 for non-git dir, got {result.returncode}"

    print("✅ PASS: Gracefully skips non-git directory")
    return True


def test_post_commit_hook_syntax():
    """hooks/post-commit has valid bash syntax."""
    print("\n" + "=" * 60)
    print("TEST 8: hooks/post-commit valid syntax")
    print("=" * 60)

    hook = HOOKS_DIR / "post-commit"
    assert hook.exists(), f"post-commit hook not found at {hook}"

    result = run(["bash", "-n", str(hook)])
    assert result.returncode == 0, f"Syntax error: {result.stderr}"

    print("✅ PASS: post-commit hook has valid syntax")
    return True


def test_post_commit_skips_during_rebase():
    """hooks/post-commit exits cleanly during rebase."""
    print("\n" + "=" * 60)
    print("TEST 9: post-commit skips during rebase")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        run(["git", "init", tmpdir])
        run(["git", "-C", tmpdir, "config", "user.email", "test@test.com"])
        run(["git", "-C", tmpdir, "config", "user.name", "Test"])

        # Create initial commit
        (Path(tmpdir) / "file.txt").write_text("hello")
        run(["git", "-C", tmpdir, "add", "file.txt"])
        run(["git", "-C", tmpdir, "commit", "-m", "init"])

        # Simulate rebase-in-progress
        rebase_dir = Path(tmpdir) / ".git" / "rebase-merge"
        rebase_dir.mkdir()

        # Run hook - should exit 0 without doing anything
        result = run(
            ["bash", str(HOOKS_DIR / "post-commit")],
            cwd=tmpdir,
            env={
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "GIT_DIR": str(Path(tmpdir) / ".git")
            }
        )
        assert result.returncode == 0, f"Hook should exit 0 during rebase, got {result.returncode}"

    print("✅ PASS: Skips during rebase")
    return True


def test_session_start_triggers_narrative_creation():
    """session-start.sh includes narrative creation logic."""
    print("\n" + "=" * 60)
    print("TEST 10: session-start.sh has narrative creation logic")
    print("=" * 60)

    # Verify session-start.sh contains the narrative creation trigger
    # (actually running it requires uv, scan.py deps, etc. which may not be available)
    session_start = SCRIPTS_DIR / "session-start.sh"
    content = session_start.read_text()

    assert "update-context.sh" in content, "session-start.sh should reference update-context.sh"
    assert "--background --create" in content, "Should trigger background create when no narrative"
    assert "HAS_NARRATIVE" in content, "Should check for existing narrative"

    print("✅ PASS: session-start.sh includes narrative creation logic")
    return True


def test_precompact_has_update_logic():
    """precompact.sh includes narrative update trigger."""
    print("\n" + "=" * 60)
    print("TEST 11: precompact.sh includes narrative update logic")
    print("=" * 60)

    precompact = SCRIPTS_DIR / "precompact.sh"
    content = precompact.read_text()

    assert "update-context.sh" in content, "precompact.sh should reference update-context.sh"
    assert "--background --update" in content, "Should trigger background update"
    assert "needs-reorientation" in content, "Should create reorientation marker"

    # Also verify syntax
    result = run(["bash", "-n", str(precompact)])
    assert result.returncode == 0, f"Syntax error: {result.stderr}"

    print("✅ PASS: precompact.sh includes narrative update logic")
    return True


def test_detect_project_switch_syntax():
    """hooks/detect-project-switch.sh has valid bash syntax."""
    print("\n" + "=" * 60)
    print("TEST 12: detect-project-switch.sh valid syntax")
    print("=" * 60)

    hook = HOOKS_DIR / "detect-project-switch.sh"
    assert hook.exists(), f"detect-project-switch.sh not found at {hook}"

    result = run(["bash", "-n", str(hook)])
    assert result.returncode == 0, f"Syntax error: {result.stderr}"

    print("✅ PASS: detect-project-switch.sh has valid syntax")
    return True


def test_update_context_project_flag():
    """update-context.sh accepts --project flag."""
    print("\n" + "=" * 60)
    print("TEST 13: update-context.sh accepts --project flag")
    print("=" * 60)

    script = SCRIPTS_DIR / "update-context.sh"
    content = script.read_text()
    assert "--project" in content, "update-context.sh should support --project flag"

    # Verify it doesn't fail with --project pointing to a valid dir
    # (it will fail at the claude binary step, but should parse args OK)
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / ".claude"
        claude_dir.mkdir()

        # Create a fresh lockfile so it bails early (before needing claude binary)
        lockfile = claude_dir / ".update-context.lock"
        lockfile.write_text("99999")

        result = run(
            ["bash", str(script), "--create", "--project", tmpdir],
            cwd=tmpdir,
            env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        )
        # Should bail due to lockfile, not due to bad arg parsing
        assert "already in progress" in result.stderr, f"Expected lockfile skip, got: {result.stderr}"

    print("✅ PASS: --project flag accepted correctly")
    return True


def test_detect_project_switch_same_project():
    """detect-project-switch.sh is a no-op for same project."""
    print("\n" + "=" * 60)
    print("TEST 14: detect-project-switch.sh no-op for same project")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a git repo
        run(["git", "init", tmpdir])
        run(["git", "-C", tmpdir, "config", "user.email", "test@test.com"])
        run(["git", "-C", tmpdir, "config", "user.name", "Test"])

        # Create a test file
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hello")

        # Set marker to this repo
        marker_file = Path(f"/tmp/.claude-project-root-{os.getuid()}")
        original_marker = marker_file.read_text() if marker_file.exists() else None

        try:
            # Resolve tmpdir the same way git does
            resolved_root = run(["git", "-C", tmpdir, "rev-parse", "--show-toplevel"]).stdout.strip()
            marker_file.write_text(resolved_root)

            # Feed it a file_path in the same repo
            stdin_json = json.dumps({
                "tool_input": {"file_path": str(test_file)}
            })

            result = run(
                ["bash", str(HOOKS_DIR / "detect-project-switch.sh")],
                cwd=tmpdir,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", ""),
                    "CLAUDE_PLUGIN_ROOT": str(PROJECT_ROOT),
                }
            )
            # Provide stdin via a different approach
            result = subprocess.run(
                ["bash", str(HOOKS_DIR / "detect-project-switch.sh")],
                cwd=tmpdir,
                input=stdin_json,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CLAUDE_PLUGIN_ROOT": str(PROJECT_ROOT),
                },
                timeout=10
            )

            assert result.returncode == 0, f"Should succeed, got rc={result.returncode}: {result.stderr}"
            # No additionalContext for same project
            if result.stdout.strip():
                data = json.loads(result.stdout)
                assert "additionalContext" not in data or "Switched" not in data.get("additionalContext", ""), \
                    "Should NOT report a switch for same project"
            # Empty output is also valid (no-op)
        finally:
            # Restore original marker
            if original_marker is not None:
                marker_file.write_text(original_marker)
            elif marker_file.exists():
                marker_file.unlink()

    print("✅ PASS: No-op for same project")
    return True


def test_detect_project_switch_different_project():
    """detect-project-switch.sh detects switch to different git repo."""
    print("\n" + "=" * 60)
    print("TEST 15: detect-project-switch.sh detects project switch")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two separate git repos
        repo_a = Path(tmpdir) / "repo-a"
        repo_b = Path(tmpdir) / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()

        for repo in [repo_a, repo_b]:
            run(["git", "init", str(repo)])
            run(["git", "-C", str(repo), "config", "user.email", "test@test.com"])
            run(["git", "-C", str(repo), "config", "user.name", "Test"])

        # Create a test file in repo_b
        test_file = repo_b / "test.txt"
        test_file.write_text("hello")

        # Create .claude/narrative.md in repo_b so the hook skips spawning update-context.sh
        claude_dir_b = repo_b / ".claude"
        claude_dir_b.mkdir()
        (claude_dir_b / "narrative.md").write_text("# Test Narrative\n## Summary\nTest project\n")

        # Set marker to repo_a
        marker_file = Path(f"/tmp/.claude-project-root-{os.getuid()}")
        original_marker = marker_file.read_text() if marker_file.exists() else None

        try:
            resolved_a = run(["git", "-C", str(repo_a), "rev-parse", "--show-toplevel"]).stdout.strip()
            marker_file.write_text(resolved_a)

            # Feed it a file_path in repo_b
            stdin_json = json.dumps({
                "tool_input": {"file_path": str(test_file)}
            })

            result = subprocess.run(
                ["bash", str(HOOKS_DIR / "detect-project-switch.sh")],
                cwd=str(repo_a),
                input=stdin_json,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CLAUDE_PLUGIN_ROOT": str(PROJECT_ROOT),
                },
                timeout=30
            )

            assert result.returncode == 0, f"Should succeed, got rc={result.returncode}: {result.stderr}"
            assert result.stdout.strip(), "Should produce output for project switch"

            data = json.loads(result.stdout)
            assert "additionalContext" in data, "Should include additionalContext"
            assert "SWITCH" in data["additionalContext"].upper(), \
                f"Should mention switch, got: {data['additionalContext']}"

            # Verify marker was updated
            new_marker = marker_file.read_text().strip()
            resolved_b = run(["git", "-C", str(repo_b), "rev-parse", "--show-toplevel"]).stdout.strip()
            assert new_marker == resolved_b, f"Marker should be updated to repo_b: {new_marker} vs {resolved_b}"

        finally:
            if original_marker is not None:
                marker_file.write_text(original_marker)
            elif marker_file.exists():
                marker_file.unlink()

    print("✅ PASS: Detects project switch correctly")
    return True


def test_detect_project_switch_no_file_path():
    """detect-project-switch.sh handles missing file_path gracefully."""
    print("\n" + "=" * 60)
    print("TEST 16: detect-project-switch.sh handles missing file_path")
    print("=" * 60)

    stdin_json = json.dumps({"tool_input": {}})

    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "detect-project-switch.sh")],
        input=stdin_json,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CLAUDE_PLUGIN_ROOT": str(PROJECT_ROOT),
        },
        timeout=10
    )

    assert result.returncode == 0, f"Should exit 0 gracefully, got rc={result.returncode}: {result.stderr}"
    # Should produce no output (no-op)
    assert not result.stdout.strip(), f"Should produce no output, got: {result.stdout}"

    print("✅ PASS: Handles missing file_path gracefully")
    return True


def test_detect_project_switch_spawns_context_generation():
    """detect-project-switch.sh spawns repo-map, manifest, and narrative generation on switch."""
    print("\n" + "=" * 60)
    print("TEST 17: detect-project-switch.sh spawns context generation")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two separate git repos
        repo_a = Path(tmpdir) / "repo-a"
        repo_b = Path(tmpdir) / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()

        for repo in [repo_a, repo_b]:
            run(["git", "init", str(repo)])
            run(["git", "-C", str(repo), "config", "user.email", "test@test.com"])
            run(["git", "-C", str(repo), "config", "user.name", "Test"])

        # Create some source files in repo_b so map.py/scan.py have something to index
        src_dir = repo_b / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("def hello():\n    print('hello')\n")
        (repo_b / "README.md").write_text("# Test Project B\n")

        # Create narrative in repo_b so update-context.sh is skipped (avoids needing claude binary)
        claude_dir_b = repo_b / ".claude"
        claude_dir_b.mkdir()
        (claude_dir_b / "narrative.md").write_text("# Test Narrative\n## Summary\nTest project B\n")

        # Set marker to repo_a
        marker_file = Path(f"/tmp/.claude-project-root-{os.getuid()}")
        original_marker = marker_file.read_text() if marker_file.exists() else None

        try:
            resolved_a = run(["git", "-C", str(repo_a), "rev-parse", "--show-toplevel"]).stdout.strip()
            marker_file.write_text(resolved_a)

            # Trigger project switch by editing a file in repo_b
            stdin_json = json.dumps({
                "tool_input": {"file_path": str(src_dir / "main.py")}
            })

            result = subprocess.run(
                ["bash", str(HOOKS_DIR / "detect-project-switch.sh")],
                cwd=str(repo_a),
                input=stdin_json,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "CLAUDE_PLUGIN_ROOT": str(PROJECT_ROOT),
                },
                timeout=60
            )

            assert result.returncode == 0, f"Hook failed: rc={result.returncode}, stderr={result.stderr}"

            # Parse the output
            data = json.loads(result.stdout)
            context = data.get("additionalContext", "")

            # Verify the output mentions background tasks
            assert "BACKGROUND TASKS STARTED" in context, \
                f"Should mention background tasks, got: {context}"
            assert "map.py" in context.lower() or "repo-map" in context.lower(), \
                f"Should mention repo-map generation, got: {context}"

            # Verify project manifest was created (scan.py runs synchronously)
            manifest = claude_dir_b / "project-manifest.json"
            assert manifest.exists(), \
                f"scan.py should have created project-manifest.json in {claude_dir_b}"
            manifest_data = json.loads(manifest.read_text())
            assert "project" in manifest_data, \
                f"Manifest should have project key, got: {list(manifest_data.keys())}"

            # Verify .claude/logs dir was created for map.py output
            logs_dir = claude_dir_b / "logs"
            assert logs_dir.exists(), \
                f".claude/logs should be created for background map.py output"

            # Verify project structure is included in context
            assert "src" in context, \
                f"Should include project structure with 'src' dir, got: {context}"

            # Wait briefly and check if map.py background process created the DB
            import time
            time.sleep(3)
            db_file = claude_dir_b / "repo-map.db"
            if db_file.exists():
                # If DB was created, verify it has symbols
                import sqlite3
                conn = sqlite3.connect(str(db_file))
                count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                conn.close()
                print(f"  Bonus: repo-map.db created with {count} symbol(s)")
                assert count > 0, "repo-map.db should have indexed at least one symbol"
            else:
                # map.py may still be running or uv may not have tree-sitter cached
                print("  Note: repo-map.db not yet created (background task may still be running)")

        finally:
            if original_marker is not None:
                marker_file.write_text(original_marker)
            elif marker_file.exists():
                marker_file.unlink()

    print("✅ PASS: Context generation spawned correctly on project switch")
    return True


if __name__ == "__main__":
    tests = [
        test_update_context_sh_exists,
        test_update_context_requires_mode,
        test_update_context_lockfile,
        test_install_git_hooks_creates_hook,
        test_install_git_hooks_idempotent,
        test_install_git_hooks_appends_to_existing,
        test_install_git_hooks_skips_non_git,
        test_post_commit_hook_syntax,
        test_post_commit_skips_during_rebase,
        test_session_start_triggers_narrative_creation,
        test_precompact_has_update_logic,
        test_detect_project_switch_syntax,
        test_update_context_project_flag,
        test_detect_project_switch_same_project,
        test_detect_project_switch_different_project,
        test_detect_project_switch_no_file_path,
        test_detect_project_switch_spawns_context_generation,
    ]

    print("\n" + "=" * 60)
    print("UPDATE CONTEXT & GIT HOOKS TESTS")
    print("=" * 60)

    results = []
    for test in tests:
        try:
            passed = test()
            results.append(passed)
        except Exception as e:
            print(f"❌ FAIL: {test.__name__}: {e}")
            results.append(False)

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
