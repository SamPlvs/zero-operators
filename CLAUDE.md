# CLAUDE.md

Zero Operators (ZO) is an autonomous AI research and engineering team system.
You input a plan; agents coordinate to build and deliver code.
The human edits the plan; agents execute the plan; the oracle verifies the work.


## Design Principles

- **Oracle-first**: every project must have a hard, verifiable success metric
- **Contract-first spawning**: define all agent interfaces before parallel spawn
- **Memory-aware**: read STATE.md at session start, write session summary at end
- **Self-evolving**: when a bug or failure occurs, update the rules that allowed it, not just fix the symptom
- **Repo separation**: ZO code never touches the delivery repo


## Client Project Confidentiality (NON-NEGOTIABLE)

ZO is a **public repository**. Client/project-specific information MUST NEVER appear in any tracked file — this is a legal requirement.

### What is confidential
- Client or company names, project names, locations, domain-specific terminology that identifies the client
- Plan contents, data descriptions, oracle thresholds, domain priors
- Delivery repo paths, branch names that reference clients
- Any information from documents provided during `zo draft` or `zo build`

### Alias convention
In platform memory (`memory/zo-platform/`), commits, PRs, and branch names, refer to projects by sequential alias:
- `prod-001`, `prod-002`, ... for production projects
- `demo-mnist`, `demo-cifar10`, ... for demos/validation

The alias mapping lives ONLY in the gitignored `memory/{project}/` directory.

### What is gitignored (automatically)
- `plans/*` (except ZO's own: `zero-operators-build.md`, `mnist-digit-classifier.md`)
- `targets/*`
- `memory/*` (except `memory/zo-platform/`)
- `.claude/agents/custom/*` (except README.md)
- `logs/`

### Enforcement
- `.gitignore` blocks project-specific paths
- All commits, PR titles, and descriptions use aliases only
- `memory/zo-platform/` entries describe what ZO learned generically, never name the client
- If you notice a client name in a tracked file, remove it immediately


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
| specs/report_templates.md | Structured report templates for Phase 1 (Data Quality) and Phase 5 (Analysis) | Read when producing phase output reports |


## Design System

All ZO outputs (dashboard, reports, documentation, diagrams, presentations) follow the ZO brand system v2 defined in `design/`:

- **Canvas:** #12110F (dark) · **Paper:** #F4EFE6 (light)
- **Ink (light):** #1A1712 · **Cream (dark):** #EBE3D2
- **Coral accent:** oklch(0.74 0.14 35) ≈ #D87A57 — the primary highlight (italic emphases, focus states, status dots)
- **Dusk:** oklch(0.70 0.10 245) · **Moss:** oklch(0.62 0.08 150) — secondary status colors
- **Sans:** Geist (300/400/500/600/700) — body, UI, headings
- **Italic / display:** Cormorant Garamond — emphasized prose, taglines
- **Monospace:** JetBrains Mono — code, terminal, plan refs
- **Mark:** simplified C — circle with a diagonal slash and centered coral dot. Replaces the prior orbital mark.

Canonical references: `design/brand-system.html` (dark) · `design/brand-system-light.html` (light) · `design/logos.html` (mark exploration) · `design/font-pairings.html`. Shared CSS variables live in `design/styles.css`.


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
4. **Cascade doc updates** — if the change affects the public interface, update ALL files in the cascade chain. Run `scripts/validate-docs.sh` to verify.

   **Agent added/removed** (trigger: any change to `.claude/agents/`):
   - `setup.sh` → update EXPECTED_AGENTS array AND hardcoded count
   - `README.md` → update agents badge count AND agent roster table
   - `specs/agents.md` → update team counts in Team Philosophy AND add/remove agent entry
   - `.claude/agents/lead-orchestrator.md` → update agent count in "Agent Roster" section AND roster table
   - `plans/zero-operators-build.md` → update agent count references
   - `PRD.md` → update acceptance criteria counts

   **Command added/removed** (trigger: any change to `.claude/commands/`):
   - `README.md` → update slash command count
   - `docs/COMMANDS.md` → add/remove command entry
   - `memory/zo-platform/STATE.md` → update command count

   **Version changed** (trigger: change to `pyproject.toml` version):
   - `src/zo/__init__.py` → update `__version__`
   - `src/zo/cli.py` → update `_VERSION`
   - `README.md` → update version badge

   **Model tier changed** (trigger: change to agent `model:` frontmatter):
   - `specs/agents.md` → update "Model tier" line for that agent
   - `README.md` → update agent roster table

   A PreToolUse hook enforces this: `git commit` is blocked if `scripts/validate-docs.sh` fails.

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
