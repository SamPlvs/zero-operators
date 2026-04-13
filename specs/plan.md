# Plan File Specification

## Overview

The `plan.md` file is the human's sole lever of control over a Zero Operators project. It is the equivalent of Karpathy's `program.md` in autoresearch — the single document that defines what agents should build, how success is measured, and what constraints apply. Everything else flows from this file.

The orchestrator reads `plan.md` at session start and uses it to decompose work into phases, spawn agents, configure oracle criteria, and enforce gates. If the human wants to change direction mid-project, they edit `plan.md`. Agents detect the delta and replan.

**Location:** `plans/{project-name}.md`

---

## Required Sections

Every plan.md must contain these sections. Missing required sections cause the orchestrator to halt and request human input before proceeding.

### 1. Project Identity

```yaml
---
project_name: "project-alpha"
version: "1.0"
created: "2026-04-09"
last_modified: "2026-04-09"
status: active | paused | completed
owner: "Sam"
---
```

The YAML frontmatter identifies the project and tracks its lifecycle. `status` is updated by the orchestrator when the project is paused or completed.

### 2. Objective

A clear, concise statement of what the project aims to achieve. This is not a vague mission statement — it defines the deliverable.

**Requirements:**
- State what is being built or researched (a model, a pipeline, a report, an analysis)
- State the domain and context (what problem this solves, for whom)
- State the expected output format (trained model, inference pipeline, report, codebase)
- Be specific enough that two different agents reading this section would agree on what "done" looks like

**Example:**
```markdown
## Objective

Build a soft sensor model that predicts real-time PO composition and purity
from process sensor data (DCS tags), calibrated against lab measurements
(SAP QM F5LB tag series). The model must operate in advisory mode (no DCS
writes) and produce predictions with quantified uncertainty at 1-minute
resolution.

Deliverables: trained model, inference pipeline, validation report, model
card, and drift detection logic.
```

### 3. Oracle Definition

The oracle is the hard, verifiable metric that determines success. Without this section, no autonomous work proceeds.

```markdown
## Oracle

**Primary metric:** RMSE on held-out lab samples
**Ground truth source:** SAP QM F5LB tag series (frozen at project start, 81,906 records)
**Evaluation method:** Evaluate on temporally disjoint held-out set (last 6 months of data)
**Target threshold:** RMSE ≤ 0.05 (Tier 1), RMSE ≤ 0.08 (Tier 2), RMSE ≤ 0.12 (Tier 3)
**Evaluation frequency:** After every training iteration
**Secondary metrics:** MAE, R², per-regime RMSE, prediction interval coverage

**Statistical significance:** Required. Compare to baseline with paired t-test, p < 0.05.
```

**Required fields:**
- **Primary metric**: Numerical, directional (lower-is-better or higher-is-better), unambiguous
- **Ground truth source**: Where correct answers come from. Must be immutable for the project duration
- **Evaluation method**: How the metric is computed. Reproducible and version-locked
- **Target threshold**: The number that constitutes "pass" per tier
- **Evaluation frequency**: When the oracle runs

**Optional fields:**
- **Secondary metrics**: Additional metrics logged but not gating
- **Statistical significance**: Whether improvement must be statistically significant and how

### 4. Workflow Configuration

Specifies how the project flows through the workflow phases defined in `specs/workflow.md`.

```markdown
## Workflow

**Mode:** classical_ml | deep_learning | research
**Phases:** default | [list of phases to include]
**Phase overrides:**
  - Skip: [phases to skip, e.g., "phase_0"]
  - Add: [phases to add, e.g., "deployment after phase_6"]

**Gates:**
  - Gate 2: blocking (human approval required)
  - Gate 3: automated (oracle threshold)
  - Gate 4: blocking (human approval required)

**Iteration budget:** 100 iterations or 48 GPU-hours, whichever comes first
**Human checkpoints:** After feature selection (Gate 2), after model approval (Gate 4)
```

**Required fields:**
- **Mode**: Determines which subtask sets are activated
- **Gates**: Which gates are blocking vs. informational

