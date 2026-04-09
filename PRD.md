# Zero Operators: Product Requirements Document

## Overview

Zero Operators (ZO) is an autonomous AI research and engineering team system. A human inputs a plan describing what should be built; a coordinated team of AI agents executes the work with minimal further intervention. The system operates in three modes: **Build** (from scratch), **Continue** (pick up where left off), and **Maintain** (update with new instructions). 

Zero Operators is not a coding assistant. It is a digital research and engineering team that happens to express itself in code, mathematical models, reports, and data artifacts. The human is the research director; the plan is the only communication medium.

### How the Human Experiences ZO

The human writes (or approves an agent-drafted) `plan.md`, then launches ZO. From there:

1. **Plan approval** — the human reviews and approves the plan (30-60 min)
2. **Autonomous work** — agents execute Phase 1 (data review) and Phase 2 (feature engineering) without human involvement
3. **Gate 2 checkpoint** — the human reviews the feature list with a domain expert (15-30 min)
4. **Autonomous work** — agents design, train, and iterate on models autonomously
5. **Human wakeup** (if triggered) — if the oracle threshold isn't met, the human decides next steps (10-15 min)
6. **Gate 4 checkpoint** — the human reviews the full analysis package: performance, explainability, ablations, significance (30-60 min)
7. **Delivery** — agents package everything into a clean delivery repo

The human is involved at plan approval and two blocking gates. Everything else is autonomous. The human can also edit `plan.md` at any time to change direction; agents detect the delta and replan.

### Agentic Plan Drafting

The human does not need to write `plan.md` from scratch. ZO includes a plan drafting capability: an agent reads the plan.md schema (`specs/plan.md`), ingests project source documents (scopes of work, domain documentation, data dictionaries), and drafts a compliant plan.md. The human reviews and approves the draft — never writes blind.

---

## 1. What is Zero Operators

### Core Concept

A human writes a `plan.md` file describing research objectives, success criteria, constraints, and milestones. The Zero Operators system reads this plan, decomposes it into executable contracts, spawns a team of AI agents, and orchestrates their work toward the defined goal. The human can edit the plan at any time; agents pick up the delta and continue.

### Operating Modes

**Build Mode**: Initialize from a plan.md, create foundational artifacts (data preparation, architecture sketches, initial models), and iterate.

**Continue Mode**: Restore state from previous sessions, load decision logs and memory, and resume from the last gate/checkpoint.

**Maintain Mode**: Accept new instructions in plan.md, replan current work, and execute updated directives without losing prior progress.

### The Human-Agent Contract

- **Human input**: A well-formed plan.md with objectives, success metrics, constraints, and milestones.
- **Agent output**: Versioned code, trained models, reports, DECISION_LOG audit trails, and a final delivery repository containing zero ZO infrastructure.
- **Checkpoints**: Human approves the plan, then approves passage through major gates (e.g., after feature selection, before final validation).
- **Iteration**: Agents improve autonomously within each phase; humans guide phase transitions.

---

## 2. Core Thesis

Zero Operators assembles insights from four sources that have not previously been combined:

### From Andrej Karpathy's AutoResearch
The `plan.md` file is the human's sole lever of control. The system enforces *hard oracle discipline*: every claim must be verified against a concrete, measurable criterion. Autonomy scales through rigorous specification, not natural language ambiguity.

### From Ruflo's Research Infrastructure Concepts
Three-tier model routing based on task complexity, session hooks for maintaining agent memory across resumable work, and semantic memory indexed over past decisions and rule updates. The system learns from its own mistakes.

### From coleam00's Agent Team Methodology
Contract-first spawning: all interfaces, inputs, outputs, and success criteria are defined before agents are spun up in parallel. Rich spawn prompts encode domain knowledge, precedent, and constraints. PRP (Problem, Requirements, Precedent) structure in every agent briefing.

### From Claude Code Native Capabilities
Peer-to-peer agent comms via session context, built-in agent teams, markdown-based skill and agent definitions, and out-of-the-box JSONL logging for audit trails.

---

## 3. Four Core Problems the Architecture Solves

### 1. What the Team Knows: Context Engineering

Agents need access to domain knowledge, past decisions, and project specifications without balloning context windows.

**Solution**: 
- `CLAUDE.md` serves as a modular table of contents, referencing spec files in subdirectories.
- Spec files live in `specs/` (agents.md, workflow.md, oracle.md, memory.md, comms.md, evolution.md).
- Agents load only what they need for their task, reducing context bloat.
- Domain-specific priors (e.g., common pitfalls, platform constraints) are encoded once and reused.
- The orchestrator maintains a context budget and enforces lean spec design.

