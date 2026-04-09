# Memory Layer Specification
## Zero Operators — v1 Design

The Memory Layer enables persistent state and decision tracking across agent sessions without requiring neural training or complex pattern matching. This document covers the memory architecture for v1.

## The Memory Problem

Agents operating across multiple sessions face a fundamental challenge: **no persistent context between runs**. Without memory, each session restarts from zero, losing accumulated knowledge about project state, architectural decisions, and resolved blockers.

Zero Operators solves this with four static files and one lightweight semantic search library. The approach trades flexibility for simplicity and auditability:

- **Four files**: STATE.md, DECISION_LOG.md, PRIORS.md, session summaries
- **One library**: fastembed + SQLite for semantic search
- **No neural training**: v1 uses simple cosine similarity over embeddings
- **Self-learning deferred**: SONA-style pattern extraction targets v2 (requires 5+ projects of comparable data)

This design is sufficient for v1 because:

1. Structured state is explicit and queryable
2. Decision logs provide complete audit trails
3. Semantic search scales to hundreds of decisions per project
4. No external services, no dependency chains, no infrastructure overhead

## Memory Components

### STATE.md

Lightweight checkpoint file recording the agent's operational state. Written at session end; read at session start.

**Schema** (plain markdown, readable by humans and tools):

```
# STATE
timestamp: 2026-04-09T14:32:00Z
mode: build | continue | maintain
phase: {phase-name}
last_completed_subtask: {description or null}
active_blockers: [list of blocking issues]
next_steps: [list of actionable items]
active_agents: [agents currently assigned to tasks]
git_head: {commit hash}
context_window_usage: {percentage or "not tracked in v1"}
```

**Constraints**:

- One STATE.md per project
- Location: `memory/{project-name}/STATE.md`
- Human-readable format (markdown with key-value pairs)
- Updated at session end via postSessionEnd hook
- Checkpoint updates during long sessions via postToolUse hook (every 5 tool invocations or 30 minutes, whichever comes first)
- Never edited directly by humans; always overwritten by hooks

**Usage at Session Start**:

1. Orchestrator reads STATE.md as first action
2. Parses mode, phase, and last_completed_subtask
3. Determines whether to resume, pivot, or restart
4. Verifies git_head against actual repository history (ensures external changes are detected)

### DECISION_LOG.md

Append-only audit log of all orchestrator decisions. Every decision is recorded with rationale and outcome.

**Schema** (markdown, one entry per decision):

```
## Decision: {short title}
**Timestamp**: 2026-04-09T14:15:00Z
**Context**: {brief description of the situation}
**Decision**: {what was decided}
**Rationale**: {why this decision was made}
**Alternatives Considered**: {other options and why they were rejected}
**Outcome**: {result of the decision, or "pending"}
**Confidence**: high | medium | low
---
```

**Constraints**:

- Append-only: never rewrite, edit, or delete entries
- One DECISION_LOG.md per project
- Location: `memory/{project-name}/DECISION_LOG.md`
- Entry order reflects chronological sequence (oldest first)
- Decisions are written at the moment of decision, outcome is updated later via postToolUse hooks
- Used by clients and auditors as source of truth for agent reasoning

**Usage at Runtime**:

- Semantic search queries return relevant decisions to inform current phase
- Audit trails extracted from DECISION_LOG for client reports
- Enables post-hoc analysis of decision quality

### PRIORS.md

Domain-specific knowledge accumulated across iterations. Updated when the domain evaluator resolves a case marked QUESTIONABLE.

**Schema** (markdown with sections):

```
# Domain Priors
**Project**: {project-name}
**Domain**: {domain discipline: architecture, compliance, etc.}
**Last Updated**: 2026-04-09T14:15:00Z

## Prior: {category}
**Statement**: {factual claim about the domain}
**Evidence**: {case or reference where this was learned}
**Confidence**: high | medium | low
**Superseded By**: {reference to newer prior, if applicable}

---
```

**Constraints**:

- One PRIORS.md per project
- Location: `memory/{project-name}/PRIORS.md`
- Priors are written by the domain evaluator when resolving QUESTIONABLE cases
- Never delete priors; mark as superseded if knowledge changes
- Scoped to project domain (e.g., "Kubernetes deployment patterns" is project-specific, not shared)
- Enables ZO to avoid re-resolving the same questions across iterations

