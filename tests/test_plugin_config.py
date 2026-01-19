#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Plugin configuration validation tests.
Ensures plugin.json, hooks.json, and all referenced files are properly configured.
"""

import json
import sys
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = PROJECT_ROOT / ".claude-plugin"
HOOKS_ROOT = PROJECT_ROOT / "hooks"
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SERVERS_ROOT = PROJECT_ROOT / "servers"

# Note: hooks are autodiscovered from hooks/hooks.json, NOT in plugin.json
REQUIRED_PLUGIN_FIELDS = ["name", "version", "description", "author", "keywords", "repository"]
VALID_HOOK_TYPES = ["SessionStart", "SessionEnd", "PreCompact", "Stop", "PreToolUse", "UserPromptSubmit"]

def test_plugin_json_required_fields():
    """Validate plugin.json has all required fields."""
    print("\n" + "=" * 60)
    print("TEST 1: plugin.json required fields")
    print("=" * 60)

    plugin_path = PLUGIN_ROOT / "plugin.json"
    if not plugin_path.exists():
        print(f"❌ FAIL: plugin.json not found at {plugin_path}")
        return False

    with open(plugin_path) as f:
        plugin = json.load(f)

    missing = [field for field in REQUIRED_PLUGIN_FIELDS if field not in plugin]
    if missing:
        print(f"❌ FAIL: Missing required fields: {', '.join(missing)}")
        return False

    print("✅ PASS: All required fields present")
    for field in REQUIRED_PLUGIN_FIELDS:
        value = plugin[field]
        if isinstance(value, dict):
            print(f"  ✓ {field}: {json.dumps(value)}")
        else:
            print(f"  ✓ {field}: {value}")
    return True

def test_hooks_json_exists():
    """Validate hooks/hooks.json exists at project root (autodiscovered by Claude Code)."""
    print("\n" + "=" * 60)
    print("TEST 2: hooks/hooks.json existence")
    print("=" * 60)

    # Hooks are autodiscovered from hooks/hooks.json at plugin root
    # NOT configured in plugin.json
    hooks_path = HOOKS_ROOT / "hooks.json"

    if not hooks_path.exists():
        print(f"❌ FAIL: hooks/hooks.json not found at {hooks_path}")
        print("  Hooks won't load - Claude Code autodiscovers from hooks/hooks.json")
        return False

    print(f"✅ PASS: hooks/hooks.json exists at {hooks_path}")
    return True

def test_hooks_json_structure():
    """Validate hooks.json structure and hook types."""
    print("\n" + "=" * 60)
    print("TEST 3: hooks.json structure and hook types")
    print("=" * 60)

    hooks_path = HOOKS_ROOT / "hooks.json"
    if not hooks_path.exists():
        print(f"❌ FAIL: hooks.json not found at {hooks_path}")
        return False

    with open(hooks_path) as f:
        hooks_config = json.load(f)

    if "hooks" not in hooks_config:
        print("❌ FAIL: 'hooks' key missing from hooks.json")
        return False

    hooks = hooks_config["hooks"]
    invalid_types = [hook_type for hook_type in hooks.keys() if hook_type not in VALID_HOOK_TYPES]

    if invalid_types:
        print(f"❌ FAIL: Invalid hook types: {', '.join(invalid_types)}")
        print(f"Valid types: {', '.join(VALID_HOOK_TYPES)}")
        return False

    print(f"✅ PASS: All hook types valid ({len(hooks)} hook types defined)")
    for hook_type in hooks.keys():
        print(f"  ✓ {hook_type}")
    return True

def test_hook_scripts_exist():
    """Verify all scripts referenced in hooks.json exist."""
    print("\n" + "=" * 60)
    print("TEST 4: Hook scripts existence")
    print("=" * 60)

    hooks_path = HOOKS_ROOT / "hooks.json"
    with open(hooks_path) as f:
        hooks_config = json.load(f)

    missing_scripts = []
    checked_scripts = set()

    for hook_type, hook_configs in hooks_config["hooks"].items():
        for config in hook_configs:
            if "hooks" in config:
                for hook in config["hooks"]:
                    if hook.get("type") == "command":
                        cmd = hook["command"]
                        # Resolve ${CLAUDE_PLUGIN_ROOT}
                        if "${CLAUDE_PLUGIN_ROOT}" in cmd:
                            rel_path = cmd.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                            script_path_project = PROJECT_ROOT / rel_path
                            script_path_plugin = PLUGIN_ROOT / rel_path

                            # Check both locations
                            if script_path_project.exists():
                                script_path = script_path_project
                            elif script_path_plugin.exists():
                                script_path = script_path_plugin
                            else:
                                # Neither exists, record as missing
                                script_path = script_path_project
                        else:
                            script_path = Path(cmd)

                        if script_path not in checked_scripts:
                            checked_scripts.add(script_path)
                            if not script_path.exists():
                                missing_scripts.append((hook_type, str(script_path)))

    if missing_scripts:
        print(f"❌ FAIL: {len(missing_scripts)} missing script(s):")
        for hook_type, script in missing_scripts:
            print(f"  ✗ {hook_type}: {script}")
        return False

    print(f"✅ PASS: All {len(checked_scripts)} referenced scripts exist")
    for script in sorted(checked_scripts, key=str):
        print(f"  ✓ {script.name}")
    return True

def test_version_format():
    """Validate version follows semver format (X.Y.Z)."""
    print("\n" + "=" * 60)
    print("TEST 5: Version format (semver)")
    print("=" * 60)

    plugin_path = PLUGIN_ROOT / "plugin.json"
    with open(plugin_path) as f:
        plugin = json.load(f)

    version = plugin.get("version", "")
    semver_pattern = r'^\d+\.\d+\.\d+$'

    if not re.match(semver_pattern, version):
        print(f"❌ FAIL: Version '{version}' doesn't match semver format (X.Y.Z)")
        return False

    print(f"✅ PASS: Version '{version}' is valid semver")
    return True

def test_mcp_servers_exist():
    """Verify MCP server scripts exist."""
    print("\n" + "=" * 60)
    print("TEST 6: MCP server scripts existence")
    print("=" * 60)

    plugin_path = PLUGIN_ROOT / "plugin.json"
    with open(plugin_path) as f:
        plugin = json.load(f)

    if "mcpServers" not in plugin:
        print("⚠️  WARNING: No mcpServers defined")
        return True

    servers = plugin["mcpServers"]
    missing_servers = []

    for server_name, config in servers.items():
        if "args" in config:
            # Find the script path in args (typically second arg after 'run')
            for arg in config["args"]:
                if "${CLAUDE_PLUGIN_ROOT}" in arg:
                    rel_path = arg.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                    server_path_project = PROJECT_ROOT / rel_path
                    server_path_plugin = PLUGIN_ROOT / rel_path

                    # Check both locations
                    if not server_path_project.exists() and not server_path_plugin.exists():
                        missing_servers.append((server_name, str(server_path_project)))

    if missing_servers:
        print(f"❌ FAIL: {len(missing_servers)} missing MCP server(s):")
        for name, path in missing_servers:
            print(f"  ✗ {name}: {path}")
        return False

    print(f"✅ PASS: All {len(servers)} MCP server script(s) exist")
    for name in servers.keys():
        print(f"  ✓ {name}")
    return True

def test_marketplace_version_match():
    """Verify marketplace.json version matches plugin.json version."""
    print("\n" + "=" * 60)
    print("TEST 7: Marketplace/Plugin version consistency")
    print("=" * 60)

    plugin_path = PLUGIN_ROOT / "plugin.json"
    marketplace_path = PLUGIN_ROOT / "marketplace.json"

    with open(plugin_path) as f:
        plugin = json.load(f)
    with open(marketplace_path) as f:
        marketplace = json.load(f)

    plugin_version = plugin.get("version")

    # Find our plugin in marketplace.json
    our_plugin = None
    for p in marketplace.get("plugins", []):
        if p.get("name") == plugin.get("name"):
            our_plugin = p
            break

    if not our_plugin:
        print(f"❌ FAIL: Plugin '{plugin.get('name')}' not found in marketplace.json")
        return False

    marketplace_version = our_plugin.get("version")

    if plugin_version != marketplace_version:
        print(f"❌ FAIL: Version mismatch!")
        print(f"  plugin.json:      {plugin_version}")
        print(f"  marketplace.json: {marketplace_version}")
        return False

    print(f"✅ PASS: Versions match: {plugin_version}")
    return True

if __name__ == "__main__":
    tests = [
        test_plugin_json_required_fields,
        test_hooks_json_exists,
        test_hooks_json_structure,
        test_hook_scripts_exist,
        test_version_format,
        test_mcp_servers_exist,
        test_marketplace_version_match,
    ]

    print("\n" + "=" * 60)
    print("PLUGIN CONFIGURATION VALIDATION TESTS")
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
