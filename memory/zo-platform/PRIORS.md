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
   CIFAR-10 is clean, balanced, well-known. prod-001 data is messy,
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

---

## PR-017: Conversational Interview > Flag Proliferation When Decisions Need Context
**Source:** Session 013 (2026-04-13), `zo init` redesign for prod-001 readiness
**Root cause category:** missing_rule
**Failure:** Original `zo init` was a programmatic one-shot — fine for fresh demo projects (CIFAR-10) but accumulated five distinct gaps when faced with a real production project (prod-001): hardcoded `target_branch: main`, no `Environment` section, no overlay-vs-scaffold mode, no remote-data handling, target template's `agent_working_dirs` mismatched the new responsibility-based scaffold layout. Each gap could be patched with a flag, but the gaps themselves arose from *decisions that need context to make correctly* — context that lives in the user's head and the existing repo, not in defaults.

### Rules

1. **When a decision requires inspecting the target environment, prefer a conversational agent over a flag.**
   Adding `--branch`, `--existing-repo`, `--base-image`, `--gpu-host`, `--data-path`, `--layout-mode` etc. would have worked syntactically but pushed inspection-and-decision burden onto the user. The Init Architect inspects the repo (Glob/Read/Bash) and asks targeted questions; the user makes 5-6 confirmations instead of crafting a 7-flag CLI invocation.
   - *Failure ref:* prod-001 setup needed `target_branch: feature-branch` (manual edit), Environment section (manual fill-in), overlay vs scaffold (no mode existed), STRUCTURE.md customization for src-layout (no mechanism). Five sequential gaps from one root cause.

2. **The conversational agent must ROUTE WRITES through the headless CLI, not write files itself.**
   Two layers: (a) Agent collects answers + inspects context, (b) CLI does deterministic file writes. Keeps tests easy (CLI tested standalone), keeps writes consistent across conversational and CI invocations, lets the agent be replaced or improved without touching write logic. Single source of truth for filesystem effects.
   - *Pattern:* Agent calls `zo init project --no-tmux --branch X --existing-repo Y ...` via Bash. Same code path as `zo init project --no-tmux ...` from a CI script.

3. **The conversational mode must have a `--no-tmux` escape hatch for CI/scripts.**
   Mirror `zo draft --no-tmux`. Default is conversational (best human UX); `--no-tmux` is the universal headless mode (best for automation). Detect tmux availability up front and give a clear actionable error if it's missing — never silently fail in the wrapper.
   - *Failure ref:* If tmux is uninstalled, the wrapper would have errored deep in tmux command execution. Pre-check at CLI boundary catches this with a one-line fix-it message.

4. **Conversational agents must enumerate failure modes explicitly in their .md.**
   The Init Architect's protocol covers ~25 specific failure modes across 7 categories (path/repo, branch, environment, layout, user interaction, CLI, post-scaffold). Without enumeration, the agent improvises and fails inconsistently. *List the failures, list the recoveries, name the actions.*
   - *Failure ref:* "Full adaptability" requested by user (session 013). Adaptability without enumeration = unpredictability.

### Verified Solution

`zo init`:
- Default: `zo init project` → tmux pane with Init Architect (Opus). Agent interviews, inspects, calls CLI.
- Headless: `zo init project --no-tmux --branch X --existing-repo Y --base-image Z --gpu-host H --data-path P --layout-mode {standard,adaptive} --no-detect`. Same code path; agent uses this internally.
- Guardrails at CLI boundary: tmux availability check, mutually-exclusive flags (`--existing-repo` xor `--scaffold-delivery`), `--layout-mode=adaptive` requires `--existing-repo`, `--existing-repo` must contain `.git/`, branch existence warning via `git rev-parse`.
- Init Architect protocol enumerates failure modes explicitly (path, branch, env, layout, user interaction, CLI invocation, post-scaffold drift, rollback).

