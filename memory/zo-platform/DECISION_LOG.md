# DECISION_LOG — Zero Operators Platform Build

Append-only. Every orchestration decision with timestamp, rationale, and outcome.

---

## Decision: 2026-04-09T16:00:00Z
**Type:** ARCHITECTURE
**Title:** Orchestration approach — Hybrid
**Decision:** Use Claude Code native agent teams for peer-to-peer communication + Python lifecycle wrapper that invokes `claude` CLI, captures lifecycle events, and pipes to JSONL comms logger.
**Rationale:** Native agent teams provide the best communication model (peer-to-peer is the superpower). Python wrapper adds observability without interfering with communication.
**Alternatives considered:** (1) Pure native — less control over logging/lifecycle. (2) Pure Python subprocess — loses peer-to-peer comms.
**Outcome:** Documented in build plan v2.0 as RD1.

---

## Decision: 2026-04-09T16:05:00Z
**Type:** ARCHITECTURE
**Title:** Semantic index granularity — Full entries with summary prefix
**Decision:** One vector per DECISION_LOG entry. Extract 1-line summary from title + outcome at index time. Summary embedded for matching; full entry returned on retrieval.
**Rationale:** Optimizes for context-window density. 3 highly relevant full decisions > 10 noisy fragments.
**Alternatives considered:** (1) Sentence-level splits — too noisy. (2) Paragraph-level — fragments rationale from decision. (3) Defer to v1.1 — loses the value of semantic search.
**Outcome:** Documented in build plan v2.0 as RD2.

---

## Decision: 2026-04-09T16:10:00Z
**Type:** SCOPE
**Title:** zo draft in v1 — Yes, with document indexing
**Decision:** Include `zo draft <source-dir>` in v1 CLI. Takes source docs, indexes them (project-scoped, persisted), generates compliant plan.md.
**Rationale:** Plan drafting is core to the human experience. Without it, every project requires manual plan authoring against a complex 8-section schema.
**Alternatives considered:** Defer to v1.1 — but plan quality directly impacts ZO effectiveness.
**Outcome:** Documented in build plan v2.0 as RD3.

---

## Decision: 2026-04-09T16:15:00Z
**Type:** SCOPE
**Title:** Dashboard API deferred to v2
**Decision:** No API design in v1. CLI + files only.
**Rationale:** Premature API design without frontend to drive requirements leads to wrong abstractions.
**Outcome:** Documented in build plan v2.0 as RD4.

---

## Decision: 2026-04-09T16:20:00Z
**Type:** ARCHITECTURE
**Title:** Agent definition contracts — Inline + shared reference
**Decision:** Each agent .md has a minimal inline contract example + pointer to specs/agents.md for full template.
**Rationale:** Inline makes agents self-contained. Shared reference prevents duplication and ensures consistency.
**Outcome:** Documented in build plan v2.0 as RD5.

---

## Decision: 2026-04-09T16:25:00Z
**Type:** SCOPE
**Title:** Docker deferred to v2
**Decision:** Use uv lockfile + setup.sh for reproducibility. No Docker in v1.
**Rationale:** Single-developer platform build doesn't benefit enough from Docker to justify the complexity. uv lockfile provides deterministic deps.
**Outcome:** Documented in build plan v2.0 as RD6.

---

## Decision: 2026-04-09T16:30:00Z
**Type:** ARCHITECTURE
**Title:** Setup tooling — Both setup.sh + zo init
**Decision:** `setup.sh` for environment bootstrap (claude CLI, agent teams, deps). `zo init` for project scaffolding (memory files, template plan.md).
**Rationale:** Different concerns at different times. setup.sh runs once per environment. zo init runs once per project.
**Outcome:** Documented in build plan v2.0 as RD7.

---

## Decision: 2026-04-09T16:35:00Z
**Type:** SEQUENCING
**Title:** Agent definitions as Step 0
**Decision:** Write all 17 agent .md files before any Python code.
**Rationale:** (1) Immediately usable by Claude Code. (2) Define contracts all modules implement against. (3) Platform build agents needed to build ZO itself. (4) Forces finalization of every agent interface.
**Outcome:** Phase 0 added to build sequence. Documented in build plan v2.0 as RD8.

---

## Decision: 2026-04-09T17:15:00Z
**Type:** MILESTONE
**Title:** Phase 0 complete — 17 agents written
**Decision:** All 17 agent definition files written to .claude/agents/. Settings.json created. Build plan updated to v2.0.
**Rationale:** Phase 0 deliverables met: 11 project delivery agents (7 launch + 4 phase-in) + 6 platform build agents. Each has YAML frontmatter, role description, ownership, off-limits, contract produced/consumed with inline examples, pointer to specs/agents.md, coordination rules, validation checklist.
**Outcome:** Gate 0 ready for human verification. Phase 1 unblocked.

---

## Decision: 2026-04-09T17:30:00Z
**Type:** GATE
**Title:** Gate 0 passed — Human approved agent definitions
**Decision:** PROCEED to Phase 1
**Rationale:** Sam reviewed and approved all 17 agent definitions and .claude/settings.json.
**Outcome:** Phase 1 (Scaffolding) unblocked.

---

## Decision: 2026-04-09T18:00:00Z
**Type:** GATE
**Title:** Gate 1 passed — Phase 1 modules complete
**Decision:** PROCEED to Phase 2
**Rationale:** All 4 Phase 1 modules built and tested. 76 tests passing, 97% code coverage, ruff lint clean. Modules: plan parser (src/zo/plan.py), target parser (src/zo/target.py), comms logger (src/zo/comms.py), setup.sh. PyYAML added as dependency.
**Outcome:** Phase 2 (Core Infrastructure) unblocked.

---

## Decision: 2026-04-09T18:30:00Z
**Type:** ARCHITECTURE
**Title:** Memory layer — three-file split for 500-line limit
**Decision:** Split memory module into memory.py (292 lines), _memory_models.py (89 lines), _memory_formats.py (285 lines).
**Rationale:** Single file would exceed 500-line limit. Models have zero deps beyond pydantic, formats depend only on models, memory.py re-exports everything for clean imports.
**Outcome:** Clean separation, all tests pass.

---

## Decision: 2026-04-09T18:45:00Z
**Type:** ARCHITECTURE
**Title:** Semantic index — graceful fallback without fastembed
**Decision:** When fastembed/numpy are not installed, store entries without embeddings and fall back to word-overlap scoring on summaries for query().
**Rationale:** fastembed is an optional dependency. Core ZO must function without it. Word-overlap is a reasonable fallback for small decision sets.
**Outcome:** 25 tests run without fastembed, 7 additional tests verify embedding path. Both paths verified.

---

## Decision: 2026-04-09T19:00:00Z
**Type:** GATE
**Title:** Phase 2 complete — Gate 2 ready for human review
**Decision:** Memory layer and semantic index both built, tested, and verified.
**Rationale:** 151 tests passing (32 memory + 32 semantic + 76 Phase 1 + 11 integration), 96% coverage, ruff clean. End-to-end smoke test demonstrates full lifecycle: initialize → write state → log decisions → add priors → write summary → build index → semantic query → session recovery.
**Outcome:** Gate 2 ready for human review. Phase 3 (Orchestration Engine) unblocked pending approval.

---

## Decision: 2026-04-09T19:00:00Z
**Type:** ARCHITECTURE
**Title:** Wrapper redesign — observer/launcher, not agent spawner
**Decision:** wrapper.py launches ONE Claude Code session (the Lead Orchestrator), does NOT spawn individual agents via subprocess. The Lead Orchestrator creates the team internally using TeamCreate + Agent(team_name=...). Wrapper monitors via file system (tasks, logs, tmux).
**Rationale:** Research confirmed that Claude Code agent teams with peer-to-peer comms (SendMessage) can only be created from WITHIN a running Claude Code session, not via external CLI calls. Previous design of wrapper.py spawning N individual agents would have produced isolated sessions without peer-to-peer messaging — defeating the core requirement.
**Alternatives considered:** (1) N subprocess calls per agent (no peer-to-peer). (2) Custom file-based messaging (fragile, not native). (3) Single session with TeamCreate (chosen — leverages native peer-to-peer).
**Outcome:** wrapper.py redesigned as observer/launcher. orchestrator.py builds the lead prompt. Lead Orchestrator agent definition updated with 17-agent roster and dynamic agent creation capability.

---

