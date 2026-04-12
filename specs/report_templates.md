# Report Templates

Comprehensive report structures for agents producing phase output reports. Each template defines **required sections** — agents must fill in every section, marking any as "N/A" with a rationale if not applicable.

Reports are markdown files written to `{delivery_repo}/reports/`. They are the primary deliverables humans review at gate checkpoints.

---

## Phase 1: Data Quality Report

**File**: `reports/data_quality_report.md`
**Owner**: Data Engineer (primary), Domain Evaluator (review)
**When**: After all Phase 1 subtasks complete, before Gate 1

### Required Sections

```markdown
# Data Quality Report

Project: {project_name}
Generated: {timestamp}
Data source: {source description}

## 1. Schema Validation

### Expected vs Actual Columns

| Column       | Expected | Actual | Dtype Expected | Dtype Actual | Valid Range     | Status |
|-------------|----------|--------|----------------|-------------|-----------------|--------|
| temperature | Yes      | Yes    | float64        | float64     | [-50, 60]       | PASS   |
| sensor_id   | Yes      | Yes    | int64          | object      | —               | FAIL   |

### Schema Issues
- {List any dtype mismatches, unexpected columns, missing columns}
- Action taken: {e.g. "Cast sensor_id to int64, dropped 3 rows with non-numeric values"}

## 2. Completeness Analysis

### Missing Values Summary

| Feature      | Count | Percentage | Pattern          | Mechanism |
|-------------|-------|-----------|------------------|-----------|
| temperature | 45    | 0.3%      | Random           | MCAR      |
| pressure    | 1200  | 8.1%      | Systematic (sensor 5 offline) | MAR |

### Imputation Strategy

| Feature   | Method            | Rationale                              |
|-----------|-------------------|----------------------------------------|
| temperature | Linear interpolation | Small gaps, smooth signal            |
| pressure  | Forward fill + flag | Sensor outage, flag preserves info   |

## 3. Distribution Analysis

### Per-Feature Statistics

| Feature      | Mean   | Std    | Median | Skew  | Kurtosis | Normality (p) | Type       |
|-------------|--------|--------|--------|-------|----------|---------------|------------|
| temperature | 22.3   | 5.1    | 22.0   | 0.12  | 2.98     | 0.42          | Normal     |
| vibration   | 0.045  | 0.089  | 0.012  | 3.41  | 15.2     | <0.001        | Heavy-tail |

### Distribution Notes
- {Flag any bimodal distributions, heavy tails, or unexpected shapes}
- {Recommend transformations if needed: log, Box-Cox, etc.}

## 4. Outlier Analysis

### Detection Results

| Feature    | Method | Threshold | Outliers | Percentage | Treatment   | Rationale           |
|-----------|--------|-----------|----------|-----------|-------------|---------------------|
| vibration | IQR    | 1.5x      | 234      | 1.6%      | Cap at P99  | Physical max exists |
| pressure  | Z-score| 3.0       | 12       | 0.08%     | Keep        | Valid extreme events|

### Impact Assessment
- {How do outlier treatments affect feature distributions?}
- {Any domain reason to keep extreme values?}

## 5. Target / Class Analysis

### Class Distribution

| Class      | Count  | Percentage | Ratio to Minority |
|-----------|--------|-----------|-------------------|
| Normal    | 12,450 | 83.0%     | 4.9x             |
| Anomaly   | 2,550  | 17.0%     | 1.0x (minority)  |

### Imbalance Assessment
- Imbalance ratio: {X:1}
- Strategy: {oversampling / undersampling / class weights / focal loss}
- Rationale: {why this strategy for this data}

## 6. Temporal Analysis

{Mark "N/A — non-temporal dataset" if not applicable}

### Time Coverage
- Date range: {start} to {end}
- Resolution: {e.g. 1 second, 1 minute, daily}
- Total records: {N}

### Gaps and Duplicates
- Gaps detected: {count, longest gap, total missing time}
- Duplicate timestamps: {count, action taken}

### Temporal Patterns
- Trend: {increasing / decreasing / stationary}
- Seasonality: {detected period or "none detected"}
- Stationarity test: {ADF p-value, KPSS result}

## 7. Correlation and Multicollinearity

### Top Correlated Feature Pairs

| Feature A   | Feature B   | Correlation | Action        |
|------------|------------|-------------|---------------|
| temp_inlet | temp_outlet| 0.97        | Drop one      |
| pressure_1 | pressure_2 | 0.91        | Keep both (different sensors) |

### Multicollinearity (VIF)

| Feature    | VIF   | Action |
|-----------|-------|--------|
| temp_inlet| 12.3  | Remove |
| pressure  | 3.1   | Keep   |

### Target Correlations

| Feature      | Correlation with Target | Rank |
|-------------|------------------------|------|
| vibration   | 0.72                   | 1    |
| temperature | 0.45                   | 2    |

## 8. Drift Baseline

### Reference Distribution Snapshots

| Feature      | Mean   | Std   | P5     | P25    | P50    | P75    | P95    |
|-------------|--------|-------|--------|--------|--------|--------|--------|
| temperature | 22.3   | 5.1   | 14.2   | 18.5   | 22.0   | 26.1   | 31.0   |

### Baseline Test Thresholds
- KS test threshold: {alpha value}
- PSI threshold: {0.1 = minor, 0.2 = significant}
- Monitoring cadence: {daily / weekly / per-batch}

## 9. Data Split Report

### Split Sizes

| Split | Rows   | Percentage | Strategy                |
|-------|--------|-----------|-------------------------|
| Train | 10,500 | 70%       | Stratified by class     |
| Val   | 2,250  | 15%       | Stratified by class     |
| Test  | 2,250  | 15%       | Stratified, held out    |

### Split Validation
- Stratification verified: {yes/no — class distributions match across splits}
- Leakage check: {passed/failed — no data leakage between splits}
- Temporal ordering preserved: {yes/no/N/A}
- Split hash: {sha256 for reproducibility}

## 10. Recommendations

### Critical Issues (blocking)
- {Issue 1: description, severity, recommended action}

### Warnings (non-blocking)
- {Warning 1: description, impact, suggested resolution}

### Data Readiness Verdict

**Verdict: READY / NEEDS_WORK / BLOCKED**

{One-paragraph rationale summarizing the overall data quality assessment
and whether it's safe to proceed to feature engineering.}
```

