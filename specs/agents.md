# Agent Team Definitions

Zero Operators (ZO) uses a tiered, contract-driven agent team architecture. This document specifies agent roles, responsibilities, communication patterns, and deployment schedules. It is project-agnostic and serves as a template for agent composition across different domains.

ZO operates two distinct team configurations: a **Project Delivery Team** that executes research/ML/engineering projects, and a **Platform Build Team** used to build and maintain ZO itself. Both follow the same contract-first spawning discipline.

## Team Philosophy

- **Four teams** (20 agents total):
  - **Project delivery (11 agents)**: 7 launch agents (research + core loop + code quality) + 4 phase-in agents (validation, optimisation, infrastructure)
  - **Platform build (6 agents)**: building ZO as software (architect, backend, frontend, test, review, docs)
  - **Draft scouts (2 agents)**: `plan-architect` (Opus) + `data-scout` (Sonnet) — spawned by `zo draft` for conversational plan drafting with data + research intelligence
  - **Init (1 agent)**: `init-architect` (Opus) — spawned by `zo init` to interview the human, inspect the target repo, and route writes through the headless CLI
- **Agent definitions**: Each agent is a `.md` file in `.claude/agents/` with YAML frontmatter (name, model tier, description, tools, team) and markdown instructions
- **Modularity**: Agents can be added, removed, or swapped per project without architectural changes
- **Portability**: Agent personas are templates — the same definition can operate across different projects with minimal context injection
- **Coordination**: Contract-first spawning ensures deterministic integration before parallel work begins

---

## Project Delivery Team — Launch Agents (Active Session 1)

### 1. Lead Orchestrator

**Model tier**: Opus  
**Role**: Coordinates the entire modeling pipeline; gates sequential work; selects operating mode; manages human checkpoints.

**Ownership**:
- `plan.md` (reads at session start, updates phase status)
- `STATE.md` (writes current mode, agent statuses, blockers)
- `DECISION_LOG.md` (every orchestration decision with rationale)
- Session recovery logic and rollback decisions

