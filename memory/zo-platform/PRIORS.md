# PRIORS.md — Zero Operators Platform

Domain knowledge accumulated through building and running ZO.
Each prior references the failure that triggered it (self-evolution protocol).

---

## PR-001: Claude CLI Interactive Mode Constraints
**Source:** Session 007-008 (2026-04-10), wrapper tmux debugging
**Root cause category:** missing_rule
**Failure:** `zo build` appeared stuck — no TUI visible, no agent panes

### Rules

1. **`--dangerously-skip-permissions` exits immediately in interactive mode.**
   It shows a warning and returns to shell. Only works with `--print` (headless).
   For interactive TUI, use `.claude/settings.json` allow/deny rules instead.
   - *Failure ref:* Claude showed bypass warning and exited. User saw blank tmux pane.

2. **`claude -p "prompt" --dangerously-skip-permissions` runs non-interactively.**
   No TUI renders even without `--print`. The combination suppresses the terminal UI.
   - *Failure ref:* Process ran (visible in `ps aux`) but tmux pane was blank.

3. **Claude Code renders its TUI to stderr.**
   Never redirect stderr (`2>file`) when you want the TUI visible.
   - *Failure ref:* Launcher script had `2>stderr.log` which captured the entire TUI.

4. **`#!/usr/bin/env bash -l` does not work on macOS.**
   `env` cannot pass flags to the interpreter. Use `#!/bin/bash -l` instead.
   - *Failure ref:* Launcher script shebang silently failed.

5. **Shell escaping in tmux commands is unreliable.**
   Passing complex commands (with `$(cat ...)`, quotes, newlines) through
   `tmux new-window "cmd"` or `tmux send-keys` breaks in subtle ways.
   - *Failure ref:* Multiple escaping approaches failed before paste-buffer worked.

### Verified Solution

The only reliable method to get an interactive Claude Code TUI in tmux:
```
1. tmux new-window           → open shell with real TTY
2. tmux send-keys "claude --model opus --add-dir /path" Enter
3. sleep 3                   → wait for TUI init
4. tmux load-buffer prompt.txt
5. tmux paste-buffer         → paste prompt into TUI input
6. tmux send-keys Enter      → submit
```

Reserve `--print --dangerously-skip-permissions` for headless/CI mode only.

---

## PR-002: Agent Permissions in Interactive Mode
**Source:** Session 008 (2026-04-10), MNIST live test
**Root cause category:** incomplete_rule
**Failure:** Agents constantly asked for permission, blocking progress

### Rules

1. **`.claude/settings.json` permissions must cover common agent operations.**
   Default allow list was missing: `Bash(cd *)`, `Bash(pip *)`, `Bash(source *)`.
   Agents blocked waiting for team-lead approval on routine commands.

2. **Supervised gate mode + narrow permissions = double bottleneck.**
   Phase-level gates (supervised) AND tool-level permissions (settings.json)
   both require human approval. For practical use, broaden settings.json
   or use `--gate-mode auto`.

### Recommendation
Add to `.claude/settings.json` for smoother agent operation:
```json
"Bash(cd *)", "Bash(pip *)", "Bash(source *)",
"Bash(cat *)", "Bash(head *)", "Bash(tail *)",
"Bash(find *)", "Bash(wc *)", "Bash(touch *)"
```

---

## PR-003: Documentation Staleness is a Systemic Risk
**Source:** Session 008 (2026-04-10), doc audit
**Root cause category:** missing_rule
**Failure:** After adding research-scout agent and removing zo maintain,
12+ files had stale references (agent counts, command lists, version numbers)

### Rules

1. **Every code change that modifies the public interface must update:**
   - README.md (badges, command list, agent roster, version)
   - specs/agents.md (team counts)
   - plans/zero-operators-build.md (deliverables, module descriptions)
   - CLAUDE.md (operating modes)
   - PRD.md (mode descriptions)
   - memory/zo-platform/STATE.md
   - memory/zo-platform/DECISION_LOG.md

2. **Agent additions/removals cascade to 6+ files.**
   Changing the agent roster requires updating: specs/agents.md,
   README.md (badge + roster table), plans/ (deliverables), CLAUDE.md.

3. **Command additions/removals cascade to 4+ files.**
   Changing CLI commands requires updating: README.md, PRD.md,
   CLAUDE.md, plans/zero-operators-build.md.

### Recommendation
Set up a postToolUse hook that reminds about doc updates after
file changes to src/zo/cli.py or .claude/agents/.

---

## PR-004: Research Before Building
**Source:** Session 008 (2026-04-10), architecture discussion
**Root cause category:** missing_rule
**Failure:** No systematic literature review before model design phase

### Rules

1. **Phase 0 (Research) should run before Phase 3 (Model Design).**
   Without literature review, architecture selection is uninformed guessing.
   The research-scout agent fills this gap.

2. **Customer projects have no published benchmarks.**
   Don't block on "no SOTA found." Find analogous problems, use first
   experiments as the baseline, report typical ranges from similar work.

3. **Open-source code saves iteration cycles.**
   If a working implementation exists for a similar problem, adapting it
   is faster than building from scratch. Research Scout catalogs these.

---

## PR-005: Aspirational Rules Without Enforcement Are Dead Letter
**Source:** Session 009 (2026-04-10), doc-codebase drift audit
**Root cause category:** missing_rule
**Failure:** CLAUDE.md "Cascade doc updates" protocol existed as text instructions
but had ZERO enforcement. Adding the 17th agent (Research Scout) left 10+ files
with stale agent counts (16 instead of 17), stale version (1.0.0 instead of 1.0.1),
stale test counts, and incorrect model tiers. PR-003 recommended a postToolUse hook
but it was never implemented — deferred prevention is no prevention.

### Rules

1. **Every protocol that says MUST needs a corresponding enforcement mechanism.**
   Text-only rules degrade to suggestions within one session. If CLAUDE.md says
   "Claude MUST update X before commit", there must be a hook, script, or CI check
   that blocks the commit if X is not updated.
   - *Failure ref:* CLAUDE.md cascade protocol was ignored across 3+ sessions.

2. **When a PRIOR recommends a preventive action, implement it immediately.**
   PR-003 recommended hooks. They were never built. The exact failure PR-003
   warned about then happened. Deferred prevention is no prevention.
   - *Failure ref:* PR-003 recommended hooks (2026-04-10). Same session ended
     without implementing them. Next session repeated the drift failure.

3. **Documentation consistency is verified programmatically before every commit.**
   `scripts/validate-docs.sh` checks agent count, command count, version,
   model tiers, and name registry. A PreToolUse hook in `.claude/settings.json`
   blocks `git commit` if validation fails.
   - *Failure ref:* Manual doc updates across 10+ files are error-prone.
     Automated validation catches drift before it reaches git history.

### Verified Solution

Three-layer defense against doc-codebase drift:

1. **Layer 1 — Validation script** (`scripts/validate-docs.sh`):
   7 checks, runs in <2 seconds, exits non-zero on failure. Checks agent
   count, agent names, command count, version, model tiers, test badge.

2. **Layer 2 — Claude Code hooks** (`.claude/settings.json`):
   - PreToolUse hook on `Bash(git commit *)` runs validation script, blocks commit on failure
   - PostToolUse hook on `Write|Edit` injects cascade reminders when trigger files are modified

3. **Layer 3 — Explicit cascade mappings** (CLAUDE.md):
   File-to-file cascade chains for agent, command, version, and tier changes.
   No ambiguity about which files to update.