### 2. How It Verifies Work: Oracle Framework

Autonomous agents without measurable criteria become hallucinating cost centers. 

**Solution**:
- Every project must define a **hard oracle**: a verifiable, reproducible metric (test accuracy, inference latency, data drift below threshold, artifact file size, etc.).
- Tiered success criteria: **must-pass** (blockers), **should-pass** (milestones), **could-pass** (stretch goals).
- Agents iterate until the oracle passes at the must-pass tier, or the budget exhausts.
- The oracle itself is defined in `plan.md` and validated by `specs/oracle.md`; if the oracle is wrong, the human updates plan.md and agents re-run.
- No deliverable is deemed complete until the oracle confirms it.

### 3. How It Remembers: Memory Layer

Without persistent memory, agents re-solve problems, forget constraints, and make the same mistakes across sessions.

**Solution**:
- `STATE.md` records current phase, last checkpoint, agent roles, and data lineage.
- `DECISION_LOG.md` is an append-only audit trail: every decision, every agent reasoning, every oracle result.
- Domain-specific `PRIORS.md` encodes rules, precedents, and lessons learned from prior sessions.
- Semantic search via fastembed + SQLite indexes the decision log; agents query "what did we try last time for feature selection?" and retrieve relevant context.
- **Context Reset Protocol**: Planning → Building = fresh conversation. Previous phase outputs become file artifacts; only those artifacts (plus STATE.md, DECISION_LOG.md, PRIORS.md) are loaded as context. This prevents context pollution and keeps token budgets predictable.

### 4. How It Plans and Executes: Orchestrator

A human-editable plan is worthless without a system to execute it.

**Solution**:
- The **Lead Orchestrator** agent reads `plan.md`, decomposes it into phases, and issues execution contracts to other agents.
- Each contract specifies inputs, outputs, success criteria, time budget, and precedent from DECISION_LOG.
- Sequential phases are gated: the Oracle validates one phase before the next begins.
- Parallel work (e.g., multiple model variants) spawns after a gate passes.
- The orchestrator re-plans if new instructions arrive in `plan.md` mid-project; the human confirms the revised plan before execution resumes.
- All orchestration decisions are logged to DECISION_LOG for auditability and learning.

---

## 4. Design Principles

**Oracle-First**
No agent operation proceeds without a verifiable metric. If something cannot be measured, it cannot be validated. The oracle is the system's source of truth.

**Contract-First Spawning**
Before spawning parallel agents, define all interfaces, inputs, outputs, and acceptance criteria. This eliminates mid-execution clarifications and surprises. Contracts reference the oracle and prior decisions.

**Memory-Aware**
Every session reads state at entry, executes work, and writes state at exit. SESSION.md, DECISION_LOG.md, and semantic indices are not nice-to-haves; they are required infrastructure.

**Self-Evolving**
When agents discover a bug or inefficiency, they fix the immediate issue *and* update the rule or spec that allowed the bug to exist. Post-mortem protocol: after every failure, the system updates `PRIORS.md` or the relevant spec so the same error cannot recur.

**Repo Separation**
The Zero Operators codebase is the surgeon; the delivery repository is the patient. ZO infrastructure (agent configs, memory files, workflow specs) lives in a `.zo/` directory or separate repo. The delivery repo contains only application code, models, and data artifacts. No ZO artefacts leak into production or client deliverables.

**Modular Context**
CLAUDE.md is the index. Spec files are the chapters. Agents download only what they need. Context windows are finite resources managed by design, not luck. Lazy loading of domain priors is preferred; eager loading of critical specs is required.

**Phase-Aware Context Resets**
Planning, building, and maintenance are separate phases with separate conversation contexts. When transitioning from planning to building, the orchestrator closes the planning context and opens a fresh building context, loading only previous phase artifacts. This prevents accumulation of irrelevant reasoning and keeps token costs predictable.

---

## 5. Agent Team Architecture

ZO uses two distinct team configurations: a **Project Delivery Team** that executes research/ML/engineering projects, and a **Platform Build Team** used to build and maintain ZO itself. Both follow the same contract-first spawning discipline.

### Project Delivery Team

The team that executes projects defined in `plan.md`. Composed of research, ML, and software engineering agents.

**Launch agents (v1):**

