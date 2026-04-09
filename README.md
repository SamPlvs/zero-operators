<div align="center">

```
        ╭──────────╮
      ╭─┤          ├─╮
    ╭─┤  ╭──────╮  ├─╮
    │ │  │  ZO  │  │ │
    ╰─┤  ╰──────╯  ├─╯
      ╰─┤          ├─╯
        ╰──────────╯
```

# ZERO OPERATORS

**Autonomous AI research and engineering team system.**

You input a plan. Agents coordinate to build, continue, or maintain code.

*The human edits the plan; agents execute the plan; the oracle verifies the work.*

---

</div>

## What is this

Zero Operators (ZO) is a digital research and engineering team that happens to express itself in code, models, and reports. A human writes a `plan.md` describing objectives, success criteria, and constraints. ZO reads the plan, spawns a coordinated agent team, and orchestrates their work — autonomously — until the oracle says the work is done.

Three operating modes: **Build** from scratch, **Continue** from where you left off, **Maintain** with new instructions.

## How it works

```
plan.md  ──►  Orchestrator  ──►  Agent Team  ──►  Delivery Repo
                  │                    │
                  ▼                    ▼
             STATE.md            DECISION_LOG
             PRIORS.md           JSONL comms
```

The orchestrator reads the plan, decomposes it into phases, issues contracts to agents, and gates each phase with oracle validation. Agents work autonomously between human checkpoints. Every decision is logged. Every session is recoverable.

## Core principles

**Oracle-first** — no deliverable is complete without a hard, verifiable metric passing.

**Memory-aware** — STATE.md at session start, session summary at end. Semantic search over past decisions. Pick up exactly where you left off.

**Self-evolving** — errors trigger post-mortems that update the rules, not just fix the symptom.

**Contract-first** — all agent interfaces defined before parallel spawn. No surprises.

**Repo separation** — ZO is the surgeon; the delivery repo is the patient. Zero ZO artifacts leak into deliverables.

## Repository structure

```
zero-operators/
├── CLAUDE.md                          # Agent context index
├── PRD.md                             # Product requirements
├── plans/
│   └── zero-operators-build.md        # Platform build plan
├── specs/
│   ├── architecture.md                # Repo separation, file structure
│   ├── agents.md                      # 16 agent definitions, contracts
│   ├── memory.md                      # STATE.md, DECISION_LOG, semantic search
│   ├── oracle.md                      # Verification framework
│   ├── workflow.md                    # ML/DL/research pipeline phases
│   ├── plan.md                        # Plan file schema
│   ├── comms.md                       # JSONL logging, reporting
│   └── evolution.md                   # Self-evolving rules, post-mortems
├── design/                            # Brand system reference
├── plan/                              # Planning context documents
├── .claude/
│   ├── agents/                        # Agent prompt definitions (TBD)
│   └── skills/                        # Workflow skills (TBD)
├── src/zo/                            # Platform code (TBD)
├── memory/                            # Project-scoped state (TBD)
├── logs/                              # Audit trails (TBD)
└── targets/                           # Delivery repo pointers (TBD)
```

## Agent teams

**Project Delivery Team** (10 agents) — executes research/ML/engineering projects defined in plan.md.

| # | Agent | Model | Role |
|---|-------|-------|------|
| 1 | Lead Orchestrator | Opus | Plan decomposition, phase gating, coordination |
| 2 | Data Engineer | Sonnet | Data pipeline, validation, DataLoaders |
| 3 | Model Builder | Opus | Architecture, training, iteration |
| 4 | Oracle / QA | Sonnet | Hard metric evaluation, gating |
| 5 | Code Reviewer | Sonnet | Code quality, convention enforcement |
| 6 | Test Engineer | Sonnet | Unit, integration, regression tests |
| 7+ | XAI, Domain Evaluator, ML Engineer, Infra Engineer | Mixed | Phase-in after core loop proven |

**Platform Build Team** (6 agents) — builds ZO itself.

| # | Agent | Model | Role |
|---|-------|-------|------|
| B1 | Software Architect | Opus | Module decomposition, contracts |
| B2 | Backend Engineer | Sonnet/Opus | Core infrastructure modules |
| B3 | Frontend Engineer | Sonnet | Command dashboard (v2) |
| B4 | Test Engineer | Sonnet | Platform test suite |
| B5 | Code Reviewer | Sonnet | Platform code quality |
| B6 | Documentation Agent | Haiku | Docs, README, API reference |

## Design system

All ZO outputs follow the brand system defined in `design/`.

| Token | Value |
|-------|-------|
| Primary | `#F0C040` amber |
| Dim | `#8a6020` |
| Void | `#080808` |
| Surface | `#0d0d0d` |
| Paper | `#f5f0e8` |
| Ink | `#1a1400` |
| Mono font | Share Tech Mono |
| Heading font | Rajdhani 300/400/600/700 |

## Status

**Phase: Specification complete. Build not started.**

All specs written and QA'd. Platform build plan defined. Next step: bootstrap `src/zo/` package and write agent definition files.

---

<div align="center">

`ZERO OPERATORS` · `v0.1` · `specs complete`

</div>
