# ZO Commands Reference

## Overview

Zero Operators provides 24 slash commands for Claude Code, covering the full project lifecycle from import to retrospective. Commands are organized into eight categories: Project Lifecycle, Memory & Continuity, Gate Management, Observability, Documentation, Agent Management, Platform Development, and Utility.

All commands are defined in `.claude/commands/` and invoked as `/category/command` in a Claude Code session.

---

## CLI Commands

These are terminal commands provided by the `zo` CLI (installed via `uv`). They are distinct from the slash commands used inside Claude Code sessions.

### zo build

Launch an agent team to execute a plan. Parses the plan, shows a phase review, and spawns agents in a tmux session for parallel execution.

```
zo build plans/project.md [--gate-mode supervised|auto|full-auto] [--no-tmux]
```

### zo continue

Resume a paused project. Shorthand for `zo build` with an existing plan -- finds the plan by project name and picks up from the current phase.

```
zo continue project-name [--gate-mode supervised|auto|full-auto]
```

### zo draft

Draft a plan conversationally. Accepts source documents, a description, or launches an interactive prompt. Starts a Claude session to refine the plan collaboratively.

```
zo draft [SOURCE_PATHS...] --project NAME [-d DESC] [--no-tmux]
```

### zo init

Initialize a project scaffold including memory directory, targets, plans, and delivery repo. Auto-scaffolds the delivery repo if `--scaffold-delivery` is provided.

```
zo init project-name [--scaffold-delivery PATH]
```

### zo status

Show the current project status by reading `STATE.md`. Displays phase, blockers, recent activity, and next steps.

```
zo status project-name
```

### zo preflight

Validate the environment before building. Checks CLI tools, plan structure, agent definitions, Docker availability, and GPU access.

```
zo preflight plans/project.md [-t TARGET_REPO]
```

### zo gates set

Change the gate mode for a running project. The active build session picks up the change within 10 seconds.

```
zo gates set MODE --project NAME
```

`MODE` is one of: `supervised` (human approves every gate), `auto` (orchestrator approves unless ambiguous), `full-auto` (all gates auto-approved).

### zo watch-training

Live training metrics dashboard. Tails `logs/training/metrics.jsonl` in the delivery repo and renders a persistent Rich panel with epoch progress, loss/metrics table, checkpoint log, and loss sparkline. Auto-launched by `zo build` during Phase 4 via tmux split-pane.

```
zo watch-training --project NAME [-i INTERVAL]
```

`INTERVAL` (default: 2.0) is the refresh rate in seconds. The dashboard shows current and best metrics, ETA, and the oracle target threshold from `plan.md`.

---

## Slash Commands

The following slash commands are available inside Claude Code sessions.

---

## Project Lifecycle

### /project/import \<github-url\>

Clone a repo, analyze the codebase, and draft a full plan.md.

**Arguments:** `<github-url>` -- the GitHub repository URL to import.

**What happens:**

1. Runs `/project/connect` to clone the repo, create the target file, and initialize memory.
2. Analyzes the codebase: directory structure, dependencies, README/docs, existing tests, and source code.
3. Detects the workflow mode (`deep_learning`, `classical_ml`, or `research`) from dependencies.
4. Drafts `plans/{project-name}.md` with all 8 required sections (identity, objective, oracle, workflow, data sources, domain context, agents, constraints).
5. Presents the plan for human review. Saves only after confirmation.

**Example:**
```
/project/import https://github.com/user/sensor-anomaly-detector
```

---

### /project/connect \<github-url\>

Clone a repo and scaffold a ZO project target for it.

**Arguments:** `<github-url>` -- the GitHub repository URL to connect.

**What happens:**

1. Parses the repo name from the URL.
2. Clones the repo to a sibling directory of the ZO root.
3. Detects the default branch.
4. Creates `targets/{project-name}.target.md` with repo path, branch, agent working directories, and isolation rules.
5. Initializes the memory scaffold: `STATE.md`, `DECISION_LOG.md`, `PRIORS.md`, and `sessions/` directory.
6. Reports a summary and suggests running `/project/import` next.

**Example:**
```
/project/connect https://github.com/user/sensor-anomaly-detector
```

---

### /project/plan \<task-description\>

Create or update a structured task plan for the current project.

**Arguments:** `<task-description>` -- what you want to plan.

**What happens:**

1. Loads context: reads `STATE.md`, `PRIORS.md`, the existing plan, and recent decisions.
2. Searches the codebase for files relevant to the task.
3. Writes a structured plan with: objective, approach, agents needed, ordered subtasks with dependencies, acceptance criteria, risks, and phase breakdown.
4. Integrates with the existing plan based on mode (build = new, continue = append, maintain = targeted update).
5. Presents for review. Writes to `plans/{project-name}.md` and updates memory only after approval.

