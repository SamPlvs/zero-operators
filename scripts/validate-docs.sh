#!/bin/bash
# Zero Operators — Documentation Consistency Validator
# Checks that documentation claims match codebase reality.
# Run: ./scripts/validate-docs.sh
#
# Exit 0 = all pass, Exit 1 = any fail
# Uses same format as setup.sh
# macOS + Linux compatible (no grep -P)

set -uo pipefail

# Navigate to repo root (script may be called from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 1

# Colors (matches setup.sh)
AMBER='\033[38;2;240;192;64m'
GREEN='\033[38;2;80;200;80m'
RED='\033[38;2;240;80;80m'
DIM='\033[38;2;100;100;100m'
RESET='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() { echo -e "  ${GREEN}✓${RESET} $1"; ((PASS_COUNT++)); }
fail() { echo -e "  ${RED}✗${RESET} $1"; ((FAIL_COUNT++)); }
warn() { echo -e "  ${AMBER}⚠${RESET} $1"; ((WARN_COUNT++)); }

# Extract a number from a pattern in a file. Usage: extract_num "file" "sed-pattern"
extract_num() {
    local result
    result=$(sed -n "$2" "$1" 2>/dev/null | head -1)
    echo "${result:-?}"
}

echo ""
echo -e "${AMBER}Zero Operators — Documentation Consistency Validator${RESET}"
echo -e "${DIM}─────────────────────────────────────────────────────${RESET}"
echo ""

# ─────────────────────────────────────────────────────
# Check 1: Agent file count vs documented counts
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 1: Agent file count...${RESET}"
ACTUAL_AGENTS=$(find .claude/agents -maxdepth 1 -name "*.md" -type f | wc -l | tr -d ' ')

# README badge: agents-17_defined
README_AGENTS=$(grep -oE 'agents-[0-9]+' README.md | head -1 | grep -oE '[0-9]+')
README_AGENTS="${README_AGENTS:-?}"
if [[ "$README_AGENTS" == "$ACTUAL_AGENTS" ]]; then
    pass "README.md badge: ${ACTUAL_AGENTS} agents"
else
    fail "README.md badge says ${README_AGENTS}, actual is ${ACTUAL_AGENTS}"
fi

# setup.sh hardcoded count: AGENT_COUNT -eq 17
SETUP_COUNT=$(grep -oE 'AGENT_COUNT -eq [0-9]+' setup.sh | head -1 | grep -oE '[0-9]+')
SETUP_COUNT="${SETUP_COUNT:-?}"
if [[ "$SETUP_COUNT" == "$ACTUAL_AGENTS" ]]; then
    pass "setup.sh count: ${ACTUAL_AGENTS}"
else
    fail "setup.sh expects ${SETUP_COUNT}, actual is ${ACTUAL_AGENTS}"
fi

# lead-orchestrator.md: "17 pre-defined agents"
LO_COUNT=$(grep -oE '[0-9]+ pre-defined agents' .claude/agents/lead-orchestrator.md | head -1 | grep -oE '[0-9]+')
LO_COUNT="${LO_COUNT:-?}"
if [[ "$LO_COUNT" == "$ACTUAL_AGENTS" ]]; then
    pass "lead-orchestrator.md: ${ACTUAL_AGENTS} pre-defined"
else
    fail "lead-orchestrator.md says ${LO_COUNT} pre-defined, actual is ${ACTUAL_AGENTS}"
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 2: Agent name registry (setup.sh vs files)
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 2: Agent name registry...${RESET}"

# Extract agent names from files
ACTUAL_NAMES=$(find .claude/agents -maxdepth 1 -name "*.md" -type f -exec basename {} .md \; | sort)

# Extract names from setup.sh EXPECTED_AGENTS array
# Grab lines between ( and ), extract hyphenated words
SETUP_NAMES=$(sed -n '/EXPECTED_AGENTS=(/,/)/p' setup.sh | grep -oE '[a-z][-a-z]*' | sort)

# Compare both directions
MISSING_FROM_SETUP=$(comm -23 <(echo "$ACTUAL_NAMES") <(echo "$SETUP_NAMES"))
MISSING_FROM_DIR=$(comm -13 <(echo "$ACTUAL_NAMES") <(echo "$SETUP_NAMES"))

