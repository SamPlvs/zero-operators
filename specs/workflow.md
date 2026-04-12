# Zero Operators: ML/Research Workflow Framework

## Overview

This document specifies the standard ML/research workflow framework for Zero Operators (ZO). It describes the general-purpose pattern that applies to any ML or research project — classical ML, deep learning, NLP, computer vision, time series, or hybrid approaches — from data intake through model packaging. The framework emphasizes sequential task dependency, defined human checkpoints, and autonomous iteration with human-in-the-loop validation gates.

The workflow is encoded as `ml-workflow/SKILL.md` and serves as the default orchestration pattern. Individual projects customize this workflow via `plan.md` overrides while maintaining core sequencing discipline.

---

## Workflow Philosophy

### Core Pattern

The standard workflow follows this sequence:

1. **Data Review** — understand raw data, identify quality issues, document exclusions, version data
2. **Feature Engineering & Selection** — create derived features, reduce feature space, or define input representations
3. **Model Design** — select architecture, define loss function, configure training strategy
4. **Training & Iteration** — train, evaluate, iterate on hyperparameters and architecture
5. **Analysis & Validation** — ablation studies, error analysis, explainability, statistical significance
6. **Packaging** — inference pipeline, model card, validation report, test suite

### Workflow Modes

The orchestrator selects the appropriate workflow mode based on `plan.md`:

**Classical ML mode** (tabular data, feature engineering focus): All six phases run as specified. Phase 2 emphasizes statistical feature selection and engineering. Phase 3 focuses on model selection across algorithm families.

**Deep Learning mode** (learned representations): Phase 2 shifts from manual feature selection to input representation design (tokenization, normalization, embedding strategy). Phase 3 expands with architecture search, training dynamics, and optimization strategy. Phase 4 adds learning rate scheduling, gradient diagnostics, and convergence analysis.

**Research mode** (publication-oriented): Adds Phase 0 (literature review and prior art survey). Phase 5 expands with ablation studies, statistical significance testing, and reproducibility verification. Phase 6 adds paper-ready figures and results tables.

The orchestrator reads `plan.md`'s `workflow_mode` field and applies the appropriate phase configuration. If unspecified, default is Classical ML mode.

### Sequencing Discipline

Within each phase, subtasks are sequenced: each feeds the next. Phases themselves are gated. Parallel work spawns only after a gate passes. This design prevents wasted computation and ensures human oversight at critical decision points.

**Key principle:** The orchestrator enforces sequencing. Agents cannot skip phases, jump ahead, or proceed without gate approval. Progress is tracked in `STATE.md`. Phase completion is logged to `DECISION_LOG.md`.

### Human-in-the-Loop Architecture

Human checkpoints occur at defined gates, not ad-hoc. This allows agents to work autonomously between checkpoints while ensuring humans retain authority over major decisions (feature selection, architecture approval, model approval, deployment validation). Checkpoints are summarized in gate review documents so humans can decide quickly.

### Modularity and Customization

The workflow is extensible. Each `plan.md` can:
- Add, remove, or reorder phases
- Convert blocking gates to informational gates
- Move or add human checkpoints
- Define project-specific subtask dependencies
- Specify custom validation thresholds or metrics
- Set workflow mode (classical_ml, deep_learning, research)

The `ml-workflow/SKILL.md` provides the default. Projects override selectively.

---

## Phase 0: Literature Review and Prior Art (Research Mode Only)

**Status:** Sequential
**Gate:** Gate 0 (Orchestrator review)
**Input:** Research question from `plan.md`, domain specification
**Output:** Prior art summary, baseline benchmarks, methodology candidates

This phase is activated when `plan.md` specifies `workflow_mode: research` or explicitly includes Phase 0.

### Subtask 0.1: Prior Art Survey

Identify and summarize relevant prior work:
- Search for existing approaches to the problem defined in `plan.md`
- Document state-of-the-art methods, their reported metrics, and known limitations
- Identify benchmark datasets and evaluation protocols used in the field
- Record key architectural choices and training strategies from top-performing methods

**Artifact:** `prior_art_survey.md`.

### Subtask 0.2: Baseline Definition

Establish comparison baselines:
- Select 2-3 baseline approaches (simple heuristic, classical ML, prior best DL method)
- Document expected performance range based on prior art
- Define evaluation protocol consistent with prior work (enables fair comparison)
- Identify any pretrained models or checkpoints available for transfer learning

**Artifact:** `baseline_definition.md`, `pretrained_models.yaml` (if applicable).

### Gate 0: Research Scope Review

Orchestrator confirms: Is the problem well-defined? Are baselines identified? Is the evaluation protocol consistent with prior art? If yes, proceed. If ambiguous, escalate to human.

---

## Phase 1: Data Review and Pipeline

**Status:** Sequential
**Gate:** Gate 1 (Orchestrator review)
**Input:** Raw data sources, data source documentation
**Output:** Data quality report, versioned data pipeline, correlation artifact
**Agents:** data-engineer, test-engineer, research-scout, code-reviewer, domain-evaluator

This phase validates and understands raw data. Each subtask feeds the next. Do not parallelize.

> **Cross-cutting agents:** `code-reviewer` and `research-scout` are cross-cutting agents present in ALL phases. `code-reviewer` validates code quality, test coverage, and adherence to standards in every phase that produces code. `research-scout` monitors for relevant prior art, methodology updates, and domain-specific best practices throughout the project lifecycle.

