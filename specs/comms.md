# Communication, Logging, and Reporting

## Overview

This document specifies how Zero Operators agents communicate with each other, how their actions are logged for audit and debugging, and how reports are structured for human consumption. All communication flows through structured channels; no implicit side-effects or silent coordination.

---

## Agent Communication Patterns

### Peer-to-Peer Messaging

Agents communicate via Claude Code's native agent team session context. Every message between agents follows a structured format and is logged to the JSONL audit trail.

**Message types:**

| Type | Sender → Receiver | Purpose |
|------|-------------------|---------|
| `request` | Any → Any | Ask another agent to perform work or provide data |
| `response` | Any → Requester | Return results from a request |
| `status` | Any → Orchestrator | Report progress, completion, or blockers |
| `escalation` | Any → Orchestrator | Flag a problem that requires human or cross-agent resolution |
| `broadcast` | Orchestrator → All | Announce phase changes, gate results, or go/no-go decisions |
| `verdict` | Oracle → Orchestrator | Structured pass/fail evaluation result |

### Communication Rules

1. **All messages are logged.** No off-the-record communication. Every agent interaction is appended to the daily JSONL file.
2. **Direct messaging for data exchange.** When Agent A needs output from Agent B, Agent A sends a `request`; Agent B responds with a `response` containing file paths or inline data.
3. **Orchestrator relay for conflicts.** If two agents disagree (e.g., Model Builder disputes Oracle's verdict), both escalate to Orchestrator. Orchestrator mediates and logs the resolution.
4. **Adversarial debate protocol.** For high-stakes disagreements, Orchestrator can invoke a structured debate: each agent states position with evidence, Orchestrator synthesizes, decision is logged with both positions preserved.
5. **No implicit coordination.** Agents do not watch each other's files for changes. All coordination flows through explicit messages.

---

## JSONL Audit Schema

Every agent action, message, and decision is logged to a daily JSONL file at `logs/comms/{YYYY-MM-DD}.jsonl`. One JSON object per line. Append-only; never edit or delete entries.

### Base Schema

Every log entry includes these fields:

```json
{
  "timestamp": "2026-04-09T14:32:15.123Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "message | decision | gate | error | checkpoint",
  "agent": "lead-orchestrator",
  "project": "project-alpha"
}
```

### Message Events

Logged when agents communicate:

```json
{
  "timestamp": "2026-04-09T14:32:15.123Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "message",
  "agent": "model-builder",
  "project": "project-alpha",
  "message_type": "request",
  "recipient": "data-engineer",
  "subject": "Need updated DataLoader with regime splits",
  "body": "Phase 3 requires regime-segmented DataLoaders. Please produce train/val/test loaders partitioned by operating_mode field.",
  "priority": "normal",
  "references": ["decision-2026-04-09-001"]
}
```

### Decision Events

Logged when an agent or the orchestrator makes a significant decision:

```json
{
  "timestamp": "2026-04-09T15:01:00.000Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "decision",
  "agent": "lead-orchestrator",
  "project": "project-alpha",
  "decision_id": "decision-2026-04-09-002",
  "title": "Proceed to Phase 3 after Gate 2 pass",
  "rationale": "Human approved feature list with no changes. All Phase 2 artifacts verified.",
  "alternatives": ["Iterate Phase 2 with expanded feature set", "Request additional domain review"],
  "outcome": "proceed",
  "confidence": "high"
}
```

### Gate Events

Logged when an oracle gate is evaluated:

```json
{
  "timestamp": "2026-04-09T16:45:00.000Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "gate",
  "agent": "oracle-qa",
  "project": "project-alpha",
  "gate_id": "gate-3",
  "gate_name": "Oracle Metric Threshold",
  "metric_name": "RMSE",
  "metric_value": 0.042,
  "threshold": 0.05,
  "tier": 1,
  "result": "pass",
  "breakdown": {
    "regime_a": 0.038,
    "regime_b": 0.051,
    "regime_c": 0.039
  },
  "notes": "Regime B marginally above threshold; overall passes."
}
```

### Error Events

Logged when something fails:

```json
{
  "timestamp": "2026-04-09T14:50:00.000Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "error",
  "agent": "data-engineer",
  "project": "project-alpha",
  "error_type": "data_validation",
  "severity": "blocking",
  "description": "Sensor 12 data contains 45% NaN values in Q3 2025 window",
  "affected_artifacts": ["data/processed/sensor_12.parquet"],
  "resolution": "pending",
  "escalated_to": "lead-orchestrator"
}
```

### Checkpoint Events

Logged periodically during long sessions (triggered by postToolUse hook):

```json
{
  "timestamp": "2026-04-09T15:30:00.000Z",
  "session_id": "session-2026-04-09-143000",
  "event_type": "checkpoint",
  "agent": "model-builder",
  "project": "project-alpha",
  "phase": "phase-4-iteration",
  "subtask": "iteration-17",
  "progress": "17/100 iterations complete",
  "current_best_metric": 0.058,
  "target_metric": 0.05,
  "blockers": []
}
```

---

## Reporting Standards

### Session Reports

At session end, the orchestrator produces a structured session report. This report is written to `memory/{project}/sessions/session-{timestamp}.md` (see memory.md for schema). The JSONL log is the raw data; the session summary is the human-readable narrative.

### Gate Review Documents

Before each human checkpoint, the orchestrator assembles a gate review document summarizing everything the human needs to decide. Structure:

```markdown
# Gate Review: {Gate Name}
**Date**: {date}
**Phase**: {phase number and name}
**Prepared by**: Lead Orchestrator

## Summary
{1-2 sentence overview of what happened and what decision is needed}

## Key Metrics
{Table of relevant metrics, thresholds, and pass/fail status}

## Artifacts for Review
{Links to artifacts the human should examine}

## Flagged Issues
{Any concerns, anomalies, or disagreements between agents}

## Recommendation
{Orchestrator's recommendation: proceed, iterate, or escalate}

## Decision Required
{Explicit statement of what the human must decide}
```

### Iteration Reports

During Phase 4 (iteration loop), the orchestrator produces periodic iteration summaries when the loop pauses or completes:

```markdown
# Iteration Report
**Iterations completed**: {N}
**Best metric**: {value} (target: {threshold})
**Metric trajectory**: {improving / plateauing / diverging}

## Top 3 Candidates
| Rank | Config | Metric | Notes |
|------|--------|--------|-------|
| 1 | ... | ... | ... |
| 2 | ... | ... | ... |
| 3 | ... | ... | ... |

## Flagged Issues
{Any data leakage, overfitting, divergence, or anomalies}

## Recommendation
{Continue iterating / change approach / escalate to human}
```

---

## Explainability Output Levels

Explainability reports (Phase 5) are structured in three tiers of detail to serve different audiences.

### Level 1: Executive Summary

For non-technical stakeholders:
- Top 5 features driving model predictions (plain language)
- Model accuracy in business terms (e.g., "correct 94% of the time on standard inputs")
- Any red flags or caveats (plain language)
- 1-page maximum

### Level 2: Technical Summary

For domain experts and engineers:
- Full SHAP feature importance ranking with values
- Domain consistency check results (agreement/disagreement per feature)
- Data corroboration results (correlation vs. SHAP sign alignment)
- Magnitude plausibility assessment
- Key visualizations (SHAP summary plot, top feature dependence plots)
- 3-5 pages

### Level 3: Full Analysis

For audit, reproducibility, and deep review:
- All SHAP plots (force plots, dependence plots, interaction plots)
- Per-regime explainability breakdown
- Complete correlation vs. SHAP comparison tables
- Raw SHAP values exported as CSV
- Statistical significance of feature contributions
- Full methodology description
- Unlimited length; stored as directory of artifacts

Each project's `plan.md` specifies which levels are required. Default: Level 2 is always produced; Level 1 and Level 3 are optional.

---

## Log Retention and Maintenance

### Retention Policy

- **JSONL logs**: Retained indefinitely per project. Append-only; no deletion.
- **Session summaries**: Retained indefinitely. Consolidated into era summaries at 100+ sessions (v2 feature, see memory.md).
- **Gate review documents**: Retained with project artifacts in delivery repo reports/ directory.
- **Iteration reports**: Retained in memory/{project}/sessions/.

### Log Rotation

Daily JSONL files prevent unbounded file sizes. Each day starts a new file (`logs/comms/{YYYY-MM-DD}.jsonl`). The semantic index (see memory.md) indexes across all daily files.

### Log Querying

Logs are queryable via:
1. **grep/jq**: For exact matches on event_type, agent, decision_id, etc.
2. **Semantic search**: Via fastembed+SQLite index for natural language queries ("what errors occurred during feature selection?")
3. **Structured queries**: Filter by timestamp range, agent, event type, severity

---

## Summary

All agent communication is explicit, structured, and logged. The JSONL audit trail is the system's source of truth for what happened and why. Reports distill raw logs into human-readable summaries at appropriate detail levels. No implicit coordination, no silent failures, no unlogged decisions.