if [[ -z "$MISSING_FROM_SETUP" && -z "$MISSING_FROM_DIR" ]]; then
    pass "All agent files match setup.sh EXPECTED_AGENTS"
else
    if [[ -n "$MISSING_FROM_SETUP" ]]; then
        fail "Agents in .claude/agents/ but NOT in setup.sh: $(echo $MISSING_FROM_SETUP | tr '\n' ', ')"
    fi
    if [[ -n "$MISSING_FROM_DIR" ]]; then
        fail "Agents in setup.sh but NO .md file: $(echo $MISSING_FROM_DIR | tr '\n' ', ')"
    fi
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 3: Command file count vs documented counts
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 3: Command file count...${RESET}"
ACTUAL_COMMANDS=$(find .claude/commands -name "*.md" -type f | wc -l | tr -d ' ')

# README: "24 slash commands"
README_COMMANDS=$(grep -oE '[0-9]+ slash commands' README.md | head -1 | grep -oE '[0-9]+')
README_COMMANDS="${README_COMMANDS:-?}"
if [[ "$README_COMMANDS" == "$ACTUAL_COMMANDS" ]]; then
    pass "README.md: ${ACTUAL_COMMANDS} slash commands"
else
    fail "README.md says ${README_COMMANDS} commands, actual is ${ACTUAL_COMMANDS}"
fi

# STATE.md: "24 commands across"
STATE_COMMANDS=$(grep -oE '[0-9]+ commands across' memory/zo-platform/STATE.md | head -1 | grep -oE '[0-9]+')
STATE_COMMANDS="${STATE_COMMANDS:-?}"
if [[ "$STATE_COMMANDS" == "$ACTUAL_COMMANDS" ]]; then
    pass "STATE.md: ${ACTUAL_COMMANDS} commands"
else
    fail "STATE.md says ${STATE_COMMANDS} commands, actual is ${ACTUAL_COMMANDS}"
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 4: Version consistency
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 4: Version consistency...${RESET}"
VER_TOML=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)
VER_INIT=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/zo/__init__.py | head -1)
VER_CLI=$(sed -n 's/^_VERSION = "\(.*\)"/\1/p' src/zo/cli.py | head -1)
VER_TOML="${VER_TOML:-?}"
VER_INIT="${VER_INIT:-?}"
VER_CLI="${VER_CLI:-?}"

if [[ "$VER_TOML" == "$VER_INIT" && "$VER_INIT" == "$VER_CLI" ]]; then
    pass "Version ${VER_TOML} consistent across pyproject.toml, __init__.py, cli.py"
else
    fail "Version mismatch: pyproject.toml=${VER_TOML}, __init__.py=${VER_INIT}, cli.py=${VER_CLI}"
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 5: Model tier consistency (warn-only)
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 5: Model tier consistency...${RESET}"
TIER_ISSUES=0
for agent_file in .claude/agents/*.md; do
    agent_name=$(basename "$agent_file" .md)
    # Extract model from YAML frontmatter
    model_id=$(sed -n '/^---$/,/^---$/{ /^model:/s/model: *//p; }' "$agent_file")

    # Map model ID to tier name
    case "$model_id" in
        *opus*) expected_tier="Opus" ;;
        *sonnet*) expected_tier="Sonnet" ;;
        *haiku*) expected_tier="Haiku" ;;
        *) expected_tier="Unknown" ;;
    esac

    # Check specs/agents.md for this agent heading
    # Convert hyphens to spaces for heading match (e.g., "model-builder" -> "model builder")
    search_name="${agent_name//-/ }"
    spec_tier=$(grep -i -A 2 "### .*${search_name}" specs/agents.md 2>/dev/null | grep -i "model tier" | head -1 || true)

    if [[ -n "$spec_tier" ]]; then
        if ! echo "$spec_tier" | grep -qi "$expected_tier"; then
            warn "${agent_name}: agent file says ${expected_tier}, specs/agents.md says: $(echo "$spec_tier" | sed 's/.*: *//')"
            ((TIER_ISSUES++))
        fi
    fi
done

