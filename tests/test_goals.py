#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Tests for scripts/goals.py - cross-session goal tracking.
Tests use temp directories for HOME and project root to avoid side effects.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GOALS_SCRIPT = PROJECT_ROOT / "scripts" / "goals.py"
SESSION_START_SCRIPT = PROJECT_ROOT / "scripts" / "session-start.sh"


def run_goals(args: list[str], home_dir: str, cwd: str | None = None,
              check: bool = True) -> subprocess.CompletedProcess:
    """Run goals.py with a custom HOME."""
    env = {**os.environ, "HOME": home_dir}
    result = subprocess.run(
        ["uv", "run", str(GOALS_SCRIPT)] + args,
        capture_output=True, text=True, env=env, timeout=30,
        cwd=cwd or str(PROJECT_ROOT),
    )
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
    return result


def get_current_goal_raw(claude_dir: Path) -> str | None:
    """Read the raw .current-goal file content."""
    p = claude_dir / ".current-goal"
    return p.read_text().strip() if p.exists() else None


def get_current_goal(claude_dir: Path) -> str | None:
    """Read the .current-goal file, returning just the UUID part."""
    raw = get_current_goal_raw(claude_dir)
    if raw is None:
        return None
    # v2 format: UUID:step-id, v1 format: bare UUID
    return raw.split(":")[0]


def get_index(claude_dir: Path) -> dict:
    """Read active-goals.json."""
    p = claude_dir / "active-goals.json"
    return json.loads(p.read_text()) if p.exists() else {}


def extract_goal_id(output: str) -> str:
    """Extract the UUID from 'Created goal: UUID (slug)' output."""
    line = output.split("Created goal: ")[1].split("\n")[0].strip()
    # v2 format: "UUID (slug)" -> just UUID
    return line.split(" ")[0]


