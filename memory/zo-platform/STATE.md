# STATE.md — Zero Operators Platform Build

project: zero-operators-build
mode: maintain
phase: complete
iteration: 1
status: complete

## Current Position

ZO v1.0.2-pre — **CIFAR-10 demo running**. Dynamic agent creation (custom/ dir, plan-defined + mid-build), draft scout team, live training dashboard, auto test reports, structured phase report templates. 19 core agents + custom library, 415 tests, ruff clean, validate-docs 10/10. PRs #22-#28.

## Completed

- [x] Phase 0: Agent definitions (17 files), settings.json, build plan v2.0
- [x] Phase 1: Plan Parser, Target Parser, Comms Logger, setup.sh
- [x] Phase 2: Memory Layer, Semantic Index
- [x] Phase 3: Orchestration Engine + Lifecycle Wrapper + gate mode toggle
- [x] Phase 4: Evolution Engine, CLI, integration tests
- [x] Phase 5: End-to-end validation (MNIST: 99% accuracy, 98 tests, ~$11)
- [x] Slash commands: 24 commands across 8 categories
- [x] Documentation: COMMANDS.md reference, interactive HTML demo
- [x] README: full user workflow, architecture, commands, e2e results
- [x] v1.0.1: Interactive tmux agent sessions (send-keys + paste-buffer)
- [x] v1.0.1: ZO brand panel at startup (project, mode, phase, gate info)
- [x] v1.0.1: Smart build (auto-detects fresh/continue/plan-edited)
- [x] v1.0.1: Pre-launch phase review in all modes
- [x] v1.0.1: zo maintain removed (zo build handles plan edits)
- [x] v1.0.1: zo continue is thin alias for zo build
- [x] v1.0.1: zo draft accepts multiple file/dir paths + interactive refinement
- [x] v1.0.1: Live monitoring dashboard (tasks, team, comms events)
- [x] v1.0.1: Doc-code consistency: validate-docs.sh (10 checks, <2s)
- [x] v1.0.1: Hook system: SessionStart, PreToolUse, PostToolUse, Stop
- [x] v1.0.1: Self-evolution: PR-005 (enforcement > aspiration), three-layer defense
- [x] v1.0.1: Full doc audit: agent counts 16→17, version 1.0.0→1.0.1
- [x] v1.0.2-pre: Phase persistence fix (SessionState tracks per-phase status + completed subtasks)
- [x] v1.0.2-pre: Blocking gates fix (get_current_phase returns GATED phases for human review)
- [x] v1.0.2-pre: Phase artifact contracts (required_artifacts on all 6 phases)
- [x] v1.0.2-pre: Auto-generated Jupyter notebooks per phase (notebooks.py)
- [x] v1.0.2-pre: Delivery repo scaffold with Docker (scaffold.py, Dockerfile, docker-compose.yml)
- [x] v1.0.2-pre: zo preflight command (10 validation checks, GPU/Docker detection)
- [x] v1.0.2-pre: Delivery repo structure redesign (configs/, src/ by responsibility, experiments context trail, tests unit/ml split, docker/ subdir, STRUCTURE.md)
- [x] v1.0.2-pre: Orchestrator pipeline wiring (artifact validation at gates, auto-notebook generation, Docker/STRUCTURE.md in lead prompt)
- [x] v1.0.2-pre: setup.sh auto-fix — interactive prompt installs uv, Claude CLI, global settings (bash 3.2 compatible)
- [x] v1.0.2-pre: Claude CLI install updated to official curl method (replaced deprecated npm install)
- [x] v1.0.2-pre: setup.sh verifies zo CLI callable on PATH (check #11), auto-fixes via symlink to ~/.local/bin/
- [x] v1.0.2-pre: setup.sh deps check upgraded from dry-run to actual `uv sync`
- [x] v1.0.2-pre: zo draft works without source docs — conversational, description-based, or interactive prompt
- [x] v1.0.2-pre: Draft plans write to main repo (not worktrees) via _main_repo_root()
- [x] v1.0.2-pre: Draft session wrap-up — Claude asks "anything else?" then tells user to /exit and run zo build
- [x] v1.0.2-pre: Brand banner (_show_banner) on all 6 CLI commands (build, draft, init, status, preflight, continue)
- [x] v1.0.2-pre: Phase 1 enriched — 13 subtasks (was 7), 5 agents (was 2) for production data workflows
- [x] v1.0.2-pre: Cross-cutting agents — code-reviewer + research-scout default on ALL phases, all workflow modes
- [x] v1.0.2-pre: README updated — zo draft docs reflect conversational flow + new usage patterns
- [x] v1.0.2-pre: Autonomous path handoff — zo init writes absolute delivery path to target file, auto-scaffolds delivery repo
- [x] v1.0.2-pre: init → draft → build pipeline carries context via target file (no user path passing)
- [x] v1.0.2-pre: Haiku headline summaries — live 1-line status every 60s during zo build
- [x] v1.0.2-pre: tmux orphan prevention — draft kills existing window before creating new one
- [x] v1.0.2-pre: Draft tests fixed — all use --no-tmux (was spawning real tmux windows)
- [x] v1.0.2-pre: zo gates set — toggle gate mode mid-session (supervised/auto/full-auto)
- [x] v1.0.2-pre: Full doc audit — COMMANDS.md, workflow.md, README, SAMPLE_PROJECT updated for consistency
- [x] v1.0.2-pre: Training metrics protocol (ZOTrainingCallback) — JSONL + status JSON for live dashboards
- [x] v1.0.2-pre: zo watch-training — Rich Live dashboard (progress bar, metrics table, sparkline, checkpoints)
- [x] v1.0.2-pre: Auto split-pane — wrapper detects training_status.json, splits tmux pane for dashboard
- [x] v1.0.2-pre: Model-builder contract updated with required ZOTrainingCallback usage
- [x] v1.0.2-pre: Phase 4 notebook reads from metrics.jsonl (with legacy fallback)
- [x] v1.0.2-pre: Auto test reports at gates — pytest JUnit XML → structured markdown test_report.md
- [x] v1.0.2-pre: Phase 1 report template (10 sections: schema, completeness, distributions, outliers, class, temporal, correlations, drift, splits, recommendations)
- [x] v1.0.2-pre: Phase 5 report template (7 sections: explainability, error analysis, bias, ablation, significance, reproducibility, verdict)
- [x] v1.0.2-pre: Agent contracts reference specs/report_templates.md for structured reports
- [x] v1.0.2-pre: Draft scout team — Plan Architect (Opus lead) + Data Scout (Sonnet) + Research Scout
- [x] v1.0.2-pre: zo draft CLI redesigned — --docs, --data, -d flags (all optional, conversational fallback)
- [x] v1.0.2-pre: _launch_and_monitor refactored — shared by build and draft, model/max_turns params
- [x] v1.0.2-pre: Agent count 17 → 19 (plan-architect, data-scout added)
- [x] v1.0.2-pre: Dynamic agent creation — .claude/agents/custom/ for project-specific specialists
- [x] v1.0.2-pre: Plan parser supports **Custom agents:** block (name: Model — role)
- [x] v1.0.2-pre: Orchestrator auto-creates custom agent .md files from plan at build start
- [x] v1.0.2-pre: Custom agents available for all phases (not restricted by AGENT_PHASE_MAP)
- [x] v1.0.2-pre: _prompt_roster scans both core and custom/ directories, labels each

## Known Issues

1. ~~Phase state not persisted between zo build calls~~ (RESOLVED: session-010)
2. ~~Blocking gates cause repeated sessions in auto mode~~ (RESOLVED: session-010)
3. MNIST Phase 6 (packaging: model card, validation report) not completed
4. ~~Agent permissions need broader .claude/settings.json allow patterns~~ (resolved)
5. Device detection (Linux vs Mac) not yet implemented — affects Docker GPU passthrough
6. Plan.md missing Environment section for base_image, CUDA version, paths

## What's Next

1. **CIFAR-10 demo** — running, plan drafted, zo build in progress
2. Phase completion snapshots (C1) — capture context at phase boundaries for reports
3. Domain evaluator refactor — make project-specific via plan.md domain priors
4. XAI + Domain Evaluator activation for IVL F5 Phase 5
5. Device detection and user directory paths in plan schema
6. IVL F5 project — first production deployment

## Session Metadata

last_checkpoint: 2026-04-13T01:00:00Z
last_session: session-012
branch: claude/charming-lovelace (worktree)
test_count: 415 passed, 7 skipped
lint: ruff clean (src/zo/)
validation: scripts/validate-docs.sh 10/10 passed, 0 warnings
prs: #22-#25 (UX), #26 (training dashboard + test reports), #27 (draft scout team), #28 (dynamic agents)
