#!/bin/bash
# Zero Operators — Pre-commit documentation validation hook
# Triggered by PreToolUse on Bash(git commit *)
# Reads Claude Code hook JSON from stdin, runs validate-docs.sh,
# blocks commit if validation fails.

set -uo pipefail

# Find repo root relative to this hook
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
VALIDATE_SCRIPT="$REPO_ROOT/scripts/validate-docs.sh"

# If validation script doesn't exist, allow commit (graceful degradation)
if [[ ! -x "$VALIDATE_SCRIPT" ]]; then
    exit 0
fi

# Run validation, capture output
VALIDATION_OUTPUT=$("$VALIDATE_SCRIPT" 2>&1)
VALIDATION_EXIT=$?

if [[ $VALIDATION_EXIT -ne 0 ]]; then
    # Validation failed — block the commit
    # Strip ANSI color codes for clean JSON
    CLEAN_OUTPUT=$(echo "$VALIDATION_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g')

    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Documentation consistency check failed. Fix the issues below before committing:\n\n${CLEAN_OUTPUT//
/\\n}"
  }
}
EOF
    exit 0
fi

# Validation passed — allow silently
exit 0
