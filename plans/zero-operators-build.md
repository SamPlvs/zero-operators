# Zero Operators Platform Build Plan

---
project_name: "zero-operators-build"
version: "2.0"
created: "2026-04-09"
last_modified: "2026-04-09"
status: active
owner: "Sam"
---

## Objective

Build the Zero Operators (ZO) platform itself — the orchestration engine, memory layer, communication system, plan parser, target file enforcer, agent definitions, setup tooling, and CLI that together form an autonomous AI research and engineering team system. The platform reads a `plan.md`, spawns a coordinated agent team via Claude Code's native agent teams, executes work against delivery repositories, and enforces oracle-driven validation at every gate.

Deliverables: a working ZO platform deployed as a Python package in the `zero-operators/` repository, with all 20 agent definition files in `.claude/agents/`, a functional memory layer, hybrid orchestration engine (native Claude Code teams + Python lifecycle wrapper), JSONL comms logger, plan.md validator, target file parser with isolation enforcement, semantic search index (full decision entries with summary prefix), a `zo` CLI with build/continue/draft subcommands, `setup.sh` bootstrapper, `zo init` project scaffolder, and a comprehensive test suite proving the system can execute a real project end-to-end.

## Oracle

**Primary metric:** End-to-end project execution success
**Ground truth source:** A controlled test project (mini-project with synthetic data) that exercises all phases, gates, memory operations, and agent contracts.

**Evaluation method:** Run the test project through ZO from plan.md to delivery. Verify:
1. All phases execute in sequence with correct gating
2. STATE.md is read at session start and written at session end
3. DECISION_LOG.md contains entries for every orchestration decision
4. PRIORS.md is seeded from plan.md domain priors
5. Semantic index returns relevant results for test queries (full decision entries with summary prefix)
6. JSONL comms logs contain all 5 event types (message, decision, gate, error, checkpoint)
7. Target file isolation is enforced (writes to zo_only_paths are blocked)
8. Delivery repo contains zero ZO artifacts
9. Session recovery works (interrupt + resume from STATE.md)
10. Self-evolution triggers (error → root cause → rule update → verified fix)
11. Plan.md edit mid-execution triggers replan, human confirms, execution resumes with new objectives
12. Agent self-validation checklists execute and results are logged to DECISION_LOG
13. README.md and module-level documentation are complete and accurate
14. Continue mode works: launch ZO against a paused project, it reads STATE.md and resumes from the correct phase
15. `setup.sh` validates all prerequisites and reports pass/fail
16. `zo init` creates correct project scaffold with all memory files
17. `zo draft` generates a valid plan.md from source documents
18. Python lifecycle wrapper captures agent spawn/completion events and pipes them to JSONL comms logger

**Target threshold:**
- Tier 1: All 18 verification checks pass, test suite >80% line coverage, first real project (prod-001) executes Phases 1-2 successfully
- Tier 2: 14/18 verification checks pass, test suite >70% coverage, test project completes
- Tier 3: 10/18 verification checks pass, core modules functional, manual orchestration required

**Evaluation frequency:** After each module is complete (unit), after integration (integration), after full assembly (end-to-end)

**Secondary metrics:** Test suite line coverage, module-level documentation completeness, ruff lint pass rate, type hint coverage on public functions

**Statistical significance:** Not applicable (deterministic system tests, not stochastic ML).

## Workflow

**Mode:** classical_ml (adapted — this is a software build, not ML training, but the phase structure maps)
**Phases:**
- Phase 0: Agent definitions and Claude Code environment setup
- Phase 1: Codebase scaffolding and core module implementation
- Phase 2: Core infrastructure (memory layer, semantic index)
- Phase 3: Integration and orchestration engine
- Phase 4: Testing, hardening, CLI, evolution engine
- Phase 5: Validation and documentation
- Phase 6: Packaging and release

**Gates:**
- Gate 0: blocking (human verifies all 20 agent definitions are correct, Claude Code setup validated)
- Gate 1: automated (plan parser, target parser, comms logger, setup tooling pass unit tests)
- Gate 2: blocking (human reviews module contracts and integration plan)
- Gate 3: automated (orchestration engine passes unit tests with mocked agents)
- Gate 4: blocking (human reviews integrated system, approves for real project trial)
- Gate 5: automated (test project executes end-to-end, 18 oracle checks evaluated)

**Iteration budget:** No GPU budget. Iteration budget: 200 agent sessions or 2 calendar weeks, whichever comes first.
**Human checkpoints:** After agent definitions (Gate 0), after core infrastructure (Gate 2), after integration (Gate 4)

## Data Sources