def test_script_exists():
    """goals.py exists and has valid syntax."""
    print("\n" + "=" * 60)
    print("TEST 1: Script exists and has valid syntax")
    print("=" * 60)

    if not GOALS_SCRIPT.exists():
        print(f"❌ FAIL: {GOALS_SCRIPT} not found")
        return False

    result = subprocess.run(
        ["python3", "-c", f"import py_compile; py_compile.compile('{GOALS_SCRIPT}', doraise=True)"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"❌ FAIL: Syntax error: {result.stderr}")
        return False

    print("✅ PASS: Script exists and compiles")
    return True


def test_create_goal():
    """Create goal - file created, index updated, set as current."""
    print("\n" + "=" * 60)
    print("TEST 2: Create goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        result = run_goals(["create", "Test Goal", "This is a test objective"], home, str(project))
        if result.returncode != 0:
            print(f"❌ FAIL: Create failed: {result.stderr}")
            return False

        # Check goal file was created
        goals_dir = Path(home) / ".claude" / "goals"
        goal_files = list(goals_dir.glob("*.md"))
        if len(goal_files) != 1:
            print(f"❌ FAIL: Expected 1 goal file, got {len(goal_files)}")
            return False

        goal_content = goal_files[0].read_text()
        assert "# Goal: Test Goal" in goal_content, "Title not in goal file"
        assert "This is a test objective" in goal_content, "Objective not in goal file"
        assert "**Status**: active" in goal_content, "Status not set"

        # Check current goal set
        current = get_current_goal(project / ".claude")
        assert current == goal_files[0].stem, f"Current goal mismatch: {current} vs {goal_files[0].stem}"

        # Check index updated
        index = get_index(project / ".claude")
        assert len(index.get("goals", [])) == 1, "Index should have 1 goal"
        assert index["goals"][0]["name"] == "Test Goal", "Index name mismatch"

        print("✅ PASS: Goal created with file, index, and current marker")
        return True


def test_list_goals():
    """List goals shows created goals."""
    print("\n" + "=" * 60)
    print("TEST 3: List goals")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        # Create two goals
        run_goals(["create", "Goal A", "Objective A"], home, str(project))
        run_goals(["create", "Goal B", "Objective B"], home, str(project))

        result = run_goals(["list"], home, str(project))
        if result.returncode != 0:
            print(f"❌ FAIL: List failed: {result.stderr}")
            return False

        output = result.stdout
        # At least the current goal should appear
        if "Goal B" not in output and "Goal A" not in output:
            print(f"❌ FAIL: Goals not in list output: {output}")
            return False

        # Test --all flag
        result_all = run_goals(["list", "--all"], home, str(project))
        if "Goal A" not in result_all.stdout or "Goal B" not in result_all.stdout:
            print(f"❌ FAIL: --all should show both goals: {result_all.stdout}")
            return False

        print("✅ PASS: List shows goals correctly")
        return True


def test_switch_goal():
    """Switch goal updates .current-goal."""
    print("\n" + "=" * 60)
    print("TEST 4: Switch goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        # Create two goals
        r1 = run_goals(["create", "Goal A", "Obj A"], home, str(project))
        id_a = extract_goal_id(r1.stdout)

        r2 = run_goals(["create", "Goal B", "Obj B"], home, str(project))
        id_b = extract_goal_id(r2.stdout)

        # Current should be B (last created)
        current = get_current_goal(project / ".claude")
        assert current == id_b, f"Expected {id_b}, got {current}"

        # Switch to A
        run_goals(["switch", id_a], home, str(project))
        current = get_current_goal(project / ".claude")
        assert current == id_a, f"Expected {id_a} after switch, got {current}"

        print("✅ PASS: Switch updates current goal")
        return True


def test_unset_goal():
    """Unset removes .current-goal marker."""
    print("\n" + "=" * 60)
    print("TEST 5: Unset goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        run_goals(["create", "Test", "Obj"], home, str(project))
        assert get_current_goal(project / ".claude") is not None, "Should have current goal"

        run_goals(["unset"], home, str(project))
        assert get_current_goal(project / ".claude") is None, "Should have no current goal"

        print("✅ PASS: Unset removes current goal marker")
        return True


def test_update_step_complete():
    """Update step with --complete marks step done and advances marker."""
    print("\n" + "=" * 60)
    print("TEST 6: Update step --complete")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        # Create goal then manually add steps
        r = run_goals(["create", "Multi Step", "Testing steps"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Add more steps
        run_goals(["add-step", goal_id, "Step two"], home, str(project))
        run_goals(["add-step", goal_id, "Step three"], home, str(project))

        # Complete step 1 (the default "Define plan steps")
        run_goals(["update-step", goal_id, "1", "--complete"], home, str(project))

        # Read goal file and verify
        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        assert "[x]" in content and "Define plan steps" in content, "Step 1 should be completed"
        assert "← current" in content, "Should have a current marker"

        # Verify index updated
        index = get_index(project / ".claude")
        goal_entry = next(g for g in index["goals"] if g["id"] == goal_id)
        assert goal_entry["current_step"] == 2, f"Current step should be 2, got {goal_entry['current_step']}"

        print("✅ PASS: Step completed and marker advanced")
        return True


def test_add_learning():
    """Add learning appears in goal file."""
    print("\n" + "=" * 60)
    print("TEST 7: Add learning")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Learn Goal", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        run_goals(["add-learning", goal_id, "Direct AST annotation doesn't work because optimisation strips it."], home, str(project))

        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        if "Direct AST annotation" not in content:
            print(f"❌ FAIL: Learning not in goal file")
            return False

        if "## Approaches & Learnings" not in content:
            print("❌ FAIL: Missing Approaches section")
            return False

        print("✅ PASS: Learning added to goal file")
        return True


def test_add_commit():
    """Add commit appears in Recent Activity, trims to 10."""
    print("\n" + "=" * 60)
    print("TEST 8: Add commit (with trim)")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Commit Goal", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Add 12 commits - only 10 should remain
        for i in range(12):
            run_goals(["add-commit", goal_id, f"abc{i:04d}", f"Commit message {i}"], home, str(project))

        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        # Count activity entries
        activity_lines = [l for l in content.split("\n") if l.startswith("- `")]
        if len(activity_lines) != 10:
            print(f"❌ FAIL: Expected 10 activity entries, got {len(activity_lines)}")
            return False

        # Most recent should be first
        if "abc0011" not in activity_lines[0]:
            print(f"❌ FAIL: Most recent commit should be first: {activity_lines[0]}")
            return False

        print("✅ PASS: Commits tracked and trimmed to 10")
        return True


def test_add_step():
    """Add step at correct position."""
    print("\n" + "=" * 60)
    print("TEST 9: Add step")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Step Goal", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Add step at end
        run_goals(["add-step", goal_id, "Last step"], home, str(project))

        # Add step after position 1
        run_goals(["add-step", goal_id, "Middle step", "--after", "1"], home, str(project))

        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        lines = [l for l in content.split("\n") if l.startswith("- [")]
        if len(lines) != 3:
            print(f"❌ FAIL: Expected 3 steps, got {len(lines)}: {lines}")
            return False

        # Middle step should be second
        if "Middle step" not in lines[1]:
            print(f"❌ FAIL: Middle step should be second: {lines}")
            return False

        print("✅ PASS: Steps inserted at correct positions")
        return True


def test_link_project():
    """Link project adds project to goal."""
    print("\n" + "=" * 60)
    print("TEST 10: Link project")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        other_project = Path(tmpdir) / "other-project"
        other_project.mkdir()
        (other_project / ".claude").mkdir()

        r = run_goals(["create", "Multi Project", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        run_goals(["link-project", goal_id, str(other_project), "--role", "dependency"], home, str(project))

        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        if str(other_project.resolve()) not in content:
            print(f"❌ FAIL: Other project not in goal file")
            return False

        if "(dependency)" not in content:
            print("❌ FAIL: Role not set correctly")
            return False

        # Check other project has an index now
        other_index = get_index(other_project / ".claude")
        other_goals = other_index.get("goals", [])
        if not any(g["id"] == goal_id for g in other_goals):
            print(f"❌ FAIL: Goal not in other project's index")
            return False

        print("✅ PASS: Project linked with correct role")
        return True


def test_archive():
    """Archive changes status, moves file, clears current."""
    print("\n" + "=" * 60)
    print("TEST 11: Archive goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Archive Me", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Verify it exists
        assert (Path(home) / ".claude" / "goals" / f"{goal_id}.md").exists()

        run_goals(["archive", goal_id], home, str(project))

        # Original file should be gone
        assert not (Path(home) / ".claude" / "goals" / f"{goal_id}.md").exists(), "Original should be removed"

        # Should be in archive
        archived = Path(home) / ".claude" / "goals" / ".archive" / f"{goal_id}.md"
        assert archived.exists(), "Should be in archive"

        # Status should be archived
        assert "**Status**: archived" in archived.read_text(), "Status should be archived"

        # Current goal should be cleared
        assert get_current_goal(project / ".claude") is None, "Current goal should be cleared"

        # Index should not contain it
        index = get_index(project / ".claude")
        assert not any(g["id"] == goal_id for g in index.get("goals", [])), "Should not be in index"

        print("✅ PASS: Goal archived correctly")
        return True


def test_sync_discovers_goals():
    """Sync discovers cross-project goals."""
    print("\n" + "=" * 60)
    print("TEST 12: Sync discovers goals")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        # Create a goal from this project
        r = run_goals(["create", "Sync Test", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Delete the index to simulate fresh sync
        (project / ".claude" / "active-goals.json").unlink()

        # Run sync
        run_goals(["sync"], home, str(project))

        # Should rediscover the goal
        index = get_index(project / ".claude")
        assert len(index.get("goals", [])) == 1, f"Should find 1 goal, got {len(index.get('goals', []))}"
        assert index["goals"][0]["id"] == goal_id, "Should find the right goal"

        print("✅ PASS: Sync discovers goals")
        return True


def test_sync_idempotent():
    """Sync is idempotent."""
    print("\n" + "=" * 60)
    print("TEST 13: Sync is idempotent")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        run_goals(["create", "Idem Test", "Obj"], home, str(project))

        # Run sync twice
        run_goals(["sync"], home, str(project))
        index1 = get_index(project / ".claude")

        run_goals(["sync"], home, str(project))
        index2 = get_index(project / ".claude")

        assert len(index1.get("goals", [])) == len(index2.get("goals", [])), "Sync should be idempotent"

        print("✅ PASS: Sync is idempotent")
        return True


def test_partial_uuid():
    """Partial UUID matching works."""
    print("\n" + "=" * 60)
    print("TEST 14: Partial UUID matching")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Partial Test", "Obj"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Use first 4 chars
        short_id = goal_id[:4]
        result = run_goals(["show", short_id], home, str(project))
        if result.returncode != 0:
            print(f"❌ FAIL: Partial UUID failed: {result.stderr}")
            return False

        if "Partial Test" not in result.stdout:
            print(f"❌ FAIL: Show with partial UUID didn't return goal")
            return False

        # Too short should fail
        result = run_goals(["show", "ab"], home, str(project), check=False)
        if result.returncode == 0:
            print("❌ FAIL: 2-char UUID should fail")
            return False

        print("✅ PASS: Partial UUID matching works")
        return True


def test_show_current():
    """Show without args shows current goal."""
    print("\n" + "=" * 60)
    print("TEST 15: Show current goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        run_goals(["create", "Current Show", "My objective"], home, str(project))

        result = run_goals(["show"], home, str(project))
        if result.returncode != 0:
            print(f"❌ FAIL: Show current failed: {result.stderr}")
            return False

        if "Current Show" not in result.stdout:
            print(f"❌ FAIL: Current goal not shown")
            return False

        print("✅ PASS: Show without args shows current goal")
        return True


def test_goal_focus():
    """Focus command updates .current-goal with step ID."""
    print("\n" + "=" * 60)
    print("TEST 16: Goal focus updates .current-goal with step ID")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Focus Test", "Test focus"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Add steps
        run_goals(["add-step", goal_id, "Implement feature"], home, str(project))
        run_goals(["add-step", goal_id, "Write tests"], home, str(project))

        # Focus on second added step (should be 'implement-feature' or similar)
        # First, read the goal to find step IDs
        show_result = run_goals(["show", goal_id], home, str(project))
        content = show_result.stdout

        # Extract step IDs from the output
        step_ids = []
        for line in content.split("\n"):
            import re
            m = re.match(r"^- \[[ x]\]\s*\[([a-z0-9-]+)\]", line)
            if m:
                step_ids.append(m.group(1))

        assert len(step_ids) >= 2, f"Expected at least 2 step IDs, got {step_ids}"

        # Focus on the second step
        target_step = step_ids[1]
        result = run_goals(["focus", target_step], home, str(project))
        assert result.returncode == 0, f"Focus failed: {result.stderr}"
        assert target_step in result.stdout, f"Step ID not in output: {result.stdout}"

        # Verify .current-goal format is UUID:step-id
        raw = get_current_goal_raw(project / ".claude")
        assert ":" in raw, f"Expected UUID:step-id format, got: {raw}"
        parts = raw.split(":")
        assert parts[0] == goal_id, f"UUID mismatch: {parts[0]} vs {goal_id}"
        assert parts[1] == target_step, f"Step ID mismatch: {parts[1]} vs {target_step}"

        print("✅ PASS: Focus updates .current-goal with step ID")
        return True


def test_goal_context():
    """Goal context returns project-filtered data."""
    print("\n" + "=" * 60)
    print("TEST 17: Goal context returns project-scoped data")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Context Test", "Test context output"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        run_goals(["add-step", goal_id, "First step"], home, str(project))
        run_goals(["add-learning", goal_id, "Learned something important"], home, str(project))

        # Run context command
        result = run_goals(["context"], home, str(project))
        assert result.returncode == 0, f"Context failed: {result.stderr}"

        ctx = json.loads(result.stdout)
        assert ctx.get("goal_id") == goal_id, f"Goal ID mismatch: {ctx.get('goal_id')}"
        assert ctx.get("name") == "Context Test", f"Name mismatch: {ctx.get('name')}"
        assert ctx.get("slug") == "context-test", f"Slug mismatch: {ctx.get('slug')}"
        assert ctx.get("total_steps") >= 2, f"Expected >= 2 steps, got {ctx.get('total_steps')}"
        assert ctx.get("plan_summary"), "Plan summary should not be empty"
        assert "Learned something" in ctx.get("recent_learnings", ""), \
            f"Learning not in context: {ctx.get('recent_learnings')}"

        print("✅ PASS: Context returns project-scoped data")
        return True


def test_backwards_compat_bare_uuid():
    """Bare UUID in .current-goal (v1 format) still works."""
    print("\n" + "=" * 60)
    print("TEST 18: Backwards compat - bare UUID in .current-goal")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Compat Test", "Test backwards compat"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Manually write bare UUID (v1 format) to .current-goal
        (project / ".claude" / ".current-goal").write_text(goal_id + "\n")

        # Show should still work
        result = run_goals(["show"], home, str(project))
        assert result.returncode == 0, f"Show failed with bare UUID: {result.stderr}"
        assert "Compat Test" in result.stdout, "Goal not shown with bare UUID"

        # Context should still work
        result = run_goals(["context"], home, str(project))
        assert result.returncode == 0, f"Context failed with bare UUID: {result.stderr}"
        ctx = json.loads(result.stdout)
        assert ctx.get("goal_id") == goal_id, "Context should work with bare UUID"

        print("✅ PASS: Bare UUID backwards compat works")
        return True


def test_slug_lookup():
    """Goals can be found by slug."""
    print("\n" + "=" * 60)
    print("TEST 19: Slug-based goal lookup")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Slug Lookup Test", "Test slug-based lookup"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        # Show by slug
        result = run_goals(["show", "slug-lookup-test"], home, str(project))
        assert result.returncode == 0, f"Show by slug failed: {result.stderr}"
        assert "Slug Lookup Test" in result.stdout, "Goal not found by slug"

        # Switch by slug
        result = run_goals(["switch", "slug-lookup-test"], home, str(project))
        assert result.returncode == 0, f"Switch by slug failed: {result.stderr}"

        print("✅ PASS: Slug-based lookup works")
        return True


def test_step_ids_auto_generated():
    """Step IDs are auto-generated from description."""
    print("\n" + "=" * 60)
    print("TEST 20: Step IDs auto-generated")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Step ID Test", "Test step IDs"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        run_goals(["add-step", goal_id, "Add source annotations"], home, str(project))
        run_goals(["add-step", goal_id, "Write integration tests"], home, str(project))

        # Read goal file and verify step IDs exist
        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()

        import re
        step_id_matches = re.findall(r"\[([a-z0-9-]+)\]", content)
        # Filter to only step IDs (inside checkbox lines)
        step_lines = [l for l in content.split("\n") if l.startswith("- [")]
        step_ids = []
        for line in step_lines:
            m = re.search(r"\[([a-z0-9-]+)\]\s", line)
            if m:
                step_ids.append(m.group(1))

        assert len(step_ids) >= 3, f"Expected at least 3 step IDs, got {step_ids}"
        assert "define-plan" in step_ids, f"Default step ID 'define-plan' not found: {step_ids}"

        # All IDs should be unique
        assert len(step_ids) == len(set(step_ids)), f"Step IDs not unique: {step_ids}"

        print(f"✅ PASS: Step IDs auto-generated: {step_ids}")
        return True


def test_update_step_by_id():
    """Update step by step ID (not just number)."""
    print("\n" + "=" * 60)
    print("TEST 21: Update step by step ID")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        project = Path(tmpdir) / "myproject"
        project.mkdir()
        (project / ".claude").mkdir()

        r = run_goals(["create", "Step By ID", "Test updating by ID"], home, str(project))
        goal_id = extract_goal_id(r.stdout)

        run_goals(["add-step", goal_id, "Implement feature"], home, str(project))

        # Complete step by ID
        result = run_goals(["update-step", goal_id, "define-plan", "--complete"], home, str(project))
        assert result.returncode == 0, f"Update by ID failed: {result.stderr}"

        # Verify step is completed
        goal_file = Path(home) / ".claude" / "goals" / f"{goal_id}.md"
        content = goal_file.read_text()
        assert "[x] [define-plan]" in content, "Step should be marked complete"

        print("✅ PASS: Update step by ID works")
        return True


def test_migrate_v1_goal():
    """Migration adds slug and step IDs to v1 goals."""
    print("\n" + "=" * 60)
    print("TEST 22: Migrate v1 goal to v2")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        home = tmpdir
        goals_dir = Path(home) / ".claude" / "goals"
        goals_dir.mkdir(parents=True)

        # Create a v1 goal file directly (no Slug field, no step IDs)
        v1_content = """# Goal: Legacy Goal

**ID**: deadbeef
**Status**: active
**Created**: 2026-01-01
**Updated**: 2026-01-15

## Objective

A legacy goal from before v2.

## Projects

- /tmp/myproject (primary)

## Plan

- [x] First step done
- [ ] Second step in progress  ← current
- [ ] Third step pending

## Approaches & Learnings

### 2026-01-10
Found a good approach.

## Recent Activity

- `abc1234` (myproject) 2026-01-15: Fixed something
"""
        goal_file = goals_dir / "deadbeef.md"
        goal_file.write_text(v1_content)

        # Run migrate
        env = {**os.environ, "HOME": home}
        result = subprocess.run(
            ["uv", "run", str(GOALS_SCRIPT), "migrate"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert result.returncode == 0, f"Migrate failed: {result.stderr}"
        assert "Migrated" in result.stdout, f"Expected migration message: {result.stdout}"

        # Verify v2 format
        content = goal_file.read_text()
        assert "**Slug**: legacy-goal" in content, f"Slug not added: {content[:200]}"

        # Verify step IDs were added
        import re
        step_lines = [l for l in content.split("\n") if l.startswith("- [")]
        for line in step_lines:
            assert re.search(r"\[[a-z0-9-]+\]", line), f"Step missing ID: {line}"

        # Verify done/current markers preserved
        assert "[x]" in content, "Completed step should be preserved"
        assert "← current" in content, "Current marker should be preserved"

        print("✅ PASS: V1 goal migrated to v2 with slug and step IDs")
        return True


if __name__ == "__main__":
    tests = [
        test_script_exists,
        test_create_goal,
        test_list_goals,
        test_switch_goal,
        test_unset_goal,
        test_update_step_complete,
        test_add_learning,
        test_add_commit,
        test_add_step,
        test_link_project,
        test_archive,
        test_sync_discovers_goals,
        test_sync_idempotent,
        test_partial_uuid,
        test_show_current,
        test_goal_focus,
        test_goal_context,
        test_backwards_compat_bare_uuid,
        test_slug_lookup,
        test_step_ids_auto_generated,
        test_update_step_by_id,
        test_migrate_v1_goal,
    ]

    print("\n" + "=" * 60)
    print("GOALS TRACKING TESTS")
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