---

## Phase 5: Analysis Report

**File**: `reports/analysis_report.md`
**Owner**: XAI Agent (explainability), Oracle/QA (error analysis), Domain Evaluator (bias/domain)
**When**: After all Phase 5 subtasks complete, before Gate 5

### Required Sections

```markdown
# Analysis and Validation Report

Project: {project_name}
Model: {architecture_name} v{version}
Generated: {timestamp}
Primary metric: {metric_name} = {value} (target: {threshold})

## 1. Explainability

### Method
{SHAP / LIME / GradCAM / Attention maps / Integrated Gradients}

### Global Feature Attribution

| Rank | Feature      | Importance | Direction | Domain Aligned? |
|------|-------------|------------|-----------|-----------------|
| 1    | vibration   | 0.42       | +         | Yes — primary indicator |
| 2    | temperature | 0.23       | +         | Yes — thermal stress |

### Per-Class / Per-Regime Attribution

| Class/Regime | Top Feature   | Importance | Notes               |
|-------------|--------------|------------|---------------------|
| Normal      | vibration    | 0.38       | Low vibration = normal |
| Anomaly     | temperature  | 0.51       | Temperature spike precedes failure |

### Interaction Effects
- {Top feature interaction pairs and their joint effect}

### Domain Consistency
- {Do attributions align with domain expertise? Flag any surprises.}
- {Are there features the model relies on that shouldn't matter?}

## 2. Error Analysis

### Per-Class / Per-Regime Breakdown

| Class    | Count | Correct | Errors | Precision | Recall | F1   |
|---------|-------|---------|--------|-----------|--------|------|
| Normal  | 2250  | 2200    | 50     | 0.98      | 0.98   | 0.98 |
| Anomaly | 450   | 410     | 40     | 0.89      | 0.91   | 0.90 |

### Confusion Matrix

```
              Predicted
            Normal  Anomaly
Actual Normal   2200    50
       Anomaly   40   410
