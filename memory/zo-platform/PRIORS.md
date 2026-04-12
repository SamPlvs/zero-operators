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

---

## PR-006: Ephemeral In-Memory State Must Be Persisted If It Crosses Sessions
**Source:** Session 010 (2026-04-12), phase persistence bug fix
**Root cause category:** missing_rule
**Failure:** `decompose_plan()` created fresh PhaseDefinition objects on every call,
discarding all in-memory phase progress. `end_session()` only wrote scalar fields
(phase name, last subtask) but not the per-phase status map or completed subtask lists.

### Rules

1. **Any in-memory state that must survive across sessions needs a persistence path.**
   PhaseDefinition.status and .completed_subtasks were tracked in memory but never
   serialized. The fix: `phase_states` and `completed_subtasks_by_phase` fields on
   SessionState, rendered to a `## Phases` section in STATE.md.
   - *Failure ref:* Second `zo build` call always restarted from phase_1.

2. **Factory functions that create fresh objects must check for saved state.**
   `decompose_plan()` calls `factory()` which returns default-initialized phases.
   A `_restore_phase_states()` step must follow to rehydrate from saved state.
   - *Failure ref:* Line 222 of orchestrator.py unconditionally set phase to phases[0].

3. **Round-trip tests are mandatory for any persisted state.**
   The fix included 5 tests: full round-trip, backward compat (old STATE.md format),
   partial progress restoration, and GATED phase detection.

### Verified Solution

1. SessionState extended with `phase_states: dict[str, str]` and `completed_subtasks_by_phase: dict[str, list[str]]`
2. STATE.md format extended with `## Phases` section (backward compatible — old format still parses)
3. `decompose_plan()` → `_restore_phase_states()` rehydrates after factory()
4. `end_session()` → `_capture_phase_states()` serializes before write

---

## PR-007: Docker Builds — Layer Order and Caching Are Everything
**Source:** Session 010 (2026-04-12), Docker template design from user's R&D setup analysis
**Root cause category:** novel_case
**Failure:** User's existing Docker setup took 30+ minutes to build and required full
rebuild on any dependency change. Root causes: `--no-cache` flag, venv inside Docker,
pip one-at-a-time installs, source builds in single stage, 80+ apt packages.

### Rules

1. **Never use `--no-cache` on `docker build` unless debugging.**
   Layer caching is the primary mechanism for fast rebuilds. `--no-cache` defeats it entirely.

2. **Multi-stage builds: least-changing → most-changing.**
   Stage 1: base image (CUDA). Stage 2: tooling (uv). Stage 3: deps (pyproject.toml).
   Stage 4: code (COPY .). Code changes rebuild only stage 4 (~1 second).

3. **No venv inside Docker.** Docker IS the isolation. Venv adds complexity and confusion.

4. **Use uv, not pip.** 50-100x faster dependency resolution and installation.
   `uv sync --frozen` with a lock file gives deterministic, fast installs.

5. **Keep base template bare minimum.** Only git, curl, tmux, sudo in template.
   Agents add project-specific packages based on plan.md requirements.

---

## PR-008: Context Efficiency Through Modular References
**Source:** Session 010 (2026-04-12), delivery structure redesign
**Root cause category:** novel_case
**Failure:** No failure — proactive design based on user requirement to avoid context bloat.

### Rules

1. **Use index files that point to detail files, not monolithic docs.**
   experiments/README.md is a scannable index. Each exp-NNN/ has its own notes.
   Agents read the index first, then drill into relevant experiments only.

