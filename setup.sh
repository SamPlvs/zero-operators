#!/usr/bin/env bash
# Zero Operators — Environment Bootstrap
# Validates all prerequisites for running ZO.
# Run once per environment: ./setup.sh

set -uo pipefail
# Note: not using -e because arithmetic ((...)) returns 1 when result is 0

AMBER='\033[38;2;240;192;64m'
RED='\033[0;31m'
GREEN='\033[0;32m'
DIM='\033[2m'
RESET='\033[0m'

PASS=0
FAIL=0
WARN=0
FIXABLE_COUNT=0
FIXABLE_ITEMS=""

pass() { echo -e "  ${GREEN}✓${RESET} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${RESET} $1"; ((FAIL++)); }
warn() { echo -e "  ${AMBER}!${RESET} $1"; ((WARN++)); }
fixable() { FIXABLE_ITEMS="$FIXABLE_ITEMS $1"; ((FIXABLE_COUNT++)); }

echo -e "${AMBER}━━━ Zero Operators Setup ━━━${RESET}"
echo ""

# 1. Python version
echo -e "${DIM}Checking Python...${RESET}"
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        pass "Python $PY_VERSION"
    else
        fail "Python $PY_VERSION (need 3.11+)"
    fi
else
    fail "Python 3 not found"
fi

# 2. uv package manager
echo -e "${DIM}Checking uv...${RESET}"
if command -v uv &>/dev/null; then
    UV_VERSION=$(uv --version 2>/dev/null | head -1)
    pass "uv ($UV_VERSION)"
else
    fail "uv not found — install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fixable "uv"
fi

# 3. Claude Code CLI
echo -e "${DIM}Checking Claude Code CLI...${RESET}"
if command -v claude &>/dev/null; then
    pass "Claude Code CLI available"
else
    fail "Claude Code CLI not found — install: curl -fsSL https://claude.ai/install.sh | bash"
    fixable "claude"
fi

# 4. Agent teams enabled
echo -e "${DIM}Checking agent teams...${RESET}"
SETTINGS_FILE="$HOME/.claude/settings.json"
if [[ -f "$SETTINGS_FILE" ]]; then
    if grep -q "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" "$SETTINGS_FILE" 2>/dev/null; then
        pass "Agent teams enabled in global settings"
    else
        fail "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS not set in $SETTINGS_FILE"
        fixable "agent-teams-env"
    fi
else
    fail "Global settings not found at $SETTINGS_FILE"
    fixable "global-settings"
fi

# 5. Project settings.json
echo -e "${DIM}Checking project settings...${RESET}"
if [[ -f ".claude/settings.json" ]]; then
    pass "Project .claude/settings.json exists"
else
    fail "Project .claude/settings.json missing"
fi

# 6. Agent definition files
echo -e "${DIM}Checking agent definitions...${RESET}"
EXPECTED_AGENTS=(
    lead-orchestrator research-scout data-engineer model-builder oracle-qa
    code-reviewer test-engineer xai-agent domain-evaluator
    ml-engineer infra-engineer software-architect backend-engineer
    frontend-engineer platform-test-engineer platform-code-reviewer
    documentation-agent
)
AGENT_COUNT=0
MISSING_AGENTS=()
for agent in "${EXPECTED_AGENTS[@]}"; do
    if [[ -f ".claude/agents/${agent}.md" ]]; then
        ((AGENT_COUNT++))
    else
        MISSING_AGENTS+=("$agent")
    fi
done

if [[ $AGENT_COUNT -eq 17 ]]; then
    pass "All 17 agent definitions present"
else
    fail "$AGENT_COUNT/17 agent definitions found"
    for missing in "${MISSING_AGENTS[@]}"; do
        echo -e "      ${RED}missing:${RESET} .claude/agents/${missing}.md"
    done
fi

# 7. Git state
echo -e "${DIM}Checking git...${RESET}"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    pass "Inside git repository"
    if [[ -z "$(git status --porcelain 2>/dev/null)" ]]; then
        pass "Working tree clean"
    else
        warn "Working tree has uncommitted changes"
    fi
else
    fail "Not a git repository"
fi

# 8. ruff linter
echo -e "${DIM}Checking ruff...${RESET}"
if command -v ruff &>/dev/null; then
    pass "ruff available"
else
    warn "ruff not found — install: uv tool install ruff"
fi

# 9. Dependencies synced
echo -e "${DIM}Checking dependencies...${RESET}"
if [[ -f "pyproject.toml" ]]; then
    pass "pyproject.toml exists"
    if command -v uv &>/dev/null; then
        if uv sync --dry-run &>/dev/null 2>&1; then
            pass "Dependencies resolvable"
        else
            warn "uv sync --dry-run failed — run: uv sync"
        fi
    fi
