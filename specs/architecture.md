# Architecture: Zero Operators Repository Separation and Structure

## Core Principle: Surgeon and Patient

Zero Operators (ZO) operates as a surgical team—clean, isolated, and specialized. The ZO repository is the surgeon; delivery repositories are patients. This separation ensures:

- **ZO internals** (memory, logs, agent definitions, skills) remain private to the ZO repository
- **Delivery repositories** remain clean, containing only project artifacts: code, models, reports, data
- **Isolation enforcement** via Claude Code's `--cwd` flag and target file configuration
- **Scalability** through per-project state scoping and stateless agent replacement

## Repo Separation Model

ZO and all delivery repositories maintain strict boundaries:

| Responsibility | Location | Visibility |
|---|---|---|
| Agent definitions | `zero-operators/.claude/agents/` | ZO only |
| Skills and patterns | `zero-operators/.claude/skills/` | ZO only |
| State and memory | `zero-operators/memory/{project}/` | ZO only |
| Plans and specs | `zero-operators/specs/`, `zero-operators/plans/` | ZO only |
| Communication logs | `zero-operators/logs/` | ZO only |
| **Project output** | `{delivery-repo}/` | Clean, no ZO traces |

Agents launched by ZO operate on delivery repositories via `--cwd` flag only. No CLAUDE.md, .claude/ directory, STATE.md, or ZO references ever appear in delivery repos.

---

## Zero Operators Repository Structure

```
zero-operators/
├── CLAUDE.md                     ← lean table of contents; every agent reads
├── PRD.md                        ← platform requirements and invariants
│
├── specs/                        ← modular specification documents
│   ├── architecture.md           ← this file
│   ├── agents.md                 ← agent personas and responsibilities
│   ├── memory.md                 ← memory system, STATE.md structure
│   ├── oracle.md                 ← oracle evaluation framework
│   ├── workflow.md               ← ML/DL/research pipeline and phases
│   ├── plan.md                   ← plan.md schema and validation rules
│   ├── comms.md                  ← agent communication protocols
│   └── evolution.md              ← learning and adaptation mechanisms
│
├── plans/                        ← project-specific plans
│   ├── project-alpha.md
│   ├── project-beta.md
│   └── {project-name}.md
│
├── .claude/                      ← encrypted by default; agent runtime
│   ├── agents/                   ← persona and directive definitions
│   │   ├── lead-orchestrator.md  ← project delivery: launch
│   │   ├── data-engineer.md
│   │   ├── model-builder.md
│   │   ├── oracle-qa.md
│   │   ├── code-reviewer.md
│   │   ├── test-engineer.md
│   │   ├── xai-agent.md          ← project delivery: phase-in
│   │   ├── domain-evaluator.md
│   │   ├── ml-engineer.md
│   │   ├── infra-engineer.md
│   │   ├── software-architect.md  ← platform build team
│   │   ├── backend-engineer.md
│   │   ├── frontend-engineer.md
│   │   └── documentation-agent.md
│   │
│   ├── skills/                   ← encoded expertise and patterns
│   │   ├── ml-workflow/SKILL.md
│   │   ├── shap-patterns/SKILL.md
│   │   ├── logging/SKILL.md
│   │   ├── pytorch-patterns/SKILL.md
│   │   └── {domain}-patterns/SKILL.md
│   │
│   └── settings.json             ← runtime configuration
│
├── memory/                       ← project-scoped knowledge base
│   ├── {project-name}/
│   │   ├── STATE.md              ← current project state snapshot
│   │   ├── DECISION_LOG.md       ← decisions and rationale
│   │   ├── PRIORS.md             ← domain-specific assumptions
│   │   └── sessions/             ← agent session transcripts
│   │       ├── session-001.md
│   │       └── session-{N}.md
│   │
│   └── semantic_index.sqlite     ← indexed memory for fast retrieval
│
├── logs/                         ← audit and communication trails
│   └── comms/                    ← JSONL agent message logs
│       ├── 2026-04-09.jsonl
│       └── {date}.jsonl
│
└── targets/                      ← delivery repo pointers and config
    ├── project-alpha.target.md
    ├── project-beta.target.md
    └── {project-name}.target.md
```

---