### Subtask 1.1: Raw Data Audit

Load all data sources and perform statistical profiling:
- Count records per source, per time window
- Plot distributions (histograms, quantiles) for each feature
- Identify regime changes: sudden shifts in mean, variance, or autocorrelation
- Generate time series plots for all key variables (if temporal data)
- Document data availability (gaps, sensor dropouts, missing periods)
- Identify obvious outliers or physically impossible values
- For image/text data: document class distributions, sequence length distributions, data quality samples
- For multi-modal data: document each modality separately, then cross-modal alignment

**Artifact:** `data_audit_report.md` with distributions, regime plots, and data availability summary.

### Subtask 1.2: Data Hygiene

Validate data integrity and identify corruption:
- Scan for duplicate records (timestamps, IDs, or content hashes)
- Check for sensor saturation, label noise, or annotation inconsistency
- Identify physically impossible or semantically invalid values
- Generate missing data heatmap (missing percentage per feature, per time window)
- Check for systematic biases (e.g., missing data clustered by class, time, source)
- For text: check encoding issues, language mix, truncation artifacts
- For images: check corrupted files, resolution inconsistencies, mislabeled samples

**Artifact:** `data_hygiene_report.md` with violation counts, heatmaps, and recommendations.

### Subtask 1.3: Exclusion Filters

Apply domain-specific filters to remove invalid records:
- Identify exclusion criteria from domain priors (e.g., turnaround periods, manual mode flags, known bad sensors, annotation disagreements)
- Apply each filter; record record count before and after
- Document every exclusion with count, criteria, and domain justification
- Produce inclusion/exclusion flags in cleaned dataset

**Artifact:** `exclusion_filters.yaml` and cleaned dataset with filter flags.

### Subtask 1.4: Data Alignment and Joining

Join multiple data sources with appropriate logic:
- For time series: define timestamp tolerance, perform time-aware joins, validate alignment quality
- For tabular: define join keys, handle one-to-many relationships, validate referential integrity
- For multi-modal: align across modalities (e.g., image-caption pairs, audio-transcript alignment)
- Flag any sources with poor alignment or high join loss

**Artifact:** `alignment_report.md` with validation metrics and source-pair quality.

### Subtask 1.5: Exploratory Data Analysis

Deep statistical exploration beyond the audit:
- Compute pairwise correlations (Pearson, Spearman, mutual information) between inputs and outputs
- Include autocorrelations and lagged correlations for time series
- Produce correlation matrix heatmap and identify near-zero/near-perfect correlations
- Perform dimensionality reduction visualization (PCA, t-SNE, UMAP) on feature space
- Identify natural clusters or groupings in the data
- Document any surprising patterns, anomalies, or distributional properties

**Artifact:** `eda_report.md`, `correlation_matrix.csv`, `correlation_heatmap.png`, `embedding_plots/`.

### Subtask 1.6: Data Versioning and Split Definition

Version data and define training splits:
- Hash the cleaned dataset (SHA-256) and record in `data_version.yaml`
- Define train/val/test split with appropriate strategy:
  - **Time series:** temporal split with purge gap (no temporal leakage)
  - **Tabular:** stratified random split preserving class distribution
  - **CV/NLP:** standard random split or domain-specific protocol (e.g., leave-one-domain-out)
- For time series: implement walk-forward or expanding window validation if specified in `plan.md`
- Validate that test set is disjoint from training on the appropriate dimension
- Document split ratios, boundaries, and stratification strategy

**Artifact:** `data_version.yaml`, `split_config.yaml`, `split_report.md`.

### Subtask 1.7: Data Loader Implementation

Build the training data pipeline:
- Implement PyTorch Dataset and DataLoader classes (or framework equivalent)
- Include preprocessing transforms (normalization, standardization, tokenization, augmentation)
- Implement data augmentation pipeline if applicable:
  - **Tabular:** noise injection, SMOTE for imbalanced classes, mixup
  - **Images:** random crop, flip, rotation, color jitter, cutout, mixup, CutMix
  - **Text:** back-translation, synonym replacement, random insertion/deletion
  - **Time series:** jittering, scaling, window slicing, magnitude warping
- Validate DataLoader: batch creation, no data leakage, correct shapes and dtypes
- Benchmark DataLoader throughput (samples/sec) to ensure it won't bottleneck training

**Artifact:** `dataset.py`, `data_loader.py`, `transforms.py`, `loader_benchmark.md`.

### Subtask 1.8: Data Schema Validation

Enforce expected schema on the cleaned dataset:
- Validate column names, data types, and value ranges against a schema definition
- Flag columns with unexpected types (e.g., numeric stored as string) or out-of-range values
- Produce a schema compliance report with pass/fail per column

**Artifact:** `data_schema.yaml`, `schema_validation_report.md`.

### Subtask 1.9: Missing Value Analysis and Strategy

Analyze and document a strategy for handling missing data:
- Quantify missingness per feature (MCAR, MAR, MNAR classification where feasible)
- Evaluate imputation strategies (mean/median, forward-fill, model-based, drop) with impact analysis
- Document chosen strategy per feature with justification

**Artifact:** `missing_value_report.md`, `imputation_config.yaml`.

### Subtask 1.10: Outlier Detection

