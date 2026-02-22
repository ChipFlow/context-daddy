#!/usr/bin/env bash
# Install context-daddy git hooks into the current project
# Safe to run multiple times (idempotent)
#
# Usage: install-git-hooks.sh [project_root]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="${1:-${PWD}}"

# Verify we're in a git repo
if ! git -C "${PROJECT_ROOT}" rev-parse --git-dir &>/dev/null; then
    echo "Not a git repository: ${PROJECT_ROOT}" >&2
    exit 0  # Don't fail - just skip
fi

GIT_DIR=$(cd "${PROJECT_ROOT}" && git rev-parse --git-dir)
# Resolve relative .git path against PROJECT_ROOT
if [[ "${GIT_DIR}" != /* ]]; then
    GIT_DIR="${PROJECT_ROOT}/${GIT_DIR}"
fi
HOOKS_DIR="${GIT_DIR}/hooks"
CLAUDE_DIR="${PROJECT_ROOT}/.claude"

mkdir -p "${HOOKS_DIR}"
mkdir -p "${CLAUDE_DIR}"

# Save plugin path so the hook can find our scripts
echo "${PLUGIN_ROOT}" > "${CLAUDE_DIR}/.context-daddy-path"

# Install post-commit hook
POST_COMMIT="${HOOKS_DIR}/post-commit"
MARKER="# context-daddy post-commit hook"

if [[ -f "${POST_COMMIT}" ]]; then
    # Check if our hook is already installed
    if grep -q "${MARKER}" "${POST_COMMIT}" 2>/dev/null; then
        # Already installed
        exit 0
    fi

    # Existing hook - append ours
    cat >> "${POST_COMMIT}" << HOOK

${MARKER}
source "${PLUGIN_ROOT}/hooks/post-commit" 2>/dev/null || true
HOOK
    echo "Appended context-daddy hook to existing post-commit" >&2
else
    # No existing hook - create one
    cat > "${POST_COMMIT}" << HOOK
#!/usr/bin/env bash
${MARKER}
source "${PLUGIN_ROOT}/hooks/post-commit" 2>/dev/null || true
HOOK
    chmod +x "${POST_COMMIT}"
    echo "Installed context-daddy post-commit hook" >&2
fi