## Decision: 2026-04-09T19:10:00Z
**Type:** ARCHITECTURE
**Title:** Lead Orchestrator — dynamic agent creation
**Decision:** Lead Orchestrator can create new agent definition files (.claude/agents/*.md) on the fly if a project requires expertise not covered by the 17 pre-defined agents.
**Rationale:** The agent roster is a starting point, not a ceiling. Real projects will need domain-specific experts (NLP specialist, time-series expert, security auditor). The Lead Orchestrator has the context to identify gaps and write appropriate agent definitions following the established template.
**Outcome:** lead-orchestrator.md updated with agent roster table and dynamic creation protocol.

---

## Decision: 2026-04-09T19:30:00Z
**Type:** GATE
**Title:** Phase 3 complete — Orchestration engine + wrapper built
**Decision:** PROCEED to Phase 4
**Rationale:** 224 tests passing, 93% coverage, ruff clean. Orchestrator decomposes plans into phases for all 3 workflow modes, generates agent contracts, builds lead prompts with full context. Wrapper launches sessions, monitors teams, handles rate limits. Architecture validated: Python CLI → one Claude session → native agent team with peer-to-peer comms.
**Outcome:** Phase 4 (Hardening — Evolution Engine, CLI, integration tests) unblocked.

---

## Decision: 2026-04-09T20:00:00Z
**Type:** GATE
**Title:** Phase 4 complete — Evolution engine, CLI, integration tests
**Decision:** PROCEED to Phase 5
**Rationale:** 296 tests passing, 90% coverage, ruff clean. Evolution engine implements full post-mortem protocol (5 steps), retrospective, and metrics. CLI provides zo build/continue/maintain/init/status/draft with gate mode toggle (default: supervised). Integration tests verify full pipeline flows. All modules wired together.
**Outcome:** Phase 5 (End-to-end validation) unblocked.

---

## Decision: 2026-04-09T20:30:00Z
**Type:** ARCHITECTURE
**Title:** Wrapper CLI flags corrected — --cwd and --teammate-mode don't exist
**Decision:** Replace `--cwd` with `--add-dir` for delivery repo access. Remove `--teammate-mode tmux` (non-existent flag). Add `--dangerously-skip-permissions` for non-interactive execution.
**Rationale:** First live run failed with "error: unknown option '--cwd'". Investigation showed these flags don't exist in the claude CLI. `--add-dir` grants file access to additional directories. Teams are created internally via TeamCreate, not via CLI flag.
**Alternatives considered:** (1) Use subprocess cwd parameter — doesn't work because claude needs to run from ZO root. (2) Symlinks — fragile. (3) --add-dir — correct approach, grants access without changing working directory.
**Outcome:** First successful live run of ZO. MNIST Phase 1 completed.

---

## Decision: 2026-04-09T21:00:00Z
**Type:** GATE
**Title:** Phase 5 complete — MNIST end-to-end validation passed
**Decision:** ZO platform validated. Ready for real projects.
**Rationale:** MNIST digit classifier built autonomously across 5 phases. 99.00% test accuracy (Tier 1 threshold: 95%). Agent team produced model, inference script, oracle evaluation, GradCAM/saliency XAI, ablation study, significance testing, reproducibility verification. 98 tests in delivery repo. Zero ZO artifacts. 4 clean git commits. Total cost ~$11.
**Known issues:** (1) Phase state not persisted between zo build calls — lead session re-discovers resume point from delivery repo. (2) Blocking gates cause repeated sessions in auto mode. Both are hardening items, not blockers.
**Outcome:** ZO is production-ready for real projects. prod-001 is next.

---

## Decision: 2026-04-09T22:00:00Z
**Type:** FEATURE
**Title:** 23 slash commands added for Claude Code
**Decision:** Implement full command vocabulary: project lifecycle (connect/import/plan/launch), memory (recall/prime/priors/session-summary), gates (approve/reject/gates), observability (watch/logs/decisions/history), documentation (code-docs/validation-report/model-card/retrospective), agent management (agents/spawn/create-agent), utility (commit).
**Rationale:** Inspired by coleam00/habit-tracker .claude/commands pattern. ZO needs its own vocabulary mapping to the plan→execute→verify→evolve loop. Commands provide the interface between human and ZO inside Claude Code sessions.
**Outcome:** 23 command files in .claude/commands/, COMMANDS.md reference, interactive HTML demo. Session closed — ready for prod-001.

---

## Decision: 2026-04-10T10:00:00Z
**Type:** BUGFIX
**Title:** Wrapper launches Claude in visible tmux pane instead of headless
**Decision:** Split `launch_lead_session` into two paths: tmux-visible (default when inside tmux) and headless fallback. tmux mode uses `tmux new-window` to spawn Claude without `--print`, giving the user the interactive TUI. Headless mode preserves the original `--print --output-format json` behavior.
**Rationale:** First live user test revealed that `zo build` appeared stuck — "Monitoring session: pid=XXXXX" with no visible output. The wrapper was running Claude as an invisible background process with stdout piped to log files. The `use_tmux` parameter was accepted but never used. Users need to see agent teams working (the whole point of tmux teammateMode).
**Alternatives considered:** (1) Stream subprocess stdout to terminal — doesn't work for TUI rendering. (2) Always use headless + progress bar — loses the live agent visibility that makes ZO compelling. (3) Visible tmux pane (chosen) — natural integration with Claude Code's native teammateMode.
**Outcome:** wrapper.py split into `_launch_tmux` / `_launch_headless` + `_wait_tmux` / `_wait_headless`. LeadProcess gains `tmux_pane_id` field. CLI shows pane navigation tips. 296 tests pass, 7 new tests added.

---

## Decision: 2026-04-10T11:00:00Z
**Type:** ARCHITECTURE
**Title:** Interactive tmux launch via send-keys + paste-buffer
**Decision:** Launch Claude Code interactively (no `-p`, no `--dangerously-skip-permissions`) using tmux send-keys to type the command and tmux paste-buffer to submit the prompt. This gives the user the exact same experience as manually opening Claude Code.
**Rationale:** Three approaches failed: (1) subprocess.Popen — no TTY, no TUI. (2) Launcher scripts — shell escaping issues, stderr redirect hid TUI. (3) `-p` with `--dangerously-skip-permissions` — runs non-interactively, no TUI. (4) `--dangerously-skip-permissions` alone — shows warning and exits in interactive mode. The send-keys approach simulates manual user interaction and works reliably.
**Alternatives considered:** (1) Popen (no TTY). (2) Launcher script (escaping). (3) -p flag (no TUI). (4) --dangerously-skip-permissions (exits). (5) send-keys + paste-buffer (chosen).
**Outcome:** Users see full Claude Code TUI with agent team panes. Permissions handled via .claude/settings.json allow/deny rules.

---

## Decision: 2026-04-10T12:00:00Z
**Type:** ARCHITECTURE
**Title:** Merge continue/maintain into smart zo build, add brand panel
**Decision:** (1) `zo build` auto-detects mode (fresh/continue/plan-edited). (2) `zo continue` becomes a thin alias. (3) `zo maintain` removed entirely. (4) Phase review shows in ALL modes. (5) `zo draft` accepts multiple paths. (6) ZO brand panel at startup.
**Rationale:** `zo continue` and `zo maintain` were doing almost the same thing as `zo build` — parsing plan, decomposing, launching agents. Having three commands confused the user. Smart detection in `zo build` handles all cases. Brand panel gives professional identity matching Claude Code's startup experience.
**Outcome:** Simplified CLI: build (primary), continue (alias), draft, init, status. 295 tests pass.

---

## Decision: 2026-04-10T14:00:00Z
**Type:** EVOLUTION
**Title:** Three-layer defense against doc-codebase drift
**Decision:** Implement automated documentation consistency validation with enforcement hooks. (1) `scripts/validate-docs.sh` — 7 programmatic checks (agent count, agent names, command count, version, model tiers, test badge, setup.sh literal). (2) PreToolUse hook in `.claude/settings.json` blocks `git commit` if validation fails. (3) PostToolUse hook on Write|Edit injects cascade reminders when trigger files modified. (4) CLAUDE.md updated with explicit file-to-file cascade mappings. (5) PR-005 added to PRIORS.md.
**Rationale:** Adding Research Scout (17th agent) left 10+ files with stale counts. CLAUDE.md "Cascade doc updates" protocol existed but had zero enforcement. PR-003 recommended hooks but they were never implemented. Root cause: `missing_rule` — aspirational text without enforcement degrades to suggestion. Self-evolution protocol requires fixing both the symptom and the rule.
**Alternatives considered:** (1) Manual discipline only — already failed. (2) CI pipeline — too heavy for v1, not available in local dev. (3) Automated validation with hooks (chosen) — catches drift at commit time, lightweight, works in all environments.
**Outcome:** Three new files created (validate-docs.sh, pre-commit-validate.sh, cascade-reminder.sh). settings.json updated with hooks. CLAUDE.md cascade protocol strengthened. PR-005 documents the failure and fix. Validation runs 10 checks in <2 seconds.

---

## Decision: 2026-04-12T11:00:00Z
**Type:** BUGFIX
**Title:** Phase persistence across zo build sessions
**Decision:** Extend SessionState with `phase_states: dict[str, str]` and `completed_subtasks_by_phase: dict[str, list[str]]`. Add `## Phases` section to STATE.md format. Fix `decompose_plan()` to restore saved phase states after creating fresh PhaseDefinition objects. Fix `end_session()` to capture phase states before writing STATE.md.
**Rationale:** `decompose_plan()` unconditionally set `session_state.phase = phases[0].phase_id` (line 222), discarding all saved progress. Second `zo build` call always restarted from phase 1. This blocked any multi-session workflow.
**Alternatives considered:** (1) Store phase state in a separate file — adds complexity. (2) Use git tags for phase tracking — fragile. (3) Extend SessionState + STATE.md format (chosen) — minimal, uses existing persistence infrastructure.
**Outcome:** Phase states persist across sessions. 5 new tests verify round-trip, backward compat, and partial progress restoration. Known issue #1 resolved.

---

## Decision: 2026-04-12T11:15:00Z
**Type:** BUGFIX
**Title:** Blocking gates returned by get_current_phase()
**Decision:** `get_current_phase()` now returns GATED phases first (before checking PENDING phases). This allows the CLI to detect "this phase needs human approval" instead of reporting "all phases complete."
**Rationale:** In auto mode, blocking gates caused wrapper to re-launch sessions that couldn't advance because gated phases were skipped (only PENDING phases were considered). Known issue #2.
**Outcome:** Known issue #2 resolved. 1 new test verifies GATED phase returned for human review.

---

## Decision: 2026-04-12T11:30:00Z
**Type:** FEATURE
**Title:** Phase artifact contracts — required_artifacts per phase
**Decision:** Add `required_artifacts: list[str]` to PhaseDefinition model. Define expected artifacts for all 6 classical_ml phases (e.g., Phase 1 requires `reports/data_quality_report.md`, `reports/figures/eda_summary.png`, `data/processed/`).
**Rationale:** Agents need to know what artifacts each phase must produce. Without explicit contracts, artifact generation is inconsistent. Required artifacts also enable gate-time validation (check files exist before advancing).
**Outcome:** Artifact contracts defined for all 6 phases. No test breakage — field has default empty list for backward compat.

---

## Decision: 2026-04-12T11:45:00Z
**Type:** FEATURE
**Title:** Auto-generated Jupyter notebooks per phase
**Decision:** New `src/zo/notebooks.py` module generates `.ipynb` files with pre-populated cells per phase: data loading, plotting, analysis. Uses nbformat library. Each notebook starts with phase summary, standard imports, and project root setup. Phase-specific cells include try/except for missing artifacts.
**Rationale:** User needs interactive exploration after each phase. Agents produce reports, but notebooks allow hands-on data inspection. Auto-generation ensures consistent structure across phases.
**Alternatives considered:** (1) Template notebooks (user fills in) — requires manual work. (2) Agent-generated notebooks — inconsistent quality. (3) Auto-generated with phase-specific cells (chosen) — consistent, works out of the box.
**Outcome:** 27 tests. Notebooks generated for all 6 phases with valid nbformat. nbformat>=5.0 added to dependencies.

---

## Decision: 2026-04-12T12:00:00Z
**Type:** FEATURE
**Title:** Delivery repo scaffold with Docker (zo init --scaffold-delivery)
**Decision:** New `src/zo/scaffold.py` creates standard ML project layout with multi-stage Dockerfile and docker-compose.yml. Template is bare minimum — agents customize based on plan.md. Dockerfile uses pytorch/pytorch base image, uv for deps, multi-stage for layer caching. No venv inside Docker.
**Rationale:** ZO runs on host (SSH+tmux). Delivery project runs in Docker container with NVIDIA runtime. This separates ZO infrastructure from GPU compute environment. Multi-stage build with uv gives fast rebuilds (~1s for code changes, ~10s for dep changes).
**Alternatives considered:** (1) Docker for ZO itself — too complex for v1. (2) No Docker — loses reproducibility. (3) Docker for delivery only (chosen) — clean separation, agents customize per project.
**Outcome:** 8 new tests. Scaffold creates 10 directories, 6 template files. Idempotent (no-overwrite).

---

## Decision: 2026-04-12T12:15:00Z
**Type:** FEATURE
**Title:** zo preflight command for pre-launch validation
**Decision:** New `src/zo/preflight.py` with `zo preflight plan.md` command. Runs 10 local-only checks: Claude CLI, tmux, plan validation, agent definitions, target repo, delivery structure, Dockerfile, memory round-trip, Docker, GPU availability. GPU/Docker are warnings (not blockers).
**Rationale:** MNIST run revealed multiple issues (tmux TUI, permissions, CLI flags) with no automated detection. Preflight catches configuration problems before committing to a real project run.
**Outcome:** Rich-formatted pass/fail output. <10 seconds, no API calls.

---

## Decision: 2026-04-12T12:30:00Z
**Type:** ARCHITECTURE
**Title:** GPU/CUDA strategy — Docker for delivery, not ZO
**Decision:** ZO runs on host (SSH+tmux). Delivery projects run in Docker containers with NVIDIA runtime. `zo init --scaffold-delivery` provides multi-stage Dockerfile template. Agents customize based on plan.md Environment section. Server needs NVIDIA drivers + Docker + NVIDIA Container Toolkit.
**Rationale:** User analyzed existing R&D Docker setup (pytorch base, 80+ apt packages, CMake from source, venv inside Docker). Identified root causes of slow builds: --no-cache, pip one-at-a-time, source builds in single stage. ZO template fixes all: uv (50-100x faster), multi-stage, layer caching, bare minimum base.
**Alternatives considered:** (1) Docker for ZO itself — too complex. (2) No Docker (direct install) — loses reproducibility. (3) Conda — slower than uv. (4) Docker for delivery only (chosen) — clean separation.

---

## Decision: 2026-04-12T12:45:00Z
**Type:** ARCHITECTURE
**Title:** Auto-detected Environment section in plan.md
**Decision:** During planning phase (`zo draft` / `zo build`), the agent auto-detects platform, GPU, CUDA version, Docker availability, and Python version, then populates the `## Environment` section in plan.md. User reviews and can override. Only data paths require manual input (project-specific, can't be guessed).
**Rationale:** User should never manually specify CUDA version or platform — these are machine properties, not project decisions. Auto-detection during planning ensures correctness and reduces friction. User confirms or overrides (e.g., pin a specific CUDA version for reproducibility).
**Auto-detected fields:** platform (uname), gpu_available (nvidia-smi), cuda_version, gpu_count, gpu_memory, python_version, docker_available, docker_compose_available.
**User-provided fields:** data_paths (where raw data lives), docker_mounts (if non-standard paths needed).
**Alternatives considered:** (1) User manually fills Environment — error-prone, unnecessary. (2) Fully automatic with no review — risky, user should confirm. (3) Auto-detect + user review (chosen) — correct defaults, user can override.
**Outcome:** Design captured. Implementation during prod-001 plan setup. Detection logic will extend `zo preflight` (already detects GPU/Docker) into the planning phase.

---

## Decision: 2026-04-12T14:00:00Z
**Type:** ARCHITECTURE
**Title:** Delivery repo structure redesign — configs, experiments trail, responsibility-based src
**Decision:** Redesigned the delivery repo scaffold to separate concerns: configs/ (YAML, never hardcode), src/ by responsibility (data, model, engineering, inference, utils), experiments/ as context trail (README index + per-experiment config/results/notes), notebooks/ split (human exploration + ZO auto-generated), tests/ split (unit for code correctness + ml for oracle thresholds), docker/ subdirectory. Added STRUCTURE.md as in-repo reference that agents read section-by-section to stay context-efficient.
**Rationale:** Combined user's production ML experience (configs dir, experiment tracking, granular src) with ZO's agent-driven patterns (auto-notebooks, phase reports, artifact contracts). Key insight: experiments/README.md as index + exp-NNN/notes.md for detail follows the same lazy-loading pattern as ZO's own memory (STATE.md as index, drill into DECISION_LOG for detail).
**Alternatives considered:** (1) Keep original flat structure — too vague for real projects. (2) User's exact past structure — lacked ZO-specific patterns (auto-notebooks, reports). (3) Combined best of both (chosen) — responsibility-based code, YAML configs, experiment trail, context-optimised.
**Outcome:** scaffold.py updated (20 dirs, 9 template files), STRUCTURE.md template, experiments/README.md template, configs/experiment/base.yaml template. notebooks.py writes to notebooks/phase/. Architecture spec updated. 334 tests passing.

---

## Decision: 2026-04-12T15:00:00Z
**Type:** FEATURE
**Title:** Orchestrator pipeline wiring — artifact validation, notebooks, Docker in prompt
**Decision:** Wire three previously-disconnected modules into the orchestrator's advance_phase() flow: (1) _check_artifacts() verifies required_artifacts exist in delivery repo before gate passes — missing artifacts return ITERATE. (2) _generate_notebook() auto-generates per-phase Jupyter notebook after gate passes (both automated and human-approved). (3) Lead prompt updated with required artifacts list per phase, Docker build/run commands, STRUCTURE.md reference, configs/ workflow, and experiments/ context trail instructions.
**Rationale:** Modules were built and independently tested but not connected to the orchestrator. Without wiring, a real run would produce no auto-notebooks and no artifact validation — defeating the purpose of building them. Non-negotiable for production use.
**Alternatives considered:** (1) Leave as independent modules, call manually — defeats automation. (2) Wire only notebooks, skip artifact checks — misses the enforcement value. (3) Wire everything into advance_phase() (chosen) — single enforcement point, both automated and human gates covered.
**Outcome:** 4 new tests verify: missing artifacts block gate, present artifacts pass + generate notebook, prompt includes artifacts, prompt includes Docker. 338 tests total.

---

## Decision: 2026-04-12T20:00:00Z
**Type:** UX
**Title:** setup.sh interactive auto-fix — no flags, just prompt
**Decision:** setup.sh now detects fixable failures (uv, Claude CLI, global settings) and prompts "N issue(s) can be auto-fixed. Install now? [Y/n]" instead of requiring a --fix flag. On success, re-execs itself for validation. Uses string-based tracking (FIXABLE_ITEMS/FIXABLE_COUNT) instead of bash arrays.
**Rationale:** User ran setup.sh on a new machine for CIFAR-10 demo and hit 3 failures. Original script only reported errors with manual fix instructions. First iteration added --fix flag, but user correctly pointed out this should be automatic — the install commands are known, why make the user copy-paste them?
**Alternatives considered:** (1) Report-only (original) — poor UX, forces manual copy-paste. (2) --fix flag — still requires user to know about the flag. (3) Interactive prompt with default Y (chosen) — zero-friction, user just hits Enter.
**Outcome:** PR #22. Tested on macOS bash 3.2.57. Auto-installed uv 0.11.6 + Claude Code 2.1.104. Re-validation passed 11/11.

---

## Decision: 2026-04-12T20:00:00Z
**Type:** BUGFIX
**Title:** Claude CLI install command updated to official curl method
**Decision:** Replaced `npm install -g @anthropic-ai/claude-code` with `curl -fsSL https://claude.ai/install.sh | bash` in both the check message and auto-fix function.
**Rationale:** The npm method is deprecated. Official install is now via curl. Discovered during CIFAR-10 demo setup on new machine.
**Alternatives considered:** npm (deprecated), brew (not official), curl (chosen — official method).
**Outcome:** Claude Code 2.1.104 installed successfully via curl on fresh machine.

---

## Decision: 2026-04-12T20:00:00Z
**Type:** BUGFIX
**Title:** Bash 3.2 compatibility — replace array tracking with string counters
**Decision:** Replaced `FIXABLE=()` array + `${#FIXABLE[@]}` length checks with `FIXABLE_ITEMS=""` string + `FIXABLE_COUNT=0` integer counter. Iterates with `for item in $FIXABLE_ITEMS` (word splitting).
**Rationale:** macOS ships bash 3.2.57. In bash 3.2, `${#array[@]}` on an empty array with `set -u` throws "unbound variable" and silently kills the auto-fix block. The --fix flag appeared to do nothing on first attempt because of this.
**Alternatives considered:** (1) Remove `set -u` — weakens safety. (2) Use `${FIXABLE[@]+"${FIXABLE[@]}"}` workaround — fragile, hard to read. (3) String + counter (chosen) — simple, works on all bash versions.
**Outcome:** Auto-fix block now triggers correctly on macOS bash 3.2.57.

---

## Decision: 2026-04-12T20:30:00Z
**Type:** BUGFIX
**Title:** setup.sh must verify zo CLI is callable, not just deps resolvable
**Decision:** Added check #11 to setup.sh: verify `command -v zo` passes. Auto-fix: `uv sync` to build .venv, then symlink `.venv/bin/zo` → `~/.local/bin/zo` (already on PATH from uv install). Changed dep check from dry-run to actual `uv sync --quiet`. Handles worktree case by checking superproject .venv.
**Rationale:** User ran `uv sync` then `zo init` → "command not found". `uv sync` installs into `.venv/bin/` which isn't on PATH when conda/pyenv/system Python is active. setup.sh only checked deps *resolve* (dry-run), never verified the CLI was *callable*. This is the difference between "package manager happy" and "user can type the command".
**Alternatives considered:** (1) Tell user to `source .venv/bin/activate` — adds manual step, breaks "just run setup.sh" promise. (2) `uv pip install -e .` into active env — fragile with conda, pollutes base env. (3) Symlink to `~/.local/bin/` (chosen) — clean, already on PATH, works with any Python env manager.
**Outcome:** setup.sh now passes 12/12 checks. `zo, version 1.0.1` callable after setup. PR-012 prior added.

---

## Decision: 2026-04-12T21:00:00Z
**Type:** FEATURE
**Title:** Conversational zo draft — source documents optional
**Decision:** Reworked `zo draft` so source paths are optional. Three usage modes: (1) source docs → index + template + tmux session, (2) `-d "description"` → skeleton from keywords + tmux session, (3) no args → interactive prompt for description + tmux session. All paths converge at a Claude session that drafts the plan conversationally. Added `generate_plan_from_description()` with workflow mode inference (CNN/PyTorch → deep_learning) and metric hint extraction.
**Rationale:** User ran `zo draft plans/cifar10-demo.md` expecting it to work — but the command required source document paths. CIFAR-10 is a well-known domain with no source docs needed. The rigid template-filling approach produced plans full of TODOs. Making the tmux Claude session the primary drafter (not a refinement afterthought) gives much better results.
**Alternatives considered:** (1) Require source docs always — breaks well-known-domain use case. (2) Generate smarter template without Claude — still static, can't ask questions. (3) Conversational agent-driven (chosen) — Claude asks about objectives, data, metrics, constraints.
**Outcome:** PR #24. 3 new tests, 341 total. zo draft works in all three modes.

---

## Decision: 2026-04-12T21:30:00Z
**Type:** ARCHITECTURE
**Title:** Plans write to main repo, not worktrees — _main_repo_root() helper
**Decision:** Added `_main_repo_root()` to cli.py that detects git worktrees via `git worktree list --porcelain` and returns the main repo path. `zo draft` uses this to write plans to the main repo's `plans/` directory. Draft session prompt references `zo build plans/{project}.md` with main-repo relative path.
**Rationale:** User ran `zo draft` from a worktree. Plan landed in worktree's `plans/` dir. Then `zo build` from main repo couldn't find it. ZO artifacts (plans, memory, state) should always live in the main repo — worktrees are for ZO development, not ZO usage.
**Alternatives considered:** (1) Tell user to copy manually — bad UX. (2) Always run from main repo — doesn't help when you're already in a worktree. (3) Auto-detect and write to main repo (chosen) — transparent, no user action needed.
**Outcome:** PR #25. Plans always land in main repo regardless of cwd.

---

## Decision: 2026-04-12T22:00:00Z
**Type:** UX
**Title:** Brand banner on all CLI commands via shared _show_banner()
**Decision:** Extracted the ZO brand panel (orbital mark, version, project/mode/phase/gates) into a shared `_show_banner()` function. Called at the top of all 6 CLI commands: build, draft, init, status, preflight, continue. Fields are optional — commands that don't have a phase or gates simply omit those lines.
**Rationale:** The brand panel was only in `zo build`. User noted it should appear everywhere — it establishes identity and shows current context at a glance. Professional tooling has consistent branding across all entry points.
**Alternatives considered:** None — clearly the right move.
**Outcome:** PR #25. All commands show the banner.

---

## Decision: 2026-04-12T22:00:00Z
**Type:** ARCHITECTURE
**Title:** Production-grade phase definitions — enriched Phase 1, cross-cutting agents
**Decision:** (1) Phase 1 (Data Review) expanded from 7 to 13 subtasks: added data schema validation, missing value analysis, outlier detection, class imbalance analysis, train/val/test split strategy, data drift baseline. Added research-scout, code-reviewer, domain-evaluator to Phase 1 agents (5 total, was 2). (2) Made code-reviewer and research-scout default on ALL phases across all 3 workflow modes (classical_ml, deep_learning, research).
**Rationale:** Phase 1 with only data-engineer + test-engineer and 7 subtasks was adequate for CIFAR-10 but not for production data (messy, large-scale, domain-specific). The 6 new subtasks cover real-world essentials that were missing. Code review and research are cross-cutting concerns — code quality degrades silently and domain understanding should inform every phase, not just Phase 0.
**Alternatives considered:** (1) Keep minimal, let plan.md override — misses the "good defaults" principle. (2) Add agents to Phase 1 only — leaves other phases thin on review/research. (3) Cross-cutting defaults + enriched Phase 1 (chosen) — good defaults everywhere, plan.md can still override.
**Outcome:** PR #25. Phase 1: 13 subtasks, 5 agents. All phases: code-reviewer + research-scout default.

---

## Decision: 2026-04-12T23:00:00Z
**Type:** ARCHITECTURE
**Title:** Autonomous path handoff — target file as single source of truth for delivery repo
**Decision:** (1) `zo init` now always writes an absolute delivery path to `targets/{project}.target.md`. If `--scaffold-delivery PATH` given, uses that resolved path. If not, defaults to `../{project}-delivery/` resolved to absolute. (2) `zo init` always scaffolds the delivery repo (not just with `--scaffold-delivery`). (3) Target template uses `{target_repo}` placeholder instead of hardcoded `../target-{project}`. (4) `zo build` reads the absolute path from the target file — no path guessing. The user never needs to pass paths between commands.
**Rationale:** User ran `zo init --scaffold-delivery ~/projects/cifar10-delivery`, then `zo build` looked for `/code/target-cifar10-demo` — a completely different path. The target template hardcoded a relative path that never matched the scaffold. The init → draft → build pipeline must carry its own context autonomously through the target file.
**Alternatives considered:** (1) Ask user to pass path at every step — breaks autonomous promise. (2) Store path in STATE.md — wrong abstraction, target file already exists for this. (3) Target file as single source of truth with absolute paths (chosen) — deterministic, no user input between commands.
**Outcome:** PR #25. Target file always has absolute paths. init auto-scaffolds. build reads target file. Full pipeline works without user passing paths.

---

## Decision: 2026-04-12T23:30:00Z
**Type:** FEATURE
**Title:** Haiku headline summaries in live build status feed
**Decision:** Buffer comms events (decisions, gates, checkpoints, errors) during `zo build` status polling. Every 60 seconds, send the last 15 buffered events to Claude Haiku with a prompt to generate a 1-line headline (80 chars max). Print with `▸` prefix in amber. Non-blocking — fails silently if Haiku unavailable.
**Rationale:** The raw event feed (decisions, checkpoints, errors) is useful but verbose. A periodic natural language summary gives the user a quick "what's happening" without reading every line. Like a news ticker for their build.
**Alternatives considered:** (1) No summaries — raw events only. (2) Python-based summariser — brittle, can't handle diverse events. (3) Haiku API call (chosen) — fast, cheap, high quality, graceful degradation.
**Outcome:** PR #25. 60s interval, 15-event batch, 80-char headline.

---

## Decision: 2026-04-12T23:30:00Z
**Type:** FEATURE
**Title:** zo gates set — toggle gate mode mid-session
**Decision:** New CLI command `zo gates set MODE --project NAME` writes the mode to `memory/{project}/gate_mode`. The orchestrator calls `_refresh_gate_mode()` at the top of `advance_phase()` to re-read the file before each gate decision. The wrapper calls `_check_gate_mode_change()` each poll cycle. Changes take effect within 10 seconds — no restart needed.
**Rationale:** In supervised mode, every agent tool call needs approval. User wants to start supervised (to verify things work), then switch to auto once confident. Previously required killing the session and restarting with a different flag.
**Alternatives considered:** (1) Restart with different flag — loses session context. (2) Signal-based (SIGUSR1) — fragile, platform-specific. (3) File-based with polling (chosen) — simple, reliable, works from any terminal.
**Outcome:** PR #25. 6 new tests, 347 total. MemoryManager.read_gate_mode() / write_gate_mode().

---

## Decision: 2026-04-13T00:00:00Z
**Type:** DOCUMENTATION
**Title:** Full documentation audit and consistency sweep
**Decision:** Audited README, COMMANDS.md, SAMPLE_PROJECT.md, workflow.md, DELIVERY_STRUCTURE.md for consistency with session 011 features. Found: (1) COMMANDS.md missing all CLI commands (only had slash commands). (2) specs/workflow.md Phase 1 still had 7 subtasks (should be 13). (3) README agent table showed Research Scout as "Phase 0" (should be "All phases"). (4) Test counts stale (338 → 347). (5) New features (Haiku headlines, zo gates set, tmux orphan prevention) not documented. Fixed all issues.
**Rationale:** PR-005 prior: aspirational docs without enforcement degrade. This session added 10+ features but only partially updated docs. Full sweep ensures any user reading any doc gets consistent, current information.
**Alternatives considered:** None — mandatory per CLAUDE.md protocol.
**Outcome:** All user-facing docs updated and cross-referenced.

---

## Decision: 2026-04-13T01:00:00Z
**Type:** ARCHITECTURE
**Title:** Training visualisation — infrastructure, not an agent
**Decision:** Implemented live training dashboard as infrastructure (callback + Rich display + tmux split-pane), not as a new agent. Training scripts use `ZOTrainingCallback` to write JSONL metrics. `zo watch-training` tails the file and renders a Rich Live panel. Wrapper auto-splits the tmux pane when `training_status.json` appears during Phase 4.
**Rationale:** User wanted PyTorch Lightning-like visibility into training (epoch progress, loss, checkpoints) without switching tmux windows. A "visualiser agent" was considered and rejected — formatting numbers doesn't need LLM reasoning. Infrastructure is cheaper, faster, and more reliable. Auto split-pane puts the dashboard in the same window (40% bottom).
**Alternatives considered:** (1) Visualiser agent — wastes LLM tokens on formatting. (2) Rich Live replaces entire monitoring — bigger refactor, loses task/event view. (3) Standalone `zo watch-training` only — requires manual pane setup. (4) Auto split-pane (chosen) — best UX, zero manual setup.
**Outcome:** PR #26. 17 new tests, 2 new modules (training_metrics.py, training_display.py), wrapper + CLI wiring.

---

## Decision: 2026-04-13T01:30:00Z
**Type:** ARCHITECTURE
**Title:** Auto test reports at phase gates via JUnit XML
**Decision:** Orchestrator generates `reports/test_report.md` at every phase gate by running pytest with `--junitxml`, parsing the XML, and rendering a structured markdown report. Triggered in both `advance_phase()` (automated gates) and `apply_human_decision()` (human gates). Handles missing tests/pytest gracefully with a placeholder report.
**Rationale:** User found no test report artifact during CIFAR-10 build. For production projects (prod-001), every gate needs a test report showing pass/fail, per-module breakdown, failures with tracebacks. Auto-generation means the test-engineer writes tests, the infra produces the report — separation of concerns.
**Alternatives considered:** (1) Manual `zo test-report` command — requires user to remember. (2) Auto at gates only (chosen) — always current, zero manual steps. (3) Both — unnecessary complexity.
**Outcome:** PR #26. 18 new tests, CaseResult/SuiteResult models, JUnit XML parser, markdown renderer.

---

## Decision: 2026-04-13T01:30:00Z
**Type:** ARCHITECTURE
**Title:** Structured phase report templates — specs/report_templates.md
**Decision:** Created comprehensive report templates for Phase 1 (Data Quality, 10 sections) and Phase 5 (Analysis, 7 sections) in `specs/report_templates.md`. Agent contracts (data-engineer, oracle-qa, test-engineer) reference these templates. Reports are the primary artifacts reviewed at gate checkpoints.
**Rationale:** User noted existing data quality reports were too thin for production data (prod-001). CIFAR-10 is clean and simple; prod-001 has messy, complex, domain-specific data requiring comprehensive quality assessment. Templates ensure agents produce production-grade reports with statistical tests, per-feature breakdowns, and actionable recommendations.
**Alternatives considered:** (1) Inline templates in agent contracts — bloats agent definitions. (2) Separate spec file (chosen) — reusable, single source of truth, agents reference it. (3) Auto-generated reports from code — too rigid, can't capture domain-specific analysis.
**Outcome:** PR #26. specs/report_templates.md, 3 agent contracts updated.

---

## Decision: 2026-04-13T02:00:00Z
**Type:** ARCHITECTURE
**Title:** Draft scout team — multi-agent plan drafting with data and research intelligence
**Decision:** Upgraded `zo draft` from a single Sonnet session to a 3-agent scout team: Plan Architect (Opus, lead), Data Scout (Sonnet), Research Scout (existing, Opus). The Plan Architect converses with the human in tmux while scouts gather intelligence in the background. Data Scout inspects raw data (schema, distributions, quality flags). Research Scout finds prior art and baselines. Findings arrive via Claude Code native peer messaging and are woven into the plan.
**Rationale:** Single-session draft works for toy datasets (CIFAR-10) but not for production data (prod-001). Plans written without data inspection or research are uninformed — the plan.md quality directly determines build quality. The scout team grounds the plan in data reality and domain knowledge. User wanted to keep the conversational UX — the architect chats, scouts work in background. Same monitoring UX as zo build (team status feed in terminal).
**Alternatives considered:** (1) Full preliminary analysis (mini Phase 1) — too expensive, risk of doing Phase 1 twice. (2) Keep single session, evolve plan after Phase 1 — plan starts uninformed. (3) Lightweight scout team (chosen) — quick (10-15 min), grounded, conversational.
**Outcome:** PR #27. 2 new agents (plan-architect, data-scout), CLI redesigned (--docs, --data, -d all optional), _launch_and_monitor shared between build and draft.

---

## Decision: 2026-04-13T02:00:00Z
**Type:** ARCHITECTURE
**Title:** zo draft CLI — explicit --docs and --data flags, all optional
**Decision:** Changed `zo draft` CLI from positional `SOURCE_PATHS` to explicit `--docs PATH` and `--data PATH` flags. Both are optional and repeatable. If neither provided, the Plan Architect asks conversationally. `--docs` feeds source documents to PlanDrafter for indexing. `--data` passes paths to Data Scout for raw data inspection.
**Rationale:** The old positional arg was overloaded — no way to distinguish docs from data. For the scout team, Data Scout needs to know which paths are actual data files to inspect. Explicit flags are clear. Making everything optional preserves the conversational fallback — the architect asks the human for anything not provided on the command line.
**Alternatives considered:** (1) Single positional arg, heuristic separation — fragile, confusing. (2) Explicit flags (chosen) — clear intent, both optional. (3) Config file — over-engineered for this.
**Outcome:** PR #27. CLI: `zo draft -p NAME [--docs PATH...] [--data PATH...] [-d DESC]`.

---

## Decision: 2026-04-13T03:00:00Z
**Type:** ARCHITECTURE
**Title:** Dynamic agent creation — custom/ directory, plan-defined + mid-build
**Decision:** Custom agents live in `.claude/agents/custom/` (separate from 19 core agents). Two creation paths: (1) plan.md declares custom agents via `**Custom agents:**` block — orchestrator auto-creates `.md` files at build start. (2) Lead orchestrator creates agents mid-build when it discovers unplanned expertise gaps — full-auto, logged to DECISION_LOG. Custom agents persist across projects and are reusable. `_agents_for_phase()` treats unknown agents as available for ALL phases (lead decides when to spawn). `_prompt_roster()` scans both core and custom/ directories.
**Rationale:** Static 19-agent roster doesn't scale to production projects with domain-specific needs (prod-001: signal processing, sensor calibration, etc.). Custom agents can be any role — researchers, data scientists, testers, QA — not limited to domain specialists. The agent library grows as ZO encounters new problem types.
**Alternatives considered:** (1) All agents in flat directory — mixes core with project-specific, hard to tell apart. (2) Agents in delivery repo — doesn't persist across projects. (3) Custom subdirectory (chosen) — clean separation, reusable, visible in roster.
**Outcome:** PR #28. CustomAgentSpec in plan parser, _ensure_custom_agents + _render_custom_agent in orchestrator, 16 new tests.

---

## Decision: 2026-04-13T11:00:00Z
**Type:** ARCHITECTURE
**Title:** Conversational `zo init` via Init Architect — same UX pattern as `zo draft`
**Decision:** `zo init project` defaults to launching a tmux session with the **Init Architect** (Opus, 20th agent). The architect interviews the user (new vs existing repo, branch, training host, data location, Docker base image, layout mode), inspects any existing target repo via `Glob`/`Read`/`Bash`, then invokes `zo init project --no-tmux ...` to commit all writes. The headless flag-driven path is the single source of truth for file writes — the agent never writes target/plan/memory files itself.
**Rationale:** The original `zo init` had a hardcoded `target_branch: main`, no Environment section, no overlay mode for existing repos. Each gap suggested a new flag, but flag proliferation doesn't scale: real init questions need *context* (is this an existing src-layout repo? is the GPU server local or remote? is the data on a separate host?). A conversational interview adapts to the project; flags don't. Mirrors the proven `zo draft` pattern.
**Alternatives considered:** (1) Add 5+ flags to the existing programmatic `zo init` — works for single questions but degrades when answers depend on inspecting the repo. (2) Agent writes files directly with `Write`/`Edit` — fragments responsibility, hard to test, easy to drift from CLI behavior. (3) Hybrid (chosen) — agent collects answers + inspects, CLI does all writes.
**Outcome:** New `init-architect.md`, `src/zo/environment.py` (host detection), scaffold `layout_mode={standard,adaptive}`, `_TARGET_TEMPLATE` with `{target_branch}` + responsibility-based `agent_working_dirs`, `_PLAN_TEMPLATE` with `## Environment` section, `zo init` with 8 headless flags + tmux/git/path guardrails. 4 new test files / classes, 28 new tests (433→443 passed when also accounting for prior cleanup).

---

## Decision: 2026-04-13T11:30:00Z
**Type:** ARCHITECTURE
**Title:** Scaffold `layout_mode=adaptive` — preserve existing code layout in overlay mode
**Decision:** Split scaffold directories into `_META_DIRECTORIES` (always created: `configs/`, `experiments/`, `reports/`, `notebooks/phase/`, `docker/`) and `_STANDARD_DIRECTORIES` (only created in standard mode: `src/*`, `data/*`, `models/`, human notebooks, tests). Adaptive mode also skips `README.md`, `pyproject.toml`, `.gitignore` template files (the existing repo has these). `.gitkeep` writes are restricted to dirs that are truly empty after creation — no pollution of pre-existing code dirs.
**Rationale:** prod-001 (and any serious existing project) has its own src-layout, e.g. `src/prod-001/data/`. Naively running scaffold would create both `src/data/` AND leave `src/prod-001/data/` — agents get confused about where code lives. Adaptive mode preserves the user's layout; the Init Architect then writes a project-specific `STRUCTURE.md` and updates `agent_working_dirs` in the target file to point at real paths (the one allowed direct-write exception, since only the agent has the project context to do this correctly).
**Alternatives considered:** (1) Always run full scaffold — pollutes existing repos. (2) Skip scaffold entirely on existing repos — loses ZO's `configs/`, `experiments/`, `docker/` infrastructure that agents depend on. (3) Two layout modes (chosen) — clean separation of "ZO infrastructure" vs "code layout".
**Outcome:** scaffold.py refactor with `layout_mode` param + `_META_DIRECTORIES`/`_STANDARD_DIRECTORIES` split. CLI guardrail: adaptive requires --existing-repo. 5 new tests covering empty-dir gitkeep, adaptive mode skipping src/, README/pyproject preservation, invalid layout mode rejection, overlay logging.

---

## Decision: 2026-04-13T11:45:00Z
**Type:** ARCHITECTURE
**Title:** Plan template `## Environment` section + auto-detection
**Decision:** Plan template (`_PLAN_TEMPLATE` in cli.py) gains an `## Environment` section with three blocks: **Host** (where ZO runs — platform, Python, Docker, GPU count, CUDA), **Training target** (where Docker runs — gpu_host, base_image, train_cuda), **Data** (data_layout, data_path, docker_mounts). At `zo init` time, `src/zo/environment.py` runs detection probes (subprocess to nvidia-smi + docker + python version + uname) and the values are interpolated into the template. User-supplied flags (`--gpu-host`, `--base-image`, `--data-path`) override detection. `--no-detect` produces TODO placeholders.
**Rationale:** Resolves known issue #6. Manual Environment specification was error-prone. Distinguishing host (where ZO runs) from training target (where Docker runs) is essential because prod-001 dev happens on Mac but training runs on a Linux GPU server with different CUDA. Auto-detection captures host correctly; explicit flags capture training target.
**Alternatives considered:** (1) Single `Environment` block conflating host + training — wrong abstraction for remote-GPU setups. (2) Defer to `zo draft` — but draft happens after init, and Environment should be in the plan from the start. (3) Three-block Environment (chosen) — explicit separation matches reality.
**Outcome:** _render_plan_template() in cli.py builds the populated section. Environment.suggest_base_image() picks a sensible PyTorch image from detected CUDA (12.4 / 12.1 / 11.8 with safe fallback).

---

## Decision: 2026-04-13T12:15:00Z
**Type:** ARCHITECTURE
**Title:** `zo init` dry-run + reset — mid-flight adaptability for the Init Architect
**Decision:** Added two CLI affordances that make the conversational init safely reversible: (1) `--dry-run` prints the exact file tree, directory preserved/added counts, target.md content, and plan.md Environment section WITHOUT any filesystem writes. Init Architect runs dry-run before every commit and shows the user what will happen. (2) `--reset` deletes `memory/{project}/`, `targets/{project}.target.md`, and `plans/{project}.md`; prompts for the project name as confirmation (or `--yes` to skip); NEVER touches the delivery repo. Init Architect mentions reset in its closing message only when the user seemed uncertain.
**Rationale:** The first pass made init conversational but the user asked: "will the agent adapt mid-flight?" The answer revealed gaps: no preview before commit (user commits blind), no rollback after commit (user has to rm-rf manually, risky if they confuse ZO paths with delivery paths). Dry-run + reset close the loop: agent can preview, user can undo, without any path-sensitive shell commands. Mirrors the "plan before action, action if approved" pattern from the rest of ZO.
**Alternatives considered:** (1) Leave as-is — real prod-001 friction would catch issues, but expensive when you're mid-session and unsure. (2) Separate `zo reset` command — cleaner surface but adds another command to cascade across docs; init+reset on same command is more discoverable ("how do I undo init? init --reset"). (3) Agent writes files directly with Write tool so it can re-edit — breaks the "single source of truth for writes" rule and is harder to test.
**Outcome:** 3 new classes (TestInitDryRun, TestInitReset) + 10 tests. Total 451 passing. PR-019 added (preview-before-commit principle). COMMANDS.md updated with --dry-run / --reset / --yes. Init Architect protocol gets explicit partial-match guidance (default standard for partial src/) and semantic-alias guidance (adaptive + map for src/data_loading → src/data), closing the layout adaptability gap the user raised.

---

## Decision: 2026-04-13T14:30:00Z
**Type:** ARCHITECTURE
**Title:** Per-project agent adaptations — `**Agent adaptations:**` block in plan.md
**Decision:** Introduced a third Agent Configuration knob (alongside Active agents and Custom agents): `**Agent adaptations:**` maps an agent name to a project-specific prompt addition. Plan Architect proposes adaptations during `zo draft` based on Research Scout + Data Scout findings — typically for `xai-agent` and `domain-evaluator` which are generic by default and need domain context to produce useful output. At build time, the orchestrator reads the plan's adaptations and (a) injects each into the relevant agent contract inline within `_prompt_contracts`, and (b) emits a dedicated top-level `# Per-project Agent Adaptations` section in the Lead Orchestrator's prompt. The Lead Orchestrator's protocol tells it to append the adaptation text to the spawn prompt when spawning the adapted agent — the agent's base `.md` file is unchanged, so it remains reusable across projects. Adaptations work for both core agents and plan-declared custom agents.
**Rationale:** Static `xai-agent.md` and `domain-evaluator.md` files produce the same generic output for CIFAR-10 images as for prod-001 vibration signals — defeats the point of having these agents. User flagged this when reviewing the scorecard for original prod-001 gaps: XAI

---

## Decision: 2026-04-13T16:30:00Z
**Type:** UX
**Title:** Branded `zo --help` — Rich-rendered banner + QUICK START sequence
**Decision:** Override Click's default help output with a ZO-branded Rich rendering. Introduced `ZoCommand(click.Command)` and `ZoGroup(click.Group)` whose `get_help()` delegates to a shared `_render_help(ctx, command)` that prints: (1) an orbital-mark panel (◎ + `ZERO OPERATORS` + `v{version}`) in the brand amber `#F0C040` on void `#080808` with a two-line tagline on the root group only, (2) a `USAGE` line, (3) a `QUICK START` section listing the five numbered commands `init → draft → preflight → build → continue` with one-line descriptions (root group only), (4) per-command `DESCRIPTION`/`ARGUMENTS`, (5) `COMMANDS` (groups) and `OPTIONS` sections. `ZoGroup.command_class = ZoCommand` and `group_class = type` propagate the classes to every registered subcommand and nested group (including `gates` and future additions) with no per-command wiring. Root group gets the full banner + tagline + QUICK START; subcommands get a compact banner only.
**Rationale:** The prior `zo --help` showed Click's default plain text — no brand identity, no guidance on the workflow. A user running `zo --help` for the first time saw an alphabetical command list with no indication that `init → draft → preflight → build` is the canonical pipeline. Branding the help and exposing the sequence turns the first `--help` into onboarding rather than a reference card. The banner matches `design/banner-dark.svg` (amber on void, uppercase `ZERO OPERATORS`, same tagline) so terminal output is a direct reflection of the brand system. Using `ZoGroup.command_class`/`group_class = type` instead of decorating each command individually means this change scales to future commands with zero touch.
**Alternatives considered:** (1) Custom `HelpFormatter` via `click.Context.formatter_class` — only controls layout primitives (indent_increment, dl), cannot emit Rich panels or ANSI color. (2) Prepend a banner in `format_help` and let Click render the rest — works, but leaves `Usage:`/`Options:`/`Commands:` headers in plain text (unbranded). (3) Dedicated `zo banner` or `zo tour` command — discoverable only if the user already knows to run it; `--help` is the universal entry point. (4) Write the QUICK START into each command's docstring — duplicated content, no sequencing visible on the root help. Full override on the root group with class-level propagation to subcommands gives complete brand control while preserving Click's option/argument introspection (`get_help_record`, `collect_usage_pieces`).
**Outcome:** `src/zo/cli.py` adds `_render_help()` + `ZoCommand` + `ZoGroup`; `@click.group()` becomes `@click.group(cls=ZoGroup)`; the existing group docstring shortens (banner covers the tagline). `tests/unit/test_cli.py::test_help_output` extended to assert on sectioned headers, `QUICK START`, and the init→draft→preflight→build→continue ordering. All 476 tests pass, ruff clean, validate-docs 10/10. One implementation-level gotcha: `rich.markup.escape()` doubles trailing backslashes (captured as PR-021), so user-content sections (DESCRIPTION lines, option decls like `[standard|adaptive]`) render via Rich `Text` objects with `style=` rather than inline `[bold]…[/]` markup — keeps shell-continuation `\` in docstrings intact and stops Rich from swallowing `[foo|bar]` choice metavars as tags.

---

## Decision: 2026-04-14T12:30:00Z
**Type:** BUGFIX
**Title:** Tmux TUI paste timing — 3s wait too short for cold starts
**Decision:** Increased `time.sleep(3)` to `time.sleep(8)` in `_launch_tmux()` for the TUI initialization wait before paste-buffer. Also increased Enter key delay from 0.5s to 1s.
**Rationale:** First live `zo init prod-001` run opened a blank Claude Code session — the TUI rendered but no prompt was submitted. The 3s wait was insufficient for Claude Code's cold start (loading extensions, hooks, CLAUDE.md, memory files). The paste-buffer arrived before the input field was ready, so the prompt was silently dropped. 8s covers observed cold start times (5-10s) with margin. This is the same tmux paste-buffer approach validated in PR-001, but the timing assumption was wrong.
**Alternatives considered:** (1) Poll-based wait (check tmux pane content for ready indicator) — fragile, depends on TUI rendering internals. (2) Retry with double-paste — risks submitting the prompt twice if the first paste succeeded. (3) Increase fixed wait to 8s (chosen) — simple, covers the range, no double-paste risk.
**Outcome:** PR #34. 476 tests pass, 7 skipped. Fix applied to both worktree and main repo `src/zo/wrapper.py`. PR-022 prior added.

---

## Decision: 2026-04-14T12:45:00Z
**Type:** UX
**Title:** Agent session auto-cleanup — kill tmux window, Haiku summary, return control
**Decision:** Three changes to the post-session flow: (1) `_tmux_claude_running()` checks `#{pane_current_command}` to detect when Claude exits but the shell remains — replaces the previous check that only tested pane existence. (2) `_kill_tmux_window()` closes the leftover shell window when Claude exits. (3) `_generate_session_summary()` asks Haiku for a 2-3 bullet summary of buffered events, printed in the invoking terminal before returning control.
**Rationale:** After `zo init prod-001`, user typed `/exit` in the Claude session but: (a) the tmux agent window stayed open (shell still running), (b) the invoking terminal showed only elapsed-time ticks with no summary, (c) the monitoring loop never terminated. The user had to manually kill windows and got no feedback on what happened. The fix makes the end-of-session experience match the beginning: automatic, informative, clean.
**Alternatives considered:** (1) Require user to kill the tmux window manually — poor UX, the whole point is automation. (2) Send SIGTERM to the pane — risks killing Claude mid-work if called too early. (3) Check `pane_current_command` for shell fallback (chosen) — safe, detects the natural /exit flow.
**Outcome:** PR #34 updated. `_tmux_claude_running()`, `_kill_tmux_window()`, `_generate_session_summary()` added. `_wait_tmux()` uses two-condition check (pane exists AND Claude running). 476 tests pass.

---

## Decision: 2026-04-14T14:00:00Z
**Type:** EVOLUTION
**Title:** Preflight integration tests — prevent untested interface mismatches
**Decision:** Added `tests/integration/test_preflight.py` with 9 tests that run preflight checks against real fixture plans and real parser output. No mocks on `ValidationReport` or `ValidationIssue`. Also fixed three stacked bugs: `report.is_valid` → `report.valid`, `i.field` → `i.section`, oracle parser now strips parenthetical suffixes before alias lookup.
**Rationale:** First `zo preflight` against a production plan failed with `AttributeError`. Investigation found THREE bugs — all present since the module was written, all invisible because (a) preflight had zero tests and (b) mocked tests would have used the same wrong attribute names. Self-evolution protocol: fix the symptom (3 bugs) AND fix the rule (add integration tests that use real objects, add PR-025 prior).
**Alternatives considered:** (1) Just fix the bugs — violates self-evolution principle. (2) Add unit tests with mocks — would have caught `is_valid` if written correctly, but mocks can perpetuate the same misconception. (3) Integration tests with real objects (chosen) — catches interface mismatches by definition.
**Outcome:** PR #39. 485 tests pass (was 476). PR-025 prior added. The parenthetical oracle field test specifically guards against the exact production plan format that triggered this bug.

---

## Decision: 2026-04-14T22:00:00Z
**Type:** ARCHITECTURE
**Title:** Data pipelines should use denylist, not allowlist, for DL projects
**Decision:** When building Phase 1 data pipelines for deep learning projects, default to including all available signals (denylist approach — exclude only target leakage) rather than curating a small allowlist of input features. Feature selection is deferred to Phase 2 as a model-dependent transform.
**Rationale:** During prod-001 Phase 1, a manually-curated allowlist (~164 tags from a pre-project config file) was initially used. This artificially limited the feature space to <1% of available signals (~15,600 total). Switching to a denylist (exclude ~786 leakage tags, keep ~14,815) expanded the feature space 90×. DL models benefit from maximum feature space — they learn their own representations. Manually curating inputs pre-model introduces human bias about what's "relevant." The pipeline's job is leakage prevention, not feature selection.
**Alternatives considered:** (1) Keep the curated allowlist — limits what models can discover, biased by the human who created it. (2) Denylist but with aggressive feature engineering in pipeline — couples pipeline to model assumptions. (3) Denylist with model-dependent transforms in Phase 2 (chosen) — clean separation of concerns.
**Outcome:** Applied to prod-001. Phase 1 subtask guidance should recommend denylist-first for DL projects. Feature curation belongs in Phase 2 model config (e.g., XGBoost: no normalise; TFT: zscore + forward_fill; etc.).

---

## Decision: 2026-04-14T22:00:00Z
**Type:** PROCESS
**Title:** Notebook execution as gate validation
**Decision:** Phase notebooks should be executed end-to-end as part of gate checks, not just generated as documentation templates.
**Rationale:** During prod-001 Phase 1, the notebook had 3 bugs (wrong constructor args, renamed methods, old attribute names) that only surfaced when executing cells. Unit tests passed because they tested the functions directly, but the notebook used the public API differently. Executing the notebook catches API-level integration issues.
**Alternatives considered:** (1) Treat notebooks as documentation only — misses API drift. (2) Write separate integration tests — duplicates validation. (3) Execute notebooks at gates (chosen) — the notebook IS the integration test, and it produces visible output for the report.
**Outcome:** Not yet codified in ZO's gate checks. Candidate for v1.0.3 enhancement.

---

## Decision: 2026-04-14T22:00:00Z
**Type:** PROCESS
**Title:** Specialist review personas find complementary issues
**Decision:** Multi-persona specialist reviews (domain expert, ML specialist, data scientist) are effective at catching different classes of issues in the same pipeline. Each persona has blind spots the others cover.
**Rationale:** Three specialist reviews of the same prod-001 Phase 1 pipeline found non-overlapping issues: domain specialist found missing flow transmitter exclusions; ML specialist found trend slope inconsistency and test gaps; data scientist found detection limit handling issues and sample-to-feature ratios. No single reviewer would have caught all issues.
**Alternatives considered:** (1) Single comprehensive review — misses domain-specific blind spots. (2) Automated-only checks — can't reason about process chemistry or ML methodology. (3) Multi-persona reviews (validated) — complementary coverage.
**Outcome:** Applied to prod-001. The code-reviewer agent should support domain-specific review prompts when plan.md includes agent adaptations.

---

## Decision: 2026-04-15T10:00:00Z
**Type:** ARCHITECTURE
**Title:** Portable project memory — `.zo/` directory in delivery repo
**Decision:** Move all project-specific state (STATE.md, DECISION_LOG, PRIORS, sessions, plans, project config) from the ZO repo (`memory/{project}/`, `plans/{project}.md`, `targets/{project}.target.md`) into the delivery repo under `.zo/`. ZO public repo retains only platform-level memory (`memory/zo-platform/`). Machine-specific paths (data_dir, GPU info, gate mode) stored in gitignored `.zo/local.yaml`; portable config in committed `.zo/config.yaml`.
**Rationale:** User moved prod-001 from Mac Mini to GPU server. `zo status` failed — memory was gitignored in ZO (by design, for confidentiality) but that makes it non-portable. The delivery repo is private, committed to git, and already travels between machines via `git pull`. Putting project state there solves portability without compromising confidentiality. Separate `local.yaml` (gitignored) from `config.yaml` (committed) handles machine-specific vs portable config cleanly.
**Alternatives considered:** (1) scp memory between machines — manual, error-prone, doesn't scale. (2) Track memory in ZO repo — violates confidentiality, ZO is public. (3) Separate private config repo — over-engineered, adds a third repo. (4) `.zo/` in delivery repo (chosen) — project state travels with the project, zero confidentiality risk.
**Outcome:** New `project_config.py` module, MemoryManager `memory_root` override, scaffold `.zo/` dirs, CLI discovery layer (`_detect_delivery_repo`, `_load_project_context`), `zo migrate` command, `zo continue --repo` enhancement. Backward compatible — legacy layout still works.

---

## Decision: 2026-04-15T12:00:00Z
**Type:** BUGFIX
**Title:** Every CLI command must accept --repo for .zo/ layout resolution
**Decision:** Fixed three issues: (1) `build()` infers delivery repo from plan path when it's inside `.zo/plans/` (fixes continue→build handoff). (2) `gates_set` gains `--repo` option. (3) `watch_training` gains `--repo` option. Added integration tests for the plan-path→delivery-repo inference.
**Rationale:** First live `zo continue --repo` on GPU server crashed with `FileNotFoundError: targets/{project}.target.md`. The continue command correctly resolved `.zo/` but build re-resolved without the hint. Same class of bug existed in gates_set and watch_training. Self-evolution protocol: fix the immediate bug AND fix every other command with the same pattern AND add a prior (PR-029) so new commands include `--repo` from the start.
**Alternatives considered:** (1) Pass delivery_repo as a hidden click parameter — Click doesn't support invisible params well across ctx.invoke(). (2) Store delivery_repo in a module-level variable — global state, fragile. (3) Infer from plan path (chosen) — plan path is already passed, no new params needed.
**Outcome:** PR-029 added to PRIORS. 3 integration tests added. All commands that use `_load_project_context()` now accept `--repo`.

---

## Decision: 2026-04-20T11:00:00Z
**Type:** DOCUMENTATION
**Title:** Denylist-first DL data-pipeline prior codified into specs and agent contract
**Decision:** Propagated PR-026 (denylist-first for DL data pipelines) from platform PRIORS into two enforcement points: (1) `specs/workflow.md` Subtask 1.3 gains a callout "Denylist-first for DL projects (default)" explaining why feature selection belongs in Phase 2, plus expanded filter guidance separating leakage exclusions from invalid-record exclusions, plus a "flag any reduction >10× for explicit justification" rule when inheriting curated lists. (2) `.claude/agents/data-engineer.md` gains a "Pipeline Principles" section at the top with three numbered rules: denylist-first by default, validate inherited configs against full dataset, document every exclusion with reason.
**Rationale:** PR-026 was the platform-level learning from prod-001 Phase 1 (164-tag allowlist silently limited feature space to <1% of signals, fixed by switching to denylist → 14,815 tags). A prior in PRIORS.md doesn't enforce itself — it has to land in the specs agents read (workflow.md) and the contracts agents execute (data-engineer.md). PR-005 principle: aspirational rules without enforcement are dead letter.
**Alternatives considered:** (1) Leave only in PRIORS.md — agents don't read PRIORS as a primary contract source, so the rule wouldn't fire on new projects. (2) Add to plan template — applies only to drafted plans, not to the agent's default behavior. (3) Codify in both specs/workflow.md and data-engineer.md (chosen) — the spec tells *when* it applies (Subtask 1.3), the agent file tells *how* it applies (contract-level principle the agent reads at spawn). Enforcement at both read points.
**Outcome:** `specs/workflow.md` Subtask 1.3 expanded with callout + leakage-vs-invalid separation. `.claude/agents/data-engineer.md` gains Pipeline Principles section. validate-docs 10/10.

---

## Decision: 2026-04-20T12:00:00Z
**Type:** ARCHITECTURE
**Title:** Domain-evaluator refactored to generic shell — domain identity injected at build time via plan adaptations
**Decision:** Rewrote `.claude/agents/domain-evaluator.md` to strip all project-specific domain content (oil & gas refineries, petrochemical plants, reactor systems, DCS tags, PO purity examples). The agent is now a generic shell whose domain identity is supplied exclusively through the plan's `**Agent adaptations:**` block (PR-020 mechanism) at build time. Report template keeps its four required structural sections (Plausibility / Consistency / Failure Mode Coverage / XAI Cross-Ref) but with no domain-specific examples. Added a hard stop-rule: if no `domain-evaluator` adaptation is present in the plan, the agent must emit a DECISION_LOG entry and ask the Lead Orchestrator rather than produce a generic report. Plan Architect already proposes adaptations for `domain-evaluator` during draft (per `.claude/agents/plan-architect.md:64`), so the build-time population flow is wired end-to-end.
**Rationale:** User requested Option A over Option B (generic shell + illustrative example) and Option C (template with named generic slots). Rationale: "different users will use this differently. Domain evaluator must be populated as part of the build phase … so that it's tied to the domain of the data / plan of the task". Project-specific content hard-coded in the agent file is drift-prone (needs to be forked per project, or produces wrong-domain reports). The PR-020 adaptation mechanism exists precisely for this case — it appends project context to the spawn prompt without forking the agent file.
**Alternatives considered:** (1) Option B — keep one labeled worked example for "shape" of domain reasoning (risk: example leaks into wrong-domain output). (2) Option C — keep structural section names and rename to generic buckets (risk: structural slots still carry implicit domain assumptions). (3) Option A — pure generic shell + required adaptation (chosen, per user) — maximally reusable, explicit stop-rule when adaptation missing prevents generic report fallback. (4) Fork per project — drift-prone, defeats the shared-agent pattern.
**Outcome:** `.claude/agents/domain-evaluator.md` rewritten. `specs/agents.md` already describes domain-evaluator generically (no edit needed). validate-docs 10/10. Test suite unaffected (557 passed). Plan Architect unchanged — it already proposes the adaptation.

---

## Decision: 2026-04-20T13:00:00Z
**Type:** ARCHITECTURE
**Title:** Phase completion snapshots (C1) — MD+YAML frontmatter at `{memory_root}/snapshots/` at every gate PROCEED
**Decision:** New module `src/zo/snapshots.py` provides `PhaseSnapshot` pydantic model (with `schema_version: 1` for future migrations), `render_snapshot()` → MD with YAML frontmatter, `write_snapshot()` → `{memory_root}/snapshots/{phase_id}_{ISO-timestamp}.md`, `list_snapshots()` and `load_latest_snapshot()` for readers. Orchestrator grows three helpers: `_generate_snapshot(phase, gate_decision, gate_outcome)`, `_recent_decisions_for_phase()`, `_issues_for_phase()` — the last two pull from `comms.query_logs()` and filter events mentioning the phase id. Orchestrator calls `_generate_snapshot` at both gate PROCEED paths: automated (line 495 in `advance_phase`) and human (line 574 in `apply_human_decision`). Snapshot generation is non-blocking — failures log as warnings but don't fail the gate (snapshots are reporting artifacts, not correctness gates). Uses `MemoryManager.memory_root` so portable `.zo/memory/snapshots/` works automatically without hard-coded paths.
**Rationale:** STATE.md listed "capture context at phase boundaries for reports" as pending work. Long-running projects (prod-001) accumulate thousands of comms events per phase — a next-phase lead that has to scan raw JSONL to answer "what happened in Phase 2?" burns context. A structured snapshot written at every gate gives humans, next-phase leads, and future dashboards a single scannable file per phase. MD+YAML frontmatter (same pattern as STATE.md) keeps it machine-parseable (yaml.safe_load the frontmatter) and human-readable (markdown body). `schema_version` field is present from day 1 so future migrations can be explicit rather than guess-and-check.
**Alternatives considered:** (1) Pure JSON — machine-queryable but unreadable to humans at the CLI. (2) Pure markdown with no frontmatter — human-readable but requires regex parsing to aggregate. (3) MD + YAML frontmatter (chosen) — matches STATE.md convention, both machine and human consumable, extensible via new frontmatter fields. (4) Database-backed snapshots — overkill for v1, adds a migration story. (5) Write synchronously inside `advance_phase` as blocking — snapshot failure shouldn't fail a phase that otherwise succeeded (snapshots are reporting, not correctness). Chose non-blocking with warning log.
**Outcome:** `src/zo/snapshots.py` (~270 LoC), orchestrator hook (~90 LoC added), 23 unit tests (`tests/unit/test_snapshots.py`) + 5 integration tests (`tests/integration/test_phase_snapshots.py`). Test count 529 → 557 (+28). ruff clean, validate-docs 10/10. The Lead Orchestrator's next-phase prompt can now pull the previous phase's snapshot via `load_latest_snapshot()` for efficient context handoff (not yet wired into lead prompt builder — deferred to next session if wanted).

---

## Decision: 2026-04-20T14:00:00Z
**Type:** DESIGN
**Title:** Experiment capture-layer schema sketched — implementation deferred per PR-005
**Decision:** Sketched (design only, no code committed) a minimal experiment capture layer for Phase 4 iterations. Location: `.zo/experiments/` (portable, travels with project in `.zo/`). Shape: `registry.json` (flat list of experiments with pydantic schema — id, parent_id, hypothesis, rationale, status, result, next_ideas, artifacts_dir) + per-experiment directory (`hypothesis.md`, `config.yaml`, `metrics.jsonl`, `training_status.json`, `result.md`, `diagnosis.md`, `next.md`). Integration is additive: `ZOTrainingCallback` default dir → `.zo/experiments/{exp_id}/`, orchestrator Phase 4 enter mints exp-NNN, gate check requires `result.md` exists, model-builder/oracle-qa/xai-agent contracts extended to write their respective artifacts. The *autonomous loop* (plateau detector, next-experiment proposer, dead-end guard, budget-aware selection) stays deferred until prod-001 Phase 4 generates real iteration data — designing the loop from speculation would tune for CIFAR-scale failure modes and retrofit for production.
**Rationale:** User asked about Karpathy-style AutoResearch loop — iterative hypothesis → experiment → diagnose → design next → loop until plateau. STATE.md already deferred the full experiment tracker "post prod-001 first pass" per PR-005 (aspirational rules without enforcement are dead letter — applied inversely: design from real failure data, not speculation). But the *capture layer* is the prerequisite: without structured records of each iteration, there's nothing to design the loop from when prod-001 Phase 4 runs. Split scope: capture now (~400 LoC), loop later (~1000+ LoC when grounded in real data).
**Alternatives considered:** (1) Build both capture + loop now — risk: tune plateau threshold, dead-end guard, and proposer heuristics for CIFAR patterns and retrofit for production. (2) Defer both — risk: prod-001 Phase 4 produces unstructured iteration data that has to be retrofitted into a registry post-hoc. (3) Split (chosen) — capture layer converts every prod-001 iteration into structured data as it happens; loop is designed with that data in hand. (4) Use existing `experiments/` dir in the delivery repo scaffold — reuse, but the scaffold is free-form notes; a registry with a pydantic schema is stricter.
**Outcome:** Design recorded in this log + STATE.md "What's Next #7". No code committed. Implementation sequenced after remote-data manifest + in parallel with prod-001 Phase 2/4 baseline runs.

---

## Decision: 2026-04-20T15:30:00Z
**Type:** ARCHITECTURE
**Title:** Experiment capture layer shipped — capture only, autonomous loop still deferred
**Decision:** Implemented the capture-layer design from the earlier sketch. New module `src/zo/experiments.py` (~500 LoC) with `Experiment` / `ExperimentResult` / `ExperimentRegistry` pydantic models, atomic `save_registry` via `.tmp` rename, `mint_experiment` that creates `.zo/experiments/exp-NNN/` + appends to registry + seeds status=`running`, `update_result` that auto-computes `delta_vs_parent` from the parent's primary metric (same-name metrics only), markdown parsers for `hypothesis.md` / `result.md` / `next.md`. Orchestrator grows four helpers: `_experiments_dir()`, `_ensure_experiment_for_phase()` (idempotent — returns running exp if present, mints new with `parent_id` = previous-latest otherwise), `_finalize_experiments()` (parses `result.md` for running exps, calls `update_result`, returns missing artifacts), `_abort_running_experiments()` (used on ITERATE so the next prompt mints a child). Lead prompt grows a `# Experiment Capture Layer` section describing the active `exp_id`, artifacts_dir, file expectations, and the gate rule. `advance_phase()` joins `_check_artifacts()` output with `_finalize_experiments()` missing list for phase_4. `apply_human_decision()` calls `_finalize_experiments()` on PROCEED and `_abort_running_experiments()` on ITERATE. `ZOTrainingCallback.for_experiment(registry_dir, experiment_id)` classmethod writes metrics into the exp dir. Agent contracts (model-builder, oracle-qa, xai-agent, domain-evaluator) each gain an "Experiment Capture Layer" subsection documenting their file (hypothesis.md / result.md / diagnosis.md / next.md). New CLI group `zo experiments list / show / diff` for human inspection. Autonomous loop components (plateau detector, proposer, dead-end guard, budget-aware selection) remain deferred per PR-005.
**Rationale:** User explicitly chose Path 1 from the earlier sketch (capture first, loop later). Capture layer is the prerequisite: it converts every prod-001 Phase 4 iteration into structured data as it happens, so the loop heuristics get designed from real failure patterns when we build them. The alternative — delaying capture — means Phase 4 produces unstructured data that has to be retrofitted into a registry post-hoc. Split also keeps PR size reviewable (~500 LoC capture vs ~1500 LoC if bundled with the loop).
**Alternatives considered:** (1) Synchronous blocking orchestrator hook (mints at "phase enter" before Lead prompt build) — but there's no clean phase-enter hook today; chose lazy minting inside `build_lead_prompt` which is naturally idempotent. (2) Writing a new event type in comms instead of a separate registry — rejected; the registry is queryable directly and doesn't need a date-partitioned JSONL scan. (3) Parallel experiments per phase entry — user chose serial for now, parent_id lineage gives clean tree, parallel can be layered later. (4) `diagnosis.md` as a gate requirement — rejected; XAI/Domain Evaluator don't run every iteration, only `result.md` is mandatory.
**Outcome:** 57 new tests (38 unit on experiments models/I/O/parsers + 10 orchestrator-flow integration + 9 CLI integration). Total test count 529 → 617 (+88 over baseline; +57 this PR, +28 from session-019 v1.x polish which merged as PR #48). `specs/workflow.md` Phase 4 section references the capture layer; `docs/COMMANDS.md` documents the `zo experiments` commands. ruff clean, validate-docs 10/10. Branch: `claude/experiments-capture-layer`.

---

## Decision: 2026-04-20T17:30:00Z
**Type:** ARCHITECTURE
**Title:** Autonomous experiment loop shipped — Phase 4 auto-iterates without human intervention
**Decision:** Implemented the full Karpathy-style autonomous loop on top of the capture layer. New module `src/zo/experiment_loop.py` (~300 LoC) with: (a) `LoopPolicy` pydantic model (`max_iterations`, `plateau_epsilon`, `plateau_runs`, `stop_on_tier`, `dead_end_threshold`) with DEFAULT_POLICY constant; (b) `LoopVerdict` enum — CONTINUE / TARGET_HIT / BUDGET_EXHAUSTED / PLATEAU / DEAD_END / HUMAN_STOP; (c) `evaluate_loop_state(registry, phase, policy)` returning a `LoopDecision` with verdict + reason + last_exp_id + completed_count; (d) `check_dead_end(registry, candidate, threshold, phase, exclude_exp_id)` using token-set Jaccard similarity (dependency-free, deterministic, good enough for rephrasing detection); (e) `resolve_policy(spec)` merging plan's `ExperimentLoopSpec` onto defaults. Orchestrator grows `_auto_iterate_if_needed(phase)` called inside `advance_phase` for phase_4 in non-supervised modes — parses result.md via existing `_finalize_experiments`, consults evaluator, on CONTINUE keeps phase ACTIVE + clears subtasks + logs LoopDecision to DECISION_LOG + returns ITERATE verdict. Next `build_lead_prompt` mints child via existing `_ensure_experiment_for_phase` (latest_in_phase becomes parent). Lead prompt's experiment section gains an `# Autonomous Iteration Loop` briefing: lists stop conditions, and when `parent_id` is set, includes a strict auto-proposer protocol ("read parent's result.md shortfalls + diagnosis.md + next.md, draft child's hypothesis.md citing specific parent findings, do NOT ask the human"). Model-builder.md contract gets a matching auto-proposer section. Plan schema extends with optional `## Experiment Loop` block parsed by new `_parse_experiment_loop` into `ExperimentLoopSpec`. Retrospective DEAD_END detection: after plateau check, if the last `plateau_runs` hypotheses all Jaccard-match an earlier experiment above `dead_end_threshold`, emit DEAD_END (Model Builder stuck rephrasing; escalate to human).
**Rationale:** User direct ask: "experiment tracking should be automatically part of build phase ... and auto re-plan for new experiments + improvements should also be automatic ... no manual intervention required". PR #49 made capture automatic; this PR closes the proposer + stop-condition gap. The user reviewed and accepted the PR-005 tradeoff (loop defaults will be best-guesses without prod-001 Phase 4 data to tune them) in exchange for the end-to-end autonomy. Keeping a conservative gate (`stop_on_tier=must_pass` default, `max_iterations=10` default) limits blast radius; the plan's `## Experiment Loop` block lets specific projects tune.
**Alternatives considered:** (1) Separate "proposer agent" — extra spawn cost and coordination surface; Model Builder is already the right role since it writes hypothesis.md. (2) Embedding-based dead-end via `zo.semantic` / fastembed — higher quality match but adds a required dependency and test-environment friction. Jaccard is deterministic and catches the obvious rephrasing case, which is the failure mode; if it turns out to be too lax on real data we can layer embeddings later. (3) At-mint-time dead-end check — requires Model Builder to propose before orchestrator mints, inverting the current flow. Retrospective pairwise check (last N hypotheses vs earlier) catches the "stuck rephrasing" pattern without restructuring the mint step. (4) `HUMAN_STOP` verdict via a signal file — deferred; current stop conditions cover autonomous cases, human can still `zo gates set supervised` mid-run.
**Outcome:** New `src/zo/experiment_loop.py`. Orchestrator gains `_auto_iterate_if_needed` + `_render_loop_briefing`. Plan parser gains `_parse_experiment_loop` + `ExperimentLoopSpec`. Model-builder.md contract gets the auto-proposer section. 44 unit tests (22 tier_meets + loop verdicts + policy + dead-end + parser) + 7 integration tests (auto-iterate continues, supervised disables, target-hit stops, budget-exhausted stops, plateau stops, decision-log trail, plan override). Total test count 617 → 669 (+52 this PR, +140 over session-019 baseline). ruff clean, validate-docs 10/10. specs/workflow.md Phase 4 section gains an "Autonomous iteration loop" callout. Branch: `claude/experiments-autonomous-loop`.

---

## Decision: 2026-04-25T22:00:00Z
**Type:** DESIGN
**Title:** Brand redesign v2 + website v2 shipped — v1.0.2 release
**Decision:** Replaced the entire visual identity. Palette: canvas `#12110F` (dark) / paper `#F4EFE6` (light) / coral `oklch(0.74 0.14 35)` ≈ `#D87A57` (accent) / dusk + moss as secondary status colors — all oklch-based for perceptual uniformity. Typography: Geist (sans, body + headings) + Cormorant Garamond (italic display, emphasis) + JetBrains Mono (code + terminal) — replacing Share Tech Mono / Rajdhani. Mark: simplified C (circle + diagonal slash + centered coral dot) — replacing the orbital. `design/` wiped of 11 old files (8 HTML brand variants + 3 SVGs); replaced with 6 new files (`brand-system.html`, `brand-system-light.html`, `logos.html`, `font-pairings.html`, shared `styles.css`, `logos.js`) + 2 banners for README (`readme-banner.{svg,png}`) + extracted `logo-dark.svg` from new mark for inline README refs. `website/` rebuilt: deleted 12 `.astro` components + 4 JSON data files + 2 scripts + `Base.astro` layout + `index.astro` page + `global.css` + `PLAN.md` + old `package-lock.json` (1,800+ lines obsolete). New website is single-page Astro 5 static (`src/pages/index.html` + `public/{styles.css, app.js, favicon.svg, robots.txt, assets/hero-workshop.png}`) with mobile-tested media queries (`1024px / 900px / 640px / 400px / hover:none`), light/dark theme toggle (localStorage-persisted, prefers-color-scheme respected), inline SVG mark injection via `app.js`. README.md banner + footer logo refs swapped. CLAUDE.md "Design System" section rewritten end-to-end. `frontend-engineer.md` + `documentation-agent.md` design path + palette refs updated. Version cascade 1.0.1 → 1.0.2 across pyproject.toml + `__init__.py` + cli.py (autonomous loop + brand v2 = coherent v1.0.2).
**Rationale:** User shipped a finished new brand system + website v2 (mobile-tested) and asked for a clean replacement. Cloudflare Pages config was dashboard-managed (Build cmd: `cd website && npm install && npm run build`, Build output: `website/dist`, Production branch: `main`, Auto-deploy: enabled, Watch: `*`) and could not change — so the new website had to be wrapped in the existing Astro 5 shell (same `astro.config.mjs`, same `package.json`). Astro 5 supports `.html` files in `src/pages/` as pass-through static pages, so the new design's flat HTML structure dropped in cleanly. Build verified clean: `npm install && npm run build` produces a 6-file `dist/` (3.2 MB total, mostly the hero PNG) in 264ms. Live preview validated all sections (hero, idea, handoff, team, how, oracle, different, start, footer), both themes, all asset 200 OKs, no console errors. Cascade docs (README, CLAUDE.md, agent files) updated per CLAUDE.md PR-003/PR-005 protocol. Version bump justified by autonomous-loop + brand-v2 being a coherent forward step.
**Alternatives considered:** (1) Keep old design alongside new — clutter, mixed-brand confusion, breaks the "no orbital" principle the new mark explicitly states (logos.js: "no orbital / targeting motif"). (2) Skip version bump and tag as 1.0.1.1 — banner SVG and website hero already say `v1.0.2`, would create user-facing inconsistency. (3) Keep README banner-dark.svg → it doesn't exist in new design; either drop or replace. Replaced with the new `readme-banner.png` for visual continuity. (4) Convert `index.html` to `index.astro` for Astro idiomaticity — pure cost, no benefit; static `.html` is supported and the source-of-truth lives in the static file. (5) Add `@astrojs/sitemap` — robots.txt references `/sitemap.xml` aspirationally but no sitemap exists; could generate one but it adds a dep for a single-page site. Left as-is, will revisit if SEO needs grow.
**Outcome:** New `design/` with 9 files (4 HTML + styles.css + logos.js + readme-banner.{svg,png} + logo-dark.svg). New `website/` with `src/pages/index.html` + `public/` (6 files incl. sitemap.xml + assets/). Astro 5 build verified locally; Cloudflare's existing pipeline produces an identical `dist/`. README, CLAUDE.md, frontend-engineer.md, documentation-agent.md updated. pyproject.toml + `__init__.py` + cli.py at 1.0.2. validate-docs 10/10 (1 pre-existing test-count warning unrelated). Branch: `claude/brand-redesign-v2`. PR #51.

---

## Decision: 2026-04-25T22:30:00Z
**Type:** EVOLUTION
**Title:** Test fix surfaced by full pytest run — host-tooling guardrail must be mocked when not the test subject
**Decision:** Fixed `tests/unit/test_cli.py::TestInitDryRun::test_dry_run_rejected_in_conversational_mode` by adding `patch("shutil.which", return_value="/usr/bin/tmux")` to the test's context manager. The test was checking whether `--dry-run` without `--no-tmux` is correctly rejected with a UsageError, but on a no-tmux host the earlier `shutil.which("tmux") is None` guardrail in `zo init` fired first and the test never reached its target code path. Added `PR-032` to PRIORS.md ("Tests Targeting Downstream Logic Must Mock Upstream Environment Guardrails") capturing the rule. Full suite now passes 669 + 7 skipped on a no-tmux host.
**Rationale:** Self-evolution protocol per CLAUDE.md "On Any Failure or Error" — fix the symptom (1 line of patch), then update the rule (PRIORS.md PR-032) so the same class of bug doesn't recur. PR-025 covered "don't mock objects whose interfaces you're testing"; PR-032 is the inverse: "DO mock env guardrails that aren't your test's subject". Different failure mode, different lesson, deserves a distinct prior.
**Outcome:** 1-line test patch on the same branch (`claude/brand-redesign-v2`), PR-032 added, STATE.md test-count line annotated with "verified on no-tmux host". PR #51 now contains: brand redesign + sitemap + test fix + new prior. 669/669 pass.

---

## Decision: 2026-04-25T23:30:00Z
**Type:** DOCUMENTATION
**Title:** Troubleshooting doc shipped — captures sub-agent spawn crash diagnosis + 6 other known failure modes
**Decision:** Created `docs/TROUBLESHOOTING.md` after diagnosing a user report ("Claude Code crashes when sub-agents spawn on Mac"). Confirmed the failure is upstream of ZO — ZO launches one Claude Code session in tmux; the Lead inside that session uses Claude Code's native `TeamCreate` + `Agent(...)` to spawn teammates, which Claude Code itself process-forks. Spawning 5–7 teammates can add 100–250 procs in seconds, easily pushing heavy-Electron-app users over macOS `kern.maxprocperuid=2666`. Doc covers: (1) sub-agent spawn crashes — full diagnosis + 5 mitigations (upgrade Claude Code, check ulimits, raise `kern.maxproc`, try `--no-tmux`, capture diagnostic reports), (2) `zo: command not found` (PR-012), (3) tmux paste timing on cold start (PR-022/PR-031), (4) build appears stuck without tmux (PR-001), (5) plan written to worktree (PR-013), (6) bash 3.2 silent failures (PR-010), (7) where to find logs. README's Slash Commands section gains a one-line link. README Status section refreshed (v1.0.1 → v1.0.2, 17 → 20 agents, 476 → 669 tests, "pre-F5" row replaced with "1.0.2" row covering phase snapshots + experiment loop + brand v2 + website v2).
**Rationale:** Confirmed via 207 wrapper/orchestrator/integration tests + full 669-test pytest run + live `zo init` smoke test that ZO is working correctly. Per user direction ("if it's claude code side, nothing changes"), no code changes — but documenting the diagnosis + mitigations means future users hitting the same wall don't have to file an issue or wait for help. Six other known failure modes harvested from PRIORS.md PR-001/PR-010/PR-012/PR-013/PR-022/PR-031 because they're already-solved issues whose mitigations weren't surfaced anywhere user-facing.
**Alternatives considered:** (1) Inline troubleshooting section in README — README already 500+ lines, would bloat further; harder to extend per failure mode. (2) GitHub Discussions — relies on GitHub being reachable; no offline access during a crash. (3) Wiki — same problem, plus splits docs from repo. (4) Single-issue doc covering only the spawn crash — misses the chance to surface the other 6 PRIORS-encoded mitigations users would benefit from knowing about. Chose dedicated `docs/TROUBLESHOOTING.md` linked from README — follows the existing pattern (`docs/COMMANDS.md`, `docs/DELIVERY_STRUCTURE.md`, `docs/SAMPLE_PROJECT.md`).
**Outcome:** New `docs/TROUBLESHOOTING.md` (180 lines, 7 sections). README updated with link + status refresh. validate-docs 10/10. Branch `claude/troubleshooting-doc` off `main` (post-PR #51 merge).

---

## Decision: 2026-04-26T10:00:00Z
**Type:** DESIGN
**Title:** Brand polish — favicon, hero balance, idea-diagram label semantics, oracle box width
**Decision:** Four post-launch website fixes spotted in real use of v1.0.2: (1) **Favicon** — `website/public/favicon.svg` was still the pre-redesign orbital mark (4 cross-tick lines + amber `#F0C040` everywhere). Replaced with the new simplified C (circle + diagonal slash + center dot) at 32×32, single coral `#D87A57` so it reads on both light and dark browser tabs (cream would disappear on light backgrounds, ink would disappear on dark — coral is mid-tone and works on both). (2) **Hero column ratio** — `.hero-inner` was `1.1fr 1fr` (copy-weighted), making the workshop image visually undersized at desktop. Flipped to `1fr 1.15fr` (image-weighted). Mobile/tablet ≤900px collapses to single column unchanged. (3) **Idea-diagram side labels** — `decompose / verify / ship` were positioned at the level of source/destination boxes (y=56, 194, 388), so each label sat *beside* a box rather than *between* two boxes. Moved each label to the action-midpoint between boxes (y=148, 243, 341) so they label the transition itself. SHIP was particularly broken — sat *below* the trained-model box, reading as "the trained-model is the ship state" rather than "the action of shipping the model". (4) **Oracle box width** — text "must · should · could" rendered at 147px (JetBrains Mono 9px uppercase + 0.18em letter-spacing) but the box was only 120px wide, overflowing 14px on each side past the coral border. Widened rect to 170 (still centered at x=240 via translate 155, all three centerline elements — plan.md, oracle, trained-model — remain aligned). 11px symmetric padding now. Also fixed 2px arrow misalignment for the `analysis` and `package` chips (decompose + verify arrow endpoints x=336/402 → x=338/404, matching the actual chip text centers).
**Rationale:** All four issues surfaced from looking at the live website with fresh eyes. None were blocking but each scratched at the polish bar v1.0.2 set with the brand redesign. Per the existing brand-system principles in CLAUDE.md (coral as the primary highlight, mark = simplified C, no orbital), the favicon was a clear miss from PR #51 — likely the asset wasn't replaced when the rest of `design/` was. Hero column ratio is a UX call: the workshop scene is the emotional hook, copy is the rational pitch — equal-or-image-weighted is correct. Side labels are pure semantics — they describe ACTIONS (decompose, verify, ship), so they should sit at action positions, not box positions. Oracle width is a measurement bug — the text was always wider than the box, just not caught until inspected. Fixing all four in one PR keeps the polish work coherent rather than fragmenting across micro-PRs.
**Alternatives considered:** (1) Single coral favicon vs. two-color (cream stroke + coral dot like `design/logo-dark.svg`) — chose single coral for universal browser-tab visibility (cream fails on light tabs). (2) Hero ratio `0.95fr 1.2fr` for even bolder image weight — chose `1fr 1.15fr` as a measured first step; user can ask for more if they want it. (3) Reduce `.flow-sub` letter-spacing on the oracle text only — fragments the brand style (uppercase mono with 0.18em spacing is consistent across the diagram); widening the box is the right fix. (4) Move chips left by 2px to fix arrow misalignment instead of moving arrow endpoints — would create a 2px gap before chip 4, asymmetric. Moving the arrows was simpler.
**Outcome:** 3 files changed (`website/public/favicon.svg`, `website/public/styles.css`, `website/src/pages/index.html`). Verified in both light and dark themes at desktop 1440×900, tablet 1024×800 + 900×800, mobile 375×812. Theme toggle, burger menu, copy button, smooth scroll all working. No console errors, no failed network requests. Pre-existing `.team-diagram` mobile overflow (668px content on 375px viewport) noted but not fixed — out of scope for this PR. Branch `claude/epic-banzai-fe0458` off `main` (post-PR #52 merge).

---

## Decision: 2026-04-26T11:00:00Z
**Type:** DESIGN
**Title:** README banner regenerated and consolidated into `design/banner/` sub-dir
**Decision:** User shipped a new README banner (iterated v1 → v6, v6 final). Consolidated all banner source files into a new `design/banner/` sub-dir of the existing `design/` directory: `readme-banner.svg` (master overlay — typography + mark + frame ticks + fade gradient), `readme-banner.png` (1280×640 final composite, what README references), `readme-banner-2x.png` (2560×1280 retina), `workshop.png` (source photo for the right half — identical to `website/public/assets/hero-workshop.png` but kept as a sibling here so the render script is self-contained), `render.mjs` (Canvas-sandbox compositing script with full edit-points documentation in the header), `README.md` (explains the asset structure + parameter table + edit workflow). Old top-level `design/readme-banner.{svg,png}` removed (replaced by the new versions in the sub-dir). Root `README.md` image path updated `design/readme-banner.png` → `design/banner/readme-banner.png`. `render.mjs` and `design/banner/README.md` paths edited from sandbox-relative `assets/...` to bare `./...` so they match the new on-disk layout. The sub-dir `README.md`'s "How to regenerate" section was simplified — it previously duplicated the entire `render.mjs` body inline, which now lives in `render.mjs` itself with full headers; the README links to it rather than redundantly inlining.
**Rationale:** Three reasons to consolidate: (1) the previous brand-redesign-v2 PR #51 only kept `readme-banner.svg + readme-banner.png` at the top of `design/` — no source photo, no render script, no documentation. Future iteration would have required reverse-engineering the composite. The user explicitly said "all the assets associated with it so that we can edit it + improve it in the future". (2) Putting source files (workshop.png, render.mjs) as siblings to the brand-system HTMLs (brand-system.html, logos.html, etc.) at the top of `design/` would mix iteration tooling with brand-reference docs. A dedicated sub-dir keeps the concerns separate and discoverable. (3) The 4 v* iteration snapshots and inlined/overlay SVG variants and `workshop.b64.txt` from the user's local `Downloads/assets/` folder were intentionally NOT brought across — the user's own README labeled them "snapshots of earlier iterations" and "older variants kept for reference, can be ignored". Excluding them keeps the public repo lean (~25MB saved on iteration PNGs alone, ~9MB saved on the b64+older-SVG variants). Total kept: ~9MB across 6 files — reasonable for a public repo since the assets are needed for forward iteration.
**Alternatives considered:** (1) Replace `design/readme-banner.{svg,png}` in place without a sub-dir, drop workshop.png + render.mjs + README at the same level — clutters `design/` with iteration tooling next to brand-reference docs. (2) Don't duplicate `workshop.png`; have `render.mjs` reference `../../website/public/assets/hero-workshop.png` instead — saves 2.9MB but couples iteration tooling to website layout (any restructure of `website/public/` breaks the render). Chose duplication for self-containment; the SHA-identical files are functionally one source-of-truth maintained by the brand-redesign cascade. (3) Keep the v* iteration snapshots as a "history" — git history already preserves any version that was ever committed, and the user iterated locally before the first commit so v1-v5 were never in the repo anyway. No reason to land them now. (4) Keep `readme-banner.inlined.svg` (with base64-embedded photo) for self-contained-SVG use cases — out of scope; the live README references the PNG, the SVG is for editing not embedding, and inlined variants drift from the master.
**Outcome:** New `design/banner/` sub-dir with 6 files (~9MB). 2 deletions (`design/readme-banner.{svg,png}`). 1 root file edit (`README.md` image path). 2 in-banner-dir path edits (`render.mjs` + `design/banner/README.md` from `assets/...` to bare). Root README image preview verified — banner renders correctly with new C mark + workshop scene + dark panel composite. validate-docs 10/10 (1 pre-existing test-count warning unrelated). Same branch `claude/epic-banzai-fe0458`; PR #53 auto-updates with this commit.

---

## Decision: 2026-04-26T15:00:00Z
**Type:** ARCHITECTURE
**Title:** Platform-aware Docker scaffold — CPU compose for macOS / no-GPU Linux, GPU compose otherwise
**Decision:** Split the previously-monolithic `_COMPOSE_TEMPLATE` in `src/zo/scaffold.py` into two variants — `_COMPOSE_GPU_TEMPLATE` (existing content with `deploy.resources.reservations.devices: capabilities: [gpu]` block + `pytorch:2.4.0-cuda12.1-cudnn9-runtime` base image) and `_COMPOSE_CPU_TEMPLATE` (no deploy block, `pytorch:2.4.0-cpu` base image, header comment explaining the macOS / no-GPU rationale and pointing Mac users at native execution for hardware acceleration). Added `gpu_enabled: bool | None = None` parameter to `scaffold_delivery` — `None` probes the host via `zo.environment.detect_environment().gpu_count > 0`, with detection failure falling back to the GPU template (safest default on a Linux build server where omitting the deploy block would silently leave the model on CPU). New `_resolve_compose_template(gpu_enabled)` helper centralises the branch. `_create_template_files` builds the templates list dynamically, slotting the right compose. CLI's `_init_commit_writes` detects host GPU once and passes through to all three `_scaffold(...)` call sites (overlay / fresh scaffold / existing-path-as-overlay). Service name kept as `gpu` across both templates so the README quickstart is platform-independent (the misnomer is acceptable; the alternative — a per-platform README — is worse for the agent contract).
**Rationale:** STATE.md "Known Issues" #5 flagged "Device detection (Linux vs Mac) not yet implemented — affects Docker GPU passthrough". On a Mac host, `docker compose up` against the previous template either fails ("could not select device driver") or silently runs without GPU acceleration, depending on Compose version. Docker Desktop on Mac has no GPU passthrough at all (Apple Silicon MPS lives outside Docker's Linux VM, Intel iGPUs aren't exposed). The previous fix would have been a runtime warning at `docker compose up` time — but the right fix is at scaffold time, when we already know the host platform via the same `detect_environment()` ZO uses to populate the plan's Environment section. Same probe, same data, two consumers. The fix is also forward-compatible with the CIFAR-10 demo flow (Mac dev → Mac scaffold → CPU compose) and the prod-001 flow (Mac dev box scaffolds + draft → git push → GPU server `zo continue --repo` will use the existing on-disk compose file, not re-scaffold).
**Alternatives considered:** (1) Single template with profiles — `services.gpu.profiles: ["gpu"]` and `services.runtime.profiles: ["cpu"]`. Cleaner Compose pattern but changes the user's command from `docker compose run gpu ...` to `docker compose --profile gpu run gpu ...`, which propagates into README quickstarts and agent contracts. Rejected for blast radius. (2) Runtime warning at `zo build` time — detect Mac, print "GPU passthrough unavailable" warning. Doesn't fix the broken compose file, just papers over it. (3) Rename service to `runtime` (more generic) — breaking change for prod-001 and any in-flight scaffolds. Kept `gpu` for backwards compatibility. (4) Always emit GPU template, document Mac workaround — pushes problem to the user; misses the point of having env detection in the first place.
**Outcome:** `src/zo/scaffold.py` adds `_COMPOSE_CPU_TEMPLATE` + `_resolve_compose_template()` + `gpu_enabled` parameter. `src/zo/cli.py` `_init_commit_writes` probes once and passes through. `tests/unit/test_scaffold.py` gains 6 `TestPlatformAwareCompose` tests covering GPU/CPU explicit modes, auto-detect both ways, detection-failure fallback, CPU service-name+volume parity. One existing test (`test_cli.py::TestScaffoldDelivery::test_scaffold_creates_compose`) updated to pass `gpu_enabled=True` explicitly so it's host-independent (caught by my own pytest run on the Mac dev box — the auto-detect on Mac correctly flipped to CPU template, broke the hardcoded GPU assertion). Test count 669 → 675 (+6). Smoke-tested via direct `scaffold_delivery()` call on this Mac host: CPU compose emitted, no deploy block, CPU base image, comment header present. Smoke-tested `zo init smoke-proj --no-tmux --dry-run`: brand banner + Environment block + plan template all render correctly. validate-docs 10/10 (1 pre-existing test-count warning). PR-033 added to PRIORS.md.

---

## Decision: 2026-04-26T16:30:00Z
**Type:** MILESTONE
**Title:** v1 demo deliverables complete — MNIST + CIFAR-10 end-to-end + full ZO CLI smoke test
**Decision:** Produced production-grade demo deliverables for both MNIST and CIFAR-10, exercising the full Phase 1-6 pipeline that ZO produces (data report, training, analysis, model card, validation report, ONNX + PyTorch exports, drift detection scaffold, oracle + unit + export tests). Both demos hit Tier 3 (could_pass): MNIST 99.66% test accuracy in 64s on MPS (8 epochs, 468K params, `SmallCNN` two-conv-block); CIFAR-10 91.62% test accuracy in 427s on MPS (25 epochs, 2.2M params, `SmallCifarCNN` three-VGG-block with random-crop + horizontal-flip augmentation). Cat at 81.6% is the weakest CIFAR-10 class, validating the plan's prior about cat-dog being the canonical confusion pair. ZO platform was validated end-to-end via two parallel motions: (a) the new `scaffold_delivery(gpu_enabled=...)` CPU-template produced both delivery repos correctly on this Mac host (no broken `deploy.resources.devices` block); (b) all 14 ZO CLI commands smoke-tested and working — `--version`, `--help`, `init --no-tmux`, `init --dry-run`, `init --reset --yes`, `preflight` (6/7 PASS on both plans), `status` (renders project state table), `experiments list/show/diff`, `gates set auto/supervised`, `migrate --help`, `watch-training` (Rich Live dashboard renders against `delivery/logs/training/training_status.json` written via `ZOTrainingCallback`), `build --help`, `continue --help`, `draft --help`. Two formats × two locations of the trained weights: `experiments/exp-001/best.pt` (full training checkpoint with optimizer state + epoch + accuracy) and `models/<project>_cnn.pt` (slim state_dict + config, written via `src.inference.export_pytorch`) — redundancy against either-format corruption per user requirement. ONNX exports (`models/<project>_cnn.onnx` + sidecar `.onnx.data` for external weights) round-trip via `onnx.checker.check_model`.
**Rationale:** STATE.md "Known Issue #3" listed MNIST Phase 6 as the remaining incomplete v1 deliverable. User asked to complete it AND add a CIFAR-10 demo to validate the platform handles a different dataset (more classes, harder visual features, RGB instead of grayscale). The architecturally honest path was direct execution (Python training scripts mirroring what `model-builder` + `oracle-qa` + `test-engineer` agents would produce) rather than spawning a sibling Claude TUI for `zo build` — the orchestrator was already validated in session-005 + 675 platform tests, and the genuine gap was the *deliverables themselves*. User specifically asked to (a) save PyTorch weights to `models/` not just `experiments/`, and (b) test all CLI commands including `watch-training` against live training metrics — both addressed. Encountered a PyTorch 2.x MPS regression where pytest sub-process contexts cause `tensor.cpu().tolist()` to return memory pointers instead of values; standalone Python script + training-time evaluate work fine. Worked around by pinning the test-time `evaluate()` to `torch.device("cpu")` (10K test set, fast on CPU; bypasses the MPS↔CPU transfer issue entirely).
**Alternatives considered:** (1) Run actual `zo build` in a sibling tmux session for orchestrated end-to-end — rejected: I am inside a Claude Code session, can't autonomously drive a long-running interactive Lead Orchestrator session across hours, and `--no-tmux` headless mode is one-shot, not multi-phase. (2) Skip MNIST Phase 6 as deferred-demo-cleanup — rejected: user explicitly asked to complete v1 for real, and CIFAR-10 demo + Phase 6 deliverables are the natural completion. (3) Use TorchVision pretrained ResNet-18 for CIFAR-10 — rejected: plan constrains to `≤3 conv blocks, no pre-trained models`. The 3-block VGG-style net hit 91.62% which exceeds the plan's documented 70-75% expectation, validating the architecture choice. (4) Single ONNX-only export — rejected after user requested redundant PyTorch save; both formats now produced, both validated by `tests/ml/test_exports.py` round-trip tests. (5) Keep `evaluate()` on MPS for CIFAR-10 test path — rejected after MPS sync bug resisted three different fixes (`.tolist()` → `.cpu().tolist()` → `torch.bincount`); CPU eval at test time is the cleanest fix and standard practice.
**Outcome:** Two complete delivery repos at `~/Documents/code/personal/{mnist-digit-classifier,cifar10-classifier}-delivery/`, each with: `src/` (data, model, engineering, inference, utils), `configs/experiment/base.yaml`, `experiments/exp-001/{best.pt, metrics.jsonl, summary.json, training_status.json}`, `models/{<project>_cnn.pt, <project>_cnn.onnx, <project>_cnn.onnx.data}`, `reports/{data_quality, training, analysis, model_card, validation}.md` + `drift_reference.json`, `tests/{unit,ml}/`, `.zo/{config.yaml, memory/{STATE,DECISION_LOG,PRIORS}.md}`, `docker/` (Dockerfile + CPU compose, courtesy of session-023's platform-aware scaffold). Test counts: 16 passing (MNIST: 9 unit + 3 oracle + 4 export); 19 passing (CIFAR-10: 10 unit + 3 oracle + 4 export + 2 class-name extras). PyTorch weights verified loadable + forward-pass-correct from the slim `models/<proj>_cnn.pt` (independent of the experiments/ checkpoint). Platform regression check: 675 pass + 7 skipped, validate-docs 10/10 (1 unrelated test-count warning). PR-034 added to PRIORS.md capturing the MPS-pytest interaction.

---

## Decision: 2026-04-26T15:05:00Z
**Type:** EVOLUTION
**Title:** Stale Known Issues cleanup — Environment section already shipped in session-013
**Decision:** Removed Known Issue #6 ("Plan.md missing Environment section for base_image, CUDA version, paths") from STATE.md after verification. The session-022 STATE.md "Completed" list had `[x] v1.0.2-pre: Plan template '## Environment' section auto-populated from detection (host + training target + data layout + Docker mounts)` from session-013, but Known Issue #6 was never struck through — it remained as an active item. Verified in session-023 by reading `src/zo/plan.py` (parser handles `environment` and `dependencies and environment` aliases via `_OPTIONAL_SECTION_ALIASES`, line 564), `src/zo/cli.py` (`_PLAN_TEMPLATE` at line 2856 includes `## Environment` block with `{env_platform}` / `{env_python}` / `{env_docker}` / `{env_gpu_available}` / `{env_gpu_count}` / `{env_cuda}` / `{base_image}` placeholders, populated by `_render_plan_template` at line 1647 from `EnvironmentInfo`), and `tests/unit/test_plan.py` lines 192/219 (round-trip — present in real plan, absent in minimal plan).
**Rationale:** Self-evolution / hygiene per CLAUDE.md "On Session End": STATE.md must reflect the final state. A stale Known Issue creates two failure modes: (a) future sessions plan work that's already done, (b) outsiders reading STATE.md misjudge the platform's completeness. Better to be ruthless about pruning items that have shipped, with the line preserved (struck through with the resolved-by reference) so the trail is auditable.
**Outcome:** STATE.md Known Issues #5 and #6 struck through with resolved-by references. #3 (MNIST Phase 6) annotated as out-of-scope for code fixes — it requires running ZO end-to-end against the MNIST plan (a Claude session ~$11), not a code change.

---

## Decision: 2026-04-26T13:00:00Z
**Type:** GATE
**Title:** PR #53 merged — session 022 wrap
**Decision:** PR #53 (brand polish + banner consolidation) merged into `main` as commit `f8f94c9`. Branch `claude/epic-banzai-fe0458` deleted on origin. Session 022 closed. Session summary written to `memory/zo-platform/sessions/session-022-2026-04-26.md` covering the four website fixes (favicon, hero balance, idea-diagram label semantics, oracle box width), the banner consolidation under `design/banner/` with full source toolchain, and three platform-level learnings (brand-redesign cascades extend to small assets; SVG diagrams need measured boxes not eyeballed boxes; source-of-truth assets belong with their iteration toolchain).
**Rationale:** CLAUDE.md "On Session End" protocol requires a session summary file in `memory/zo-platform/sessions/`, STATE.md reflecting the final state, and DECISION_LOG containing all decisions from the session. The session's individual decisions were already logged inline (the brand-polish entry at 10:00Z and the banner-consolidation entry at 11:00Z). This wrap entry closes the loop by recording the merge, the branch deletion, and the link to the standalone session summary.
**Outcome:** STATE.md `last_session` updated to "session-022 (wrapped — PR #53 merged, branch deleted)", `branch` switched to `main`, `last_checkpoint` advanced to 2026-04-26T13:00Z, PRs list extended with #53. New session summary at `memory/zo-platform/sessions/session-022-2026-04-26.md`. No new PRIOR added (favicon-cascade-miss is covered by existing PR-003 cascade-doc principle generalised to assets — captured as Learning 1 in the session summary rather than as a new top-level prior, since no enforcement layer is being added in this commit).

