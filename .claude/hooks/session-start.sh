#!/bin/bash
# Zero Operators — SessionStart hook
# Auto-loads project context at the start of every Claude Code session.
# Injects STATE.md, PRIORS.md, and recent DECISION_LOG entries so Claude
# starts every session already knowing where we are, what we've learned,
# and what decisions were made.

set -uo pipefail

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
cd "$REPO_ROOT" || exit 0

# Detect project memory directory
# Default to zo-platform (the ZO platform itself)
MEMORY_DIR="$REPO_ROOT/memory/zo-platform"

# If we're in a delivery repo worktree, check for project-specific memory
if [[ -f "$REPO_ROOT/targets/"*.target.md ]] 2>/dev/null; then
    PROJECT_NAME=$(basename "$REPO_ROOT/targets/"*.target.md .target.md 2>/dev/null | head -1)
    if [[ -d "$REPO_ROOT/memory/$PROJECT_NAME" ]]; then
        MEMORY_DIR="$REPO_ROOT/memory/$PROJECT_NAME"
    fi
fi

# Bail if no memory directory exists
if [[ ! -d "$MEMORY_DIR" ]]; then
    exit 0
fi

# Build context sections
CONTEXT=""

# ── STATE.md ──────────────────────────────────────
STATE_FILE="$MEMORY_DIR/STATE.md"
if [[ -f "$STATE_FILE" ]]; then
    STATE_CONTENT=$(cat "$STATE_FILE")
    CONTEXT="$CONTEXT
## Current State (from STATE.md)

$STATE_CONTENT
"
fi

# ── PRIORS.md ─────────────────────────────────────
PRIORS_FILE="$MEMORY_DIR/PRIORS.md"
if [[ -f "$PRIORS_FILE" ]]; then
    PRIORS_CONTENT=$(cat "$PRIORS_FILE")
    CONTEXT="$CONTEXT
## Accumulated Learnings (from PRIORS.md)

$PRIORS_CONTENT
"
fi

# ── DECISION_LOG.md (last 10 entries) ─────────────
DECISION_FILE="$MEMORY_DIR/DECISION_LOG.md"
if [[ -f "$DECISION_FILE" ]]; then
    # Extract last 10 decision entries (separated by ---)
    # Each entry starts with "## Decision:"
    TOTAL_ENTRIES=$(grep -c "^## Decision:" "$DECISION_FILE" 2>/dev/null || echo "0")
    if [[ "$TOTAL_ENTRIES" -gt 0 ]]; then
        # Get last 10 entries: find line numbers of "## Decision:" headers,
        # take the last 10, and extract from the first of those to EOF
        SKIP=$((TOTAL_ENTRIES - 10))
        if [[ $SKIP -lt 0 ]]; then SKIP=0; fi

        if [[ $SKIP -gt 0 ]]; then
            START_LINE=$(grep -n "^## Decision:" "$DECISION_FILE" | tail -10 | head -1 | cut -d: -f1)
            RECENT_DECISIONS=$(tail -n +"$START_LINE" "$DECISION_FILE")
        else
            RECENT_DECISIONS=$(cat "$DECISION_FILE")
        fi

        CONTEXT="$CONTEXT
## Recent Decisions (last 10 from DECISION_LOG.md, $TOTAL_ENTRIES total)

$RECENT_DECISIONS
"
    fi
fi

# ── Session reminders ─────────────────────────────
CONTEXT="$CONTEXT
## Session Reminders

- **Before committing**: Run \`./scripts/validate-docs.sh\` (enforced by PreToolUse hook)
- **When editing agents/commands/version files**: Follow cascade protocol in CLAUDE.md
- **Before session end**: Update STATE.md, append to DECISION_LOG.md, write session summary to memory/zo-platform/sessions/
- **On any failure**: Document in DECISION_LOG, classify root cause, add prior to PRIORS.md, fix the rule not just the symptom
"

# Output as additionalContext
# Escape newlines and quotes for JSON
ESCAPED_CONTEXT=$(echo "$CONTEXT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null)

if [[ -n "$ESCAPED_CONTEXT" ]]; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": $ESCAPED_CONTEXT
  }
}
EOF
fi

exit 0
