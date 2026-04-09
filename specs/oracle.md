# Oracle / Verification Framework

## The Oracle Principle

The entire Zero Operators architecture rests on a single foundational insight: autonomous agents can confidently iterate without human oversight only when success is unambiguous and verifiable.

This principle is borrowed from Karpathy's autoresearch framework. In that work, agents could run unsupervised because the metric was hardened and objective—not interpretable in debate, not soft in judgment, but mechanically measurable. Every project using Zero Operators must establish the same foundation.

Without a near-perfect oracle, autonomous agents will ship regressions with confidence. They will optimize against proxies. They will mistake correlation for causation and call it done. The oracle is not a nice-to-have. It is architectural.

**The oracle replaces "did tests pass?" (soft signal) with "is the metric lower/higher?" (hard signal).**

## Oracle Definition Per Project

Every project's `plan.md` must declare four components of its oracle before agents begin work:

| Component | Definition | Example |
|-----------|-----------|---------|
| **Primary Metric** | What is being measured. Unambiguous, numerical, directional. | RMSE on held-out set; F1 on imbalanced test data; p95 latency in milliseconds |
| **Ground Truth Source** | Where the correct answer comes from. Immutable reference. | Validation dataset (frozen at project start); production logs (time-windowed); expert labels (v1 locked, no retraining) |
| **Evaluation Method** | How the metric is computed. Reproducible, version-locked. | 5-fold cross-validation on fixed splits; evaluation on held-out year-2025 data only; latency measured on reference hardware |
| **Target Threshold** | The number that constitutes "pass". Explicit, tied to business requirement. | Accuracy ≥ 92%; F1 ≥ 0.85; p95 latency ≤ 250ms |
| **Evaluation Frequency** | When the oracle runs. Regular cadence. | After every iteration; after every 5 training runs; hourly during active development |

Each of these must be stated explicitly in `plan.md` before work begins. Ambiguity at definition time propagates as confusion at decision time.

## Tiered Success Criteria

The oracle validates three levels of system performance. Each tier tests progressively harder requirements.

| Tier | Typical Threshold | What It Tests |
|------|------------------|---------------|
| **Tier 1** | ≥80% | Core accuracy. Can the system produce correct outputs for standard, expected inputs? Covers the main distribution. |
| **Tier 2** | ≥70% | Operational utility. Does the system handle edge cases, rare transitions, moderate anomalies? Real-world robustness. |
| **Tier 3** | ≥60% | Robustness under stress. Performance with missing data, boundary cases, distribution shift, unusual conditions. |

Thresholds are project-configurable in `plan.md`. Each project may raise or lower these bands based on domain requirements.

**Progression rule:** Tier 1 is the minimum gate for autonomous proceed. If Tier 1 passes, the orchestrator may authorize the next phase or continued iteration. If Tier 1 fails, iteration continues or the human is escalated.

Tier 2 and Tier 3 are informational by default—logged to `DECISION_LOG.md`—but may be promoted to blocking gates per project.

## Oracle Gating

The oracle runs automatically after each iteration (or after every N iterations, per `plan.md`).

**Flow:**

1. Agent reports: "Work complete."
2. Orchestrator triggers oracle evaluation.
3. Oracle computes primary metric on ground truth source.
4. Result is compared to target threshold (Tier 1 required; Tier 2/3 optional).

**Decision logic:**

- **Tier 1 passes**: Proceed to next phase, or continue iteration if improvement is still possible.
- **Tier 1 fails**: Orchestrator decides—iterate again with modified approach, change strategy, or escalate to human.

**The oracle blocks progression.** Agents cannot skip it or override it. It is not advice; it is a hard gate.

All oracle results are logged to `DECISION_LOG.md` with full metric breakdown: metric value, threshold, pass/fail status, timestamp, and which agent/iteration generated the result.

## Drift Detection Oracle (Optional, Deployment Only)

For projects in deployed or monitoring use cases, a drift detection oracle may be configured.

**Purpose:** Validate that the system correctly identifies known drift events in held-out test data.

**Mechanics:** The project provides a held-out dataset containing X known drift scenarios (e.g., out-of-distribution shifts, concept drift, label shift). The oracle flags drift and compares detections to ground truth. Pass/fail: Y out of X scenarios correctly identified.

**Configuration:** Defined in `plan.md` only if the project is actively monitoring deployed systems. Not required for offline research or batch workflows.

## Validation Loop Pattern

After any agent reports "work complete", the orchestrator executes the full validation loop:

1. **Agent-level validation**: Did the agent's own pre-defined checklist pass? (Self-validation.)
2. **Oracle validation**: Does the output meet the metric threshold? (Primary gate.)
3. **Cross-review**: Another agent reviews the work adversarially. (Human proxy.)
4. **Integration validation**: Does the work integrate cleanly with prior work? No breaking changes?

This is the coleam00 validation pattern applied to research and ML work. All four gates must pass; failure at any stage triggers iteration or escalation.

## Anti-Patterns

**Running without an oracle.** Do not schedule autonomous work with the intention to "evaluate later." The oracle must exist before agents start. If it does not exist, stop and define it. This is not optional.

**Using soft signals as oracle.** "Tests pass" is not an oracle. "Looks good to the reviewer" is not an oracle. "No errors thrown" is not an oracle. These are checks, not metrics. An oracle is numerical, directional, and reproducible.

**Adjusting the threshold to match results.** The threshold is set before evaluation. If the system misses the threshold, the system must improve—not the threshold. Threshold adjustment is prohibited except in the plan update cycle (at project start or formal review).

**Skipping Tier 2 and Tier 3 because Tier 1 passed.** This is allowed but not recommended. Tier 2 and Tier 3 catch corner-case brittleness that may hide in production. Log them at minimum; make them blocking if the project domain is safety-critical or operates under distribution shift.

---

*Last Updated: 2026-04-09*
