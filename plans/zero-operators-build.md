# Zero Operators Platform Build Plan

---
project_name: "zero-operators-build"
version: "1.0"
created: "2026-04-09"
last_modified: "2026-04-09"
status: active
owner: "Sam"
---

## Objective

Build the Zero Operators (ZO) platform itself — the orchestration engine, memory layer, communication system, plan parser, target file enforcer, and agent definitions that together form an autonomous AI research and engineering team system. The platform reads a `plan.md`, spawns a coordinated agent team, executes work against delivery repositories, and enforces oracle-driven validation at every gate.

Deliverables: a working ZO platform deployed as a Python package in the `zero-operators/` repository, with all 16 agent definition files, a functional memory layer, orchestration engine, JSONL comms logger, plan.md validator, target file parser with isolation enforcement, semantic search index, and a comprehensive test suite proving the system can execute a real project end-to-end.

## Oracle

**Primary metric:** End-to-end project execution success
**Ground truth source:** A controlled test project (mini-project with synthetic data) that exercises all phases, gates, memory operations, and agent contracts.

**Evaluation method:** Run the test project through ZO from plan.md to delivery. Verify:
1. All phases execute in sequence with correct gating
2. STATE.md is read at session start and written at session end
3. DECISION_LOG.md contains entries for every orchestration decision
4. PRIORS.md is seeded from plan.md domain priors
5. Semantic index returns relevant results for test queries
6. JSONL comms logs contain all 5 event types (message, decision, gate, error, checkpoint)
7. Target file isolation is enforced (writes to zo_only_paths are blocked)
8. Delivery repo contains zero ZO artifacts
9. Session recovery works (interrupt + resume from STATE.md)
10. Self-evolution triggers (error → root cause → rule update → verified fix)
11. Plan.md edit mid-execution triggers replan, human confirms, execution resumes with new objectives
12. Agent self-validation checklists execute and results are logged to DECISION_LOG
13. README.md and module-level documentation are complete and accurate
14. Continue mode works: launch ZO against a paused project, it reads STATE.md and resumes from the correct phase

**Target threshold:**
- Tier 1: All 14 verification checks pass, test suite >80% line coverage, first real project (IVL F5) executes Phases 1-2 successfully
- Tier 2: 11/14 verification checks pass, test suite >70% coverage, test project completes
- Tier 3: 8/14 verification checks pass, core modules functional, manual orchestration required

**Evaluation frequency:** After each module is complete (unit), after integration (integration), after full assembly (end-to-end)

**Secondary metrics:** Test suite line coverage, module-level documentation completeness, ruff lint pass rate, type hint coverage on public functions

**Statistical significance:** Not applicable (deterministic system tests, not stochastic ML).

## Workflow

**Mode:** classical_ml (adapted — this is a software build, not ML training, but the phase structure maps)
**Phases:**
- Phase 1: Codebase scaffolding and module decomposition (data review → code review)
- Phase 2: Core module implementation (feature engineering → module engineering)
- Phase 3: Integration and orchestration engine (model design → system design)
- Phase 4: Testing and iteration (training → testing cycles)
- Phase 5: Validation and hardening (analysis → system validation)
- Phase 6: Packaging and documentation (packaging → release)

**Gates:**
- Gate 1: automated (module decomposition approved by architect, contracts defined)
- Gate 2: blocking (human reviews module contracts and build sequence)
- Gate 3: automated (all modules pass unit tests independently)
- Gate 4: blocking (human reviews integrated system, approves for real project trial)
- Gate 5: automated (test project executes end-to-end)

**Iteration budget:** No GPU budget. Iteration budget: 200 agent sessions or 2 calendar weeks, whichever comes first.
**Human checkpoints:** After module decomposition (Gate 2), after integration (Gate 4)

## Data Sources

### Source 1: ZO Specification Documents
- **Location:** `zero-operators/specs/` (architecture.md, agents.md, memory.md, oracle.md, workflow.md, plan.md, comms.md, evolution.md)
- **Format:** Markdown
- **Access:** Read-only reference. Specs define WHAT to build; agents write code to implement them.
- **Known issues:** None. Documents are complete and reviewed.

### Source 2: ZO Design Reference
- **Location:** `zero-operators/design/` (zero_operators_brand_system.html, zero_operators_logos.html, zero_operators_font_options.html, zero_operators_dual_tone_system.html, zero_operators_abstract_visuals.html, zero_operators_light_deck.html, zero_operators_banners_safe_layout.html, zero_operators_orbital_grid_expanded.html)
- **Format:** HTML design files
- **Access:** Read-only reference for all visual outputs.
- **Known issues:** None. Design system is finalised.