**Optional fields:**
- **Phase overrides**: Customizations to the default workflow
- **Iteration budget**: Max iterations or compute budget
- **Human checkpoints**: Where the human must approve before proceeding

### 5. Data Sources

Describes where data comes from, its format, and access requirements.

```markdown
## Data Sources

### Source 1: Process Sensor Data
- **Location:** /data/raw/ip21_historian_export.parquet
- **Format:** Parquet, ~15,601 DCS tags at 1-minute resolution
- **Time range:** 2021-01-01 to 2025-06-30 (4.5 years)
- **Access:** Read-only, static export (no live connection)
- **Known issues:** Bypass period flags in _MA tags, turnaround gaps

### Source 2: Lab Measurements
- **Location:** /data/raw/sap_qm_f5lb.csv
- **Format:** CSV, ~6-hour sampling cadence, 6 sample points per measurement
- **Time range:** Same as Source 1
- **Access:** Read-only
- **Known issues:** Excel serialisation date format requires correction
```

For each source, document: location, format, time range, access method, and known issues. This is what the Data Engineer reads first.

### 6. Domain Context and Priors

Seeds the initial `PRIORS.md` with domain knowledge that agents would not know from data alone.

```markdown
## Domain Priors

### Process Knowledge
- Post-turnaround (TA) periods represent a different operating regime
  (different catalyst state, different analyser baselines). Pre-TA and
  post-TA should be modelled as separate regimes or regime-conditioned.
- Bypassed tags (_MA suffix) indicate manual mode; data during bypass
  periods is unreliable and should be excluded.
- AC2658 spiking to 10 is a known false causal relationship; this tag
  should be excluded or treated with extreme caution.

### Expected Relationships
- Temperature and pressure tags in the reactor section should correlate
  positively with product purity.
- Flow rate tags should correlate with composition but with lag (~5-15 min
  depending on pipe length).
- Lab sample timing has ~30 min uncertainty due to manual collection.

### Known Risks
- APC loop coverage gap: some control loops may not be represented in
  selected tags. Flag if model performance varies by APC status.
- Sensor drift over time: calibration events create step changes in
  some temperature and pressure sensors.
```

This section is critical. It encodes knowledge that would take agents many iterations to discover (or never discover). The orchestrator copies this into `memory/{project}/PRIORS.md` at project initialisation.

### 7. Agent Configuration

Specifies which agents are active and any project-specific overrides, custom specialists, or adaptations for existing agents.

```markdown
## Agents

**Active agents:** lead-orchestrator, data-engineer, model-builder, oracle-qa, xai-agent, domain-evaluator
**Phase-in agents:** xai-agent, domain-evaluator (activate after Gate 3 passes)
**Inactive agents:** ml-engineer, infra-engineer (not needed for v1)

**Agent overrides:**
  - model-builder: Use Opus (complex architecture decisions expected)
  - data-engineer: Use Sonnet (standard data pipeline work)

**Custom agents:**
- signal-analyst: Sonnet — Signal processing specialist for vibration/acoustic FFT analysis
- calibration-expert: Opus — Sensor calibration and drift correction specialist

**Agent adaptations:**

- xai-agent:
  Focus on frequency-domain attribution, spectrograms, and vibration-mode
  decomposition. Generic SHAP/GradCAM is less relevant for time-series
  signal data. Include bearing failure envelope plots in the Phase 5
  analysis report.

- domain-evaluator:
  Apply IVL F5 vibration priors — bearing failure signatures via envelope
  demodulation, modal frequency ranges 20-2000Hz, known sensor drift
  patterns. Flag predictions that contradict these priors.
```

If the Agent Configuration section is absent, the orchestrator uses the default team from `specs/agents.md`.

**Three independent knobs inside the section:**

1. **Active / phase-in / inactive** — pick which core agents run.
2. **Custom agents** — add NEW agent roles the project needs (e.g. domain specialists). The orchestrator auto-creates `.claude/agents/custom/{name}.md` from each entry at build start. Reusable across projects.
3. **Agent adaptations** — tailor EXISTING core or custom agents for this project's domain. The adaptation text is appended to the agent's base spawn prompt at build time; the agent's `.md` file is unchanged. Typically used for `xai-agent` and `domain-evaluator` which are generic by default and need project context to produce meaningful output.