1. **Lead Orchestrator** (Opus) — Reads plan.md, decomposes into phases, issues contracts, gates work, detects replans. Decides model routing based on task complexity. Owns orchestration DECISION_LOG entries.

2. **Data Engineer** (Sonnet) — Data loading, cleaning, validation, schema design, drift detection. Executes Phase 1 (data review) and supports Phase 2 (feature engineering).

3. **Model Builder** (Opus) — Architecture design, loss function design, hyperparameter search, training orchestration, model evaluation. Handles complex design trade-offs.

4. **Oracle / QA Agent** (Sonnet) — Executes oracle criteria against deliverables. Reports pass/fail with evidence. Runs tiered evaluation and statistical significance tests.

5. **Code Reviewer** (Sonnet) — Reviews all code produced by other agents. Enforces coding conventions, catches hardcoded paths, validates type hints, checks for security issues. Runs after any agent produces code artifacts.

6. **Test Engineer** (Sonnet) — Writes and runs tests for all code artifacts. Unit tests, integration tests, regression tests, edge case tests. Validates that code changes don't break existing functionality. Distinct from Oracle (which validates model performance); Test Engineer validates code correctness.

**Phase-in agents (v1.1):**

7. **XAI Agent** (Sonnet) — Feature importance, model interpretation, explainability analysis. Runs after oracle validation to explain why the model works.

8. **Domain Evaluator** (Opus) — Reviews model outputs for business/domain coherence. Flags edge cases, distributional shift, real-world applicability concerns. Owns domain-specific PRIORS.md updates.

9. **ML Engineer** (Sonnet) — Productionisation, containerisation, inference optimisation, serving setup. Ensures delivery artifacts are deployable.

10. **Infra Engineer** (Haiku) — Compute resource allocation, experiment tracking, artifact storage, logging setup. Minimal reasoning task; suitable for smaller model.

### Platform Build Team

The team used to build ZO itself as a software product. This team is invoked once during initial development and during major platform upgrades. It follows the coleam00 build-with-agent-team pattern.

1. **Software Architect** (Opus) — Reads ZO specs, decomposes the platform into buildable modules, defines inter-module contracts, sequences the build. Equivalent to the Lead in coleam00's pattern.

2. **Backend Engineer** (Sonnet/Opus) — Builds core ZO infrastructure: memory layer (STATE.md hooks, semantic index), orchestration engine (contract spawner, phase gating), comms logger (JSONL writer), target file parser, plan.md validator. May be multiple instances for parallel module development.

3. **Frontend Engineer** (Sonnet) — Builds the command dashboard (v2). Agent team panel, live log, memory state view, decision log viewer, action buttons.

4. **Test Engineer** (Sonnet) — Tests all ZO modules: unit tests for memory layer, integration tests for orchestration flow, end-to-end tests simulating a mini project through the full workflow.

5. **Code Reviewer** (Sonnet) — Reviews all platform code. Enforces ZO's own coding conventions (PEP8, type hints, Google docstrings, files <500 lines, functions <50 lines).

6. **Documentation Agent** (Haiku) — Maintains docstrings, README, API documentation, and keeps docs in sync with code changes.

### Agent Configuration

Agent definitions are `.md` files stored in `.claude/agents/` with YAML frontmatter:

```yaml
---
name: Lead Orchestrator
model: claude-opus-4-6
role: orchestration
tier: launch
team: project
---
```

The `team` field distinguishes project delivery agents from platform build agents. Team composition is modular: a project can enable/disable agents or swap model assignments by editing agent definitions or specifying overrides in `plan.md`.

---

## 6. Workflow Framework

The workflow is encoded as `SKILL.md` (in `.claude/skills/ml-workflow/`) that teaches agents how research/ML/DL jobs are structured. This is the team playbook. See `specs/workflow.md` for full subtask-level detail.

### Workflow Modes

The orchestrator selects the appropriate mode based on `plan.md`:

**Classical ML mode** — All six phases run with emphasis on feature engineering, statistical selection, and model comparison across algorithm families. Default for tabular data projects.

**Deep Learning mode** — Phase 2 shifts from manual feature selection to input representation design (tokenization, normalization, embedding strategy). Phase 3 expands with architecture search, training dynamics (LR scheduling, gradient diagnostics, mixed precision), and optimisation strategy. Phase 4 adds convergence analysis and ensemble exploration.