else
    fail "pyproject.toml missing"
fi

# 10. Directory structure
echo -e "${DIM}Checking directory structure...${RESET}"
DIRS=(src/zo memory logs targets tests specs plans design)
DIR_OK=0
for dir in "${DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        ((DIR_OK++))
    fi
done

if [[ $DIR_OK -eq ${#DIRS[@]} ]]; then
    pass "All ${#DIRS[@]} required directories present"
else
    warn "$DIR_OK/${#DIRS[@]} directories present"
fi

# ── Auto-fix ──────────────────────────────────────────────────────────────────
fix_item() {
    local item="$1"
    case "$item" in
        uv)
            echo -e "  ${AMBER}→${RESET} Installing uv..."
            if curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null; then
                # Source the env so uv is available for the rest of the script
                export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
                if command -v uv &>/dev/null; then
                    echo -e "  ${GREEN}✓${RESET} uv installed ($(uv --version 2>/dev/null | head -1))"
                    return 0
                fi
            fi
            echo -e "  ${RED}✗${RESET} uv install failed — try manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
            return 1
            ;;
        claude)
            echo -e "  ${AMBER}→${RESET} Installing Claude Code CLI..."
            if curl -fsSL https://claude.ai/install.sh | bash 2>/dev/null; then
                # Refresh PATH for newly installed binary
                export PATH="$HOME/.local/bin:$HOME/.claude/local/bin:$PATH"
                if command -v claude &>/dev/null; then
                    echo -e "  ${GREEN}✓${RESET} Claude Code CLI installed"
                    return 0
                fi
            fi
            echo -e "  ${RED}✗${RESET} Claude CLI install failed — try manually: curl -fsSL https://claude.ai/install.sh | bash"
            return 1
            ;;
        global-settings)
            echo -e "  ${AMBER}→${RESET} Creating global settings at $SETTINGS_FILE..."
            mkdir -p "$HOME/.claude"
            cat > "$SETTINGS_FILE" << 'SETTINGS_EOF'
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
SETTINGS_EOF
            echo -e "  ${GREEN}✓${RESET} Global settings created with agent teams enabled"
            return 0
            ;;
        agent-teams-env)
            echo -e "  ${AMBER}→${RESET} Adding agent teams env to $SETTINGS_FILE..."
            # Use python to merge the env key into existing settings
            if python3 -c "
import json, sys
with open('$SETTINGS_FILE') as f:
    data = json.load(f)
data.setdefault('env', {})['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] = '1'
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
" 2>/dev/null; then
                echo -e "  ${GREEN}✓${RESET} Agent teams env added to global settings"
                return 0
            else
                echo -e "  ${RED}✗${RESET} Failed to update settings — add manually"
                return 1
            fi
            ;;
    esac
}

if [[ $FIXABLE_COUNT -gt 0 && $FAIL -gt 0 ]]; then
    echo ""
    echo -ne "${AMBER}$FIXABLE_COUNT issue(s) can be auto-fixed. Install now? [Y/n]${RESET} "
    read -r REPLY
    if [[ -z "$REPLY" || "$REPLY" =~ ^[Yy] ]]; then
        echo ""
        echo -e "${AMBER}━━━ Auto-fixing $FIXABLE_COUNT issue(s) ━━━${RESET}"
        FIXED=0
        STILL_BROKEN=0
        for item in $FIXABLE_ITEMS; do
            if fix_item "$item"; then
                ((FIXED++))
            else
                ((STILL_BROKEN++))
            fi
        done
        echo ""
        if [[ $STILL_BROKEN -eq 0 ]]; then
            echo -e "${GREEN}All issues fixed.${RESET} Re-running validation..."
            echo ""
            exec "$0"
        else
            echo -e "${AMBER}Fixed $FIXED/$FIXABLE_COUNT.${RESET} $STILL_BROKEN issue(s) need manual attention."
            exit 1
        fi
    fi
fi

# Summary
echo ""
echo -e "${AMBER}━━━ Summary ━━━${RESET}"
echo -e "  ${GREEN}Pass:${RESET} $PASS"
[[ $WARN -gt 0 ]] && echo -e "  ${AMBER}Warn:${RESET} $WARN"
[[ $FAIL -gt 0 ]] && echo -e "  ${RED}Fail:${RESET} $FAIL"

echo ""
if [[ $FAIL -eq 0 ]]; then
    echo -e "${GREEN}Environment ready.${RESET} Run ${AMBER}zo build plans/<project>.md${RESET} to start."
else
    echo -e "${RED}$FAIL check(s) failed.${RESET} Fix the issues above and re-run ./setup.sh"
    exit 1
fi
