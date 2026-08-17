#!/bin/bash
# zo-hookkit.sh — thin shim routing Claude Code hook events to zo.hookkit.
#
# Part of the v2 enforcement plane (WS-A, plans/zo-v2-rearchitecture.md).
# Usage (from .claude/settings.json):
#   bash .claude/hooks/zo-hookkit.sh <event> 2>/dev/null || exit 0
#
# Fail-open by design: any missing precondition exits 0 silently. Blocking
# and denials are emitted as JSON on stdout by zo.hookkit, never via exit
# codes (matches the existing hook convention in this directory).
set -uo pipefail

EVENT="${1:-}"
[[ -z "$EVENT" ]] && exit 0

HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"

# Only run in the ZO platform repo — delivery repos never carry ZO hooks
# (specs/architecture.md isolation rule).
[[ -d "$REPO_ROOT/src/zo" ]] || exit 0

# Prefer the project venv so pydantic imports resolve; fall back to system
# python3 (zo.hookkit itself is fail-open on ImportError via the || below).
PY="python3"
[[ -x "$REPO_ROOT/.venv/bin/python3" ]] && PY="$REPO_ROOT/.venv/bin/python3"

# Pre-set ZO_REPO_ROOT wins (lets tests point the handlers at a sandbox).
export ZO_REPO_ROOT="${ZO_REPO_ROOT:-$REPO_ROOT}"
# Wall-clock stamp of the hook event (WS-C heartbeat; cheap, informational —
# the heartbeat handler stamps its own UTC time and does not require this).
export ZO_HOOK_EVENT_TS="$(date -u +%s)"
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m zo.hookkit "$EVENT" || exit 0
exit 0