**Lifecycle**:

1. During a session, the agent encounters a QUESTIONABLE case
2. Domain evaluator investigates and resolves with evidence
3. Resolution is written as a new prior at session end
4. Next session reads priors before starting, avoiding duplicate work
5. Priors compound: first iteration has none, fifth iteration has learned 20+ facts

### Session Summaries

One-file-per-session narrative of accomplishments and decisions.

**Schema** (markdown):

```
# Session Summary: {date}
**Date**: 2026-04-09
**Duration**: 45 minutes
**Mode**: build | continue | maintain
**Agent**: {agent name or "orchestrator"}

## Accomplished
- {list of completed tasks}
- {files changed}
- {decisions finalized}

## Decisions Made
- {decision 1 (see DECISION_LOG entry {ref})}
- {decision 2}

## Blockers Hit
- {blocker 1, current status}
- {blocker 2}

## Next Steps
- {action 1}
- {action 2}

## Files Changed
- {filename}: {brief description}
- {filename}: {brief description}

## Context Handoff
- Estimated completion: {date or "blocked"}
- Open questions: {list}
- Recommended next phase: {recommendation}
```

**Constraints**:

- One summary per session
- Location: `memory/{project-name}/sessions/session-{YYYY-MM-DD-HHmmss}.md`
- Written at session end via postSessionEnd hook
- Human-readable narrative, not structured data
- Summarizes but does not duplicate DECISION_LOG (references entries instead)
- Includes blockers and open questions for continuity planning

**Usage at Session Start**:

- Orchestrator reads most recent 2–3 summaries for context
- Identifies unresolved blockers from prior sessions
- Understands what was attempted and why

### Semantic Index

Lightweight embedding-based search over memory documents. Implemented in ~50 lines of Python.

**Components**:

- **Embedding model**: fastembed (CPU-only, no GPU required)
- **Vector storage**: SQLite with cosine similarity search
- **Scope**: per-project (separate index per project)
- **Content indexed**: DECISION_LOG.md entries, PRIORS.md entries, recent session summaries

**Query Interface**:

```python
query("What did we decide about X?")
# Returns: [list of relevant DECISION_LOG entries with relevance scores]
```

**Constraints**:

- No neural network training
- No external dependencies (fastembed is self-contained)
- No HNSW or approximate nearest neighbor algorithms (v1 uses simple cosine similarity)
- Reindexing: full rebuild at session end (takes <1 second for typical project)
- No incremental indexing in v1

**Performance Characteristics**:

- Index size: ~1 MB per 100 decisions
- Query latency: <50 ms per query on modern hardware
- Recall: 85–95% (depends on query formulation)
- Scales to 1000+ decisions per project without degradation

## Session Lifecycle

### Session Start Protocol

1. **Read state** (first action)
   - Load STATE.md
   - Parse mode, phase, last_completed_subtask
   - Record timestamp of session start

2. **Query memory**
   - Semantic search: "What decisions were made related to {phase}?"
   - Return top 5 relevant DECISION_LOG entries
   - Return any applicable PRIORS.md entries

3. **Read context**
   - Load most recent session summary (1–2 sessions prior)
   - Identify unresolved blockers
   - Note any open questions

4. **Verify git state**
   - Fetch current git HEAD from target repository
   - Compare against git_head in STATE.md
   - If mismatch: log discrepancy, update STATE.md
   - Prevents desynchronization with external changes

5. **Determine mode**
   - If phase is unchanged and no new commits: continue
   - If phase changed: load new context (see Context Reset Protocol)
   - If git_head differs: adjust mode to account for external changes

### Session End Protocol

1. **Summarize accomplishments**
   - Collect list of completed tasks, files changed, decisions finalized
   - Write to sessions/session-{timestamp}.md

2. **Update STATE.md**
   - Set phase to current phase (or next phase if completed)
   - Update last_completed_subtask
   - Record active blockers and next steps
   - Update active_agents list
   - Record git_head (current commit)
   - Set timestamp to session end time

3. **Append to DECISION_LOG.md**
   - For each decision made this session, append entry
   - Include outcome (if session ended before outcome determined, mark "pending")

4. **Update PRIORS.md** (if applicable)
   - For each case resolved by domain evaluator, write new prior
   - Reference the DECISION_LOG entry and evidence