**Research mode** — Adds Phase 0 (literature review, prior art survey, baseline definition). Phase 5 expands with ablation studies, statistical significance testing, and reproducibility verification. Phase 6 adds paper-ready figures and reproducibility bundles.

### General Pattern

0. **Literature Review** (research mode only): Prior art survey, baseline definition, pretrained model identification.
1. **Data Review**: Audit, hygiene, exclusion filters, alignment, EDA, data versioning, DataLoader implementation with per-modality augmentation.
2. **Feature Engineering & Selection**: Create derived features (lags, rolling stats, interactions) and select via statistical filtering, VIF pruning, and domain validation. For DL: input representation design, transfer learning assessment, augmentation strategy.
3. **Model Design**: Architecture selection (with families per data type), loss function design (custom losses, regularisation, auxiliary objectives), training strategy (optimiser, LR schedule, mixed precision, gradient clipping, checkpointing).
4. **Training & Iteration**: Baseline training, DL-specific diagnostics (gradient flow, LR finder, activation stats), autonomous iteration loop, cross-validation (with time-series-specific methods), ensemble exploration.
5. **Analysis & Validation**: Explainability (SHAP, GradCAM, attention viz), domain consistency, error analysis (per-class breakdown, failure case study, bias detection), ablation studies, statistical significance testing, reproducibility verification.
6. **Packaging**: Inference pipeline (with ONNX/TorchScript export), model card, validation report, drift detection, test suite, research artifacts.

### Execution Model

- **Sequential phases** are separated by gates (oracle validation).
- **Parallel work** spawns after gates pass (e.g., architecture + loss + oracle setup in parallel).
- **Human checkpoints** at Gate 2 (feature/representation approval) and Gate 4 (model approval).
- **Workflow modularity**: Each project customises via `plan.md`; the SKILL.md provides the default.
- All workflow transitions are logged to DECISION_LOG.

---

## 7. v1 Scope

### In Scope

- Autonomous project delivery team (6 launch agents defined and active)
- Three workflow modes (classical ML, deep learning, research) with full DL pipeline
- Memory layer (STATE.md, DECISION_LOG.md, PRIORS.md, semantic indexing)
- Oracle framework (hard metrics, tiered success criteria, statistical significance, validation gating)
- Repository separation (ZO code isolated from delivery repo)
- Contract-first spawning and rich agent briefings
- Plan.md schema with agentic plan drafting capability
- JSONL audit logging of all agent decisions
- Session recovery (interrupt + resume from STATE.md)
- Self-evolving rules (post-mortem protocol, automatic PRIORS.md updates)
- Code review and testing as first-class workflow steps

### Out of Scope (v2 and Beyond)

- Command dashboard (web UI for monitoring, checkpoint approval, plan editing)
- WASM acceleration or compiled optimization paths
- SONA-style self-learning (routing weights trained from past sessions)
- Parallel model arms racing (competing models evaluated simultaneously)
- Persistent Python REPL (agents run code in temporary, isolated sandboxes)
- Background workers (all work runs in-session)
- Visual workflow editor (plan.md editing only, via text)
- Multi-project concurrent operation (one active project per session)
- External app integrations (GitHub, Slack, WhatsApp)

---

## 8. External Connectivity (v2 Design Consideration)

While external integrations are out of scope for v1, the architecture is designed not to block them.

### Integration Points (Future)

**GitHub**: Agents commit code, open PRs, comment on issues, manage branches. Integration point: delivery repo path and branch configuration.

**Slack/WhatsApp**: Agents send human checkpoint notifications, session completion alerts, error notifications, and Pareto-relevant insights. Integration point: webhook URL in config, message templates in specs.

**Cloud Compute**: Agent reserve and monitor compute resources (GPUs, TPUs). Integration point: environment variables, resource quota in `plan.md`.

**Monitoring Systems**: Agents log metrics, traces, and alerts to external platforms. Integration point: logging config in specs.

### v1 Constraint

No direct external integrations in v1. All notifications and checkpoints flow through DECISION_LOG and require human polling or integration bridge (external script watching DECISION_LOG updates).

---

## 9. Success Criteria for v1

The first project (defined in its own `plan.md`) is the validation vehicle for the entire Zero Operators platform.

### Acceptance Criteria

