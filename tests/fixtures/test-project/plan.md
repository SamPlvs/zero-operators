---
project_name: "churn-prediction"
version: "1.0"
created: "2026-04-01"
last_modified: "2026-04-09"
status: active
owner: "TestEngineer"
---

## Objective

Build a customer churn prediction model for a SaaS product. The model should
identify customers likely to cancel within 30 days so the retention team can
intervene with targeted offers.

## Oracle Definition

**Primary metric:** ROC-AUC
**Ground truth source:** historical cancellation labels from billing system
**Evaluation method:** stratified 5-fold cross-validation
**Target threshold:** > 0.8
**Evaluation frequency:** per training iteration
**Secondary metrics:** precision at 80% recall
**Statistical significance:** p < 0.05 via paired t-test across folds

## Workflow Configuration

**Mode:** classical_ml

Phases:
1. Data ingestion and cleaning
2. Feature engineering
3. Model selection and training
4. Evaluation against oracle
5. Deployment artefact packaging

## Data Sources

### Customer Activity Logs

- **Location:** data/raw/activity_logs.parquet
- **Format:** Parquet, ~500k rows
- **Update cadence:** daily snapshot
- **Key columns:** customer_id, event_type, timestamp, session_duration

### Billing Records

- **Location:** data/raw/billing.csv
- **Format:** CSV, ~50k rows
- **Update cadence:** monthly export
- **Key columns:** customer_id, plan_tier, mrr, churn_date

## Domain Context and Priors

- Churn rates in SaaS typically range 5-7% monthly for SMB segments.
- Usage drop-off in the 14 days before cancellation is the strongest single signal.
- Contract customers (annual plans) have structurally different churn patterns
  than month-to-month subscribers; the model should handle both segments.
- Class imbalance is expected (~6% positive rate); use appropriate sampling
  or loss weighting.

## Agent Configuration

**Active agents:** lead-orchestrator, data-engineer, model-builder, oracle-qa

Agent responsibilities:
- **lead-orchestrator**: coordinates phases, manages gates
- **data-engineer**: ingestion, cleaning, feature pipelines
- **model-builder**: model selection, training, hyperparameter search
- **oracle-qa**: evaluation, drift detection, gate verdicts

## Constraints

- No live database access; all data must come from static exports.
- Model training must complete within 2 hours on a single GPU.
- No PII in model features; customer_id used only as a join key.
- All artefacts must be reproducible from a fixed random seed (42).