Identify outliers using statistical and domain-aware methods:
- Statistical detection: z-score, IQR, isolation forest, or DBSCAN as appropriate
- Domain-aware detection: flag values that violate physical or business constraints from `PRIORS.md`
- Document each outlier category with count, severity, and recommended action (keep, cap, remove)

**Artifact:** `outlier_report.md`, `outlier_flags.csv`.

### Subtask 1.11: Class Imbalance Analysis

Assess target variable distribution and plan mitigation:
- Compute class frequencies and imbalance ratio
- For regression: identify thin-tail regions with low sample density
- Recommend mitigation strategy (oversampling, undersampling, class weights, focal loss, SMOTE) with rationale
- If no imbalance detected, document confirmation

**Artifact:** `imbalance_report.md`, `sampling_config.yaml` (if mitigation needed).

### Subtask 1.12: Train/Val/Test Split Strategy

Define and validate the data splitting approach:
- Choose split method based on data type (temporal, stratified, grouped, domain-specific)
- Validate no data leakage across splits (especially for time series and grouped data)
- Document split ratios, boundaries, stratification keys, and purge gaps
- Produce split statistics (class distributions, feature distributions per split)

**Artifact:** `split_strategy.md`, `split_statistics.csv`.

### Subtask 1.13: Data Drift Baseline

Establish reference distributions for ongoing monitoring:
- Compute reference statistics (mean, std, quantiles, histograms) for all features on the training set
- Store reference distributions in a serializable format for future drift detection
- Define drift thresholds (PSI, KS-test, or domain-specific) per feature
- Document baseline assumptions and recommended monitoring cadence

**Artifact:** `drift_baseline.yaml`, `reference_distributions.pkl`, `drift_monitoring_config.yaml`.

### Gate 1: Data Quality Review

**Input criteria:**
- All subtasks complete
- Data audit, hygiene, alignment, EDA reports available
- Cleaned dataset versioned, splits defined, loader implemented and benchmarked

**Evaluation method:**
- Orchestrator (or human if specified in `plan.md`) reviews quality report
- Check: Are critical data issues (missing data >50%, regime changes, corruption) documented?
- Check: Are exclusion filters justified and counts reasonable?
- Check: Is the DataLoader performant enough for training requirements?

**Pass threshold:**
- Data quality sufficient for the next phase
- No unexplained corruption or systematic biases
- Data pipeline is reproducible (versioned, deterministic splits)

**Failure action:**
- If critical issues flagged: orchestrator pauses, summarizes gaps, escalates to human
- Human decides: collect more data, revise filters, or approve with caveats
- If approved: proceed to Phase 2

---

## Phase 2: Feature Engineering and Selection

**Status:** Sequential
**Gate:** Gate 2 (Human checkpoint)
**Input:** Cleaned dataset, EDA artifacts, correlation artifact, domain priors
**Output:** Engineered feature set or input representation definition

This phase creates and selects features (Classical ML) or defines input representations (DL). The orchestrator selects subtask sets based on workflow mode.

### Classical ML Subtasks

#### Subtask 2.1: Feature Engineering

Create derived features from raw inputs:
- **Temporal features:** lag features (t-1, t-2, ..., t-n), rolling statistics (mean, std, min, max over windows), rate of change, exponential moving averages
- **Interaction features:** polynomial interactions between correlated features, ratio features (A/B where domain-meaningful)
- **Domain-derived features:** features specified in `PRIORS.md` (e.g., efficiency = output/input, deviation from setpoint)
- **Encoding:** one-hot encoding for categoricals, target encoding for high-cardinality categoricals, cyclical encoding for periodic features (hour, day-of-week)
- Document each engineered feature with formula, rationale, and expected relationship to output

**Artifact:** `feature_engineering.py`, `engineered_features.yaml` (with formulas and rationale).

#### Subtask 2.2: Section Filter

Remove features with no causal relationship to outputs:
- Review domain priors in `PRIORS.md`
- Identify feature sections and exclude those with known irrelevance
- Document exclusion rationale per section

**Artifact:** `section_exclusions.yaml`.

#### Subtask 2.3: Statistical Filter

Remove features with weak signal:
- Use correlation matrix and mutual information from Phase 1 EDA
- Set threshold per output (typically |r| > 0.1 or mutual information > threshold)
- Remove features below threshold for ALL outputs
- Document threshold and count of removed features

**Artifact:** `statistical_filter_log.md`.

#### Subtask 2.4: Multicollinearity Pruning

Remove redundant features:
- Compute Variance Inflation Factor (VIF) for remaining features
- Identify feature clusters (near-duplicate or highly correlated groups)
- For each cluster, retain only the most informative feature
- Iteratively remove highest-VIF features until VIF < threshold (default 10, configurable)

**Artifact:** `vif_report.md`, `multicollinearity_log.md`.

#### Subtask 2.5: Domain Validation

Ensure selected features are physically and logically meaningful:
- Review feature definitions and units
- Check for redundancy or logical inconsistency
- Verify that selected features are observable (not derived from output or leaking future information)
- Confirm with domain expert (if available) that set is interpretable

**Artifact:** `domain_validation.md`.

#### Subtask 2.6: Feature List Ranking

Produce final ranked feature list:
- Rank features by importance (correlation, mutual information, or preliminary model-based importance)
- Include secondary metrics: VIF, missing rate, data quality score, engineering source
- Write brief justification for each feature
- Generate final feature count and dimensionality reduction percentage

