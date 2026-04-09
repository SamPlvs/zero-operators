---
description: Generate a comprehensive validation report from oracle results
argument-hint: <project-name>
---

# /validation-report — Oracle Validation Report Generator

You are generating a comprehensive validation report for a Zero Operators project.

## Steps

1. **Read oracle evaluation results** from the delivery repo. Look for:
   - `oracle/reports/` directory for structured evaluation reports
   - Any metric output files (JSON, CSV) from oracle runs
   - Latest gate events from comms JSONL logs (`logs/comms/`)

2. **Read DECISION_LOG.md** (`memory/{project-name}/DECISION_LOG.md`). Extract:
   - All gate events with metric results
   - All oracle-related decisions
   - Any metric threshold changes (should be rare per oracle spec)

3. **Read the project plan** (`targets/{project-name}.target.md`) for:
   - Primary metric definition and threshold
   - Tiered success criteria (Tier 1/2/3)
   - Ground truth source
   - Evaluation method

4. **Generate the validation report** with these sections:

   ```markdown
   # Validation Report: {project-name}
   **Generated**: {date}
   **Prepared by**: /validation-report command

   ## Primary Metric
   | Metric | Threshold | Result | Status |
   |--------|-----------|--------|--------|
   | {name} | {threshold} | {value} | PASS/FAIL |

   ## Tiered Results
   | Tier | Threshold | Result | Status |
   |------|-----------|--------|--------|
   | Tier 1 (Core) | ... | ... | ... |
   | Tier 2 (Operational) | ... | ... | ... |
   | Tier 3 (Robustness) | ... | ... | ... |

   ## Per-Stratum Breakdown
   {Table breaking down metric by data strata/regimes/categories}

   ## Confusion Matrix
   {If classification task — show the matrix}

   ## Comparison to Baseline
   {How does the model compare to the stated baseline or naive approach}

   ## Confidence Intervals
   {Statistical confidence bounds on the primary metric}

   ## Known Limitations
   {Edge cases, failure modes, data gaps identified during evaluation}

   ## Gate History
   {Chronological list of all oracle gate evaluations for this project}
   ```

5. **Write the report** to `reports/validation_report.md` in the delivery repo. Create the `reports/` directory if it does not exist.

6. **Report** to the user:
   - Summary of pass/fail status
   - Key findings or concerns
   - Path to the generated report