### Source 1: ZO Specification Documents
- **Location:** `zero-operators/specs/` (architecture.md, agents.md, memory.md, oracle.md, workflow.md, plan.md, comms.md, evolution.md)
- **Format:** Markdown
- **Access:** Read-only reference. Specs define WHAT to build; agents write code to implement them.
- **Known issues:** None. Documents are complete and reviewed.

### Source 2: ZO Design Reference
- **Location:** `zero-operators/design/`
- **Format:** HTML design files
- **Access:** Read-only reference for all visual outputs.

### Source 3: Feature Reference
- **Location:** `zero-operators/docs/source-design/zero_operators_features_and_separation.html`
- **Format:** HTML with 4-tab layout
- **Access:** Read-only. The 27-feature list defines the full feature backlog; v1 scope is a subset.
- **Known issues:** Some features reference project-specific context. Abstract to general use.

### Source 4: Test Project (Synthetic)
- **Location:** To be created at `zero-operators/tests/fixtures/test-project/`
- **Format:** Synthetic dataset (CSV, ~1000 rows), mock plan.md, mock target file
- **Access:** Generated by Test Engineer during Phase 4

## Domain Priors

### Core Platform Capabilities (Non-Negotiable)

1. **Memory and continuity**: Every action is logged to DECISION_LOG. STATE.md captures exact phase, agent status, and blockers. Session summaries are written at session end. On next launch, ZO reads STATE.md, queries semantic index for relevant past decisions, and resumes exactly where it left off.

2. **Self-learning from errors**: When an error occurs, ZO runs the post-mortem protocol (specs/evolution.md): document failure → identify root cause → fix immediate issue → update the rule/prior/spec that allowed it → verify the updated rule prevents recurrence.

3. **Self-verification**: Every agent has a validation checklist that must pass before reporting done. The Oracle validates deliverables against hard metrics. No deliverable is marked complete without passing its validation gate.

4. **Documentation**: The Documentation Agent maintains README.md, API docs, module docstrings, and developer setup guides. Every artifact is documented for both humans and other agents.

### Platform Architecture Knowledge

- ZO is built on Claude Code's native agent team capabilities: `.md` files in `.claude/agents/` with YAML frontmatter and markdown body instructions.
- Claude Code supports `--cwd` for working directory isolation. This is the mechanism for repo separation.
- Claude Code supports peer-to-peer agent communication via session context. Messages between agents are the native communication channel.
- **Hybrid orchestration model**: Claude Code native agent teams handle peer-to-peer communication (the superpower). A Python lifecycle wrapper invokes `claude` CLI to launch agent teams, captures lifecycle events (spawn/completion, stdout, errors, rate limits), and pipes them into the JSONL comms logger. Agents communicate natively; the wrapper observes and logs.
- JSONL logging is append-only by design. Log files rotate daily.

### Implementation Patterns
- Python 3.11+, PEP8, type hints, Google-style docstrings
- PyTorch for ML components
- uv for package management, ruff for linting
- Files under 500 lines, functions under 50 lines
- Conventional commit format: type(scope): subject
- fastembed for embeddings, SQLite for semantic index storage

### Known Risks
- Context window limits: orchestration engine must manage context budgets across agents. Implement lazy spec loading.
- Claude Code agent spawning has rate limits. Handle rate limit waits gracefully.
- Semantic index cold start: first session has no prior decisions. Handle gracefully with empty results.
- Session recovery: if crash occurs mid-write to STATE.md, implement atomic writes (write to temp, rename).

## Agents