2. **STRUCTURE.md is the in-repo map that agents read section-by-section.**
   Each section describes one directory. Agents load only their section
   (Data Engineer reads ## src/ and ## data/, not the whole file).

3. **Configs separate from code enables fast experiment iteration.**
   Agents change YAML config files to alter experiments. Frozen config
   snapshots in experiments/exp-NNN/config.yaml provide reproducibility
   without touching source code.

4. **Split tests by concern, not just by module.**
   tests/unit/ = code correctness (Test Engineer). tests/ml/ = oracle
   thresholds and benchmarks (Oracle/QA Agent). Different agents, different
   pass/fail criteria, different run frequencies.

---

## PR-009: Built Modules Must Be Wired Before Declaring Ready
**Source:** Session 010 (2026-04-12), orchestrator wiring gap discovery
**Root cause category:** missing_rule
**Failure:** notebooks.py, scaffold.py, and preflight.py were built and independently tested, but not connected to the orchestrator pipeline. A real run would have produced no auto-notebooks and no artifact validation.

### Rules

1. **"Built and tested" is not "wired and enforced."**
   A module that passes unit tests but is never called from the pipeline
   provides zero value in production. After building any new capability,
   verify it is called from the orchestrator/CLI flow.

2. **Add an integration test that traces the full call path.**
   test_artifacts_present_allows_gate verifies: subtasks complete →
   artifacts checked → gate passes → notebook generated. This catches
   wiring gaps that unit tests miss.

3. **The advance_phase() method is the single enforcement point.**
   All phase-exit logic (artifact checks, notebook generation, comms logging)
   routes through advance_phase() for automated gates and apply_human_decision()
   for human gates. New phase-exit behaviors must be wired into both paths.

---

## PR-010: macOS Bash 3.2 Breaks Empty Array Checks Under set -u
**Source:** Session 011 (2026-04-12), setup.sh --fix silent failure
**Root cause category:** missing_rule
**Failure:** setup.sh auto-fix block never triggered despite --fix flag. Bash 3.2.57 (macOS default) throws "unbound variable" on `${#ARRAY[@]}` when the array is empty and `set -u` is active. The error silently killed the auto-fix conditional.

### Rules

1. **Never use bash arrays with `set -u` if the script must run on macOS.**
   macOS ships bash 3.2 (2007). Empty arrays + `set -u` = silent failure.
   Use string variables with word splitting or integer counters instead.

2. **Always test shell scripts on bash 3.2 when targeting macOS.**
   `bash --version` on macOS returns 3.2.57. Scripts that work on bash 5+
   (Linux, Homebrew) can silently break on stock macOS. Run `bash -n` for
   syntax, but also test runtime behavior with actual bash 3.2.

3. **Setup/bootstrap scripts must be maximally portable.**
   These run on the widest variety of environments (fresh machines, CI,
   different OS versions). Avoid bashisms that require 4.0+: associative
   arrays, `${!var}`, `${array[@]}` with nounset, `&>`, `|&`.

---

## PR-011: Setup Scripts Should Auto-Fix, Not Just Report
**Source:** Session 011 (2026-04-12), CIFAR-10 demo on new machine
**Root cause category:** missing_rule
**Failure:** User hit 3 setup failures, all with known install commands printed in the error messages. Had to manually copy-paste each command. First fix added --fix flag, but user pointed out this shouldn't require a flag — if the fix is known, just offer to run it.

### Rules

1. **If the fix is known and safe, offer to run it interactively.**
   Report-only error messages with "run this command" are a UX anti-pattern
   when the script already knows the command. Prompt "Install now? [Y/n]"
   with Enter as default-yes.

2. **After auto-fixing, re-run validation to confirm.**
   Use `exec "$0"` to re-validate from scratch. Don't assume the fix worked
   — prove it by passing the same checks that originally failed.

3. **Keep install commands up to date in setup scripts.**
   The Claude CLI install changed from npm to curl. Stale install commands
   in setup scripts cause silent failures or confusion. When a dependency
   changes its install method, update all references.

---

## PR-012: uv sync Does Not Put CLI Entry Points on PATH
**Source:** Session 011 (2026-04-12), CIFAR-10 demo — `zo: command not found`
**Root cause category:** missing_rule
**Failure:** User ran `uv sync`, then `zo init` → "command not found". `uv sync` installs into `.venv/bin/` which is not on PATH when the user has conda, system Python, or any non-venv shell active. setup.sh checked that deps "resolve" (dry-run) but never verified the CLI was callable.

### Rules

1. **Checking ≠ installing ≠ callable.**
   setup.sh must verify the full chain: (1) deps resolve, (2) deps installed,
   (3) CLI entry points are on PATH and executable. A dry-run check that
   passes means nothing if the user can't type the command.

2. **`uv sync` isolates into `.venv/` — symlink entry points to `~/.local/bin/`.**
   After `uv sync`, the `zo` binary lives at `.venv/bin/zo`. Users with conda,
   pyenv, or system Python won't have `.venv/bin/` on PATH. Fix: symlink
   `.venv/bin/zo` → `~/.local/bin/zo` (already on PATH from uv's own install).

3. **Setup scripts must leave the user with a working command, not a working venv.**
   The success criterion for setup is "can the user type `zo build` and have
   it work?" — not "are dependencies resolved?". Test from the user's
   perspective, not the package manager's.

---

## PR-013: ZO Artifacts Must Always Write to Main Repo, Not Worktrees
**Source:** Session 011 (2026-04-12), zo draft wrote plan to worktree
**Root cause category:** missing_rule
**Failure:** User ran `zo draft` from a worktree. Plan was written to worktree's `plans/` dir. Then `zo build` from main repo couldn't find it. User had to manually copy the file.

### Rules

1. **Plans, memory, and state always live in the main repo.**
   Worktrees are for ZO development, not ZO usage. Use
   `_main_repo_root()` (git worktree list --porcelain) to find the
   main repo when writing artifacts that need to persist.

2. **Any zo command that writes artifacts must be worktree-aware.**
   Check if cwd is a worktree. If so, write to main repo and inform
   the user: "Written to main repo (not worktree)".

3. **Test from the user's perspective: where would they look?**
   Users expect `plans/project.md` in the repo they cloned, not in a
   hidden `.claude/worktrees/` subdirectory.

---

## PR-014: CLI Commands Need Consistent Branding and Context Display
**Source:** Session 011 (2026-04-12), user noted brand panel only in zo build
**Root cause category:** missing_rule
**Failure:** Not a failure — a UX gap. The brand panel (project, mode, phase, gates) only appeared in `zo build`. All other commands showed raw output with no context.

### Rules

1. **Every CLI entry point shows the brand banner.**
   Extract into shared `_show_banner()`. Establishes identity and
   shows current context (project, mode). Professional tooling has
   consistent branding across all entry points.

2. **Banner fields are contextual, not forced.**
   Only show fields relevant to the command. `zo preflight` has no
   project — skip that line. `zo draft` has no phase — skip it.
   Don't show empty fields.

---

## PR-015: Phase Definitions Must Be Production-Ready by Default
**Source:** Session 011 (2026-04-12), CIFAR-10 Phase 1 review
**Root cause category:** missing_rule
**Failure:** Not a failure — a gap. Phase 1 (Data Review) had only 2 agents and 7 subtasks. Sufficient for CIFAR-10 demo but would miss critical steps on messy production data (no schema validation, no outlier detection, no class imbalance analysis, no split strategy).

### Rules

1. **Phase defaults must handle the hardest case, not the easiest.**
   CIFAR-10 is clean, balanced, well-known. IVL F5 data is messy,
   domain-specific, potentially imbalanced. Defaults should be
   production-grade — users can simplify via plan.md overrides.

2. **Code review and research are cross-cutting — always present.**
   `code-reviewer` catches quality issues before they compound.
   `research-scout` ensures domain context informs every phase.
   These shouldn't be opt-in. Add to all phases by default.

3. **Data workflow subtasks must cover the full production checklist.**
   Schema validation, missing values, outliers, class imbalance,
   split strategy, drift baselines — all essential before training.
   Missing any one can silently corrupt downstream results.

---

## PR-016: Pipeline Commands Must Carry Context Autonomously
**Source:** Session 011 (2026-04-12), CIFAR-10 init → build path mismatch
**Root cause category:** missing_rule
**Failure:** User ran `zo init --scaffold-delivery ~/projects/cifar10-delivery`, then `zo build` looked for `/code/target-cifar10-demo`. Target template hardcoded `../target-{project}` — a relative path that never matched the scaffold location. User had to manually create the directory and re-init.

### Rules

1. **The user is not a message bus between commands.**
   init → draft → build must carry context through artifacts (target
   file, plan, STATE.md). If a path is set in init, every downstream
   command must read it from the same source — never guess or compute
   independently.

2. **Always write absolute paths to config files.**
   Relative paths resolve differently depending on cwd, worktree,
   tmux session, or agent working directory. Absolute paths are
   deterministic. Resolve at write time, not read time.

3. **The target file is the single source of truth for delivery repo.**
   `target_repo` in `targets/{project}.target.md` is THE path. init
   writes it, build reads it, preflight validates it. No other source.

4. **Default behavior should be autonomous — flags are for overrides.**
   `zo init project` should scaffold everything (including delivery
   repo at a default location) without flags. `--scaffold-delivery`
   is an override for non-default paths, not the only way to get a
   delivery repo.
