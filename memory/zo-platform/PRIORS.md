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
