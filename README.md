<div align="center">

<img src="design/banner-dark.svg" alt="Zero Operators — Autonomous AI Systems" width="680"/>

<br/>
<br/>

<img src="design/logo-dark.svg" alt="ZO orbital mark" width="64"/>

<br/>
<br/>

**You input a plan. Agents execute. The oracle verifies.**

<br/>

[![Status](https://img.shields.io/badge/phase-specs_complete-F0C040?style=flat-square&labelColor=080808)](#status)
[![Agents](https://img.shields.io/badge/agents-16_defined-F0C040?style=flat-square&labelColor=080808)](#agent-teams)
[![Specs](https://img.shields.io/badge/specs-8_documents-F0C040?style=flat-square&labelColor=080808)](#repository-structure)

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

**Project Delivery Team** — 10 agents that execute research/ML/engineering projects.

| # | Agent | Model | Role |
|---|-------|-------|------|
| 1 | Lead Orchestrator | Opus | Plan decomposition, phase gating, coordination |
| 2 | Data Engineer | Sonnet | Data pipeline, validation, DataLoaders |
| 3 | Model Builder | Opus | Architecture, training, iteration |
| 4 | Oracle / QA | Sonnet | Hard metric evaluation, gating |
| 5 | Code Reviewer | Sonnet | Code quality, convention enforcement |
| 6 | Test Engineer | Sonnet | Unit, integration, regression tests |
| 7–10 | XAI, Domain Eval, ML Eng, Infra | Mixed | Phase-in after core loop proven |

**Platform Build Team** — 6 agents that build ZO itself.

| # | Agent | Model | Role |
|---|-------|-------|------|
| B1 | Software Architect | Opus | Module decomposition, contracts |
| B2 | Backend Engineer | Sonnet/Opus | Core infrastructure modules |
| B3 | Frontend Engineer | Sonnet | Command dashboard (v2) |
| B4 | Test Engineer | Sonnet | Platform test suite |
| B5 | Code Reviewer | Sonnet | Platform code quality |
| B6 | Documentation Agent | Haiku | Docs, README, API reference |

## Design system

All ZO outputs follow the brand system in [`design/`](design/).

| Token | Value | Name |
|-------|-------|------|
| ![#F0C040](https://via.placeholder.com/12/F0C040/F0C040.png) | `#F0C040` | Phosphor (primary) |
| ![#8a6020](https://via.placeholder.com/12/8a6020/8a6020.png) | `#8a6020` | Dim Amber |
| ![#080808](https://via.placeholder.com/12/080808/080808.png) | `#080808` | Void Black |
| ![#0d0d0d](https://via.placeholder.com/12/0d0d0d/0d0d0d.png) | `#0d0d0d` | Surface |
| ![#f5f0e8](https://via.placeholder.com/12/f5f0e8/f5f0e8.png) | `#f5f0e8` | Paper |

**Fonts:** Share Tech Mono (monospace) · Rajdhani 300/400/600/700 (headings)

## Status

**Specs complete. Build not started.**

All 8 specification documents written and QA'd. Platform build plan defined with 9 modules, 5 gates, and 14 oracle verification checks. Next: bootstrap `src/zo/` and write agent definition files.

---

<div align="center">
<br/>

<img src="design/logo-dark.svg" alt="ZO" width="32"/>

<br/>
<br/>

`ZERO OPERATORS` · `v0.1` · `specs complete`

<br/>
</div>