Custom agents and adaptations are complementary: custom agents extend the roster; adaptations tailor existing members. The Plan Architect proposes both during `zo draft` based on Research Scout + Data Scout findings.

### 8. Constraints

Hard constraints that agents must respect at all times.

```markdown
## Constraints

- **No live system access:** Advisory only. No DCS writes, no real-time connections.
- **Data is static:** All data is pre-exported. No incremental data loading.
- **PyTorch only:** All models must use PyTorch. No TensorFlow, no scikit-learn
  for final models (sklearn OK for preprocessing and feature selection).
- **Reproducibility:** All experiments must be reproducible with fixed random seeds.
- **GPU budget:** Maximum 100 GPU-hours total across all training.
- **Delivery repo clean:** No ZO artefacts in the delivery repository.
```

Constraints are non-negotiable. Agents cannot override them. If a constraint makes a task impossible, the agent escalates to the orchestrator, who escalates to the human.

---

## Optional Sections

These sections are included based on project needs.

### 9. Milestones and Timeline

```markdown
## Milestones

| Week | Milestone | Gate |
|------|-----------|------|
| 1-2 | Data review and pipeline complete | Gate 1 |
| 3 | Feature selection approved by process engineer | Gate 2 |
| 4-6 | Model training and iteration | Gate 3 |
| 7 | Explainability validation and human approval | Gate 4 |
| 8 | Packaging and delivery | Final |
```

Milestones are informational. Agents do not skip work to meet deadlines. If a milestone is missed, the orchestrator logs the delay and notifies the human.

### 10. Delivery Specification

```markdown
## Delivery

**Target repo:** ../ivl_f5/
**Target branch:** main
**Delivery structure:**
  - src/models/ — trained model checkpoint
  - src/inference.py — prediction pipeline
  - reports/validation_report.md — oracle results and analysis
  - reports/model_card.md — model documentation
  - tests/ — automated test suite
```

Maps to the target file in `targets/{project-name}.target.md`.

### 11. Dependencies and Environment

```markdown
## Environment

**Python version:** 3.11+
**Key dependencies:** torch>=2.0, pandas, numpy, shap, fastembed
**Hardware:** Single NVIDIA A100 (or equivalent)
**Package manager:** uv
**Linting:** ruff
```

### 12. Open Questions

```markdown
## Open Questions

- Should we train separate models per regime or a single model with regime
  as a feature? (Decision needed before Phase 3)
- What is the acceptable latency for real-time inference? (Needed for
  packaging constraints)
- Should drift detection trigger automatic retraining or just alerting?
```

Open questions are logged to `DECISION_LOG.md` when they're resolved. Agents can flag new open questions during execution.

---

## Plan Update Protocol

The human can edit `plan.md` at any time. When the orchestrator detects a change:

1. **Diff detection:** Compare current plan.md against last-read version (stored in STATE.md)
2. **Impact assessment:** Determine which phases, agents, or constraints are affected
3. **Replan:** Produce a revised execution plan showing what changes
4. **Human confirmation:** Present the replan to the human for approval before executing
5. **Log:** Record the plan change and replan decision in DECISION_LOG.md

Changes to the oracle definition or constraints during active training trigger an immediate pause and human review.

---

## Validation

The orchestrator validates plan.md at project initialisation:

- [ ] All required sections present (1-8)
- [ ] Oracle definition has all required fields
- [ ] Workflow mode is valid
- [ ] At least one data source specified
- [ ] At least one agent active
- [ ] Target repo path exists and is accessible
- [ ] No contradictions between constraints and workflow configuration

If validation fails, the orchestrator halts and reports missing or invalid sections to the human.

---

## Summary

The plan.md is the contract between human and system. It defines the objective, success criteria, data, domain knowledge, team, constraints, and workflow. Agents read it; they do not write it. The human writes it; they do not execute it. Every autonomous decision traces back to something specified (or implied) by this file.