This pattern generalises: any time a CLI ergonomics gap suggests "just add a flag", check first whether the answer requires *context* (inspection of the user's repo / environment / preferences). If yes, a conversational agent backed by a headless CLI is the better shape.

---

## PR-018: Scaffold Adaptive Mode — Preserve Existing Code Layouts
**Source:** Session 013 (2026-04-13), prod-001 readiness analysis
**Root cause category:** novel_case
**Failure:** Not a runtime failure — proactive design. The existing scaffold (`scaffold_delivery`) was designed for greenfield projects and assumed a responsibility-based layout (`src/data/`, `src/model/`, etc.). Real production repos have their own established layouts (src-layout with single nested package, django-style, monorepo, notebook-first). Naively running scaffold on these creates *both* ZO's dirs AND leaves the user's, producing a confused two-layout repo.

### Rules

1. **Distinguish ZO infrastructure dirs from code-layout dirs.**
   `configs/`, `experiments/`, `reports/`, `notebooks/phase/`, `docker/` are ZO infrastructure that every project needs regardless of code layout. `src/data/`, `src/model/`, `src/engineering/`, `data/raw/`, `models/`, `tests/unit/` are *one possible* code layout. Treat them differently.
   - *Implementation:* `_META_DIRECTORIES` list (always created) vs `_STANDARD_DIRECTORIES` list (only in `layout_mode=standard`).

2. **`.gitkeep` placeholders only belong in truly empty directories.**
   Writing `.gitkeep` into a dir that already has files is pollution — it adds a tracked file the user didn't ask for, and it's confusing in code review. Check `if not any(d.iterdir())` after `mkdir -p`, and only then `touch .gitkeep`.
   - *Failure ref:* Original behavior added `.gitkeep` unconditionally; in overlay mode this would have polluted every existing code dir.

3. **In adaptive mode, skip template files the user almost certainly already has.**
   `README.md`, `pyproject.toml`, `.gitignore` — existing repos always have these and ZO's templates would either no-op (existing files preserved by idempotency) or, worse, drift expectations. Omit them entirely from `_FILE_TEMPLATES` in adaptive mode.

4. **Layout adaptation requires project-specific writes that the agent must own.**
   `STRUCTURE.md` and the target file's `agent_working_dirs` describe *this project's* layout. Only the Init Architect (with its inspection of the actual repo) has the context to fill these correctly. This is the one allowed direct-write exception in the Init Architect's protocol — narrowly scoped, post-CLI, with validation.

### Verified Solution

`scaffold_delivery(path, project_name, *, overlay=False, layout_mode="standard"|"adaptive")`. CLI surface: `zo init --layout-mode={standard,adaptive}` with adaptive requiring `--existing-repo`. Tests cover empty-dir gitkeep behavior, adaptive skipping src/data, standard creating both meta + standard dirs, README/pyproject preservation in adaptive mode, invalid layout mode rejection, overlay logging.

---

## PR-019: Conversational Commands Need Preview + Reversal, Not Just Confirmation
**Source:** Session 013 (2026-04-13), follow-up question on `zo init` adaptability
**Root cause category:** missing_rule
**Failure:** Not a runtime failure — a design gap exposed by user challenge. After making `zo init` conversational (PR-017), the user asked: "will the Init Architect adapt if the repo is partial or mismatched?" Investigation showed that while the agent could inspect the repo and pick a layout mode, the user had no way to (a) see exactly what would land on disk before it happened, or (b) undo it cleanly if the agent chose wrong. Text summaries are not previews; idempotent re-runs don't remove earlier wrong writes. Conversational commands with real side effects need the full loop: preview → commit → reverse.

### Rules

1. **Conversational commands must have a `--dry-run` that prints the exact effect without any filesystem writes.**
   Text summaries like "I'll use adaptive mode, branch X, base-image Y" describe intent, not outcome. `--dry-run` prints the actual directory tree that will appear, the actual target.md content, the actual plan.md Environment block. The agent runs `--dry-run` before every commit; the user approves against concrete output, not paraphrased intent.
   - *Failure ref:* PR-017 had the user confirm decisions in natural language. Without file-tree preview, they couldn't catch a wrong layout-mode pick before it hit disk.

2. **Any command that writes artifacts needs a `--reset` that reverses its writes — but only its own writes.**
   `zo init --reset` deletes `memory/{project}/`, target, and plan. It refuses to touch the delivery repo, even though it wrote into it (scaffold operations only add files, and user code may have been added alongside). The invariant is: *reset removes what the ZO side wrote to its own directories; user code and project-side artifacts are never ZO's to delete.*
   - *Failure ref:* Without --reset, the recovery path was `rm -rf memory/{project} targets/{project}.target.md plans/{project}.md` — user has to type those paths correctly under pressure, easy to hit the wrong `memory/` on the wrong repo.

3. **Destructive commands must require active confirmation, not passive acknowledgment.**
   `--reset` asks the user to *type the project name* as confirmation. Y/N prompts train users to reflexively press Enter; typing the project name forces attention on which project they're about to wipe. For scripts, `--yes` / `-y` opts out explicitly.
   - *Failure ref:* Passive Y/N prompts are muscle memory; projects with similar names can be mistakenly reset.

4. **Protocols for adaptive agents must explicitly cover `partial match` and `semantic alias` cases.**
   "Adaptive mode" and "standard mode" aren't enough — real repos sit between them. A repo with `src/data/` but no `src/model/` is partial; default to **standard** mode (idempotent fill-in). A repo with `src/data_loading/` (semantic alias for `src/data/`) goes **adaptive** with an explicit path mapping in `agent_working_dirs`. Enumerate these cases in the agent protocol, don't let the agent improvise.
   - *Failure ref:* Partial and alias cases weren't explicit in PR-017. Agent would have guessed, producing inconsistent results.

### Verified Solution

`zo init --dry-run` and `zo init --reset [--yes]` added to CLI surface. Init Architect protocol updated with: dry-run as mandatory step before commit, partial-match guidance (standard mode default for partial src/), semantic alias guidance (adaptive + explicit mapping), `--reset` as the canonical rollback path. 10 new tests covering: dry-run writes nothing, dry-run shows branch + layout, dry-run rejected without --no-tmux, reset deletes ZO artifacts, reset preserves delivery repo + user code, reset no-ops on nonexistent project, reset refuses on name mismatch, reset accepts matching name.

---

## PR-020: Generic Agents Need a Per-Project Adaptation Mechanism
**Source:** Session 014 (2026-04-13), prod-001 readiness review
**Root cause category:** missing_rule
**Failure:** The user asked for XAI and Domain Evaluator to adapt per project, but there was no mechanism — the agent `.md` files were static. For CIFAR-10 (generic image classification) the defaults worked; for prod-001 (rotating-machinery vibration signals) they were useless. The "custom agents" feature (PR #28) adds NEW roles but doesn't modify existing ones. This left `xai-agent` and `domain-evaluator` producing generic SHAP/GradCAM output for a project that needed frequency-domain attribution, envelope-demodulation plots, and rotating-machinery domain priors (BPFO/BPFI/BSF/FTF bearing defect frequencies).

### Rules

1. **Generic, cross-project agents need a per-project adaptation channel.**
   Not everything should be hard-coded in the agent's `.md`. The static portion is the agent's role, tools, and coordination protocol — stable across projects. The project-specific portion (domain priors, relevant techniques, dataset-specific quirks) lives in the plan and is injected at spawn time. This keeps the agent file reusable and the plan the single source of truth for project context.
   - *Failure ref:* Without an adaptation mechanism, the user's options were (a) fork xai-agent.md per project — drift-prone, (b) accept generic output — defeats the purpose, (c) manually override in the build session — not reproducible. An explicit plan-level mechanism is the only clean option.

2. **Adaptations are additive, not replacement.**
   Append to the agent's base spawn prompt rather than replacing it. Keeps the agent's core identity and coordination rules intact; the adaptation just tailors focus areas, techniques, and priors. Replacement-style overrides fragment agent behavior across projects and make regressions hard to trace.
   - *Implementation:* Lead Orchestrator prompt includes a `# Per-project Agent Adaptations` section; Lead spawns agents with `Agent(name="xai-agent", prompt="... base contract ... ## Project-specific adaptation\n{adaptation_text}")`.

3. **The Plan Architect during draft is the right author for adaptations.**
   Adaptations require domain understanding (from Research Scout) and data understanding (from Data Scout) that emerges during plan drafting. Asking the user to write them manually after `zo init` misses the conversational advantage. The architect proposes adaptations as part of the normal flow, and the user approves/revises like any other plan section.

4. **Adaptations compose with custom agents, not compete.**
   A project can have both: `**Custom agents:**` (new roles like `signal-analyst`) AND `**Agent adaptations:**` (domain context for `xai-agent` + `domain-evaluator` + custom agents themselves). Orchestrator handles both in one pass. Don't force the user to pick a single mechanism.

### Verified Solution

Plan schema extension: `AgentAdaptation` pydantic model, `AgentConfig.adaptations` field, `adaptation_for(name)` lookup. Parser: `_ADAPTATIONS_RE` + `_parse_adaptations` supports single-line and multi-line entries, blank-line-separated. Orchestrator: `_adaptation_for`, `_prompt_adaptations` dedicated section in lead prompt, inline adaptation inside each agent contract in `_prompt_contracts`. Protocol: Plan Architect tells its scouts' findings become adaptation text; Lead Orchestrator tells the Lead to append adaptations to spawn prompts. 23 new tests (7 parser + 9 orchestrator + 7 integration covering core + custom agent adaptations, plans without adaptations, contracts inline, lead prompt dedicated section) bring total to 476 passing.

---

## PR-021: Rich Markup + User Content — Use `Text` Objects, Not Inline Tags
**Source:** Session 015 (2026-04-13), branded `zo --help` implementation
**Root cause category:** novel_case
**Failure:** When rendering the `DESCRIPTION` section of `zo init --help`, shell-continuation backslashes at line ends (from the `init` docstring's `zo init prod-001 --no-tmux \`) rendered as `\\` (two backslashes). Separately, the `[standard|adaptive]` Choice metavar for `--layout-mode` disappeared entirely from the `OPTIONS` section — Rich consumed it as an invalid markup tag `[standard|adaptive]`. Both failures traced to mixing user-provided content with Rich's markup parser inside f-strings.

### Rules

1. **Rich interprets `[...]` in any string passed to `Console.print()` as markup.**
   `"[bold]hello[/]"` renders `hello` in bold. But so does `"[standard|adaptive]"` — Rich tries to parse it, fails, and silently drops the text (treated as an unrecognized tag). Click's `get_help_record(ctx)` returns option decls like `--layout-mode [standard|adaptive]` where the brackets are literal, not markup — feeding that into an f-string with `[bold]...[/]` wrappers destroys the metavar.
   - *Failure ref:* First pass of `_render_help` used `rc.print(f"  [bold]{decl.ljust(w)}[/]  [{_DIM}]{help_msg}[/]")`. `[standard|adaptive]` vanished from the output.

2. **`rich.markup.escape()` doubles trailing backslashes, even when no `[...]` follows.**
   The intent of `escape()` is to neutralize `[tag]` patterns so brackets render literally. As a safety measure it also doubles any `\` that precedes `[` — including the degenerate case of a `\` at the end of a string (no following character). For docstrings that use `\` as shell line-continuation, this doubles them in the rendered output (`\\` instead of `\`). Using `escape()` to sanitize user content before interpolating into markup strings is therefore NOT safe for arbitrary text.
   - *Failure ref:* Second pass replaced raw interpolation with `escape(decl)` and `escape(help_msg)`. The metavar problem resolved, but every shell-continuation `\` in the `init` docstring became `\\`.

3. **For sections that mix Rich styling with user-provided content, build Rich `Text` objects and apply `style=` programmatically.**
   `Text("  ").append(decl.ljust(w), style="bold").append("  ").append(help_msg, style=_DIM)` keeps the text verbatim — brackets, backslashes, unicode dashes — while still colorizing the segments. `rc.print(text_obj)` renders without re-parsing markup. For plain user content with no per-segment styling (the `DESCRIPTION` body), use `rc.print(line, markup=False, highlight=False)` — equivalent outcome, less construction overhead.
   - *Applies to:* Any help renderer, banner content from config files, logs of user input, agent output echoed to console.

4. **Reserve inline `[tag]…[/]` markup strings for Rich-authored content only.**
   Section headers (`f"[{_AMBER}]USAGE[/]"`), the footer hint (`f"[{_DIM}]Run[/] [bold]zo COMMAND --help[/] …"`), and fixed brand copy in the banner (the tagline) are safe — the content is literal and under our control. Any time the content comes from `command.help`, `get_help_record`, or another source we didn't author, stop the markup at the string boundary and switch to `Text` objects.

### Verified Solution

`_render_help` in `src/zo/cli.py` uses two patterns side-by-side:
- **Rich-authored content (section headers, footer, banner tagline):** inline markup is fine — `rc.print(f"[{_AMBER}]USAGE[/]")`.
- **User/Click-provided content (command/option decls, help text, metavars, docstrings):** build a `Text` object, apply styles via `append(segment, style=…)`, then print the `Text`. For multi-line docstring bodies with no per-segment styling, `rc.print(line, markup=False, highlight=False)` is the simpler shortcut.

This separation fixed both failures in one pass: `[standard|adaptive]` renders verbatim in the `OPTIONS` column (because `Text.append("--layout-mode [standard|adaptive]", style="bold")` never touches Rich's markup parser), and shell-continuation backslashes in the `DESCRIPTION` render as single `\` (because `markup=False` bypasses both parsing and escape-expansion). Validated by `tests/unit/test_cli.py::test_help_output` plus visual inspection of `zo --help`, `zo init --help`, `zo gates set --help`.

---

## PR-022: Tmux Paste Timing Must Account for Cold Start Latency
**Source:** Session 016 (2026-04-14), first `zo init prod-001` run
**Root cause category:** incomplete_rule
**Failure:** `zo init prod-001` opened a blank Claude Code session — the TUI rendered but the prompt was never submitted. The paste-buffer arrived 3 seconds after `claude` was launched, but the TUI wasn't ready for input yet (cold start with extensions, hooks, CLAUDE.md loading takes 5-10s).

### Rules

1. **Claude Code's TUI takes 5-10s to become input-ready on cold starts.**
   Extensions, hooks, CLAUDE.md loading, and memory file scanning all happen
   before the input field accepts text. 3s was based on warm-start testing
   (Claude already running, new window). Cold starts (first launch in a
   session, or after machine sleep) take significantly longer.
   - *Failure ref:* First prod-001 init. User saw Claude TUI but no prompt.

2. **tmux paste-buffer is fire-and-forget — no error if the target isn't ready.**
   `tmux paste-buffer -t %5` succeeds even if the pane is showing a
   loading screen. The pasted text simply goes nowhere. There's no
   feedback mechanism to detect that the paste missed its target.
   - *Failure ref:* All tmux commands returned exit code 0. No indication of failure.

3. **Fixed waits are fragile but retries risk double-submission.**
   A retry (paste again after N seconds) works if the first paste failed,
   but if the first paste succeeded and Claude started processing, the
   second paste lands as a new message — causing duplicate work or
   confusion. Fixed waits with generous margins are safer than retries
   for this specific interaction.
   - *Design ref:* Retry approach was implemented then removed in PR #34.

4. **Test timing assumptions against the slowest realistic environment.**
   The 3s value was tested on a warm machine with Claude already running.
   Production use (first run of the day, after machine sleep, with a large
   CLAUDE.md) is the slowest case and the most common first-time user
   experience. Default to the slow case.

### Verified Solution

`time.sleep(8)` before `tmux load-buffer` + `paste-buffer`. `time.sleep(1)` before `send-keys Enter` (was 0.5s). If 8s proves insufficient on even slower machines, the user can manually paste the prompt from `logs/wrapper/{team}-prompt.txt` — it's always written before the tmux launch.

---

## PR-023: Tmux Agent Sessions Must Auto-Cleanup When Claude Exits
**Source:** Session 016 (2026-04-14), first `zo init prod-001` run — post-session
**Root cause category:** missing_rule
**Failure:** After typing `/exit` in the Init Architect's Claude session: (a) the tmux agent window stayed open (shell still running after Claude exited), (b) the invoking terminal showed only elapsed-time ticks with no summary or next steps, (c) the `_wait_tmux` monitoring loop never terminated because `_tmux_pane_alive()` only checked pane existence, not whether Claude was the active process.

### Rules

1. **Check the running process, not just the pane.**
   `tmux display-message -t PANE -p "#{pane_current_command}"` returns
   the foreground command (e.g. `claude`, `node`). When Claude exits,
   this falls back to the shell (`bash`, `zsh`). Checking pane existence
   alone will hang forever because the shell never exits on its own.
   - *Failure ref:* Monitoring loop ran indefinitely after user typed /exit.

2. **Kill the agent window on session completion.**
   The tmux window was created by ZO for the agent — ZO should clean it
   up. Leaving orphan shell windows after every `zo init`/`zo draft`/
   `zo build` accumulates clutter the user has to manually close.

3. **Print a summary and next steps in the invoking terminal.**
   The invoking terminal (where `zo init` was run) is the user's
   home base. When the agent finishes, this terminal should show:
   what happened (Haiku summary of events), what's next (the next
   pipeline step), and return the shell prompt. Just printing
   "Session completed" with no context wastes the buffered events.

### Verified Solution

Three additions to `wrapper.py` + `cli.py`:
1. `_tmux_claude_running(pane_id)` — checks `#{pane_current_command}`, returns False if it's a shell
2. `_kill_tmux_window(pane_id)` — kills the window containing the pane
3. `_wait_tmux()` uses both conditions: pane exists AND Claude running; kills window on exit
4. `_generate_session_summary(events, team_name)` — Haiku 2-3 bullet summary printed post-completion

---

## PR-024: Public Repos Must Never Contain Client Project Data
**Source:** Session 016 (2026-04-14), preparing first production project
**Root cause category:** missing_rule
**Failure:** ZO is a public repository. Plans, targets, memory, custom agents, and logs for client projects were being tracked by git. Platform memory (`memory/zo-platform/`) referenced a client project by name in 59 instances across DECISION_LOG, PRIORS, STATE.md, and session summaries. Commit messages and PR descriptions also referenced the client name. Any of these could constitute a breach of client confidentiality if pushed to the public repo.

### Rules

1. **Project-specific files are ALWAYS gitignored.**
   `plans/*`, `targets/*`, `memory/*` (except `memory/zo-platform/`),
   `.claude/agents/custom/*`, and `logs/` are in `.gitignore`.
   Only ZO platform files (its own build plan, platform memory) are tracked.

2. **Platform memory uses project aliases, never client names.**
   Convention: `prod-001`, `prod-002` for production projects;
   `demo-mnist`, `demo-cifar10` for demos. The alias→name mapping
   lives only in the gitignored `memory/{project}/` directory.

3. **Commits, PRs, and branch names use aliases only.**
   "feat: add adaptive scaffold for prod-001 readiness" — not the client name.
   PR descriptions reference "first production project", not the client.

4. **Domain-specific details that identify the client are confidential.**
   Process chemistry, product names, plant locations, tag naming
   conventions — none of these belong in platform memory. Platform
   memory captures what ZO learned (e.g., "conversational init works
   better than flag proliferation"), not what the project contained.

5. **If a client name appears in a tracked file, remove it immediately.**
   This is a legal obligation. Do not wait for the next session.

### Verified Solution

1. `.gitignore` updated with project-specific paths and ZO-platform exceptions
2. 59 instances of client references replaced with `prod-001` alias
3. CLAUDE.md gains "Client Project Confidentiality" section (NON-NEGOTIABLE)
4. All existing tracked project files (MNIST targets, logs) untracked via `git rm --cached`

---

## PR-025: Mocked Tests Hide Interface Mismatches — Integration Tests Catch Them
**Source:** Session 016 (2026-04-14), `zo preflight` against first production plan
**Root cause category:** missing_rule
**Failure:** `zo preflight` failed with three stacked bugs: (1) `report.is_valid` → `report.valid`, (2) `i.field` → `i.section`, (3) oracle parser couldn't match parenthetical suffixes in field names. All survived because preflight had ZERO tests and no integration test ever created real `ValidationReport`/`ValidationIssue` objects.

### Rules

1. **Every module that reads another module's models needs an integration test with real objects, not mocks.**
   Mocks use whatever attribute names the test author writes — they don't validate the real interface.

2. **Test against the fixture plan, not just synthetic data.**
   `tests/fixtures/test-project/plan.md` exists for this. One `_check_plan(FIXTURE_PLAN)` call catches all attribute mismatches.

3. **When a parser uses alias lookups, test with real-world decorated variants.**
   Parenthetical qualifiers, extra whitespace, mixed case — all must work.

4. **Preflight is the last gate before `zo build` — it must be tested end-to-end.**
   A buggy preflight that gives false PASSes leads to expensive build failures.

### Verified Solution

`tests/integration/test_preflight.py` — 9 tests covering: fixture plan validation, parenthetical oracle fields, validation error formatting, full `run_preflight()` pipeline, edge cases. All use real parser output, no mocks. Test count: 476 → 485.


---

## PR-026: Denylist-First for DL Data Pipelines
**Source:** Session 017 (2026-04-14), prod-001 Phase 1 data pipeline
**Root cause category:** incomplete_rule
**Failure:** Phase 1 data pipeline initially used a ~164-tag manually-curated allowlist, limiting the feature space to <1% of available signals. This was inherited from a pre-project config file created by a different person. The pipeline worked correctly but the allowlist was an unnecessary bottleneck — DL models can handle and benefit from the full feature space (~15,600 tags → ~88,890 features after aggregation).

### Rules

1. **Default to denylist (exclude leakage only), not allowlist (curate inputs).**
   In DL/ML data pipelines, the pipeline's responsibility is preventing target leakage, not selecting features. Include all available signals and let the model handle feature importance.

2. **Curated tag/feature lists from pre-project setup should be treated as reference, not as runtime filters.**
   These lists reflect one person's assumptions about what's relevant. They may be incomplete, biased, or outdated.

3. **Feature selection belongs in Phase 2, configured per model type.**
   Tree models (XGBoost) have built-in feature selection. Neural nets learn representations. The transform should be model-dependent, not pipeline-dependent.

4. **When inheriting config from a previous human, validate assumptions against the full dataset.**
   The 164-tag list was never validated against the 15,601 available tags. A simple count comparison would have flagged the 99% reduction immediately.

### Verified Solution

Switch `align.py` from `filter_allowed_tags()` to `filter_excluded_tags()`. Mark `input_tags.yaml` as "reference only" in pipeline config. Add `filter_excluded_tags()` tests. 297 tests pass. Feature space: 164 → 14,815 tags.

---

## PR-027: Specialist Review Personas Are Complementary
**Source:** Session 017 (2026-04-14), prod-001 Phase 1 specialist reviews
**Root cause category:** novel_case
**Failure:** Not a failure — a validated practice. Three specialist reviews (domain, ML, data science) of the same pipeline found non-overlapping issues. Each caught things the others missed.

### Rules

1. **Use 3+ specialist review personas for Phase 1 pipelines: domain expert, ML methodologist, data scientist.**
   Each has distinct blind spots.

2. **Convert specialist findings into automated tests immediately.**
   Domain review findings → `test_domain_validation.py`. This prevents regression.

3. **Review findings should update pipeline code AND config AND docs.**
   A finding that only updates one layer will drift from the others.

### Verified Solution

3 specialist reviews → 40+ domain validation tests. All findings addressed in code, config, and documentation. 297 tests passing.

---

## PR-028: Project Memory Must Live in the Delivery Repo, Not the Platform Repo
**Source:** Session 018 (2026-04-15), prod-001 Mac Mini → GPU server transfer
**Root cause category:** missing_rule
**Failure:** User moved prod-001 from Mac Mini to GPU server. `zo status prod-001` failed with "No STATE.md found" because `memory/{project}/` is gitignored in the ZO public repo. All project state (STATE.md, DECISION_LOG, PRIORS, sessions, plans) was trapped on the original machine. The only recovery option was manual `scp`.

### Rules

1. **Project memory belongs in the delivery repo, not the platform repo.**
   The delivery repo is private (client-specific) and committed to git. `git pull` on a new machine brings code AND state. The ZO public repo should contain zero project-specific artifacts — not even gitignored ones, since gitignored files don't transfer.
   - *Failure ref:* `zo status` on GPU server found nothing. Memory existed only on Mac Mini.

2. **Use a `.zo/` directory in the delivery repo for all project state.**
   `.zo/config.yaml` (portable project config, committed), `.zo/local.yaml` (machine-specific paths, gitignored), `.zo/memory/` (STATE.md, DECISION_LOG, PRIORS, sessions), `.zo/plans/` (the project plan). This mirrors the `.git/`/`.claude/` convention.
   - *Implementation:* scaffold.py adds `.zo/` dirs; CLI detects `.zo/config.yaml` as project marker.

3. **Machine-specific paths must be separated from portable config.**
   Data directories, GPU info, and gate mode vary per server. Store in `.zo/local.yaml` (gitignored). Portable config (project name, branch, agent dirs, workflow mode) goes in `.zo/config.yaml` (committed). On a new machine, `zo continue --repo` auto-detects environment and populates `local.yaml` conversationally.
   - *Failure ref:* Target file stored absolute paths that were wrong on the new server.

4. **Platform memory (zo-platform/) stays in the ZO repo — only generic learnings.**
   ZO's own STATE.md, DECISION_LOG, PRIORS are platform infrastructure. Project-specific learnings go to the project's own PRIORS. Cross-reference with `**ZO Platform ref:** PR-XXX`.

### Verified Solution

New `.zo/` directory structure in delivery repos. `zo migrate` command for existing projects. `zo continue --repo` for reconnecting on new machines. `_detect_delivery_repo()` + `_load_project_context()` in CLI for dual-layout support (legacy + `.zo/`).

---

## PR-029: Every Command That Resolves Project Context Must Accept --repo
**Source:** Session 018 (2026-04-15), first `zo continue --repo` on GPU server
**Root cause category:** incomplete_rule
**Failure:** `zo continue --repo ~/my-project` correctly resolved the `.zo/` layout and found the plan at `.zo/plans/{project}.md`. But `continue_` delegates to `build()` via `ctx.invoke()`, and `build()` re-called `_load_project_context(project_name)` without the `--repo` hint. Build fell back to legacy layout, looked for `targets/{project}.target.md` in the ZO repo, and crashed with `FileNotFoundError`. Same class of bug existed in `gates_set` and `watch_training` — neither accepted `--repo`.

### Rules

1. **Every CLI command that calls `_load_project_context()` must accept a `--repo` option and pass it as `delivery_repo`.**
   Without this, the command can only find projects via cwd detection or legacy layout. On a new machine where cwd is the ZO repo (not the delivery repo), both fail. Commands affected: build, continue, status, gates set, watch-training.
   - *Failure ref:* `zo continue --repo ~/my-project` → build() → `FileNotFoundError: targets/{project}.target.md`

2. **When one command delegates to another via `ctx.invoke()`, context must flow through the call.**
   `continue_` resolved the delivery repo but passed only `plan_path` to `build()`. The fix: `build()` infers the delivery repo from the plan path when it's inside `.zo/plans/`. This is a generic pattern: any command that delegates must either pass context explicitly or encode it in the arguments.
   - *Failure ref:* `plan_path=/home/user/project/.zo/plans/{project}.md` was passed but delivery repo was not.

3. **Test every cross-machine code path, not just the happy path.**
   The original tests verified `.zo/` detection and `_load_project_context()` individually. None tested the full `continue → build` delegation with a `.zo/` plan path. The bug was in the seam between two tested components.
   - *Failure ref:* 521 tests passed, 0 tested the actual continue→build handoff.

### Verified Solution

1. `build()` infers `delivery_hint` from `plan_path.resolve().parts[-3:-1] == (".zo", "plans")`
2. `gates_set` and `watch_training` gain `--repo` options
3. Integration test `TestBuildDeliveryHint` verifies the plan-path → delivery-repo inference
4. **Rule for future commands:** any new command that uses `_load_project_context()` MUST include `--repo`

---

## PR-030: Client Confidentiality Must Be Enforced by Automated Check, Not Human Discipline
**Source:** Session 018 (2026-04-15), repeated violation of PR-024 across 3 commits + 1 PR body
**Root cause category:** ignored_rule
**Failure:** PR-024 (session 016) established that client identifiers must never appear in tracked ZO files. Despite this, session 018 committed prod-001 client identifiers into DECISION_LOG.md, PRIORS.md, cli.py docstrings, and a PR body — the EXACT same class of violation PR-024 was supposed to prevent. The prior existed as text but had no enforcement. PR-005 already established that "aspirational rules without enforcement are dead letter" — and PR-024 violated that principle by being an aspirational rule itself.

### Rules

1. **`validate-docs.sh` Check 8 scans all tracked files for a client blocklist.**
   Pattern: client-specific identifiers (case-insensitive grep, maintained in validate-docs.sh).
   This is a HARD FAIL, not a warning. The PreToolUse hook blocks `git commit`
   if validate-docs fails, so client names physically cannot be committed.
   - *Failure ref:* 4 violations in session 018 despite PR-024 existing.

2. **The blocklist lives in validate-docs.sh and is updated when onboarding new clients.**
   New project → add the client's identifiable patterns to `CLIENT_BLOCKLIST`.
   This is a one-line edit. The check runs in <2 seconds with all other validations.

3. **PR descriptions and commit messages must also be sanitised.**
   validate-docs.sh catches file contents but cannot catch git messages.
   Claude must self-check commit messages and PR bodies against the blocklist
   before submitting them. This is the one remaining manual discipline —
   but now there's an explicit checklist item, not just a vague rule.

### Verified Solution

`scripts/validate-docs.sh` Check 8: `git ls-files | xargs grep -liE "$CLIENT_BLOCKLIST"`.
HARD FAIL if any match. PreToolUse hook on `git commit` runs validate-docs.sh,
so commits with client names are physically blocked.

---

## PR-031: Fixed Sleeps for External Process Readiness Are Machine-Dependent — Poll Instead
**Source:** Session 018 (2026-04-15), `zo continue` on GPU server — blank Claude Code session
**Root cause category:** incomplete_rule
**Failure:** `_launch_tmux()` used `time.sleep(8)` before pasting the prompt into Claude Code's TUI. On the Mac Mini this was sufficient. On the GPU server (different hardware, different cold-start latency) the TUI wasn't ready after 8s — the paste was silently dropped and Claude Code appeared blank with no prompt submitted.

### Rules

1. **Never use a fixed sleep to wait for an external process to become ready.**
   Fixed sleeps are calibrated on one machine and break on another. The only
   reliable approach is polling for a readiness signal. For tmux panes, use
   `tmux capture-pane -p` to read content and detect when the TUI has rendered.
   - *Failure ref:* 3s (PR-001), increased to 8s (PR-022), still failed on GPU server.

2. **Poll with stability detection: content must be substantial AND settled.**
   Check that (a) pane has >100 chars (TUI frame rendered, not just a shell) and
   (b) content is identical across 2 consecutive polls (rendering complete, not
   mid-draw). This adapts to any machine speed automatically.

3. **After paste, verify it was received — retry once if not.**
   `tmux paste-buffer` is fire-and-forget with no error if the target isn't ready.
   After pasting + Enter, check if pane content changed. If it still looks like an
   empty input, retry the paste once. Log the prompt file path for manual recovery
   if retry also fails.

### Verified Solution

`_wait_for_tui_ready()` polls `tmux capture-pane` every 1s for up to 30s, requiring
2 consecutive stable readings with >100 chars. `_verify_prompt_submitted()` checks
post-paste content and retries once if the paste appears to have missed. Falls back
gracefully with logged error + prompt file path for manual recovery.

---

## PR-034: PyTorch MPS Tensor.tolist() Returns Garbage Under Pytest (Use bincount or CPU Eval)
**Source:** Session 023 (2026-04-26), CIFAR-10 oracle test failures
**Root cause category:** novel_case
**Failure:** CIFAR-10's `evaluate()` function builds a 10×10 confusion matrix by iterating `zip(y.tolist(), preds.tolist())`. The same code ran cleanly during training (called 25× across epochs, produced a valid confusion matrix saved to `summary.json`) and in a standalone diagnostic script. Under pytest, the test fixture re-runs `evaluate(model_on_mps, test_loader, device=mps)` and `preds.tolist()` returns garbage values like `13806002416` and `5572452850874712064` (memory addresses, not class indices in `[0, 9]`). Adding `.cpu()` before `.tolist()` did not help. Switching to `torch.bincount((y * 10 + preds).cpu(), minlength=100)` ALSO failed — the cpu-side tensor still had garbage values, suggesting the MPS→CPU copy itself was returning stale memory.

### Rules

1. **MPS tensor → CPU value extraction in pytest's process model is unreliable in PyTorch 2.x.**
   The same `evaluate()` works correctly when called from a normal Python script, from inside the training loop, and via `python3 -c "..."` one-liners. Pytest's fixture/teardown context appears to leave MPS sync state in a way that subsequent `.cpu()` calls can return uninitialised memory. Reproducible across `.tolist()`, `.numpy()`, and `torch.bincount` paths.
   - *Failure ref:* CIFAR-10 oracle tests on macOS / PyTorch 2.11 / Python 3.12.

2. **Pin test-time evaluation to `torch.device("cpu")` even when training used MPS/CUDA.**
   The 10K-sample CIFAR-10 / MNIST test set evaluates on CPU in seconds — the speed gain from MPS at test time is not worth the bug surface. Training stays on MPS via `select_device("auto")`; only the test fixture forces CPU. This is also good practice for cross-platform reproducibility (CI/Linux/different macOS hardware all behave the same way).
   - *Pattern:* `device = torch.device("cpu")` inside oracle test bodies, not `select_device("auto")`.

3. **Do not assume MPS-CPU bug fixes from PyTorch issue trackers apply to your version.**
   Various MPS sync bugs were reported and fixed across PyTorch 1.13 → 2.11. New regressions appear; old fixes get reverted. When you hit MPS weirdness, the fastest path is "don't use MPS for this code path" rather than chasing the upstream fix.

4. **Training-time evaluation can hide bugs that test-time evaluation surfaces.**
   The training loop has dozens of synchronizing operations (`.item()`, optimizer step, scheduler step, gradient calls) that incidentally force MPS sync. A test fixture that calls `evaluate()` once on a fresh model load doesn't have those sync points. Tests for evaluation paths should be allowed to differ from training in subtle ways like device choice.

### Verified Solution

`tests/ml/test_oracle.py::test_must_pass_threshold` and `::test_per_class_floor` set `device = torch.device("cpu")` explicitly, then call `model.to(device)` before `evaluate()`. Tests pass deterministically. Training path (`src/engineering/trainer.py`) still uses `select_device("auto")` and gets MPS speedup. The trainer's `evaluate()` retains the `bincount` form as a future-proof improvement (vectorised, faster, sidesteps per-element transfers when the bug is eventually fixed).

---

## PR-033: Templated Files With Platform-Specific Behavior Must Branch at Scaffold Time, Not Runtime
**Source:** Session 023 (2026-04-26), Docker GPU passthrough on Mac
**Root cause category:** missing_rule
**Failure:** `src/zo/scaffold.py` previously hardcoded a single `_COMPOSE_TEMPLATE` containing `deploy.resources.reservations.devices: capabilities: [gpu]`. On Mac (Docker Desktop has no GPU passthrough — Apple Silicon MPS lives outside Docker's Linux VM, Intel iGPUs aren't exposed), `docker compose up` either fails with "could not select device driver" or silently runs CPU-only with cryptic warnings, depending on Compose version. ZO had `detect_environment()` returning correct platform/GPU/CUDA info AND used it to populate the plan's `## Environment` section — but the same data wasn't consulted when writing the docker-compose template. Two consumers, one probe, only one wired up.

### Rules

1. **When env detection is wired into one consumer (plan template), wire it into all consumers (Docker scaffold, lockfile generation, test config, etc).**
   The same `EnvironmentInfo` struct already drives `_render_plan_template`. Adding a second consumer (`_resolve_compose_template`) is mechanical. The mistake is treating env detection as "just for the plan" when it's really "the truth about this host that any artifact-emitter might need".
   - *Failure ref:* GPU compose on Mac produced unrunnable Docker setup despite `detect_environment()` correctly reporting `gpu_count=0`.

2. **Default behavior on detection failure should match the most-common production environment, not the most-developer-friendly one.**
   `_resolve_compose_template(None)` falls back to the GPU template on detection error. Reasoning: ZO's production target is Linux GPU servers; emitting the CPU template on a probe failure (where the server actually has a GPU) would silently drop training to CPU — invisible regression. Better to emit GPU compose; if the host is actually Mac, the user gets an explicit `docker compose up` error that surfaces the misconfiguration.
   - *Pattern:* When defaults must be picked under uncertainty, optimise for "noisy failure" over "silent regression".

3. **Tests for default behavior must be host-independent.**
   `test_cli.py::test_scaffold_creates_compose` was hardcoded to assert `capabilities: [gpu]` in the emitted compose, with no parameterisation. It passed on Linux/CI (where `detect_environment()` returns no GPU, falling back to GPU template via the safety rule above) but failed on a Mac dev box (where detection succeeds and correctly picks CPU). The fix: pass `gpu_enabled=True` explicitly. Tests for the default/auto-detect path are separate and mock `detect_environment` deterministically.
   - *Failure ref:* Existing test broke on Mac immediately after the platform-aware change. Caught by the very pytest run that introduced the change — but only because the dev box happened to be Mac. On a Linux CI, the test would have continued passing while masking the new behavior.
   - *Cross-ref:* PR-032 (mock upstream env guardrails when not the test subject). Same family — the test's subject is "the GPU compose has the deploy block", not "the auto-detect picks GPU on this host". The host detection is an upstream guardrail to be mocked or bypassed.

4. **Service names in scaffolded files are stable contracts; rename only with downstream cascade.**
   The existing template named the compose service `gpu`. The CPU variant could legitimately rename it to `runtime` (more accurate), but that would force README updates, agent contract updates, prod-001 scaffold migration, and break user muscle memory. Kept `gpu` across both templates — slight misnomer on Mac, acceptable cost for cross-platform README parity.

### Verified Solution

`scaffold.py`: `_COMPOSE_GPU_TEMPLATE` (existing content) + `_COMPOSE_CPU_TEMPLATE` (no deploy block, CPU base image, header comment) + `_resolve_compose_template(gpu_enabled)` helper + `gpu_enabled: bool | None = None` parameter on `scaffold_delivery`. `cli.py`: `_init_commit_writes` probes once via `detect_environment().gpu_count > 0` and passes through to all three `_scaffold(...)` call sites. 6 new `TestPlatformAwareCompose` tests in `test_scaffold.py` covering both modes explicit, both auto-detect outcomes, detection-failure fallback, CPU service-name parity. Test count 669 → 675 (+6).

---

## PR-032: Tests Targeting Downstream Logic Must Mock Upstream Environment Guardrails
**Source:** Session 021 (2026-04-25), full pytest run on a no-tmux host
**Root cause category:** missing_rule
**Failure:** `tests/unit/test_cli.py::TestInitDryRun::test_dry_run_rejected_in_conversational_mode` failed on a host without tmux installed. The test invokes `zo init foo --dry-run` (no `--no-tmux`) and asserts the error mentions `--dry-run`. But `zo init` checks tmux availability *before* validating flag combinations: on a no-tmux host, `shutil.which("tmux") is None` short-circuits to "Install tmux..." and the `--dry-run` rejection branch is never reached. The test passed in dev/CI (tmux available) but fails on any contributor machine without tmux. This is the inverse of PR-025: PR-025 said don't mock objects whose interfaces you're testing; PR-032 says *do* mock environment guardrails that aren't your test's subject.

### Rules

1. **Mock upstream environment checks when the test targets downstream behavior.**
   `shutil.which`, `os.environ`, `Path.exists` for system tools, `subprocess.run` for external CLIs — patch these when they sit between the test invocation and the code path you're actually exercising. The test isn't about whether tmux exists; it's about whether `--dry-run` is correctly gated.
   - *Failure ref:* No-tmux machine, version-bump PR triggered full pytest, surfaced the latent dep on host tooling.

2. **A passing CI is not proof of a portable test — it's proof of a working CI environment.**
   Tests that depend on installed binaries (tmux, docker, gh, claude CLI) need explicit mocks even when CI has those binaries. Future contributors will check out the repo on stripped-down dev machines.

3. **Order-of-operations matters in CLI argument validation.**
   When the CLI checks env (tmux/docker/gh availability) *before* flag validation, tests for flag-validation paths must short-circuit the env check. Document the order in the CLI source so test authors know what to mock.

### Verified Solution

Patch `shutil.which` to return a non-None path inside the test's context manager:
```python
with patch("zo.cli._zo_root", return_value=tmp_path), \
     patch("zo.cli._main_repo_root", return_value=tmp_path), \
     patch("shutil.which", return_value="/usr/bin/tmux"):
    result = runner.invoke(cli, ["init", "foo", "--dry-run"])
```
669 tests now pass on a no-tmux host. The fix would have caught the original failure: with the patch, the test reaches the `--dry-run` rejection regardless of whether tmux is on PATH.