**Artifact:** `selected_features.yaml` (ranked, with metadata and justification).

### Deep Learning Subtasks

When `workflow_mode: deep_learning`, Phase 2 replaces classical feature selection with input representation design.

#### Subtask 2.DL.1: Input Representation Design

Define how raw data is transformed into model inputs:
- **Tabular DL:** normalization strategy (batch norm, layer norm, standardization), embedding dimensions for categoricals, handling of missing values (learned mask, imputation, or indicator)
- **NLP:** tokenizer selection (BPE, WordPiece, SentencePiece), vocabulary size, max sequence length, special token strategy
- **Computer Vision:** image resolution, channel normalization (ImageNet stats or dataset-specific), patch size (for ViT-style models)
- **Time series:** window size, stride, normalization per-window vs. global, positional encoding strategy
- **Multi-modal:** alignment strategy between modalities, fusion point (early, mid, late)

**Artifact:** `input_representation.yaml`, `preprocessing.py`.

#### Subtask 2.DL.2: Transfer Learning Assessment

Evaluate pretrained model availability and applicability:
- Identify pretrained models relevant to the domain (from Phase 0 or prior art)
- Assess domain gap between pretrained data and project data
- Decide: train from scratch, fine-tune full model, fine-tune head only, or use pretrained features as fixed embeddings
- If fine-tuning: specify which layers to freeze initially, unfreezing schedule, learning rate differential per layer group
- Document decision rationale

**Artifact:** `transfer_learning_strategy.md`.

#### Subtask 2.DL.3: Augmentation Strategy

Design data augmentation pipeline specific to DL:
- Define augmentation operations and their probability/magnitude ranges
- Implement augmentations as differentiable transforms where possible (for consistency)
- For NLP: decide on augmentation approach (back-translation, dropout, mixup in embedding space)
- For CV: implement augmentation policy (AutoAugment, RandAugment, or manual)
- Validate augmentations don't corrupt labels or produce out-of-distribution samples
- Benchmark augmented DataLoader throughput

**Artifact:** `augmentation_config.yaml`, `augmentation_validation.md`.

### Gate 2: Feature / Representation Approval

**Input criteria:**
- Feature ranking (classical) or representation design (DL) complete
- Justification document ready
- Domain validation passed (or flagged issues documented)

**Evaluation method:**
- Orchestrator produces summary for human domain expert
- Human reviews: Do selected features / representations align with domain expectations?
- This is typically a **mandatory blocking gate**

**Pass threshold:**
- Human approves with no changes or minor edits

**Failure action:**
- If human rejects: specify required changes, iterate Phase 2, resubmit
- **Pass action:** Proceed to Phase 3

---

## Phase 3: Model Design

**Status:** Parallel (spawned after Gate 2 passes)
**Gate:** None; parallel work begins
**Input:** Selected features or representation design, cleaned dataset, training infrastructure specs
**Output:** Model architecture, loss function, training strategy, experiment tracking, oracle setup

After human approves features/representations, orchestrator spawns multiple agents for parallel work.

### Concurrent Subtask 3.1: Architecture Selection

Design the model architecture:

**Classical ML path:**
- Select candidate algorithm families (linear models, tree ensembles, SVMs, etc.)
- Implement baseline model per family
- Fit on train split, report train and validation metrics
- Document algorithm selection rationale based on data characteristics (size, sparsity, nonlinearity)

**Deep Learning path:**
- Select architecture family based on data type and `plan.md` guidance:
  - **Tabular:** MLP, TabNet, FT-Transformer, SAINT
  - **Time series:** LSTM, GRU, Temporal Fusion Transformer (TFT), N-BEATS, PatchTST, TimesNet
  - **NLP:** Transformer (encoder, decoder, or encoder-decoder), BERT-style, GPT-style
  - **CV:** CNN (ResNet, EfficientNet), ViT, ConvNeXt, or task-specific (YOLO, U-Net)
  - **Multi-modal:** cross-attention, early/late fusion architectures
- Define model dimensions: hidden size, number of layers, attention heads, embedding dimensions
- Implement architecture in PyTorch with clear module structure
- If transfer learning: load pretrained weights, configure frozen/unfrozen layers
- Document parameter count, FLOPs estimate, and memory footprint

**Artifact:** `model.py`, `architecture_config.yaml`, `architecture_rationale.md`.

### Concurrent Subtask 3.2: Loss Function Design

Select or design the training objective:
- **Standard losses:** MSE, MAE, Huber (regression); cross-entropy, focal loss (classification); CTC, seq2seq loss (sequence)
- **Custom losses:** weighted loss for class imbalance, asymmetric loss for cost-sensitive domains, multi-task losses
- **Regularization terms:** L1/L2 weight decay, dropout rate, label smoothing, spectral normalization
- **Auxiliary losses:** intermediate supervision, contrastive loss, distillation loss (if applicable)
- Implement loss function with configurable weights
- Document loss choice rationale and relationship to primary oracle metric

**Artifact:** `loss.py`, `loss_config.yaml`, `loss_rationale.md`.

### Concurrent Subtask 3.3: Training Strategy Definition

