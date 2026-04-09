# CLAUDE.md

Zero Operators (ZO) is an autonomous AI research and engineering team system.
You input a plan; agents coordinate to build, continue, or maintain code.
The human edits the plan; agents execute the plan; the oracle verifies the work.


## Design Principles

- **Oracle-first**: every project must have a hard, verifiable success metric
- **Contract-first spawning**: define all agent interfaces before parallel spawn
- **Memory-aware**: read STATE.md at session start, write session summary at end
- **Self-evolving**: when a bug or failure occurs, update the rules that allowed it, not just fix the symptom
- **Repo separation**: ZO code never touches the delivery repo


## Specs Reference

| File | What it covers | When to read |
|------|----------------|--------------|
| PRD.md | Product requirements, operating modes, agent teams, v1 scope, success criteria | Read at project setup and when understanding what ZO is |
| specs/architecture.md | Repo separation, target files, --cwd mechanism, file structure | Read when setting up a new project or understanding the two-repo model |
| specs/agents.md | Agent personas, tiering, contracts, model routing, spawn prompts | Read when defining or modifying the agent team |
| specs/memory.md | STATE.md schema, DECISION_LOG, PRIORS, session recovery, context resets | Read at session start and end, and when implementing cross-session continuity |
| specs/oracle.md | Verification framework, tiered success criteria, drift detection | Read when setting up project-specific validation gates |
| specs/workflow.md | ML/research pipeline phases, gates, subtask sequencing | Read when planning or executing any project phase |
| specs/plan.md | Plan file schema, required sections, update protocol, validation rules | Read when creating a new project or reviewing plan.md structure |
| specs/comms.md | JSONL logging schema, reporting standards, explainability output levels | Read when writing agent messages or producing reports |
| specs/evolution.md | Self-evolving rules, post-mortem protocol, rule update mechanism | Read after any error or failure, and during retrospectives |


## Design System

All ZO outputs (dashboard, reports, documentation, diagrams, presentations) follow the ZO brand system defined in `design/`:

- **Primary:** amber #F0C040 | **Dim:** #8a6020 | **Void:** #080808 | **Surface:** #0d0d0d
- **Paper (light):** #f5f0e8 | **Ink (light):** #1a1400
- **Monospace:** Share Tech Mono | **Headings:** Rajdhani (300/400/600/700)
- **Logo:** orbital mark (concentric rings, amber on void)

Canonical reference: `design/zero_operators_brand_system.html`


## Coding Conventions

- Python as primary language, PEP8, type hints, Google-style docstrings
- PyTorch for ML (Sam is a heavy PyTorch user)
- uv for package management, ruff for linting
- Files under 500 lines, functions under 50 lines
- Never commit ZO artefacts to target repos
- Git commits use conventional format: type(scope): subject


## Context Management

- **At session start**: read STATE.md, query semantic index for relevant past decisions
- **At session end**: write session summary, update STATE.md, append to DECISION_LOG
- **Phase transitions** (planning → building): fresh context window, load only the artefacts produced by the previous phase
- **Keep context lean**: read only the spec files relevant to current task


## Operating Modes

- **Build**: input plan → spawn team → produce code from scratch
- **Continue**: read memory → reason about state → pick up where last session left off
- **Maintain**: new instruction → diff against existing state → targeted update