## Target File Specification

The **target file** is the bridge between ZO and a delivery repository. It specifies working directories, git configuration, and path blocklists to enforce ZO isolation.

**Location:** `zero-operators/targets/{project-name}.target.md`

**Required fields:**

```yaml
---
project: "project-alpha"
target_repo: "../../../path/to/delivery/project-alpha"
target_branch: "main"
worktree_base: "/tmp/zo-worktrees/project-alpha"

git_author_name: "Zero Operators Agent"
git_author_email: "agents@zero-operators.local"

agent_working_dirs:
  lead_orchestrator: "."
  data_engineer: "data/"
  model_builder: "src/models/"
  ml_engineer: "src/"
  infra_engineer: "."

zo_only_paths:
  - ".claude/"
  - "CLAUDE.md"
  - "STATE.md"
  - "zero-operators/"
  - ".zo/"
  - "memory/"
  - "logs/"

enforce_isolation: true
```

**Meaning of each field:**

- **project**: Unique identifier for this delivery project
- **target_repo**: Relative or absolute path to delivery repository
- **target_branch**: Branch on which agents operate (main, develop, etc.)
- **worktree_base**: Base path for git worktrees enabling parallel agent work
- **git_author_name, git_author_email**: Identify commits from ZO agents
- **agent_working_dirs**: Maps each agent to a subdirectory it owns
- **zo_only_paths**: Blocklist enforced by orchestrator before every file write
- **enforce_isolation**: Boolean; if true, orchestrator halts execution if write violates blocklist

The orchestrator reads this file on every agent spawn and validates all file operations against `zo_only_paths`.

---

## Delivery Repository Convention

Delivery repositories contain only project artifacts. They follow a standard structure:

```
{project}/
├── README.md                     ← project overview
├── pyproject.toml                ← Python package metadata
├── data/                         ← datasets and data artifacts
│   ├── raw/
│   ├── processed/
│   └── metadata.json
├── src/                          ← source code
│   ├── __init__.py
│   ├── models/
│   ├── pipelines/
│   └── utils/
├── experiments/                  ← experimental outputs
│   ├── exp-001/
│   ├── exp-002/
│   └── results.json
├── models/                       ← trained model artifacts
│   ├── v1.pkl
│   ├── v2.pkl
│   └── metrics.csv
├── reports/                      ← analysis and reports
│   ├── evaluation.md
│   ├── figures/
│   └── summary.html
├── tests/                        ← test suite
│   ├── test_models.py
│   ├── test_pipelines.py
│   └── fixtures/
├── .gitignore
└── .git/
```

No ZO-specific files appear in delivery repositories.

---

## Scaling by Replacement

ZO scales horizontally through project replication, not vertical expansion:

1. **New Project**: Create a new target file (`targets/{project-name}.target.md`) and plan file (`plans/{project-name}.md`)
2. **ZO Core Unchanged**: Agent definitions, skills, and specs remain constant across all projects
3. **Memory Isolation**: Each project gets its own memory scope (`memory/{project-name}/`), preventing state bleed
4. **PRIORS Customization**: Domain-specific assumptions live in `memory/{project-name}/PRIORS.md`
5. **Agent Spawn**: Every agent launch includes `--cwd` isolation directive from the target file

This approach allows ZO to operate on 10 projects or 100 with no core changes—only new configuration and memory scopes.

---

## Isolation Enforcement

The orchestrator enforces isolation at three points:

1. **Target File Validation**: Before spawning any agent, the orchestrator verifies the target file exists and is well-formed
2. **Pre-Write Checks**: Before agents write files to the delivery repo, the orchestrator checks against `zo_only_paths` blocklist
3. **--cwd Isolation**: Every agent receive a directive specifying the delivery repo as its working directory, preventing cross-repo navigation

If any write operation targets a path in `zo_only_paths`, execution halts and the orchestrator logs the violation.

---

## Summary

Zero Operators achieves surgical precision through strict separation: ZO lives in one repository, operates on delivery repositories via configuration files and `--cwd` isolation, and leaves only clean artifacts in patient repos. This model enables ZO to scale across multiple projects without core changes, maintaining state isolation and enforcing that no ZO internals ever leak into delivery repositories.