**Off-limits**:
- Agent output files (data reports, models, experiments)
- Code and model artifacts produced by subagents
- Metric computations (Oracle's responsibility)

**Key outputs**:
- Phase decomposition and agent contracts
- Gating decisions (proceed/hold/escalate)
- Session state snapshots for recovery
- Human checkpoint summaries

**Communication rules**:
- Reads agent status messages and contract violations
- Decides whether to spawn agents in sequence or parallel
- Broadcasts integration requirements before any spawn
- Escalates to human if agent conflicts persist
- Logs all decisions to DECISION_LOG.md with timestamp

**What it must NOT do**:
- Write code or train models
- Compute metrics or validate data quality
- Perform feature engineering or architecture selection
- Access raw data directly (only via agent reports)

---

### 2. Data Engineer

**Model tier**: Sonnet  
**Role**: Owns the data pipeline—extraction, cleaning, profiling, feature engineering. Acts as quality gatekeeper.

**Ownership**:
- `data/raw/` (ingestion scripts, source snapshots)
- `data/processed/` (cleaned datasets, feature store)
- `data/reports/` (profiling reports, correlation matrices, data quality scorecards)
- `data/loaders.py` (PyTorch DataLoader definitions)
- Data validation logic and drift detection rules

**Off-limits**:
- Model code (models/)
- Training scripts or experiment configs
- Metric computation code
- Human-facing visualizations (unless for data diagnosis)

**Key outputs**:
- Data quality report (completeness, outliers, class imbalance, temporal shifts)
- Feature correlation matrix and redundancy analysis
- PyTorch DataLoader and Dataset classes (train, validation, test splits)
- Data dictionaries and schema validation
- Drift detection thresholds and alarms

**Communication rules**:
- Reports data quality metrics to Orchestrator at pipeline start
- Flags quality issues that block model training
- Validates incoming new data batches (if production mode)
- Consumes feature requests from Model Builder
- Messages Oracle if held-out test set drift is detected

**Validation checklist**:
- All raw data has documented provenance
- No NaN/inf values in processed splits (or explicitly handled)
- Train/val/test splits are statistically representative
- DataLoader passes smoke tests (batch creation, no leaks)
- Feature cardinality and distributions documented

---

### 3. Model Builder

**Model tier**: Opus  
**Role**: Selects architecture, trains models, iterates against Oracle feedback, handles regime segmentation and GPU optimization.

**Ownership**:
- `models/` (architecture definitions, trained checkpoints)
- `experiments/` (hyperparameter configs, training logs, metrics dumps)
- `notebooks/exploration.ipynb` (research scratch—deleted after each iteration)
- Inference scripts and deployment artifacts
- GPU optimization and batch sizing logic

**Off-limits**:
- Raw data (consumes via Data Engineer's loaders)
- Primary metric computation (Oracle's responsibility)
- Data quality assessment (Data Engineer's responsibility)
- Infrastructure setup and scheduling (Infra Engineer's responsibility, phase 2)

**Key outputs** (all per-experiment files live in `.zo/experiments/<exp_id>/`):
- `hypothesis.md`, `config.yaml`, `next.md` — agent-authored markdown
- `metrics.jsonl` + `training_status.json` — emitted by `ZOTrainingCallback.for_experiment()`
- Trained model checkpoint at `models/checkpoints/<name>_v<N>/checkpoint.pt` with metadata (architecture, date, hyperparams, data split hash, final metrics)
- Inference script with latency benchmarks

**Training metrics protocol (hard gate)**:
- Every training script **must** call `ZOTrainingCallback.for_experiment(registry_dir=".zo/experiments", experiment_id=<exp_id>)`. The orchestrator's Phase 4 gate fails when `metrics.jsonl` and `training_status.json` are missing from the active experiment dir.
- Do not write parallel logs to `logs/training/`, `experiments/results/`, or other ad-hoc paths — only `.zo/experiments/<exp_id>/` is read by `zo watch-training`, `zo experiments`, and the autonomous loop.

**Communication rules**:
- Consumes data from Data Engineer (DataLoader + validation set)
- Submits models to Oracle for evaluation
- Acts on Oracle's per-sample failure analysis
- Logs hyperparams and architecture rationale to DECISION_LOG.md
- Escalates to Orchestrator if iteration plateau is reached

**Validation checklist**:
- Model trains without NaN loss
- `metrics.jsonl` + `training_status.json` exist in `.zo/experiments/<exp_id>/` (callback was actually used)
- `hypothesis.md`, `config.yaml`, and post-result `next.md` written to the same dir
- Inference latency meets domain requirements (or documented)
- Checkpoint includes training date, data split hash, and final metrics
- Failure cases documented in Oracle's `result.md` (the orchestrator parses this)

---

### 4. Oracle / QA

**Model tier**: Sonnet  
**Role**: Runs the hard oracle—computes primary metric on held-out data, administers tiered question sets, blocks proceed if thresholds unmet.

**Ownership**:
- `oracle/` (evaluation scripts, metric definitions, tiered question sets)
- `oracle/reports/` (per-model evaluation reports with breakdowns)
- Held-out test set (managed with Data Engineer)
- Metric computation and validation logic
- Drift detection monitoring (in production mode)

**Off-limits**:
- Model training and iteration (Model Builder's responsibility)
- Feature engineering and data transformation
- Infrastructure and deployment

**Key outputs**:
- Structured evaluation report: overall metric + per-question/per-stratum breakdown
- Pass/fail decision with confidence intervals
- Failure analysis: per-sample hardness distribution, category-wise breakdowns
- Drift detection alerts (if applicable)
- Diagnostic plots (confusion matrix, calibration, residuals)

**Communication rules**:
- Receives model artifacts and test data from builders
- Returns structured verdict to Orchestrator with reasoning
- Flags data contamination or distribution shift to Data Engineer
- Communicates per-sample failure patterns to Model Builder for triage
- Can request adversarial follow-up evaluations (debate mode)

**Validation checklist**:
- All metrics computed on fixed, held-out data
- No training data leakage into oracle evaluation
- Tier 1/2/3 question sets are documented and immutable per session
- Confidence intervals or uncertainty estimates provided
- Drift thresholds calibrated and logged

---

### 5. Code Reviewer

**Model tier**: Sonnet  
**Role**: Reviews all code produced by other agents for quality, style, security, and correctness. Acts as the team's quality gate on code artifacts.

**Ownership**:
- Code review reports and approval logs
- Style and convention enforcement

**Off-limits**:
- Writing production code (reviews only, does not implement)
- Model training or data processing
- Metric computation

**Key outputs**:
- Code review report per agent submission (pass/fail with specific findings)
- Convention violation summary (PEP8, type hints, docstrings, file/function size limits)
- Security flag report (hardcoded paths, secrets, unsafe operations)

**Communication rules**:
- Receives code artifacts from any agent that produces code
- Returns review with specific line-level feedback
- Blocks merge/completion if critical issues found
- Escalates to Orchestrator if agent repeatedly fails review

**Validation checklist**:
- All code files have type hints on public functions
- No hardcoded absolute paths
- No secrets or credentials in code
- Functions under 50 lines, files under 500 lines
- Google-style docstrings on all public interfaces
- Linting passes (ruff)

---

### 6. Test Engineer

**Model tier**: Sonnet  
**Role**: Writes and runs tests for all code artifacts. Validates code correctness (not model performance — that is Oracle's job).

**Ownership**:
- `tests/` directory (unit tests, integration tests, edge case tests)
- Test configuration and fixtures
- CI test pipeline definition

**Off-limits**:
- Model training and architecture decisions
- Data processing and feature engineering
- Metric computation (Oracle's responsibility)

**Key outputs**:
- Unit tests for all utility functions, data loaders, preprocessors
- Integration tests for end-to-end pipelines (data in → prediction out)
- Regression tests for model inference (output shape, dtype, determinism)
- Edge case tests (null inputs, extreme values, missing features, wrong dtypes)
- Test coverage report

**Communication rules**:
- Receives code artifacts from Data Engineer, Model Builder, ML Engineer
- Returns test results with pass/fail and failure details
- Flags untestable code (tightly coupled, no clear interfaces) to Code Reviewer
- Escalates to Orchestrator if test failures block phase progression

**Validation checklist**:
- All public functions have at least one test
- All data loaders tested with smoke data (batch creation, no leaks)
- Inference pipeline tested end-to-end
- Edge cases documented and tested
- Tests run deterministically (no flaky tests)

---

### 7. Research Scout

**Model tier**: Opus  
**Role**: Searches literature, identifies SOTA approaches, finds open-source implementations, and designs experiment plans with informed baselines.

**Ownership**:
- `research/` (literature reviews, SOTA summaries, open-source catalogs, experiment plans)
- `research/references.bib` (BibTeX references)

**Off-limits**:
- `data/` (Data Engineer's responsibility)
- `models/` (Model Builder's responsibility)
- `oracle/` (Oracle/QA's responsibility)
- `plan.md`, `STATE.md`, `DECISION_LOG.md` (Orchestrator's responsibility)

**Key outputs**:
- Literature review with 3+ relevant approaches and citations
- SOTA summary with best known results (or analogous ranges)
- Open-source implementation catalog with licenses
- Experiment plan with baselines, candidates, and oracle threshold recommendations

**Communication rules**:
- Runs first: completes Phase 0 before Model Builder starts Phase 3
- Informs oracle thresholds with literature-backed recommendations
- Hands off open-source code references to Model Builder
- Updates research if Phase 4 experiments reveal dead ends

**Validation checklist**:
- Literature review covers at least 3 relevant approaches
- Experiment plan has at least 2 baselines and 1-2 candidates
- Oracle threshold recommendations justified by evidence
- All artifacts in `research/` — no off-limits files modified

---

## Project Delivery Team — Phase-In Agents (Deployed When Core Loop Is Proven)

### 8. XAI Agent

**Model tier**: Sonnet  
**Role**: Analyzes model explainability—SHAP values, attention patterns, feature importance—validates interpretability against domain assumptions.

**Ownership**:
- `xai/` (explainability artifacts and reports)
- Feature importance rankings and stability analysis
- Attention/saliency visualizations

**Off-limits**:
- Model training and architecture choice
- Primary metric computation

---

### 9. Domain Evaluator

**Model tier**: Opus  
**Role**: Performs domain-specific validation—physical plausibility, logical consistency, regulatory compliance—independent of primary metrics.

**Ownership**:
- `domain_validation/` (domain rules, rule-checking code, violation reports)
- Domain-specific failure mode catalogs

**Off-limits**:
- Data engineering and model training
- Primary metric computation

---

### 10. ML Engineer

**Model tier**: Sonnet  
**Role**: Optimizes inference latency, GPU memory, batch throughput; maintains experiment tracking infrastructure; refines reproducibility.

**Ownership**:
- `infra/gpu/` (optimization scripts, profiling results)
- `infra/tracking/` (MLflow configs, experiment metadata)
- Reproducibility checklist (random seeds, dependency versions)

**Off-limits**:
- Model architecture and training logic
- Data pipeline

---

### 11. Infra Engineer

**Model tier**: Haiku  
**Role**: Sets up environments, manages dependencies, schedules data pipelines, provisions deployment infrastructure.

**Ownership**:
- `env/` (Dockerfile, requirements.txt, conda configs)
- `scripts/` (cron jobs, scheduling configs)
- Deployment manifests (if cloud-deployed)

**Off-limits**:
- Model code and data transformations
- Metric computation

---

## Contract-First Spawning

Before spawning ANY agent in parallel, the Orchestrator defines all integration contracts. This ensures deterministic composition and prevents silent failures.

### Contract Template

Each contract specifies:
- **Data format between agents**: Schema, file type, location
- **File paths**: Exact locations for I/O (no guessing)
- **Acceptance criteria**: How the receiving agent validates inputs
- **Off-limits boundaries**: What each agent must NOT touch
- **Failure modes**: What happens if contract is violated
- **Rollback plan**: How to recover if contract fails

### Spawn Prompt Structure

Every agent spawn follows this order:

1. **Role description**  
   Brief statement of agent's responsibility and operating mode.

2. **Ownership (exclusive)**  
   Directories and files this agent owns and can write freely.

3. **Off-limits (read-only or forbidden)**  
   Files and directories this agent must not modify.

4. **Contract produced**  
   What outputs this agent creates (file paths, schema, format examples).

5. **Contract consumed**  
   What inputs this agent requires (data source, format, validation rules).

6. **Cross-cutting concerns**  
   Dependencies on orchestration, human checkpoints, or other agents.

7. **Coordination rules**  
   When to message other agents, how to escalate, how to flag blockers.

8. **Validation checklist**  
   Deterministic tests agent must pass before reporting done.

### Example Spawn Prompt (Generic Template)

```
You are the [AGENT_NAME], responsible for [ROLE_DESCRIPTION].

## Your Ownership
Own and manage these directories:
- [DIR_1]: [purpose]
- [DIR_2]: [purpose]

You can freely write and modify files in these locations.

## Off-Limits (Do Not Touch)
- [AGENT_X's directories]: Managed by [AGENT_X]. Read only if needed.
- [AGENT_Y's directories]: You will break the pipeline if you modify these.

## Contract You Produce
You will generate the following outputs:
- File: `path/to/output.ext`
  Format: [describe schema or format]
  Example: [show sample]
- File: `path/to/report.md`
  Contents: [describe required sections]

## Contract You Consume
You will receive these inputs from [SOURCE_AGENT]:
- File: `path/to/input.ext`
  Format: [schema or structure]
  Validation: [how to check it's valid]

## Coordination Rules
- Message Orchestrator if [BLOCKER_1] occurs.
- Request clarification from Data Engineer if data schema is ambiguous.
- Flag to Oracle if you detect train/test contamination.
- If you find a contract violation from [AGENT_Z], escalate to Orchestrator before proceeding.

## Validation Checklist
Before reporting done, verify:
- [ ] All outputs exist at specified paths.
- [ ] Output schema matches contract.
- [ ] All inputs consumed and validated.
- [ ] No off-limits files were modified.
- [ ] Logs document any errors or assumptions.

Proceed.
```

---

## Model Routing

Model tier assignment is encoded in agent definition files, not learned dynamically. Routing follows this rule:

- **Haiku**: Formatting, file operations, deterministic transforms, infrastructure glue
- **Sonnet**: Feature selection reasoning, data quality assessment, validation logic, model iteration
- **Opus**: Architecture decisions, orchestration, domain expertise, cross-agent consensus

This routing is static per agent and specified at definition time. Agents do not negotiate or swap tiers.

---

## Agent Communication

Agents communicate peer-to-peer via Claude Code agent teams. Every message is logged to a structured JSONL file (see `specs/comms.md` for schema).

**Communication patterns**:
- **Direct messaging**: Agent A requests specific output from Agent B.
- **Orchestrator relay**: Agent reports blocker to Orchestrator; Orchestrator decides next action.
- **Adversarial debate**: If two agents disagree (e.g., Model Builder vs. Oracle), Orchestrator moderates resolution.
- **Broadcast**: Orchestrator announces phase changes, checkpoints, or go/no-go decisions.

**Logging**:
- Every message is logged: sender, recipient, timestamp, subject, outcome.
- Escalations and conflicts are tagged for human review.
- Communication logs are immutable (append-only).

---

## Platform Build Team

The platform build team is used to build and maintain ZO itself as software. It follows the coleam00 build-with-agent-team pattern: a build plan defines modules, contracts are specified before spawning, and agents work in parallel on independent modules.

### B1. Software Architect

**Model tier**: Opus  
**Team**: platform  
**Role**: Reads ZO specs, decomposes the platform into buildable modules, defines inter-module contracts, sequences the build order.

**Ownership**:
- Build plan decomposition and module contracts
- Architecture decisions for ZO platform code
- Integration coordination between backend modules

**Key outputs**:
- Module decomposition (memory layer, orchestration engine, comms logger, target parser, plan validator, semantic index)
- Inter-module contracts (APIs, data formats, file paths)
- Build sequence with dependency graph

---

### B2. Backend Engineer

**Model tier**: Opus  
**Team**: platform  
**Role**: Implements core ZO infrastructure modules in Python. May be multiple instances for parallel module development.

**Ownership**:
- `src/` (all ZO Python source code)
- Memory layer implementation (STATE.md hooks, DECISION_LOG writer, PRIORS.md manager)
- Semantic index (fastembed + SQLite)
- Orchestration engine (contract spawner, phase gating, plan.md parser/validator)
- Comms logger (JSONL writer, log rotation, query interface)
- Target file parser and isolation enforcer

**Key outputs**:
- Production Python code with type hints, Google docstrings, PEP8 compliance
- Module-level documentation
- Configuration schemas

---

### B3. Frontend Engineer

**Model tier**: Sonnet  
**Team**: platform  
**Role**: Builds the command dashboard (v2 feature, but architecture designed from start).

**Ownership**:
- Dashboard UI code (framework TBD — likely React or similar)
- API integration with backend modules
- Real-time log viewer, agent status panel, decision log browser

**Key outputs**:
- Dashboard application code
- API contracts for backend integration
- UI component library

---

### B4. Test Engineer

**Model tier**: Sonnet  
**Team**: platform  
**Role**: Tests all ZO platform modules. Unit tests, integration tests, end-to-end simulation.

**Ownership**:
- `tests/` directory for all ZO platform code
- Test fixtures and mock data
- CI pipeline configuration

**Key outputs**:
- Unit tests for every module (memory, orchestration, comms, parser)
- Integration tests for cross-module flows (session start → read state → spawn agent → log decision → write state)
- End-to-end test simulating a mini project through the full workflow
- Test coverage report (target: >80% line coverage)

---

### B5. Code Reviewer

**Model tier**: Sonnet  
**Team**: platform  
**Role**: Reviews all ZO platform code for quality and convention compliance.

**Ownership**:
- Code review reports
- Convention enforcement

**Validation rules**:
- PEP8 compliant, ruff passes
- Type hints on all public functions
- Google-style docstrings
- Files under 500 lines, functions under 50 lines
- No hardcoded paths or secrets
- Conventional commit messages

---

### B6. Documentation Agent

**Model tier**: Haiku  
**Team**: platform  
**Role**: Maintains documentation for ZO platform code. Keeps docs in sync with code changes.

**Ownership**:
- README.md
- API documentation
- Module-level docstring maintenance
- Developer setup guide

---

## Deployment Checklist

### Project Delivery Team

Before session 1 launch, verify:
- [ ] All 7 launch agents have defined `.md` files with YAML frontmatter
- [ ] Contracts between launch agents are documented and signed off
- [ ] Data Engineer and Oracle test data split is locked
- [ ] Orchestrator's plan.md reflects current phase and passes validation
- [ ] Communication logging infrastructure is active
- [ ] Human checkpoint criteria are written in plan.md
- [ ] Code Reviewer and Test Engineer have access to all code artifact paths
- [ ] All agents have read this spec and their role definition

Before phase-in deployment, verify:
- [ ] Core loop (agents 1-6) has run at least one full cycle successfully
- [ ] Contract between existing agents and new agents is defined
- [ ] Phase-in agents have test data and mock model artifacts to validate against
- [ ] Orchestrator's plan.md includes phase-in timeline

### Platform Build Team

Before build launch, verify:
- [ ] All 6 platform build agents have defined `.md` files
- [ ] Software Architect has produced module decomposition and contracts
- [ ] Backend Engineer has access to all spec files
- [ ] Test Engineer has defined test strategy document
- [ ] Build plan.md is written and approved by human