Configure the full training pipeline:
- **Optimizer:** SGD (with momentum/Nesterov), Adam, AdamW, LAMB, or domain-specific choice
- **Learning rate schedule:** warmup steps, schedule type (cosine annealing, step decay, OneCycleLR, polynomial decay), min/max LR
- **Batch size:** starting batch size, gradient accumulation steps if memory-constrained
- **Mixed precision:** enable FP16/BF16 if supported by hardware and model
- **Gradient management:** gradient clipping (max norm), gradient scaling for mixed precision
- **Early stopping:** patience (epochs without improvement), metric to monitor, min delta
- **Reproducibility:** random seed, deterministic mode, CUDA deterministic operations
- **Distributed training:** data parallel, model parallel, or single-GPU (based on model size and data volume)
- **Checkpointing:** save frequency, keep top-K checkpoints by validation metric, checkpoint format

**Artifact:** `training_config.yaml`, `training_strategy.md`.

### Concurrent Subtask 3.4: Regime Segmentation (if applicable)

If domain priors indicate regime-specific behavior:
- Identify regime variable (e.g., operating mode, season, load range)
- Partition dataset by regime
- Decide approach: separate models per regime, single model with regime as input, mixture-of-experts
- If separate models: define model selection logic at inference time
- Compare regime-specific performance expectations to global model

**Artifact:** `regime_analysis.md`, `regime_strategy.yaml`.

### Concurrent Subtask 3.5: Oracle Setup