**Example:**
```
/project/plan add hyperparameter tuning with Optuna
```

---

### /project/launch \<project-name\>

Launch an agent team to execute a project plan.

**Arguments:** `<project-name>` -- the project to launch (detected from `plans/` if omitted).

**What happens:**

1. Validates the plan file exists and has all 8 required sections.
2. Validates the target file exists and the delivery repo is accessible.
3. Initializes memory if not already done.
4. Decomposes the plan into execution phases based on workflow mode (classical_ml, deep_learning, or research).
5. Builds the Lead Orchestrator prompt with plan, target config, state, priors, and decisions.
6. Launches via `zo build` in supervised gate mode.
7. Reports the project summary, active agents, and how to monitor progress.

**Example:**
```
/project/launch sensor-anomaly-detector
```

---

## Memory & Continuity

### /memory/recall \<query\>

Search project memory for decisions and priors matching a query.

**Arguments:** `<query>` -- the search term or question.

**What happens:**

1. Detects the active project from `memory/*/STATE.md`.
2. Tries the semantic index first (`memory/{project}/index.db`) for ranked results.
3. Falls back to text search across `DECISION_LOG.md`, `PRIORS.md`, and recent session summaries.
4. Presents the top 5 results with source, timestamp, and relevance score.

**Example:**
```
/memory/recall learning rate schedule decisions
```

---

### /memory/prime \<project-name\>

Load full project context -- the "catch me up" command for new sessions.

**Arguments:** `<project-name>` -- the project to brief on (auto-detected if omitted).

**What happens:**

1. Reads `STATE.md` for current mode, phase, blockers, and next steps.
2. Reads the last 3 session summaries for recent accomplishments and decisions.
3. Queries relevant decisions from `DECISION_LOG.md` (semantic search if available).
4. Reads all domain priors from `PRIORS.md`.
5. Checks recent git activity in the delivery repo.
6. Presents a concise context briefing: where we are, what happened, key decisions, domain priors, delivery activity, and next steps.

**Example:**
```
/memory/prime sensor-anomaly-detector
```

---

### /memory/priors \<project-name\>

Display all accumulated domain priors for a project.

**Arguments:** `<project-name>` -- the project to show priors for (auto-detected if omitted).

**What happens:**

1. Reads `memory/{project}/PRIORS.md`.
2. Parses each prior entry (statement, evidence, confidence, superseded-by).
3. Displays priors grouped by category, highlighting high-confidence and superseded entries.
4. Shows summary statistics: total count, confidence breakdown, superseded count, and most recent prior.

**Example:**
```
/memory/priors sensor-anomaly-detector
```

---

### /memory/session-summary

Write a session summary and update all memory files -- the "wrap up cleanly" command.

**Arguments:** None.

**What happens:**

1. Detects the active project from recent activity.
2. Collects session information: tasks completed, decisions made, files changed, blockers hit.
3. Writes `memory/{project}/sessions/session-{timestamp}.md` with accomplishments, decisions, blockers, next steps, and context handoff.
4. Updates `STATE.md` with current phase, blockers, next steps, and git HEAD.
5. Appends new decisions to `DECISION_LOG.md` (append-only).
6. Rebuilds the semantic index if available.
7. Reports the session summary path, updated state, and next steps.

**Example:**
```
/memory/session-summary
```

---

## Gate Management

### /gates/approve

Approve the current pending gate and advance to the next phase.

**Arguments:** None.

**What happens:**

1. Reads `STATE.md` to find the pending gate. Stops if no gate is pending.
2. Logs the approval to `DECISION_LOG.md` with timestamp and gate details.
3. Updates `STATE.md`: marks current phase as `COMPLETED`, activates the next phase.
4. Logs the gate event to the JSONL comms log.
5. Reports which gate was approved, which phase completed, and what phase is now active.

**Example:**
```
/gates/approve
```

---

### /gates/reject \<reason\>

Reject the current pending gate with a reason, triggering rework.

**Arguments:** `<reason>` -- why the gate is being rejected.

**What happens:**

1. Reads `STATE.md` to find the pending gate. Stops if no gate is pending.
2. Logs the rejection to `DECISION_LOG.md` with the reason.
3. Updates `STATE.md`: sets phase to `ACTIVE` for rework, records the rejection in blocker history.
4. Logs the gate event to the JSONL comms log.
5. Reports which gate was rejected, the reason, and suggests next steps for rework.

