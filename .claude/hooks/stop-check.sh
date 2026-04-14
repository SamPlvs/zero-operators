#!/bin/bash
# Zero Operators — Stop hook (fires after each Claude turn)
# Checks if uncommitted changes exist in cascade-trigger files
# and reminds about running validation before session ends.

set -uo pipefail

# Find repo root
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
cd "$REPO_ROOT" || exit 0

# Check for uncommitted changes in cascade-trigger paths
TRIGGER_PATHS=(
    ".claude/agents/"
    ".claude/commands/"
    "pyproject.toml"
    "src/zo/__init__.py"
    "src/zo/cli.py"
)

DIRTY_TRIGGERS=""
for path in "${TRIGGER_PATHS[@]}"; do
    if git diff --name-only HEAD -- "$path" 2>/dev/null | grep -q .; then
        DIRTY_TRIGGERS="$DIRTY_TRIGGERS $path"
    fi
    if git diff --name-only -- "$path" 2>/dev/null | grep -q .; then
        DIRTY_TRIGGERS="$DIRTY_TRIGGERS $path"
    fi
done

# Also check for untracked agent/command files
UNTRACKED=$(git ls-files --others --exclude-standard .claude/agents/ .claude/commands/ 2>/dev/null)
if [[ -n "$UNTRACKED" ]]; then
    DIRTY_TRIGGERS="$DIRTY_TRIGGERS (untracked: $UNTRACKED)"
fi

if [[ -n "$DIRTY_TRIGGERS" ]]; then
    cat <<EOF
{
  "stopReason": "Uncommitted changes in cascade-trigger files:${DIRTY_TRIGGERS}. Run ./scripts/validate-docs.sh and update cascade files per CLAUDE.md before committing."
}
EOF
fi

exit 0
