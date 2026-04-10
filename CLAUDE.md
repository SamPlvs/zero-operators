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


## AUTOMATIC Memory & Docs Protocol (NON-NEGOTIABLE)

These rules are AUTOMATIC. Claude executes them without being asked.
The human should never need to remind Claude to update memory or docs.

### On Every Commit

Before creating ANY git commit, Claude MUST:

1. **Update `memory/zo-platform/STATE.md`** — reflect current phase, completed items, known issues, what's next
2. **Append to `memory/zo-platform/DECISION_LOG.md`** — every architectural decision, gate passage, or scope change made in this session
3. **Update `memory/zo-platform/PRIORS.md`** — if any failure, error, or unexpected behaviour occurred, add a new prior with: failure description, root cause category, rules learned, verified solution
4. **Cascade doc updates** — if the change affects the public interface:
   - Agent added/removed → update `README.md` badge + roster, `specs/agents.md` counts
   - Command added/removed → update `README.md`, `PRD.md`, `CLAUDE.md` operating modes
   - Version changed → update `README.md` badges + footer

### On Session End

Before the session closes, Claude MUST:

1. Write a session summary to `memory/zo-platform/sessions/`
2. Ensure STATE.md reflects the final state
3. Ensure DECISION_LOG has all decisions from this session

### On Any Failure or Error

When anything fails (build error, test failure, unexpected behaviour, user reports a bug):

1. **Document** the failure in DECISION_LOG.md (timestamp, type, description)
2. **Root cause**: classify as `missing_rule` | `incomplete_rule` | `ignored_rule` | `novel_case` | `regression`
3. **Fix** the immediate problem
4. **Add a prior** to PRIORS.md with: rules learned, verified solution, failure reference
5. **Verify** the updated rule would have caught the original failure

This is the self-evolution protocol. The same mistake must never happen twice.


## Operating Modes

- **Build**: input plan → spawn team → produce code (auto-detects fresh/continue/plan-edited)
- **Continue**: shorthand for build — finds plan, resumes from current phase