**Example:**
```
/gates/reject "Test coverage below 80%, need unit tests for data pipeline edge cases"
```

---

### /gates/gates \<project-name\>

Display all gates for a project with their current status.

**Arguments:** `<project-name>` -- the project to show gates for.

**What happens:**

1. Reads the project plan to extract all gate definitions (ID, phase, type, criteria).
2. Reads `STATE.md` for current phase and gate status.
3. Reads `DECISION_LOG.md` for gate history (approvals, rejections, oracle results).
4. Displays a table of all gates with phase, name, type (auto/blocking), status, date, and notes.
5. Highlights the current/next gate. Shows failure history if any gates were previously rejected.

**Example:**
```
/gates/gates sensor-anomaly-detector
```

---

## Observability

### /observe/watch \<project-name\>

Watch a running ZO session or show last known state.

**Arguments:** `<project-name>` -- the project to monitor.

**What happens:**

1. Checks for running Claude processes and active team/task files.
2. If a session is running: shows agent list with statuses, current task assignments, and the last 10 comms events in a formatted table.
3. If no session is running: reads `STATE.md` for last known state, shows the most recent session summary.
4. Always shows project name, current/last phase, and time since last activity.

**Example:**
```
/observe/watch sensor-anomaly-detector
```

---

### /observe/logs \<project-name\> [--type \<event_type\>] [--agent \<agent-name\>]

Display recent comms log events for a project.

**Arguments:** `<project-name>` -- the project. Optional filters: `--type` (message, decision, gate, error, checkpoint) and `--agent` (filter by agent name).

**What happens:**

1. Finds JSONL log files in `logs/comms/` sorted by date.
2. Reads and parses the most recent log file.
3. Applies filters if provided (by event type or agent name).
4. Displays the last 20 events in a formatted table with timestamp, agent, type, and summary.
5. Shows metadata: total events, events shown, date range, and available log files.

**Example:**
```
/observe/logs sensor-anomaly-detector --type gate
/observe/logs sensor-anomaly-detector --agent oracle-qa
```

---

### /observe/decisions \<project-name\> [search-term]

Display all decisions from the project decision log.

**Arguments:** `<project-name>` -- the project. Optional `[search-term]` to filter entries.

**What happens:**

1. Reads `DECISION_LOG.md` and parses all entries.
2. Extracts: entry number, timestamp, title, category, outcome, confidence, decided-by.
3. Applies search filter if a term is provided (case-insensitive match across all fields).
4. Displays as a numbered table with timestamp, title, decided-by, outcome, and confidence.
5. Shows summary stats: total decisions, category breakdown, date range.

**Example:**
```
/observe/decisions sensor-anomaly-detector
/observe/decisions sensor-anomaly-detector "learning rate"
```

---

### /observe/history \<project-name\>

Show a combined timeline of sessions, commits, and decisions for a project.

**Arguments:** `<project-name>` -- the project.

**What happens:**

1. Reads all session summaries from `memory/{project}/sessions/`.
2. Reads git log from the delivery repo.
3. Reads `DECISION_LOG.md` for key decisions with timestamps.
4. Combines everything into a unified chronological timeline with type labels (session, commit, decision, gate).
5. Groups by phase if the timeline is long. Shows total elapsed time, phases completed, and current status.

**Example:**
```
/observe/history sensor-anomaly-detector
```

---

## Documentation

### /document/code-docs

Generate or update documentation for the delivery repo code.

**Arguments:** None.

**What happens:**

1. Detects the delivery repo from state or plan files.
2. Scans all Python files in the delivery repo.
3. Checks documentation quality: module docstrings, function/class docstrings, type hints, parameter docs, return docs.
4. Adds missing Google-style docstrings to all public functions and classes.
5. Generates an API reference if the project has a clear public interface.
6. Commits the changes with conventional commit format.
7. Reports files scanned, docstrings added, and any files needing manual attention.

**Example:**
```
/document/code-docs
```

---

### /document/model-card \<project-name\>

Generate a standard model card for the project.

**Arguments:** `<project-name>` -- the project.

**What happens:**

1. Reads the project plan for objective, constraints, data sources, and success criteria.
2. Reads oracle evaluation results from reports and gate events.
3. Reads model architecture and hyperparameters from source code.
4. Generates a model card with: model details, intended use, training data, evaluation results, limitations/biases, and ethical considerations.
5. Writes to `reports/model_card.md` in the delivery repo.
6. Reports summary and any sections needing manual review.

**Example:**
```
/document/model-card sensor-anomaly-detector
```

---