```

### Failure Mode Taxonomy

| Mode                | Count | Percentage | Description                        |
|--------------------|-------|-----------|-------------------------------------|
| Boundary cases     | 25    | 28%       | Samples near decision boundary      |
| Regime transition  | 18    | 20%       | Errors during operational changes   |
| Sensor noise       | 12    | 13%       | High-noise periods misclassified    |

### Worst-N Sample Analysis
{Analyse the 10 worst predictions — what do they have in common?
Feature values, temporal context, regime, any patterns.}

### Error Correlation with Features
| Feature      | Error Rate When High | Error Rate When Low | Correlation |
|-------------|---------------------|---------------------|-------------|
| noise_level | 12.3%               | 2.1%                | 0.34        |

## 3. Bias and Fairness

{Mark "N/A — no protected attributes in dataset" if not applicable}

### Subgroup Performance

| Subgroup    | Count | Primary Metric | Gap vs Overall |
|------------|-------|---------------|----------------|
| Sensor A   | 5000  | 0.94          | +0.01          |
| Sensor B   | 3000  | 0.91          | -0.02          |

### Fairness Metrics
- Demographic parity difference: {value}
- Equalized odds difference: {value}
- Assessment: {acceptable / needs mitigation}

## 4. Ablation Study

### Feature Ablation

| Removed Feature | Metric Change | Relative Impact |
|----------------|--------------|-----------------|
| vibration      | -0.15        | Critical        |
| temperature    | -0.08        | Important       |
| humidity       | -0.001       | Negligible      |

### Component Ablation
{If applicable — metric with each model component removed}

| Removed Component | Metric Change |
|------------------|--------------|
| Attention layer  | -0.05        |
| Skip connections | -0.03        |

### Data Ablation (Learning Curve)

| Training Size | Metric | Notes          |
|--------------|--------|----------------|
| 10%          | 0.78   | Underfitting   |
| 25%          | 0.85   |                |
| 50%          | 0.90   |                |
| 75%          | 0.92   |                |
| 100%         | 0.93   | Diminishing returns |

## 5. Statistical Significance

### Confidence Interval

| Metric      | Value | 95% CI Lower | 95% CI Upper | Method    |
|------------|-------|-------------|-------------|-----------|
| Accuracy   | 0.93  | 0.91        | 0.95        | Bootstrap |

### Comparison to Baseline

| Model      | Metric | p-value | Significant? |
|-----------|--------|---------|-------------|
| Ours      | 0.93   | —       | —           |
| Baseline  | 0.85   | 0.001   | Yes         |

### Seed Variance

| Seed | Metric |
|------|--------|
| 42   | 0.932  |
| 123  | 0.928  |
| 456  | 0.935  |
| 789  | 0.930  |
| 1024 | 0.931  |

Mean: {X} | Std: {Y} | Range: [{min}, {max}]

## 6. Reproducibility

### Environment Lock
- Python: {version}
- PyTorch: {version}
- CUDA: {version or "CPU only"}
- Random seed: {value}
- Dependencies hash: {sha256 of requirements/lock file}

### Determinism Verification
- Same seed, same hardware → same result: {YES / NO}
- If NO: variance source identified: {e.g. non-deterministic CUDA ops}

## 7. Consolidated Verdict

### Primary Metric
{metric_name}: **{value}** (target: {threshold}) — **PASS / FAIL**

### Key Strengths
- {Strength 1}
- {Strength 2}

### Key Weaknesses
- {Weakness 1 — severity, mitigation}
- {Weakness 2 — severity, mitigation}

### Risk Assessment
- Production readiness: {HIGH / MEDIUM / LOW}
- Key risks: {list}
- Monitoring requirements: {what to watch post-deployment}

### Recommended Next Steps
1. {Next step 1}
2. {Next step 2}
```

---

## Usage

Agents should:

1. Read the relevant template section from this file
2. Copy the markdown structure into the output report
3. Fill in every section with actual data
4. Mark sections "N/A" with rationale if not applicable
5. Include actual numbers, not placeholders — every table should have real data

The orchestrator validates report presence at gates. Human reviewers check report quality at blocking gates (Gate 2, Gate 5).