**Active agents:** software-architect, backend-engineer, test-engineer, code-reviewer, documentation-agent
**Phase-in agents:** frontend-engineer (activate for v2 dashboard)
**Inactive agents:** All project delivery agents (they are what we're building FOR, not WITH)

**Agent overrides:**
- software-architect: Opus (critical architecture decomposition)
- backend-engineer: Opus for orchestration engine, Sonnet for utility modules
- test-engineer: Sonnet (standard test writing)
- code-reviewer: Sonnet (standard review)
- documentation-agent: Haiku (formatting and sync)

## Constraints

- **Approved packages only:** pydantic>=2.0, fastembed, rich, click, sqlite3 (stdlib). No web frameworks in v1.
- **Claude Code native patterns:** Use `.claude/agents/` definitions and agent team capabilities. Python wrapper adds observability, not replacement orchestration.
- **Repo separation enforced at all times.**
- **Design system compliance** for all visual outputs.
- **Spec-driven implementation:** every module traces to a spec. If not in a spec, it doesn't get built.
- **No v2 features in v1:** Dashboard, self-learning routing, multi-project concurrency, external integrations — out of scope.
- **No Docker in v1:** uv lockfile + setup.sh for reproducibility.

## Module Decomposition

### Module 0: Agent Definitions + Claude Code Setup ✅
**Spec source:** specs/agents.md
**Responsibility:** Write all 20 agent `.md` files to `.claude/agents/` with YAML frontmatter and full spawn prompts. Create `.claude/settings.json`. Validate agents can be spawned.
**Outputs:** 17 `.md` files, `.claude/settings.json`, validation report.
**Status:** COMPLETE

### Module 1: Plan Parser and Validator ✅
**Spec source:** specs/plan.md
**Responsibility:** Parse plan.md files, validate all 8 required sections, extract YAML frontmatter, check oracle definition completeness, validate workflow mode, verify data source paths.
**Outputs:** Parsed plan object (Pydantic model), validation report.
**File:** `src/zo/plan.py`
**Priority:** P0

### Module 2: Target File Parser and Isolation Enforcer ✅
**Spec source:** specs/architecture.md
**Responsibility:** Parse target files, resolve delivery repo paths, validate agent working directories, enforce zo_only_paths blocklist, halt on violation.
**Outputs:** Parsed target config, path validation function, isolation violation logger.
**File:** `src/zo/target.py`
**Priority:** P0

### Module 3: Memory Layer ✅
**Spec source:** specs/memory.md
**Responsibility:** STATE.md read/write with atomic operations, DECISION_LOG.md append-only writer, PRIORS.md manager, session summary writer, session recovery.
**Outputs:** MemoryManager class.
**File:** `src/zo/memory.py`
**Priority:** P0

### Module 4: Semantic Index ✅
**Spec source:** specs/memory.md (semantic search section)
**Responsibility:** Embed DECISION_LOG entries as full decision units. Extract 1-line summary from title + outcome at index time. Summary is embedded for matching; full entry injected into context on retrieval. SQLite with cosine similarity.
**Outputs:** SemanticIndex class.
**File:** `src/zo/semantic.py`
**Priority:** P1

### Module 5: Comms Logger ✅
**Spec source:** specs/comms.md
**Responsibility:** JSONL events (message, decision, gate, error, checkpoint), daily log rotation, query interface. Accepts events from Python lifecycle wrapper.
**Outputs:** CommsLogger class.
**File:** `src/zo/comms.py`
**Priority:** P0

### Module 6: Orchestration Engine (Hybrid) ✅
**Spec source:** specs/workflow.md, specs/agents.md, specs/oracle.md
**Responsibility:** Three-layer architecture:
1. `orchestrator.py` — Parses plan, decomposes phases (classical_ml/deep_learning/research), generates agent contracts, builds lead prompt with full context (plan + phases + agent roster + memory + coordination instructions), manages gates, detects plan edits
2. `wrapper.py` — Launches ONE Claude Code session as Lead Orchestrator (`claude --teammate-mode tmux`), monitors team via `~/.claude/tasks/` and session logs, captures tmux pane output, handles rate limits, pipes events to CommsLogger
3. Lead Orchestrator agent (inside Claude Code) uses `TeamCreate` + `Agent(team_name=...)` for native peer-to-peer messaging. Can dynamically create new agent definitions if project needs expertise beyond 17 pre-defined agents.
**Outputs:** Orchestrator class + LifecycleWrapper class (73 tests).
**Files:** `src/zo/orchestrator.py` (565 lines), `src/zo/_orchestrator_models.py`, `src/zo/_orchestrator_phases.py`, `src/zo/wrapper.py` (601 lines), `src/zo/_wrapper_models.py`
**Architecture note:** Python layer does NOT spawn agents directly. It builds context and launches one session. Agent coordination is native Claude Code with peer-to-peer comms.
**Status:** COMPLETE

### Module 7: Evolution Engine ✅
**Spec source:** specs/evolution.md
**Responsibility:** Post-mortem protocol, root cause categorization, PRIORS/spec updates, evolution metrics.
**Outputs:** EvolutionEngine class.
**File:** `src/zo/evolution.py`
**Priority:** P1

### Module 8: Setup and Initialization ✅
**Spec source:** PRD.md, specs/architecture.md
**Responsibility:**
1. `setup.sh` — validates Claude CLI, agent teams enabled, model access, `.claude/agents/` completeness, uv, git state
2. `zo init <project>` — scaffolds memory/, logs/, targets/, template plan.md, empty semantic index
**Outputs:** `setup.sh`, `zo init` subcommand.
**Priority:** P0

### Module 9: CLI Entry Point ✅
**Spec source:** PRD.md
**Responsibility:** CLI with subcommands: `zo build`, `zo continue`, `zo draft`, `zo init`, `zo status`.
- `zo draft <source-dir>` indexes source docs (project-scoped, persisted), generates compliant plan.md via agent with plan spec loaded.
**Outputs:** `zo` CLI via click.
**Files:** `src/zo/cli.py`, `src/zo/draft.py`
**Priority:** P1

## Build Sequence

```
Phase 0 — Agent Definitions + Claude Code Setup
└── Module 0: Agent Definitions + Claude Code Setup  ✅ COMPLETE
    ├── 20 agent .md files in .claude/agents/
    ├── .claude/settings.json
    └── Validation pending

Gate 0: Human verifies agent definitions and settings

Phase 1 — Scaffolding (parallel, no dependencies)
├── Module 1: Plan Parser
├── Module 2: Target Parser
├── Module 5: Comms Logger
└── Module 8: Setup + Init (setup.sh + zo init)

Gate 1: All 4 modules pass unit tests

Phase 2 — Core Infrastructure (parallel)
├── Module 3: Memory Layer       ← depends on Module 5
└── Module 4: Semantic Index     ← depends on Module 3

Gate 2: Human reviews integration plan

Phase 3 — Integration
└── Module 6: Orchestration Engine (Hybrid) ← depends on Modules 1-5

Gate 3: Orchestration engine passes unit tests with mocked agents

Phase 4 — Hardening (parallel)
├── Module 7: Evolution Engine   ← depends on Modules 3, 5
├── Module 9: CLI Entry Point    ← depends on Module 6
└── Integration test suite       ← depends on all modules

Gate 4: Human reviews integrated system

Phase 5 — Validation
└── End-to-end test project execution

Gate 5: Test project passes 18 oracle verification checks
```

## Milestones

| Week | Milestone | Gate |
|------|-----------|------|
| 0-1 | Agent definitions complete, Claude Code setup validated | Gate 0 |
| 1-2 | Modules 1, 2, 5, 8 complete with unit tests | Gate 1 |
| 2-3 | Memory layer and semantic index complete | Gate 2 |
| 3-4 | Orchestration engine functional with mocked agents | Gate 3 |
| 4-5 | Evolution engine, CLI (incl. zo draft), integration tests | Gate 4 |
| 5-6 | End-to-end test project, hardening, documentation | Gate 5 |

## Delivery

**Target repo:** This IS the target repo (zero-operators builds itself).
**Target branch:** main
**Delivery structure:**
```
src/zo/
├── __init__.py
├── plan.py                  # Module 1
├── target.py                # Module 2
├── memory.py                # Module 3
├── _memory_models.py        # Module 3 (models)
├── _memory_formats.py       # Module 3 (markdown I/O)
├── semantic.py              # Module 4
├── comms.py                 # Module 5
├── orchestrator.py          # Module 6
├── _orchestrator_models.py  # Module 6 (models)
├── _orchestrator_phases.py  # Module 6 (phase definitions)
├── wrapper.py               # Module 6
├── _wrapper_models.py       # Module 6 (models)
├── evolution.py             # Module 7
├── _evolution_models.py     # Module 7 (models)
├── cli.py                   # Module 9
└── draft.py                 # Module 9

.claude/
├── agents/           # Module 0 (17 files) ✅
└── settings.json     # Module 0 ✅

setup.sh              # Module 8
tests/
├── unit/
├── integration/
├── e2e/
└── fixtures/
```

## Environment

**Python version:** 3.11+
**Key dependencies:** pydantic>=2.0, fastembed, rich, click
**Dev dependencies:** ruff, pytest, pytest-cov
**Package manager:** uv
**Linting:** ruff
**Hardware:** No GPU required

## Resolved Decisions

### RD1: Orchestration — Hybrid (Native Claude Code Teams + Python Lifecycle Wrapper)
Use Claude Code's native agent teams for peer-to-peer communication. Python wrapper invokes `claude` CLI, captures lifecycle events, pipes to JSONL comms logger. Agents communicate natively; wrapper observes and logs.

### RD2: Semantic Index — Full Decision Entries with Summary Prefix
One vector per DECISION_LOG entry. Extract 1-line summary from title + outcome at index time. Summary is embedded for matching; full entry injected into context on retrieval. Optimizes for context-window density.

### RD3: `zo draft` in v1 — Yes, with Document Indexing
Takes source document directory, indexes them (project-scoped, persisted), generates compliant plan.md. One agent with plan spec loaded, validates against schema as it generates.

### RD4: Dashboard API — Deferred to v2
No API design in v1. CLI + files only.

### RD5: Agent Definition Contracts — Inline + Shared Reference
Each agent .md has a minimal inline contract example plus pointer to specs/agents.md for full template.

### RD6: Docker — Deferred to v2
uv lockfile + setup.sh for reproducibility.

### RD7: Setup — Both setup.sh + zo init
`setup.sh` for environment bootstrap. `zo init` for project scaffolding. Different concerns, different times.

### RD8: Agent Definitions are Step 0
Written before any Python code. Immediately usable by Claude Code. Define contracts all modules implement against.