### /document/retrospective \<project-name\>

Run a retrospective analyzing failures, evolutions, and lessons learned.

**Arguments:** `<project-name>` -- the project.

**What happens:**

1. Scans `DECISION_LOG.md` for failures, evolutions, and gate rejections.
2. Categorizes each failure by root cause: missing_rule, incomplete_rule, ignored_rule, novel_case, or regression.
3. Identifies patterns: failures clustered by phase, agent, domain area, or recurring theme.
4. Proposes systemic updates: new subtasks, stronger gates, spec file changes.
5. Generates a retrospective report with failure distribution, patterns, rule updates, recommendations, and lessons.
6. Presents findings for human review. Does NOT auto-apply systemic updates.

**Example:**
```
/document/retrospective sensor-anomaly-detector
```

---

### /document/validation-report \<project-name\>

Generate a comprehensive validation report from oracle results.

**Arguments:** `<project-name>` -- the project.

**What happens:**

1. Reads oracle evaluation results from `oracle/reports/` and comms logs.
2. Reads gate events and metric history from `DECISION_LOG.md`.
3. Reads the project plan for metric definitions and tiered success criteria.
4. Generates a report with: primary metric result, tiered results (Tier 1/2/3), per-stratum breakdown, confusion matrix (if classification), baseline comparison, confidence intervals, known limitations, and gate history.
5. Writes to `reports/validation_report.md` in the delivery repo.

**Example:**
```
/document/validation-report sensor-anomaly-detector
```

---

## Agent Management

### /agents/agents

List all defined agents with their roles, tiers, and teams.

**Arguments:** None.

**What happens:**

1. Finds all agent definition files in `.claude/agents/`.
2. Parses YAML frontmatter and role descriptions from each file.
3. Displays agents as grouped tables: Project Delivery Team (launch agents), Project Delivery Team (phase-in agents), and Platform Build Team.
4. Each entry shows: name, model tier, role summary, and status.
5. Shows summary: total agents, breakdown by team and status.

**Example:**
```
/agents/agents
```

---

### /agents/spawn \<agent-name\>

Spawn an agent in the current session with full context.

**Arguments:** `<agent-name>` -- the agent to spawn (must match a file in `.claude/agents/`).

**What happens:**

1. Reads the agent definition from `.claude/agents/{agent-name}.md`.
2. Reads current project context: `STATE.md`, plan, and recent decisions.
3. Validates the spawn: checks if the agent is appropriate for the current phase and if input dependencies are met.
4. Constructs the spawn context: role, ownership, off-limits, contracts, coordination rules, validation checklist.
5. Logs the spawn to the JSONL comms log.
6. Activates the agent with full instructions and context. The agent acknowledges its role and begins working.

**Example:**
```
/agents/spawn model-builder
```

---

### /agents/create-agent \<agent-name\>

Create a new agent definition file interactively.

**Arguments:** `<agent-name>` -- kebab-case identifier for the new agent.

**What happens:**

1. Validates the agent name is kebab-case.
2. Asks for: role description, model tier (opus/sonnet/haiku), and team (project/platform).
3. Generates `.claude/agents/{agent-name}.md` with: frontmatter, role, ownership, off-limits, contracts (produced and consumed), coordination rules, validation checklist, and prohibitions.
4. Fills reasonable defaults, marks unknowns as `{TODO}`.
5. Logs the creation to `DECISION_LOG.md`.
6. Reports the file path and suggests reviewing `{TODO}` placeholders.

**Example:**
```
/agents/create-agent time-series-specialist
```

---

## Platform Development

### /zo-dev

Resume building/improving ZO itself -- loads full platform context and picks up where we left off.

**Arguments:** None

**What happens:**

1. Reads CLAUDE.md for project rules and self-evolution protocol.
2. Reads memory/zo-platform/STATE.md for current state.
3. Reads recent decisions from DECISION_LOG.md.
4. Reads accumulated learnings from PRIORS.md.
5. Presents a concise briefing: state, recent work, what's next.
6. Asks what to work on.

**Example:**
```
/zo-dev
```

---

## Utility

### /commit

Stage and commit changes with a conventional commit message.

**Arguments:** None.

**What happens:**

1. Runs `git status` and `git diff` to see all changes.
2. Checks recent commit messages for style consistency.
3. Determines the commit type (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `style`) and scope.
4. Stages relevant files, excluding `.env`, credentials, binaries, `__pycache__`, and IDE configs.
5. Creates the commit with conventional format: `type(scope): subject`.
6. Reports the commit message, files committed, commit hash, and any excluded files.

**Example:**
```
/commit
```
