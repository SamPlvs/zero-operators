# Self-Evolving System Specification

## Overview

Zero Operators does not just fix bugs—it updates the rules that allowed them. When an agent encounters a failure, the system performs a post-mortem that produces both an immediate fix and a rule update to prevent recurrence. This document specifies the mechanism for self-evolution: how rules are updated, who updates them, what gets updated, and how updates are validated.

---

## The Self-Evolution Principle

Most agent systems fix symptoms and move on. The same failure recurs in the next session because the underlying rule, spec, or prior was never corrected.

Zero Operators breaks this cycle:

1. **Fix the immediate problem** (patch the code, retrain the model, correct the data)
2. **Identify the root cause** (why did the system allow this to happen?)
3. **Update the rule** (modify the spec, prior, or agent instruction that permitted the failure)
4. **Verify the update** (confirm the updated rule would have caught the original failure)

This is not optional. Every error that reaches escalation triggers the post-mortem protocol.

---

## Post-Mortem Protocol

### Trigger Conditions

A post-mortem is triggered when any of the following occur:

- An oracle gate fails (Tier 1 threshold not met)
- A contract violation is detected (agent writes to off-limits path, produces malformed output)
- A human rejects work at a checkpoint (feature list rejected, model rejected, report rejected)
- An agent escalates an unresolvable error to the orchestrator
- A session recovery detects state inconsistency (git_head mismatch, missing artifacts)
- A previously resolved issue recurs (same error pattern detected in DECISION_LOG)

### Post-Mortem Steps

**Step 1: Document the failure**

The agent that detected the failure (or the orchestrator, if escalated) writes a failure entry to `DECISION_LOG.md`:

```markdown
## Failure: {short title}
**Timestamp**: {ISO 8601}
**Detected by**: {agent name}
**Severity**: critical | major | minor
**Phase**: {phase where failure occurred}
**Description**: {what went wrong}
**Immediate impact**: {what was blocked or broken}
**Artifacts affected**: {file paths}
```

**Step 2: Root cause analysis**

The orchestrator (or designated agent) investigates:

- What rule, spec, or prior should have prevented this?
- Was the rule missing, incomplete, or incorrectly specified?
- Did an agent ignore an existing rule? If so, why?
- Is the failure a novel case (no prior coverage) or a regression (known issue recurring)?

Root cause is documented as part of the DECISION_LOG entry:

```markdown
**Root cause**: {explanation}
**Rule gap**: {which spec or prior was missing or wrong}
**Category**: missing_rule | incomplete_rule | ignored_rule | novel_case | regression
```

**Step 3: Implement the fix**

The responsible agent fixes the immediate issue:
- Code fix, data correction, model retrain, or artifact regeneration
- Fix is validated (tests pass, oracle re-run, artifact verified)
- Fix is committed and logged

**Step 4: Update the rule**

Based on root cause category, the orchestrator updates the appropriate document:

| Category | Document to Update | Action |
|----------|-------------------|--------|
| `missing_rule` | PRIORS.md or relevant spec | Add new rule with evidence |
| `incomplete_rule` | Relevant spec or agent definition | Expand existing rule with the missing case |
| `ignored_rule` | Agent definition (.md) | Strengthen instruction; add explicit "must not" clause |
| `novel_case` | PRIORS.md | Add new prior documenting the novel case and resolution |
| `regression` | PRIORS.md + agent definition | Add regression guard and explicit reference to prior failure |

**Step 5: Verify the update**

The orchestrator validates that the updated rule would have caught the original failure:
- Re-read the updated rule in context of the original failure scenario
- Confirm the rule is specific enough to trigger (not vague or overbroad)
- If possible, simulate the failure scenario against the updated rule
- Log verification result to DECISION_LOG

---

## What Gets Updated

### PRIORS.md Updates

Domain-specific knowledge learned from failures:

```markdown
## Prior: {category}
**Statement**: {factual claim derived from failure}
**Evidence**: {reference to failure event and resolution}
**Confidence**: high | medium | low
**Added after failure**: {DECISION_LOG entry reference}
**Prevents recurrence of**: {brief description of original failure}
```

Examples:
- "Sensor 12 data is unreliable during Q3 due to scheduled maintenance windows" (learned after data quality failure)
- "VIF threshold of 10 is insufficient for this domain; use 5" (learned after multicollinearity caused model instability)
- "SHAP values for lagged features require temporal correction" (learned after explainability inconsistency)

### Spec File Updates

Structural or procedural changes to how the system operates:

- **workflow.md**: Add a subtask, modify a gate threshold, insert a validation step
- **agents.md**: Strengthen agent instructions, add a "must not" clause, clarify ownership boundaries
- **oracle.md**: Adjust evaluation method, add a secondary metric, tighten threshold
- **comms.md**: Add a new event type, modify logging schema, add a reporting requirement
- **architecture.md**: Modify isolation rules, update target file schema, add a new path to blocklist

Every spec update includes a changelog entry at the bottom of the file:

```markdown
---
## Changelog
- {date}: Added {rule/section} after {failure reference}. Prevents {recurrence description}.
```

### Agent Definition Updates

Changes to agent behavior encoded in `.claude/agents/{agent}.md`:

- Add explicit constraints ("Never proceed without checking correlation matrix")
- Add references to new priors ("Before feature selection, read PRIORS.md section on multicollinearity thresholds")
- Strengthen validation checklists ("Verify temporal disjointness of train/test split before reporting complete")

---

## Rule Update Governance

### Who Can Update What

| Document | Who Updates | When |
|----------|------------|------|
| PRIORS.md | Domain Evaluator (primary), Orchestrator (fallback) | After any domain-related failure or QUESTIONABLE resolution |
| Spec files (workflow, agents, oracle, comms, architecture) | Orchestrator only | After post-mortem Step 4, with logged rationale |
| Agent definitions (.claude/agents/*.md) | Orchestrator only | After post-mortem identifies agent instruction gap |
| CLAUDE.md | Human only | During planned review cycles (not during sessions) |
| plan.md | Human only | At project start or planned revision points |

### Update Constraints

1. **Never delete rules.** Mark as superseded if knowledge changes. Deletion loses institutional memory.
2. **Always reference the failure.** Every rule update must cite the DECISION_LOG entry that triggered it.
3. **Keep rules specific.** "Be more careful" is not a rule. "Check VIF < 5 before approving feature list" is a rule.
4. **Test the rule.** Before finalizing, verify the rule would have caught the original failure.
5. **One update per failure.** Avoid shotgun updates that modify multiple unrelated rules. Each failure produces one targeted update.

---

## Evolution Tracking

### Evolution Log

Every rule update is tracked in a dedicated section of DECISION_LOG.md (tagged with `evolution` category):

```markdown
## Evolution: {short title}
**Timestamp**: {ISO 8601}
**Triggered by**: {failure DECISION_LOG reference}
**Document updated**: {file path}
**Change**: {description of what was added/modified}
**Rationale**: {why this prevents recurrence}
**Verified**: yes | no
**Verification method**: {how it was verified}
---
```

### Evolution Metrics

Over time, the orchestrator can extract evolution health metrics from the log:

- **Total rule updates**: How many rules have been added or modified
- **Regression rate**: How often a previously fixed failure recurs (target: 0%)
- **Coverage growth**: How many PRIORS.md entries exist per session count
- **Update categories**: Distribution of missing_rule vs. incomplete_rule vs. ignored_rule
- **Time to update**: How quickly post-mortem produces a rule update after failure detection

These metrics are informational in v1. In v2, they may feed into self-learning routing (SONA-style) to predict which rules are most likely to need updating for a given project type.

---

## Retrospective Protocol

At the end of each project (or at defined milestones), the orchestrator runs a retrospective:

### Retrospective Steps

1. **Scan DECISION_LOG** for all entries tagged `failure` or `evolution`
2. **Categorize failures** by root cause category (missing_rule, incomplete_rule, etc.)
3. **Identify patterns**: Are failures clustering in a specific phase? Agent? Domain area?
4. **Propose systemic updates**: If a pattern emerges (e.g., 3+ failures related to data alignment), propose a structural change (add a mandatory subtask, strengthen a gate, create a new skill)
5. **Human review**: Present retrospective findings to human for approval of systemic changes
6. **Implement approved changes**: Update specs, agent definitions, or workflow

### Retrospective Output

```markdown
# Project Retrospective: {project-name}
**Date**: {date}
**Sessions completed**: {count}
**Total failures**: {count}
**Total rule updates**: {count}

## Failure Distribution
| Category | Count | Example |
|----------|-------|---------|
| missing_rule | ... | ... |
| incomplete_rule | ... | ... |
| ... | ... | ... |

## Patterns Identified
{Description of recurring failure patterns and proposed systemic fixes}

## Recommended Systemic Updates
{Specific changes to specs, agents, or workflow}

## Lessons for Future Projects
{Domain-agnostic insights that apply to all ZO projects}
```

---

## v2 Evolution Features

### Automated Pattern Detection

When 5+ projects have completed with full evolution logs, implement automated pattern detection:
- Cluster similar failures across projects
- Identify rules that are frequently missing at project start
- Auto-generate "starter PRIORS.md" templates for new projects in similar domains

### Cross-Project Rule Propagation

When a rule update in one project is domain-agnostic (e.g., "always check for temporal leakage in train/test splits"), propagate it to a global rules library that seeds new projects.

### Evolution Confidence Scoring

Track which rule updates actually prevented recurrence vs. those that were never tested. Assign confidence scores to rules based on their track record. Low-confidence rules are flagged for review during retrospectives.

---

## Summary

Self-evolution is not aspirational—it is a defined protocol with concrete steps, clear ownership, and tracked outcomes. Every failure produces a fix and a rule update. Every rule update references the failure that triggered it. Every retrospective reviews the system's learning trajectory. The goal is a system that gets measurably better with each project, not one that repeats the same mistakes.