### Source 3: Feature Reference
- **Location:** `zero-operators/plan/zero_operators_features_and_separation.html`
- **Format:** HTML with 4-tab layout (Ruflo/OMC agents to steal, feature list, repo separation, blind test)
- **Access:** Read-only. The 27-feature list defines the full feature backlog; v1 scope is a subset.
- **Known issues:** Some features reference project-specific context (IVL F5). Abstract to general use.

### Source 4: Test Project (Synthetic)
- **Location:** To be created at `zero-operators/tests/fixtures/test-project/`
- **Format:** Synthetic dataset (CSV, ~1000 rows), mock plan.md, mock target file
- **Access:** Generated by Test Engineer during Phase 4
- **Known issues:** Must be realistic enough to exercise all code paths.

## Domain Priors

### Core Platform Capabilities (Non-Negotiable)
These four capabilities define what makes ZO a "full-time team member" rather than a one-shot tool:

1. **Memory and continuity**: Every action is logged to DECISION_LOG. STATE.md captures exact phase, agent status, and blockers. Session summaries are written at session end. On next launch, ZO reads STATE.md, queries semantic index for relevant past decisions, and resumes exactly where it left off. The human can review everything that happened via comms logs and decision audit trail.

2. **Self-learning from errors**: When an error occurs, ZO doesn't just fix the symptom — it runs the post-mortem protocol (specs/evolution.md): document failure → identify root cause → fix immediate issue → update the rule/prior/spec that allowed it → verify the updated rule prevents recurrence. PRIORS.md and spec files evolve over time.

3. **Self-verification**: Every agent has a validation checklist that must pass before reporting done. The Oracle validates deliverables against hard metrics. Code Reviewer and Test Engineer verify code quality and correctness. All verification results are logged. No deliverable is marked complete without passing its validation gate.

4. **Documentation**: The Documentation Agent (B6) maintains README.md, API docs, module docstrings, and developer setup guides. Agent definition files provide full context for every role. DECISION_LOG provides audit trail. Comms logs provide full reasoning chain. Every artifact is documented for both humans and other agents.

### Platform Architecture Knowledge
- ZO is built on Claude Code's native agent team capabilities: `.md` files in `.claude/agents/` with YAML frontmatter (name, model, role, tier, team) and markdown body instructions. These ARE the agent prompt templates — no separate template system needed.
- Claude Code supports `--cwd` for working directory isolation. This is the mechanism for repo separation. Agents launched with `--cwd ../delivery-repo` can only operate there.
- Claude Code supports peer-to-peer agent communication via session context. Messages between agents are the native communication channel.
- JSONL logging is append-only by design. Log files rotate daily. Query via grep or SQLite import.

### Design System Constraint
- All ZO outputs (dashboard, reports, documentation, diagrams) must follow the ZO brand system:
  - Primary color: amber #F0C040
  - Amber dim: #8a6020
  - Background void: #080808
  - Surface: #0d0d0d
  - Paper (light mode): #f5f0e8
  - Ink (light mode): #1a1400
  - Monospace font: Share Tech Mono
  - Heading font: Rajdhani (weights 300/400/600/700)
  - Logo: orbital mark (concentric rings, amber on void)
- Design files in `zero-operators/design/` are the canonical reference.

### Implementation Patterns
- Python is the primary language. PEP8, type hints, Google-style docstrings.
- PyTorch for any ML components (Sam is a heavy PyTorch user).
- uv for package management, ruff for linting.
- Files under 500 lines, functions under 50 lines.
- Git commits use conventional format: type(scope): subject.
- fastembed for embedding generation, SQLite for semantic index storage.

### Known Risks
- Context window limits: orchestration engine must manage context budgets across agents. Eager loading of all specs will blow context. Implement lazy spec loading.
- Claude Code agent spawning has rate limits. Orchestration engine must handle rate limit waits gracefully (steal: OMC rate limit wait daemon pattern).
- Semantic index cold start: first session has no prior decisions to search. Handle gracefully with empty results.
- Session recovery edge case: if a crash occurs mid-write to STATE.md, the file may be corrupt. Implement atomic writes (write to temp, rename).

## Agents

