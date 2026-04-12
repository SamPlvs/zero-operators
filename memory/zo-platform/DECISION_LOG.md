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
