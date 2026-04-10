#!/bin/bash
# Zero Operators — Cascade reminder hook
# Triggered by PostToolUse on Write|Edit
# Checks if modified file is a cascade trigger and reminds about updates.

set -uo pipefail

# Read stdin (Claude Code hook JSON)
INPUT=$(cat)

# Extract the file path from tool_input
# Write tool: tool_input.file_path
# Edit tool: tool_input.file_path
FILE_PATH=$(echo "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"//;s/"//')

# If we couldn't extract a file path, exit silently
if [[ -z "$FILE_PATH" ]]; then
    exit 0
fi

# Check against cascade trigger patterns
REMINDER=""

case "$FILE_PATH" in
    *.claude/agents/*)
        REMINDER="Agent file modified. Cascade check: update setup.sh (EXPECTED_AGENTS + count), README.md (badge + roster), specs/agents.md (team counts), lead-orchestrator.md (agent count + roster), plans/zero-operators-build.md (counts). Run: ./scripts/validate-docs.sh"
        ;;
    *.claude/commands/*)
        REMINDER="Command file modified. Cascade check: update README.md (command count), docs/COMMANDS.md (add/remove entry), memory/zo-platform/STATE.md (count). Run: ./scripts/validate-docs.sh"
        ;;
    *pyproject.toml)
        REMINDER="pyproject.toml modified. If version changed, also update: src/zo/__init__.py (__version__), src/zo/cli.py (_VERSION). Run: ./scripts/validate-docs.sh"
        ;;
    *src/zo/__init__.py|*__init__.py)
        REMINDER="__init__.py modified. If version changed, also update: pyproject.toml (version), src/zo/cli.py (_VERSION). Run: ./scripts/validate-docs.sh"
        ;;
    *src/zo/cli.py|*cli.py)
        REMINDER="cli.py modified. If version or commands changed, also update: pyproject.toml (version), src/zo/__init__.py (__version__), README.md, docs/COMMANDS.md. Run: ./scripts/validate-docs.sh"
        ;;
esac

if [[ -n "$REMINDER" ]]; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "${REMINDER}"
  }
}
EOF
fi

exit 0
