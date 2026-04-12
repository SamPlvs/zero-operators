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
**Outcome:** ZO is production-ready for real projects. IVL F5 is next.

---

## Decision: 2026-04-09T22:00:00Z
**Type:** FEATURE
**Title:** 23 slash commands added for Claude Code
**Decision:** Implement full command vocabulary: project lifecycle (connect/import/plan/launch), memory (recall/prime/priors/session-summary), gates (approve/reject/gates), observability (watch/logs/decisions/history), documentation (code-docs/validation-report/model-card/retrospective), agent management (agents/spawn/create-agent), utility (commit).
**Rationale:** Inspired by coleam00/habit-tracker .claude/commands pattern. ZO needs its own vocabulary mapping to the plan→execute→verify→evolve loop. Commands provide the interface between human and ZO inside Claude Code sessions.
**Outcome:** 23 command files in .claude/commands/, COMMANDS.md reference, interactive HTML demo. Session closed — ready for IVL F5.

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
**Outcome:** Design captured. Implementation during IVL F5 plan setup. Detection logic will extend `zo preflight` (already detects GPU/Docker) into the planning phase.

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