if [[ $TIER_ISSUES -eq 0 ]]; then
    pass "All agent tiers match between definitions and specs"
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 6: Test count badge (warn-only)
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 6: Test count badge...${RESET}"
README_TESTS=$(grep -oE 'tests-[0-9]+' README.md | head -1 | grep -oE '[0-9]+')
README_TESTS="${README_TESTS:-?}"

if [[ "$README_TESTS" == "?" ]]; then
    warn "Could not parse test badge from README.md"
else
    # Count test functions via grep (fast, no pytest dependency)
    ACTUAL_TESTS=$(grep -r "def test_" tests/ 2>/dev/null | wc -l | tr -d ' ')
    DIFF=$((ACTUAL_TESTS - README_TESTS))
    ABS_DIFF=${DIFF#-}
    if [[ $ABS_DIFF -le 5 ]]; then
        pass "Test badge: ${README_TESTS} (grep count: ${ACTUAL_TESTS}, within tolerance)"
    else
        warn "Test badge says ${README_TESTS}, grep finds ${ACTUAL_TESTS} test functions (diff: ${DIFF})"
    fi
fi

echo ""

# ─────────────────────────────────────────────────────
# Check 7: setup.sh pass message count
# ─────────────────────────────────────────────────────
echo -e "${DIM}Check 7: setup.sh agent count literal...${RESET}"
SETUP_PASS_MSG=$(grep -oE 'All [0-9]+ agent' setup.sh | head -1 | grep -oE '[0-9]+')
SETUP_PASS_MSG="${SETUP_PASS_MSG:-?}"
if [[ "$SETUP_PASS_MSG" == "$ACTUAL_AGENTS" ]]; then
    pass "setup.sh pass message matches: ${ACTUAL_AGENTS}"
else
    fail "setup.sh pass message says ${SETUP_PASS_MSG}, actual is ${ACTUAL_AGENTS}"
fi

echo ""

# Check 8: Client confidentiality — no project-specific identifiers in tracked files
# This is a HARD FAIL, not a warning. Client names in a public repo is a legal risk.
# The blocklist is maintained here. Add new project aliases to the grep pattern
# when onboarding new clients.

echo -e "${DIM}Check 8: Client confidentiality...${RESET}"
# Blocklist: add client project identifiers, real names, locations, product codes
# that must never appear in tracked ZO files. Use | to separate patterns.
# Keep patterns lowercase — grep -i handles case-insensitive matching.
CLIENT_BLOCKLIST="ivl_f5|ivl f5|indorama|port neches|pontbe|f5lb|f5ai6406|f5ai9518|f5ac2658"
# Search tracked files only (not gitignored). Exclude this script itself.
LEAKS=$(git ls-files -- '*.md' '*.py' '*.yaml' '*.yml' '*.json' '*.sh' \
    | grep -v 'validate-docs.sh' \
    | xargs grep -liE "$CLIENT_BLOCKLIST" 2>/dev/null || true)
if [[ -z "$LEAKS" ]]; then
    pass "No client identifiers found in tracked files"
else
    LEAK_COUNT=$(echo "$LEAKS" | wc -l | tr -d ' ')
    fail "Client identifiers found in ${LEAK_COUNT} tracked file(s):"
    echo "$LEAKS" | while read -r f; do
        echo -e "    ${RED}${f}${RESET}"
    done
    echo -e "    ${DIM}Blocklist: ${CLIENT_BLOCKLIST}${RESET}"
    echo -e "    ${DIM}Use project aliases (prod-001, prod-002) instead.${RESET}"
fi

echo ""

# ─────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────
echo -e "${DIM}─────────────────────────────────────────────────────${RESET}"
TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
echo -e "  ${GREEN}${PASS_COUNT} passed${RESET}  ${RED}${FAIL_COUNT} failed${RESET}  ${AMBER}${WARN_COUNT} warnings${RESET}  (${TOTAL} checks)"
echo ""

if [[ $FAIL_COUNT -gt 0 ]]; then
    echo -e "${RED}Documentation is out of sync with codebase. Fix before committing.${RESET}"
    echo ""
    exit 1
else
    echo -e "${GREEN}Documentation is consistent with codebase.${RESET}"
    echo ""
    exit 0
fi
