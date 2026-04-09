<div align="center">

<img src="design/banner-dark.svg" alt="Zero Operators — Autonomous AI Systems" width="800"/>

<br/>
<br/>

<img src="design/logo-dark.svg" alt="ZO orbital mark" width="64"/>

<br/>
<br/>

**You input a plan. Agents execute. The oracle verifies.**

<br/>

[![Status](https://img.shields.io/badge/status-validated-F0C040?style=flat-square&labelColor=080808)](#status)
[![Tests](https://img.shields.io/badge/tests-296_passing-F0C040?style=flat-square&labelColor=080808)](#status)
[![Agents](https://img.shields.io/badge/agents-16_defined-F0C040?style=flat-square&labelColor=080808)](#agent-teams)
[![E2E](https://img.shields.io/badge/MNIST-99%25_accuracy-F0C040?style=flat-square&labelColor=080808)](#e2e-validation)

---

</div>

## What is this

Zero Operators (ZO) is an autonomous AI research and engineering team. You give it a project — a GitHub repo, some source documents, and success criteria — and it builds, trains, validates, and delivers. A coordinated team of AI agents handles the full ML lifecycle: data engineering, model building, oracle validation, code review, testing, and explainability.

You stay in the loop at human checkpoints. ZO remembers everything across sessions. It learns from its mistakes. And the delivery repo stays clean — zero ZO artifacts leak into your project.

---

## User Workflow

```
  You                          ZO                           Delivery Repo
  ───                          ──                           ─────────────

  1. Provide source docs ────► zo draft ──► plan.md
                                              │
  2. Review & edit plan  ◄─────────────────────┘
                                              │
  3. Launch ─────────────────► zo build plans/project.md
                                              │
                               ┌──────────────┘
                               │
                          Orchestrator
                          decomposes plan
                          into phases
                               │
                               ▼
                    ┌─── Agent Team (tmux) ───┐
                    │                         │
                    │  Data Engineer           │
                    │  Model Builder           │ ──────► src/
                    │  Oracle / QA             │ ──────► models/
                    │  Code Reviewer           │ ──────► reports/
                    │  Test Engineer            │ ──────► tests/
                    │                         │
                    │  Peer-to-peer comms      │
                    │  via SendMessage          │
                    └─────────┬───────────────┘
                              │
  4. Review at gates ◄────────┤  (supervised mode)
     Approve / iterate        │
                              │
  5. Session ends ───► STATE.md + DECISION_LOG + PRIORS
                              │
  6. Resume anytime ─► zo continue project
                              │
  7. Delivery ◄───────────────┘  Clean repo, zero ZO artifacts
```

**Step by step:**

1. **Feed source docs** — `zo draft source-docs/ --project my-project` indexes your documents and generates a `plan.md` with all 8 required sections (objective, oracle, workflow, data sources, domain priors, agents, constraints)
2. **Review the plan** — edit `plans/my-project.md` to sharpen the objective, set oracle thresholds, add domain knowledge the agent missed
3. **Launch** — `zo build plans/my-project.md` spawns the agent team. You watch them work in tmux split panes
4. **Approve at gates** — in supervised mode (default), every phase transition pauses for your review. You see a summary of what was done, key metrics, and the recommended next action
5. **Session continuity** — stop anytime. `zo continue my-project` reads STATE.md and picks up exactly where you left off. Semantic search over past decisions provides context
6. **Self-evolution** — when something fails, ZO runs a post-mortem: fix the symptom, update the rule that allowed it, verify the rule prevents recurrence
7. **Clean delivery** — your project repo contains only code, models, reports, and tests. Zero ZO infrastructure

---

## Operating Modes

### `zo build` — Start from scratch

```bash
zo build plans/my-project.md --gate-mode supervised
```

Parses the plan, initializes project memory, decomposes into phases, and launches the agent team. This is how you start a new project.

### `zo continue` — Resume where you left off

```bash
zo continue my-project
```

Reads `STATE.md` from the last session, queries the semantic index for relevant past decisions, and resumes from the exact phase and subtask where work stopped. No context is lost.

### `zo maintain` — Apply updates

```bash
zo maintain my-project
```

Detects changes to `plan.md` since the last session. Computes a diff, identifies which phases need re-execution, and presents the replan for your approval before resuming.

### `zo draft` — Generate a plan from documents

```bash
zo draft source-docs/ --project my-project
```

Indexes all source documents (PDFs, CSVs, READMEs), then generates a compliant `plan.md` following the 8-section schema. You review and edit before launching.

### `zo init` — Scaffold a new project

```bash
zo init my-project
```

Creates the project directory structure:
```
memory/my-project/STATE.md
memory/my-project/DECISION_LOG.md
memory/my-project/PRIORS.md
memory/my-project/sessions/
targets/my-project.target.md    (template)
plans/my-project.md             (template with all 8 sections)
```

### `zo status` — Check current state

```bash
zo status my-project
```

Displays the current `STATE.md`: active phase, blockers, next steps, agent statuses.

---

## Gate Modes

Control how much autonomy ZO has at phase transitions.

| Mode | Flag | Behaviour |
|------|------|-----------|
| **Supervised** (default) | `--gate-mode supervised` | Every phase gate pauses for your approval. You review metrics, decisions, and artifacts before proceeding. |
| **Auto** | `--gate-mode auto` | Only gates marked `BLOCKING` in the plan require approval. Automated gates proceed if all subtasks pass. |
| **Full Auto** | `--gate-mode full-auto` | No human gates. ZO runs start to finish autonomously. Use when you trust the pipeline. |

You can switch modes at runtime — start supervised, watch the first few phases, then switch to auto once you trust the flow.

---

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/SamPlvs/zero-operators.git
cd zero-operators
./setup.sh                    # validates Python 3.11+, uv, Claude CLI, agent teams

# 2. Install
uv sync --extra dev

# 3. Initialize a project
zo init my-project

# 4. Option A: Draft a plan from source documents
zo draft ~/path/to/source-docs/ --project my-project

# 4. Option B: Write a plan manually
#    Edit plans/my-project.md — fill in all 8 sections

# 5. Launch
zo build plans/my-project.md

# 6. Watch agents work in tmux split panes
# 7. Approve at human checkpoints
# 8. Resume if interrupted
zo continue my-project

# 9. Check status anytime
zo status my-project
```

---

## ML Workflow

ZO follows a structured pipeline defined in `specs/workflow.md`. Three modes available:

### Classical ML (default)

```
Phase 1: Data Review & Pipeline     → Gate (automated)
  Data audit, hygiene, EDA, versioning, DataLoader

Phase 2: Feature Engineering        → Gate (BLOCKING — human approves features)
  Feature creation, statistical filtering, multicollinearity pruning

Phase 3: Model Design               → Gate (automated)
  Architecture selection, loss design, training strategy, oracle setup

Phase 4: Training & Iteration       → Gate (automated — oracle loop)
  Baseline training, iteration protocol, cross-validation, ensemble

Phase 5: Analysis & Validation      → Gate (BLOCKING — human approves model)
  SHAP/explainability, domain consistency, error analysis, significance testing

Phase 6: Packaging                  → Gate (automated)
  Inference pipeline, model card, validation report, drift detection, test suite
```

### Deep Learning

Same phases but: Phase 2 focuses on input representation and transfer learning. Phase 3 adds architecture search and gradient diagnostics. Phase 4 adds training diagnostics.

### Research

Adds **Phase 0: Literature Review** (prior art survey, baseline definition). Phase 5 expands with ablation studies and reproducibility verification. Phase 6 adds paper-ready figures.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Python CLI                                        │
│                                                             │
│  zo build ──► plan.py ──► orchestrator.py ──► wrapper.py    │
│               parse &      decompose phases    launch ONE   │
│               validate     build lead prompt   claude session│
│               plan.md      generate contracts               │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Claude Code Session                               │
│                                                             │
│  Lead Orchestrator (native agent team)                      │
│  ├── TeamCreate("project")                                  │
│  ├── Agent(name="data-engineer", team_name="project")       │
│  ├── Agent(name="model-builder", team_name="project")       │
│  ├── Agent(name="oracle-qa", team_name="project")           │
│  └── Agents communicate peer-to-peer via SendMessage        │
│                                                             │
│  The Lead knows all 16 agents and creates new ones on the   │
│  fly if the project needs expertise not in the roster.      │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Persistence                                       │
│                                                             │
│  memory.py ──► STATE.md        (session checkpoint)         │
│                DECISION_LOG.md (audit trail)                │
│                PRIORS.md       (domain knowledge)           │
│  semantic.py ► index.db        (decision search)            │
│  comms.py ───► YYYY-MM-DD.jsonl (structured event logs)     │
│  evolution.py ► post-mortem → rule updates → verification   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Delivery Repo (clean)                             │
│                                                             │
│  src/ models/ reports/ tests/ — zero ZO artifacts           │
│  Isolation enforced via target.py zo_only_paths blocklist   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent Teams

**Project Delivery Team** — 10 agents that execute ML/research projects:

| Agent | Model | When Active | What They Do |
|-------|-------|-------------|-------------|
| Lead Orchestrator | Opus | Always | Creates team, decomposes phases, manages gates, coordinates |
| Data Engineer | Sonnet | Phases 1-2 | Data pipeline, cleaning, EDA, DataLoaders |
| Model Builder | Opus | Phases 3-5 | Architecture selection, training, iteration |
| Oracle / QA | Sonnet | Phases 3-5 | Hard metric evaluation, pass/fail gating |
| Code Reviewer | Sonnet | All phases | Code quality, PEP8, security, conventions |
| Test Engineer | Sonnet | All phases | Unit, integration, regression tests |
| XAI Agent | Sonnet | Phase 5 | SHAP, feature importance, explainability |
| Domain Evaluator | Opus | Phase 5 | Domain validation, plausibility checks |
| ML Engineer | Sonnet | Phases 4-6 | Inference optimization, experiment tracking |
| Infra Engineer | Haiku | Phases 1, 6 | Environment setup, packaging, deployment |

**Dynamic agents** — if your project needs expertise not covered (NLP, time-series, security), the Lead Orchestrator creates a new agent definition on the fly.

---

## Self-Evolution

When something fails, ZO doesn't just fix the symptom:

```
Error detected
    │
    ▼
Step 1: Document failure ──► DECISION_LOG
Step 2: Root cause analysis ──► missing_rule? incomplete_rule? regression?
Step 3: Fix the immediate problem
Step 4: Update the rule ──► PRIORS.md / spec file / agent definition
Step 5: Verify the update would have caught the original failure
```

Over time, `PRIORS.md` accumulates domain knowledge. The same mistake never happens twice.

---

## Repository Structure

```
zero-operators/
├── src/zo/                     # Platform code (10 modules)
│   ├── cli.py                  # CLI: zo build/continue/maintain/init/status/draft
│   ├── draft.py                # Agentic plan generation from source docs
│   ├── plan.py                 # Plan parser and validator (8 sections)
│   ├── target.py               # Target file parser, isolation enforcer
│   ├── orchestrator.py         # Phase decomposition, gate management, lead prompt
│   ├── wrapper.py              # Claude CLI launcher + team observer
│   ├── memory.py               # STATE.md, DECISION_LOG, PRIORS, sessions
│   ├── semantic.py             # fastembed + SQLite semantic search
│   ├── comms.py                # JSONL event logger (5 event types)
│   └── evolution.py            # Self-evolving post-mortem protocol
├── .claude/agents/             # 16 agent definitions
├── specs/                      # 8 specification documents
├── plans/                      # Project plan files
├── memory/                     # Per-project state (STATE.md, DECISION_LOG, PRIORS)
├── logs/                       # JSONL audit trails
├── targets/                    # Delivery repo configuration
├── tests/                      # 296 tests (unit + integration)
├── setup.sh                    # Environment validation (11 checks)
└── pyproject.toml              # Python package config
```

---

## E2E Validation

ZO has been validated end-to-end with an MNIST digit classification project.

**The agent team autonomously:**
- Built a data pipeline with DataLoaders and 32 data tests
- Designed a CNN (2 conv + BN + 2 FC layers)
- Trained to **99.00% test accuracy** (oracle threshold: 95%)
- Produced GradCAM visualizations, ablation study, significance testing
- Delivered 98 passing tests in the clean delivery repo
- Zero ZO artifacts leaked — 4 clean git commits

**Total cost:** ~$11 across all sessions.

```
mnist-delivery/          ← delivery repo (clean)
├── src/
│   ├── model.py         ← CNN architecture
│   ├── train.py         ← training loop
│   ├── inference.py     ← prediction pipeline
│   └── data_loader.py   ← MNIST DataLoader
├── models/best_model.pt ← trained checkpoint (99% accuracy)
├── oracle/eval.py       ← oracle evaluation script
├── xai/gradcam.py       ← GradCAM visualizations
├── experiments/         ← ablation, significance, reproducibility
├── tests/               ← 98 tests passing
└── pyproject.toml
```

---

## Status

**All phases complete. Validated end-to-end.**

| Phase | What | Status |
|-------|------|--------|
| 0 | Agent definitions + Claude Code setup | Done |
| 1 | Plan parser, target parser, comms logger, setup | Done |
| 2 | Memory layer, semantic index | Done |
| 3 | Orchestration engine + lifecycle wrapper | Done |
| 4 | Evolution engine, CLI, integration tests | Done |
| 5 | E2E validation (MNIST: 99% accuracy) | Done |

296 platform tests. 92% coverage. ruff clean.

---

<div align="center">
<br/>

<img src="design/logo-dark.svg" alt="ZO" width="32"/>

<br/>
<br/>

`ZERO OPERATORS` · `v1.0` · `validated` · `99% MNIST accuracy`

<br/>
</div>