Set up validation test suite and metric computation:
- Implement oracle script that evaluates any model candidate against primary metric (from `plan.md`)
- Define Tier 1/2/3 thresholds (from `plan.md`)
- Implement secondary metrics for detailed analysis (per-class, per-regime, per-difficulty)
- Implement statistical significance testing (paired t-test, bootstrap confidence interval, McNemar's test as appropriate)
- Validate oracle script produces correct output format
- Run oracle on a dummy or baseline model to verify pipeline

**Artifact:** `oracle.py`, `oracle_config.yaml`, `oracle_validation.md`.

### Concurrent Subtask 3.6: Experiment Tracking

Set up logging and artifact storage:
- Implement experiment tracking (MLflow, Weights & Biases, or local JSONL logging)
- Configure automatic logging of: hyperparameters, metrics per epoch, model checkpoints, training curves, system metrics (GPU utilization, memory)
- Define experiment naming convention and tagging strategy
- Test tracking system end-to-end
- Ensure all logs are queryable and reproducible

**Artifact:** `experiment_tracker.py`, `experiments/` directory structure.

### Sync Point

All concurrent subtasks must report completion. Orchestrator waits for all to finish before proceeding to Phase 4.

---

## Phase 4: Training and Iteration

**Status:** Autonomous with human wakeup
**Gate:** Gate 3 (Oracle threshold)
**Input:** Model architecture, loss function, training strategy, oracle, experiment tracking
**Output:** Best model, iteration log, training diagnostics, flagged issues

Once Phase 3 parallel work completes, orchestrator initiates autonomous training and iteration.

### Subtask 4.1: Baseline Training Run

Execute the first full training run:
- Train model with Phase 3 configuration on full training set
- Log training curve (loss per epoch on train and validation)
- Record wall-clock time, GPU utilization, peak memory
- Run oracle on trained model; record baseline metrics
- Diagnose any immediate issues: NaN loss, divergence, GPU OOM, training instability

**Artifact:** `baseline_training_log.md`, `baseline_metrics.json`, `training_curves.png`.

### Subtask 4.2: Training Diagnostics (DL-specific)

For deep learning models, perform training health checks:
- **Gradient flow analysis:** plot gradient magnitudes per layer; flag vanishing or exploding gradients
- **Learning rate finder:** run LR range test to identify optimal learning rate range
- **Overfitting check:** compare train vs. validation loss curves; compute generalization gap
- **Convergence check:** is the model still improving or has it plateaued?
- **Activation statistics:** check for dead ReLU neurons, activation distribution per layer
- **Weight distribution:** plot weight histograms per layer; check for degenerate distributions

**Artifact:** `training_diagnostics.md`, `gradient_plots/`, `lr_finder.png`.

### Subtask 4.3: Iteration Protocol

Autonomous search over configurations:

1. **Model Builder proposes** a candidate configuration:
   - **Hyperparameter changes:** learning rate, batch size, dropout, weight decay, layer sizes, attention heads
   - **Architecture modifications:** add/remove layers, change activation functions, modify skip connections, adjust embedding dimensions
   - **Training strategy changes:** different optimizer, learning rate schedule, augmentation intensity
   - **Ensemble candidates:** model combination strategies (bagging, stacking, weighted average)
   - **Loss function variants:** different loss weights, auxiliary loss terms, label smoothing values

2. **Train** the candidate on the full training pipeline

3. **Oracle evaluates** the candidate on validation set; computes primary and secondary metrics

4. **Experiment Tracker logs** full configuration, metrics, model artifact, timestamp, compute cost

5. **Comparison logic:** Is candidate statistically significantly better than current best? (Not just lower loss — use paired tests or bootstrap if specified in `plan.md`)

6. **Loop condition:** Repeat until:
   - **Tier 1 threshold met** (Gate 3 pass)
   - **Iteration budget exhausted** (human wakeup)
   - **Plateau detected:** No improvement for N consecutive iterations
   - **Compute budget exhausted:** Total GPU-hours exceeds limit
   - **Human override**

### Subtask 4.4: Cross-Validation (if specified)

If `plan.md` requires cross-validation:
- **Standard CV:** K-fold stratified cross-validation (default K=5)
- **Time series CV:** walk-forward validation with expanding or sliding window; purge gap between train and validation to prevent leakage
- **Group CV:** leave-one-group-out for grouped data (e.g., leave-one-patient-out, leave-one-site-out)
- Report per-fold metrics, mean ± standard deviation
- Identify folds with anomalous performance (potential data quality issue)

**Artifact:** `cross_validation_report.md`, `fold_metrics.csv`.

### Subtask 4.5: Ensemble Exploration (if applicable)

If single-model performance plateaus or `plan.md` specifies ensemble:
- Train top-K diverse model candidates (different architectures, different random seeds, different hyperparameters)
- Evaluate ensemble strategies: simple averaging, weighted averaging (optimized on validation), stacking with meta-learner
- Compare ensemble performance to best single model
- Document ensemble composition and weighting

**Artifact:** `ensemble_report.md`, `ensemble_config.yaml`.

### Logging and Checkpointing

Every iteration logs:
- Full configuration (hyperparameters, architecture, training strategy)
- Primary and secondary metrics (train, val, test if available)
- Training curves (loss, learning rate per epoch)
- Model artifact (checkpoint with optimizer state for resumability)
- Computation time and resource usage (GPU-hours, peak memory)
- Any warnings or anomalies detected

**Artifact:** `iterations.csv`, `best_model.pt`, `iteration_log.md`.

### Human Wakeup

When loop exits without Tier 1 pass, orchestrator produces:
- Summary of iterations (counts, metric trajectory, top 3 candidates)
- Best model performance vs. threshold
- Training diagnostics summary (convergence, overfitting, gradient health)
- Flagged issues (divergence, data leakage, overfitting, mode collapse)
- Recommendation: iterate more, change approach, revisit features, try ensemble, or accept suboptimal

---

## Gate 3: Oracle Metric Threshold

**Input criteria:**
- Training iteration complete (threshold met or budget exhausted)
- Best model and full metrics available
- Iteration log and training diagnostics ready

**Evaluation method:**
- Oracle automatically evaluates best model on validation set
- Compare primary metric to Tier 1 threshold (from `plan.md`)
- If statistical significance testing is configured: verify improvement is significant (p < 0.05) over baseline

**Pass threshold:**
- Primary metric >= Tier 1 threshold
- No data leakage detected
- Model is stable (not divergent, not overfitting catastrophically)

**Failure action:**
- Automatic: If threshold met, proceed to Phase 5
- Manual: If threshold not met, human decides:
  - **Iterate more:** Extend iteration budget, continue Phase 4
  - **Change approach:** Different architecture family, different loss, ensemble
  - **Revisit features:** Return to Phase 2
  - **Accept suboptimal:** Approve despite threshold miss (documented exception)

---

## Phase 5: Analysis and Validation

**Status:** Sequential
**Gate:** Gate 4 (Human checkpoint)
**Input:** Best model, training data, EDA artifacts, domain priors, baseline metrics
**Output:** Explainability report, ablation study, error analysis, validation report

This phase validates that the model works for the right reasons and characterizes its failure modes.

### Subtask 5.1: Feature Attribution / Explainability

Run explainability analysis on the winning model:

**For classical ML and tabular DL:**
- Compute SHAP values on validation set (TreeSHAP for tree models, KernelSHAP or DeepSHAP for neural networks)
- Generate top-K feature importance rankings
- Produce force plots and dependence plots for top features
- Quantify contribution of each feature to model output

**For deep learning (NLP, CV, time series):**
- **NLP:** attention visualization, integrated gradients, token-level attribution
- **CV:** GradCAM, LIME, occlusion sensitivity, saliency maps
- **Time series:** temporal attention weights, feature-time attribution heatmaps
- Identify which input elements the model attends to most

**Artifact:** `explainability_report.md`, `feature_importance.png`, `attribution_plots/`.

### Subtask 5.2: Domain Consistency Check

Validate that model behavior aligns with domain priors:
- Review `PRIORS.md` for expected feature rankings and relationships
- Compare model attributions to domain expectations
- Flag any surprises (unexpected top features, counterintuitive directions)
- Document agreement/disagreement per feature or input element

**Artifact:** `domain_consistency_report.md`.

### Subtask 5.3: Data Corroboration Check

Validate that model attributions agree with data statistics:
- For each top attribution feature: is the sign consistent with correlation sign?
- Flag any sign disagreements (possible data leakage, spurious correlation, or collinearity artifact)
- Check if model relies on features with high missing rates or low data quality

**Artifact:** `data_corroboration_report.md`.

### Subtask 5.4: Magnitude Plausibility Check

Validate that feature contributions are proportionally reasonable:
- Are top contributions significantly larger than bottom contributions?
- Do contribution magnitudes reflect domain relevance?
- Flag any minor features with outsized contributions (possible leakage or overfitting)

**Artifact:** `magnitude_plausibility_report.md`.

### Subtask 5.5: Error Analysis

Structured analysis of model failure modes:
- **Per-class / per-regime breakdown:** where does the model fail most?
- **Hardness analysis:** rank test samples by error magnitude; identify clusters of hard samples
- **Confusion patterns:** for classification, analyze confusion matrix for systematic misclassifications
- **Failure case study:** manually inspect 10-20 worst predictions; document what they have in common
- **Bias detection:** check if error rates differ across protected groups or data segments (if applicable)
- **Edge case analysis:** performance on boundary conditions, extreme values, rare events

**Artifact:** `error_analysis.md`, `confusion_matrix.png`, `failure_cases/`.

### Subtask 5.6: Ablation Study

Systematically remove or modify components to understand their contribution:
- **Feature ablation:** retrain without top-K features one at a time; measure impact
- **Architecture ablation (DL):** remove layers, reduce dimensions, simplify attention; measure impact
- **Augmentation ablation:** retrain without augmentation; measure impact
- **Loss ablation:** retrain with standard loss (if custom loss was used); measure impact
- **Transfer learning ablation:** retrain from scratch (if fine-tuned); compare to fine-tuned version
- Present ablation results as a table: component removed → metric change

**Artifact:** `ablation_study.md`, `ablation_results.csv`.

### Subtask 5.7: Statistical Significance Testing

Verify that results are not due to random chance:
- Run best model with 3-5 different random seeds; report mean ± std
- Compare best model to baseline with paired statistical test:
  - **Paired t-test** or **Wilcoxon signed-rank test** on per-sample errors
  - **Bootstrap confidence interval** on metric difference
  - **McNemar's test** for classification accuracy comparison
- Report p-value and effect size
- Document whether improvement over baseline is statistically significant

**Artifact:** `significance_testing.md`, `seed_variance.csv`.

### Subtask 5.8: Reproducibility Verification

Confirm that results can be reproduced:
- Retrain best model from scratch with recorded configuration and fixed seed
- Verify metrics match within acceptable tolerance (e.g., ±0.5% for neural networks, exact for deterministic models)
- Verify all artifacts (config, data version, code version) are sufficient to reproduce
- Document any non-deterministic components and their impact

**Artifact:** `reproducibility_report.md`.

### Subtask 5.9: Explainability Report Assembly

Consolidate all analysis into a single human-readable report:
- Summarize all consistency checks (domain, data, magnitude)
- Include error analysis findings and failure mode catalog
- Present ablation results
- Include statistical significance results
- Produce summary of flagged issues with severity ratings
- Recommend approval, conditional approval, or rejection

**Artifact:** `analysis_report.md`.

### Gate 4: Human Model Approval

**Input criteria:**
- Model performance metrics available (from Phase 4)
- Full analysis report complete (explainability, error analysis, ablation, significance)
- All consistency checks documented

**Evaluation method:**
- Orchestrator produces human review package: performance summary + analysis report
- Human domain expert reviews: Does model behave as expected? Are failure modes acceptable? Are ablation results sensible? Is improvement statistically significant?
- This is a **mandatory blocking gate**

**Pass threshold:**
- Human approves model (no further changes required)
- Or human approves with minor modifications

**Failure action:**
- If human rejects: specify required fixes
  - Example: "Model relies too heavily on feature X; retrain without it"
  - Example: "Top driver disagrees with priors; revisit feature engineering"
  - Example: "Performance acceptable but explainability poor; try simpler model"
  - Example: "Not statistically significant; more seeds or different architecture"
- Iterate: Return to appropriate phase (Phase 4 for retraining, Phase 2 for feature changes)
- Resubmit for human approval

**Pass action:** Proceed to Phase 6

---

## Phase 6: Packaging

**Status:** Parallel (spawned after Gate 4 passes)
**Gate:** None; final assembly
**Input:** Best model, validation results, analysis report
**Output:** Inference pipeline, model card, validation suite, deployment artifacts

After human approval, orchestrator spawns final parallel work to package the model.

### Concurrent Subtask 6.1: Inference Pipeline

Develop production-ready prediction pipeline:
- Implement feature preprocessor (same transformations as training, no data leakage from test-time statistics)
- Implement model loader and prediction function
- Handle edge cases: missing inputs, out-of-range values, unexpected dtypes
- Validate end-to-end pipeline on held-out test set (metrics must match training evaluation)
- Benchmark inference latency (p50, p95, p99) and memory requirements
- For DL: export to ONNX or TorchScript if deployment requires it; verify exported model matches original

**Artifact:** `inference.py`, `preprocessor.pkl`, `inference_benchmark.md`.

### Concurrent Subtask 6.2: Model Card

Generate human-readable model documentation:
- Model name, version, date, author, training compute cost
- Architecture summary and training approach
- Performance metrics (primary + secondary) on train/val/test, by regime if applicable
- Confidence intervals and statistical significance results
- Ablation highlights (what matters most, what doesn't)
- Limitations and known failure modes (from error analysis)
- Required inputs, output format, prediction units
- Data requirements and drift sensitivity
- Ethical considerations and bias assessment (if applicable)

**Artifact:** `model_card.md`.

### Concurrent Subtask 6.3: Validation Report

Auto-generate comprehensive validation report:
- Consolidate oracle metrics from Phase 4
- Include analysis findings from Phase 5
- Cross-validation or bootstrap confidence intervals
- Performance-by-regime breakdown (if applicable)
- Comparison to baselines (from Phase 0 or Phase 3)
- Model degradation vs. baseline documented
- Statistical significance summary

**Artifact:** `validation_report.md`.

### Concurrent Subtask 6.4: Recalibration and Drift Detection

Define retraining and monitoring procedures:
- Specify triggers for retraining (data drift detected, metric degradation > threshold, concept drift)
- Implement drift detection logic: input distribution monitoring (KS test, PSI), prediction distribution monitoring, feature importance stability
- Document data collection and labeling requirements for retraining
- Provide retraining runbook for operators
- Define monitoring dashboard metrics (if deployment)

**Artifact:** `recalibration_procedures.md`, `drift_detector.py`.

### Concurrent Subtask 6.5: Test Suite

Develop automated test suite for packaged model:
- Unit tests: preprocessing correctness, model loading, prediction shape and dtype
- Integration tests: end-to-end inference on sample data, round-trip serialize/deserialize
- Regression tests: model maintains performance on benchmark data (within tolerance)
- Edge case tests: null inputs, extreme values, missing features, adversarial inputs
- Performance tests: inference latency within SLA, memory within budget
- Data validation tests: input schema validation, out-of-distribution detection

**Artifact:** `tests/`, `test_data/`, `test_report.md`.

### Concurrent Subtask 6.6: Research Artifacts (Research Mode Only)

If `workflow_mode: research`:
- Generate paper-ready figures (publication-quality plots with proper labels, fonts, legends)
- Produce results tables in LaTeX format
- Write structured results section draft (optional, if specified in `plan.md`)
- Package reproducibility bundle (code, config, data version, environment spec)

**Artifact:** `figures/`, `tables/`, `reproducibility_bundle/`.

### Sync Point

All concurrent subtasks report completion. Orchestrator produces final packaging summary.

---

## Subtask Sequencing Rules

Within each sequential phase:

1. **Strict ordering:** Each subtask must complete fully before the next begins. No parallelization within a sequential phase.
2. **Dependency enforcement:** Downstream subtasks assume upstream artifacts are ready. Do not skip or reorder without explicit `plan.md` override.
3. **State tracking:** Orchestrator records subtask completion in `STATE.md` with timestamp and artifact location.
4. **Failure handling:** If a subtask fails:
   - Do NOT skip it or proceed to next subtask
   - Either retry the subtask, escalate to human with error details, or pause the phase
   - Document failure reason and human decision in `DECISION_LOG.md`

Within parallel phases (e.g., Phase 3, Phase 6):

1. **Independent work:** Each concurrent subtask is independent (no blocking dependencies on other subtasks in the phase)
2. **Sync point:** All subtasks must report completion. Orchestrator waits for all before proceeding to next phase.
3. **Timeout:** If a subtask exceeds reasonable time budget, human is notified; orchestrator can mark as "failed" or "timed out" and proceed if critical path allows.

---

## Gate Protocol

Every gate follows this structure:

### Input Criteria

What must be ready before the gate evaluation:
- Specific artifact files (e.g., feature list, model checkpoint, analysis report)
- Completed phase(s) and subtasks
- Data quality or metric thresholds met

### Evaluation Method

How the gate is evaluated:
- **Automated gates (e.g., Gate 3):** Orchestrator evaluates metric against threshold
- **Human gates (e.g., Gate 2, Gate 4):** Orchestrator produces summary document; human domain expert reviews and approves/rejects
- **Dual gates:** Automated pre-check, then human review if automated check fails

### Pass Threshold

Explicit criterion for passing:
- Example (Gate 1): "Data quality sufficient; no critical corruption; loader benchmarked"
- Example (Gate 3): "Primary metric >= Tier 1 threshold; no data leakage; statistically significant improvement over baseline"
- Example (Gate 2, 4): "Human approves with no required changes"

### Failure Action

What happens if gate fails:
- **Automatic retry:** If temporary issue (e.g., computation timeout), retry once
- **Escalate to human:** If ambiguous or out-of-specification, summarize and ask human for decision
- **Iterate phase:** Specify which phase to return to
- **Document exception:** Any human override of a failed gate is logged to `DECISION_LOG.md` with rationale

### Logging

Every gate evaluation is logged:
- **Timestamp** of evaluation
- **Inputs** reviewed (which artifacts, data sources)
- **Criterion** applied (threshold, human judgment)
- **Result** (pass, fail, conditional)
- **Rationale** (why it passed/failed; what changed)
- **Decision** (proceed, iterate, escalate, or override)

All gate decisions are stored in `DECISION_LOG.md` for reproducibility and audit.

---

## Orchestration Contract

The orchestrator enforces:

1. **No phase skipping:** Agents cannot proceed to Phase N without Gate N-1 approval
2. **No subtask jumping:** Within sequential phases, agents must complete subtasks in order
3. **Artifact validation:** Orchestrator checks that required artifacts exist before proceeding
4. **State consistency:** Orchestrator maintains single source of truth in `STATE.md`
5. **Decision logging:** Every gate and human decision is logged and auditable
6. **Error handling:** Failed subtasks do not automatically skip; failure is escalated
7. **Workflow mode enforcement:** Orchestrator ensures correct subtask set is activated per workflow mode
8. **Compute budget tracking:** Orchestrator tracks total GPU-hours and flags when approaching budget limits

---

## Summary

This workflow encodes disciplined, auditable ML/research project execution across classical ML, deep learning, and research contexts. By enforcing sequencing, gating at critical decisions, maintaining human-in-the-loop checkpoints, and requiring structured analysis (ablation, error analysis, statistical significance), it ensures that wasted computation is minimized, human oversight is maintained, and results are reproducible, explainable, and statistically sound.

Projects adapt this default workflow via `plan.md` customizations. The orchestrator enforces the adapted workflow throughout execution.
