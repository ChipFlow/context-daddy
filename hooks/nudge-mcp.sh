#!/usr/bin/env bash
# PreToolUse hook that nudges Claude toward MCP tools when using search tools
# Returns additionalContext to remind about faster alternatives

set -euo pipefail

# Tool name is passed as argument or via CLAUDE_TOOL_NAME
TOOL_NAME="${1:-${CLAUDE_TOOL_NAME:-}}"

# Check if it's a search-related tool that could use MCP instead
case "$TOOL_NAME" in
  Grep|Search)
    # Nudge toward MCP for code searches
    cat << 'EOF'
{
  "decision": "approve",
  "additionalContext": "💡 For code symbols, MCP tools are faster: search_symbols(\"pattern\") for functions/classes, get_symbol_content(\"name\") for source code."
}
EOF
    ;;
  Glob)
    # Nudge toward list_files
    cat << 'EOF'
{
  "decision": "approve",
  "additionalContext": "💡 For file discovery, try list_files(\"*.py\") - it's faster than Glob for indexed projects."
}
EOF
    ;;
  *)
    # Approve without nudge
    echo '{"decision": "approve"}'
    ;;
esac