**Active agents:** software-architect, backend-engineer, test-engineer, code-reviewer, documentation-agent
**Phase-in agents:** frontend-engineer (activate after core backend is stable, for v2 dashboard)
**Inactive agents:** All project delivery agents (they are what we're building FOR, not WITH)

**Agent overrides:**
- software-architect: Use Opus (critical architecture decomposition decisions)
- backend-engineer: Use Opus for orchestration engine, Sonnet for utility modules
- test-engineer: Use Sonnet (standard test writing)
- code-reviewer: Use Sonnet (standard review)
- documentation-agent: Use Haiku (formatting and sync work)

## Constraints

- **No external dependencies beyond stdlib + approved packages:** Approved: fastembed, sqlite3 (stdlib), pydantic (validation), rich (CLI output), ruff (dev only). No web frameworks for v1 (dashboard is v2).
- **Claude Code native patterns only:** Do not build custom agent spawning infrastructure. Use Claude Code's native `.claude/agents/` definitions and agent team capabilities. ZO orchestration logic wraps and coordinates these native capabilities.
- **Repo separation enforced at all times:** During development, ZO code lives in `zero-operators/`. Test project artifacts live in `tests/fixtures/test-project/`. No mixing.
- **Design system compliance:** All visual outputs, reports, and documentation follow the ZO brand system defined in `design/`. No ad-hoc styling.
- **Spec-driven implementation:** Every module must trace back to a specific spec document. If a feature is not in a spec, it does not get built (or the spec is updated first).
- **No v2 features in v1:** Dashboard, WASM booster, self-learning routing, multi-project concurrency, external integrations — all out of scope.

## Module Decomposition

The Software Architect decomposes ZO into these buildable modules. Each module maps to a spec document and has defined interfaces.

### Module 1: Plan Parser and Validator
**Spec source:** specs/plan.md
**Responsibility:** Parse plan.md files, validate all 8 required sections present, extract YAML frontmatter, check oracle definition completeness, validate workflow mode, verify data source paths exist.
**Outputs:** Parsed plan object (Pydantic model), validation report (pass/fail with missing sections listed).
**Priority:** P0 (everything depends on this)

### Module 2: Target File Parser and Isolation Enforcer
**Spec source:** specs/architecture.md (target file specification)
**Responsibility:** Parse target files, resolve delivery repo paths, validate agent working directories, enforce zo_only_paths blocklist on every file write, halt execution on violation.
**Outputs:** Parsed target config, path validation function, isolation violation logger.
**Priority:** P0

### Module 3: Memory Layer
**Spec source:** specs/memory.md
**Responsibility:** Implement STATE.md read/write with atomic operations, DECISION_LOG.md append-only writer, PRIORS.md manager (seed from plan.md, append from domain evaluator), session summary writer, session recovery (read last STATE.md, determine resume point).
**Outputs:** MemoryManager class with read_state(), write_state(), append_decision(), read_priors(), write_session_summary(), recover_session() methods.
**Priority:** P0

### Module 4: Semantic Index
**Spec source:** specs/memory.md (semantic search section)
**Responsibility:** Embed DECISION_LOG entries and PRIORS using fastembed, store in SQLite with HNSW-style nearest-neighbor lookup, support natural language queries ("what did we decide about feature selection?").
**Outputs:** SemanticIndex class with index_entry(), query(), rebuild_index() methods.
**Priority:** P1 (memory layer works without it; semantic search is enhancement)

### Module 5: Comms Logger
**Spec source:** specs/comms.md
**Responsibility:** Write structured JSONL events (message, decision, gate, error, checkpoint) to daily log files, implement log rotation, provide query interface for reading logs by event type/agent/time range.
**Outputs:** CommsLogger class with log_message(), log_decision(), log_gate(), log_error(), log_checkpoint(), query_logs() methods.
**Priority:** P0

### Module 6: Orchestration Engine
**Spec source:** specs/workflow.md, specs/agents.md, specs/oracle.md
**Responsibility:** The core. Reads parsed plan, selects workflow mode, decomposes into phases, generates agent contracts from templates, manages phase sequencing and gating, spawns agents via Claude Code native capabilities, enforces gate pass/fail, handles human checkpoints, detects plan.md edits and triggers replan, manages context budgets.
**Outputs:** Orchestrator class with run_project(), spawn_agent(), check_gate(), replan(), escalate_to_human() methods.
**Priority:** P0 (but depends on Modules 1-3, 5)

### Module 7: Evolution Engine
**Spec source:** specs/evolution.md
**Responsibility:** Implement post-mortem protocol (document → root cause → fix → update rule → verify), categorize root causes, update PRIORS.md or spec files, track evolution metrics.
**Outputs:** EvolutionEngine class with run_postmortem(), categorize_root_cause(), update_rule(), verify_fix() methods.
**Priority:** P1

### Module 8: Agent Definition Files
**Spec source:** specs/agents.md
**Responsibility:** Write all 16 agent `.md` files to `.claude/agents/` with proper YAML frontmatter and full spawn prompt instructions following the contract template.
**Outputs:** 16 `.md` files (10 project delivery + 6 platform build) ready for Claude Code to use.
**Priority:** P0

### Module 9: CLI Entry Point
**Spec source:** PRD.md (operating modes)
**Responsibility:** Command-line interface for launching ZO in Build, Continue, or Maintain mode. Parses arguments, loads plan, initialises memory, starts orchestrator.
**Outputs:** `zo` CLI command with subcommands: `zo build <plan>`, `zo continue <project>`, `zo maintain <project>`.
**Priority:** P1

## Build Sequence

```
Phase 1 — Scaffolding (parallel after architect approval)
├── Module 1: Plan Parser        ← no dependencies
├── Module 2: Target Parser      ← no dependencies  
├── Module 5: Comms Logger       ← no dependencies
└── Module 8: Agent Definitions  ← no dependencies (documentation task)

Gate 1: All 4 modules pass unit tests

Phase 2 — Core Infrastructure (parallel)
├── Module 3: Memory Layer       ← depends on Module 5 (logs decisions)
└── Module 4: Semantic Index     ← depends on Module 3 (indexes memory)

Gate 2: Human reviews module contracts and integration plan

Phase 3 — Integration
└── Module 6: Orchestration Engine ← depends on Modules 1-5, 8

Gate 3: Orchestration engine passes unit tests with mocked agents

Phase 4 — Hardening (parallel)
├── Module 7: Evolution Engine   ← depends on Module 3, 5
├── Module 9: CLI Entry Point    ← depends on Module 6
└── Integration test suite       ← depends on all modules

Gate 4: Human reviews integrated system

Phase 5 — Validation
└── End-to-end test project execution

Gate 5: Test project passes all 10 oracle verification checks
```

## Milestones

| Week | Milestone | Gate |
|------|-----------|------|
| 1 | Module decomposition complete, contracts defined, scaffolding started | Gate 1 |
| 1-2 | Modules 1, 2, 5, 8 complete with unit tests | Gate 1 |
| 2-3 | Memory layer and semantic index complete | Gate 2 |
| 3-4 | Orchestration engine functional with mocked agents | Gate 3 |
| 4-5 | Evolution engine, CLI, integration tests | Gate 4 |
| 5-6 | End-to-end test project, hardening, documentation | Gate 5 |

## Delivery

**Target repo:** This IS the target repo (zero-operators builds itself).
**Target branch:** main
**Delivery structure:**
- `src/zo/` — ZO platform Python package
  - `src/zo/plan.py` — plan parser and validator (Module 1)
  - `src/zo/target.py` — target file parser and isolation enforcer (Module 2)
  - `src/zo/memory.py` — memory layer (Module 3)
  - `src/zo/semantic.py` — semantic index (Module 4)
  - `src/zo/comms.py` — comms logger (Module 5)
  - `src/zo/orchestrator.py` — orchestration engine (Module 6)
  - `src/zo/evolution.py` — evolution engine (Module 7)
  - `src/zo/cli.py` — CLI entry point (Module 9)
  - `src/zo/__init__.py` — package init
- `.claude/agents/` — all 16 agent definition files (Module 8)
- `.claude/skills/ml-workflow/SKILL.md` — ML workflow skill
- `tests/` — full test suite
  - `tests/unit/` — per-module unit tests
  - `tests/integration/` — cross-module integration tests
  - `tests/e2e/` — end-to-end test project
  - `tests/fixtures/` — test data and mock plans
- `pyproject.toml` — package metadata (uv compatible)
- `README.md` — developer setup and usage guide

## Environment

**Python version:** 3.11+
**Key dependencies:** pydantic>=2.0, fastembed, rich, click (CLI)
**Dev dependencies:** ruff, pytest, pytest-cov
**Package manager:** uv
**Linting:** ruff
**Hardware:** No GPU required (this is a software build, not ML training)

## Open Questions

- Should the orchestration engine use Claude Code's native agent spawning directly, or wrap it in a Python subprocess manager for better control over lifecycle and logging? (Decision needed before Phase 3)
- What is the right granularity for semantic index chunks — full DECISION_LOG entries, or sentence-level splits? (Decision needed before Module 4)
- Should the CLI support a `zo draft <source-docs>` command for agentic plan drafting, or is that a separate workflow? (Decision needed before Module 9)
- How should the dashboard API be designed now (v1 backend) to avoid rework when the frontend is built (v2)? (Can defer — frontend is phase-in)
- Should agent definition files include inline examples of contract formats, or reference a shared contracts directory? (Decision needed before Module 8)