- [ ] The first project's oracle criteria are fully satisfied; delivery repository is production-ready.
- [ ] Delivery repository contains zero ZO infrastructure artefacts (no .zo/ directory, no DECISION_LOG, no PRIORS.md).
- [ ] DECISION_LOG provides complete audit trail: every agent action, every oracle result, every human approval logged.
- [ ] Session recovery works: interrupt mid-project, restore from STATE.md, resume with zero data loss.
- [ ] Self-evolving mechanism triggered at least once: an error occurred, root cause was identified, a rule in PRIORS.md or a spec was updated, and the updated rule prevented recurrence.
- [ ] All 10 project delivery agent definitions written to `.claude/agents/` (6 launch + 4 phase-in).
- [ ] All 6 platform build agent definitions written to `.claude/agents/`.
- [ ] Plan.md edit during execution succeeds: replan is computed, human approves, execution resumes with new objectives integrated.

---

## 10. What Comes Next

### v1.1 (Weeks 5-8)
- Phase in remaining 4 agents (XAI, Domain Evaluator, ML Engineer, Infra Engineer).
- Project-specific feature additions (domain-specific oracles, custom workflow steps, bespoke agent roles).
- Enhanced PRIORS.md templating for vertical-specific best practices.

### v2.0 (Weeks 9-16)
- Command dashboard: web UI for monitoring, approving checkpoints, editing plan.md, viewing DECISION_LOG.
- Self-learning routing: agent model assignments optimized by past project performance (Sonnet vs. Opus for data work).
- Multi-project concurrency: multiple projects in parallel (separate state, decision logs, memory).
- External integrations: GitHub, Slack, basic cloud compute auto-provisioning.
- Refined cost model: per-agent spend tracking, budget enforcement, early termination on runaway costs.

### Scaling Path (Weeks 17+)
- **Second project**: Validates target file swap (point ZO at a different delivery repo, rerun without changing core platform code).
- **Third project**: Template library emerges (recurring domain patterns extracted and reused across projects).
- **Standardization**: Formalize agent definitions, workflow patterns, and oracle templates for common use cases (ML model training, data pipeline, API development, research paper generation).

---

## 11. Key Artifacts

The following files and directories form the Zero Operators infrastructure:

```
zero-operators/
├── CLAUDE.md                     # Modular context index
├── PRD.md                        # Platform requirements
├── specs/                        # Modular specification documents
│   ├── architecture.md
│   ├── agents.md
│   ├── memory.md
│   ├── oracle.md
│   ├── workflow.md
│   ├── comms.md
│   └── evolution.md
├── .claude/
│   ├── agents/                   # Agent persona definitions
│   │   ├── lead-orchestrator.md  # Project delivery team
│   │   ├── data-engineer.md
│   │   ├── model-builder.md
│   │   ├── oracle-qa.md
│   │   ├── code-reviewer.md
│   │   ├── test-engineer.md
│   │   ├── xai-agent.md          # Phase-in agents
│   │   ├── domain-evaluator.md
│   │   ├── ml-engineer.md
│   │   ├── infra-engineer.md
│   │   ├── software-architect.md  # Platform build team
│   │   ├── backend-engineer.md
│   │   ├── frontend-engineer.md
│   │   └── documentation-agent.md
│   ├── skills/                   # Encoded expertise and patterns
│   │   └── ml-workflow/SKILL.md
│   └── settings.json
├── memory/                       # Project-scoped knowledge base
│   └── {project-name}/
│       ├── STATE.md
│       ├── DECISION_LOG.md
│       ├── PRIORS.md
│       └── sessions/
├── logs/                         # Audit and communication trails
│   └── comms/
│       └── {date}.jsonl
└── targets/                      # Delivery repo pointers
    └── {project-name}.target.md
```

The **delivery repository** contains:
```
delivery-repo/
├── src/                      # Application code
├── models/                   # Trained artifacts
├── data/                     # Processed datasets
├── reports/                  # Analysis and findings
└── README.md                 # Deliverable documentation
```

Zero Operators infrastructure stays in the `zero-operators/` repo (with `.claude/` for runtime agent definitions); it does not appear in delivery artifacts.

---

## 12. Conclusion

Zero Operators is a system for scaling autonomous research and engineering work through rigorous specification, oracle-driven validation, persistent memory, and modular execution. It treats the plan as a specification, agents as a team, and the oracle as the source of truth. By combining insights from autoresearch, agent team methodology, and native AI agent capabilities, it bridges the gap between fully manual engineering and fully unsupervised agent wandering.

The first project will validate the architecture. Subsequent projects will refine it and extract reusable patterns. The goal is a system where a human can write a plan, the agents execute it autonomously, and a complete audit trail and production-ready artifact are the result.