5. **Reindex semantic index**
   - Scan DECISION_LOG.md for new entries
   - Scan PRIORS.md for new entries
   - Scan sessions/ for new session summaries
   - Rebuild SQLite index with cosine embeddings
   - Verify index is readable before session ends

### Session Recovery

Interruptions are expected. Every component is designed for fault tolerance.

**If session is interrupted mid-task**:

1. STATE.md has the last checkpoint (updated periodically via postToolUse hook)
2. DECISION_LOG.md has all decisions made up to interrupt point
3. Git history is ground truth for file state
4. New session reads STATE.md and picks up from last_completed_subtask
5. Previous session summary is available in sessions/ (though not yet written if session was interrupted)

**Recovery mechanism**:

- Hooks: sessionStart (read memory), postToolUse (periodic checkpoint), sessionEnd (write summary + update state)
- Implemented via Claude Code settings.json hook mechanism
- postToolUse hook triggers every 5 tool invocations or every 30 minutes, whichever comes first
- If interrupted before hook fires: STATE.md is from previous session, not current partial session

## Context Reset Protocol

Long-running projects span multiple phases (planning → architecture → building → deployment). Each phase has distinct tools, context, and artifacts.

**Problem**: Loading all prior phase outputs into context window causes exhaustion on large projects.

**Solution**: Explicit phase boundaries with context resets.

**Transition procedure**:

1. **End current phase**
   - Write phase outputs to named files: plan.md, architecture.md, validation-criteria.md, etc.
   - Append to DECISION_LOG with outcome of phase
   - Update STATE.md with phase=completed
   - Session ends and writes summary

2. **New session starts next phase**
   - Read STATE.md (mode=continue, phase={next-phase})
   - Load CLAUDE.md for the new phase
   - Load relevant spec docs for the new phase
   - Load previous phase artifacts as *files* (not in initial context, but available for Glob/Read)
   - Semantic index loads relevant decisions from DECISION_LOG

3. **STATE.md bridges the gap**
   - Previous phase state (git_head, completed tasks) is explicitly recorded
   - Next phase starts with full context via git history and STATE.md, not context accumulation

**Benefit**: Each phase operates with fresh context window; output of prior phases is available but not pre-loaded.

## Memory Scoping

Memory is **always per-project**. No shared state across projects.

**Scoping rules**:

- STATE.md location: `memory/{project-name}/STATE.md`
- DECISION_LOG.md location: `memory/{project-name}/DECISION_LOG.md`
- PRIORS.md location: `memory/{project-name}/PRIORS.md`
- Session summaries: `memory/{project-name}/sessions/`
- Semantic index: `memory/{project-name}/index.db` (SQLite file)
- Never copy, share, or reference STATE.md across projects
- Never copy, share, or reference DECISION_LOG across projects
- PRIORS.md is domain-specific; different projects learn different facts

**Multi-project concurrency** (v2 trigger):

- When running 3+ concurrent projects, implement SONA-style routing heuristics
- Orchestrator reads STATE.md for all active projects, selects which to resume
- Prevents context collisions between projects

## v2 Triggers and Future Work

v1 is intentionally minimal. These signals indicate readiness for v2 features.

**Trigger: SONA-style pattern routing** (3+ concurrent projects)
- When orchestrator is managing 3+ projects simultaneously, pattern matching can reduce decision latency
- Route new decisions to closest prior project, ask for delta instead of full context
- Requires DECISION_LOG from 3+ projects with similar decision types

**Trigger: Pattern library and auto-drafting** (5+ projects in same domain)
- Accumulate PRIORS.md from 5+ projects in the same domain (e.g., "Kubernetes deployments")
- Extract recurring decision patterns
- Auto-generate draft target and plan for new project in same domain
- Requires pattern extraction worker and similarity clustering

**Trigger: Session summary consolidation** (100+ session summaries per project)
- Consolidate old session summaries into era summaries (weekly, monthly rollups)
- Reduces index size and context load
- Requires consolidation worker and era summary schema
- Not needed for typical v1 projects (lifespan <50 sessions)

---

**Status**: v1 complete and production-ready.
**Next Review**: After 5 projects with complete memory trails.
**Maintenance**: Session hooks tested. Semantic index performance validated. No further changes anticipated before v2.
