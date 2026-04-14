# Delivery Repo Structure

Reference for the delivery repo layout created by `zo init` (or, for an existing repo, `zo init --no-tmux --existing-repo PATH [--layout-mode adaptive]`). When the conversational Init Architect runs, it inspects the target repo first and may pick `adaptive` mode automatically — in which case only the ZO meta-dirs (`configs/`, `experiments/`, `reports/`, `notebooks/phase/`, `docker/`, `STRUCTURE.md`) are added; your existing `src/` and `data/` layout is preserved.

---

## Philosophy

- **Configs separate from code** -- agents edit YAML configs, not source files. Experiments freeze config snapshots for reproducibility.
- **Experiments as context trail** -- `experiments/README.md` indexes all runs; each `exp-NNN/` is a self-contained record of what was tried and why.
- **Tests split by concern** -- `tests/unit/` for code correctness, `tests/ml/` for oracle thresholds and benchmarks.
- **Notebooks by phase** -- `notebooks/phase/` contains sequentially numbered notebooks (one per pipeline phase), combining exploration and auto-generated summaries.
- **Docker-first training** -- `docker/` provides a multi-stage build with GPU support; agents run training inside the container.

---

## Directory Tree

```
{project}/
├── configs/
│   ├── data/                     — dataset paths, splits, preprocessing
│   ├── model/                    — architecture hyperparameters
│   ├── training/                 — optimizer, LR schedule, epochs, batch size
│   └── experiment/base.yaml      — master config composing the above
├── src/
│   ├── data/                     — Dataset classes, transforms, DataLoader, splits
│   ├── model/                    — Model zoo (architectures, heads, base classes)
│   ├── engineering/              — Training loop, DDP/FSDP, tracking, checkpointing
│   ├── inference/                — Production inference, ONNX/TorchScript export
│   └── utils/                    — File I/O, plotting, logging, reproducibility
├── data/
│   ├── raw/                      — original data (gitignored)
│   └── processed/                — cleaned, split, versioned
├── models/                       — trained checkpoints (*.pt, *.onnx)
├── experiments/
│   ├── README.md                 — index of experiments + current direction
│   └── exp-NNN/                  — config.yaml, results.json, notes.md
├── reports/
│   ├── figures/                  — plots, charts
│   └── *.md                      — phase reports, model card, validation report
├── notebooks/
│   └── phase/                    — sequentially numbered notebooks (01_data_pipeline, 02_feature_engineering, etc.)
├── tests/
│   ├── unit/                     — code correctness tests
│   ├── ml/                       — oracle threshold checks, benchmarks
│   └── fixtures/                 — test data and mocks
├── docker/
│   ├── Dockerfile                — multi-stage build
│   ├── docker-compose.yml        — GPU service
│   └── .dockerignore
├── STRUCTURE.md                  — directory reference (agents read this)
├── pyproject.toml
├── .gitignore
└── README.md
```

---

## Agent Ownership

| Directory | Primary Agent | Phase | What goes in |
|-----------|--------------|-------|-------------|
| `configs/data/` | Data Engineer | 1 | Dataset config, splits, augmentation params |
| `configs/model/` | Model Builder | 3 | Architecture hyperparams |
| `configs/training/` | Model Builder | 3-4 | Optimizer, LR, epochs, batch size |
| `configs/experiment/` | Lead Orchestrator | 3+ | Master config, experiment definitions |
| `src/data/` | Data Engineer | 1-2 | Dataset, transforms, loaders, splits |
| `src/model/` | Model Builder | 3 | Architecture code, model zoo |
| `src/engineering/` | Model Builder | 3-4 | Trainer, DDP, tracking, checkpointing |
| `src/inference/` | Model Builder | 6 | Inference pipeline, export, serving |
| `src/utils/` | Any agent | Any | Shared utilities |
| `data/raw/` | Data Engineer | 1 | Source data (gitignored) |
| `data/processed/` | Data Engineer | 1 | Cleaned, split data |
| `models/` | Model Builder | 4 | Trained checkpoints |
| `experiments/` | Lead Orchestrator | 3+ | Experiment context trail |
| `reports/` | Oracle/QA, XAI | 1-6 | Phase reports, figures |
| `notebooks/phase/` | ZO + Human | 1-6 | Per-phase notebooks (NN_description.ipynb) |
| `tests/unit/` | Test Engineer | 4-6 | Code correctness tests |
| `tests/ml/` | Oracle/QA | 4-6 | Metric threshold tests, benchmarks |
| `docker/` | Data Engineer | 1 | Container config (agents customize) |

---

## Experiments as Context Trail

`experiments/` is the project's institutional memory. The Lead Orchestrator maintains it from Phase 3 onward.

**`experiments/README.md`** -- top-level index listing every experiment with a one-line summary, outcome (pass/fail/abandoned), and link to the `exp-NNN/` directory. Agents read this before proposing new runs to avoid repeating work.

**`experiments/exp-NNN/`** -- each experiment directory contains:

| File | Purpose |
|------|---------|
| `config.yaml` | Frozen snapshot of the full config at run time |
| `results.json` | Metrics (primary + secondary), training time, resource usage |
| `notes.md` | What was tried, why, what was learned, next steps |

Experiment numbering is sequential (`exp-001`, `exp-002`, ...). The frozen `config.yaml` ensures any result can be reproduced exactly.

---

## Configs

All configuration lives in `configs/` as YAML files. Agents edit configs, not code -- source files read from these configs at runtime.

```
configs/
├── data/           — dataset paths, splits, preprocessing, augmentation
├── model/          — architecture hyperparams (layers, hidden dims, dropout)
├── training/       — optimizer, learning rate schedule, epochs, batch size
└── experiment/
    └── base.yaml   — master config that composes data + model + training
```

`experiment/base.yaml` imports the other configs and defines the current active experiment. When an experiment starts, the orchestrator copies this file into `experiments/exp-NNN/config.yaml` as a frozen snapshot.

---

## Notebooks

```
notebooks/
└── phase/      — sequentially numbered per-phase notebooks
    ├── 01_data_pipeline.ipynb
    ├── 02_feature_engineering.ipynb
    ├── 03_baseline_models.ipynb
    └── ...
```

All notebooks live in `notebooks/phase/` with sequential numbering matching the pipeline phases. Each notebook combines data exploration, analysis, and auto-generated summaries for its phase. Named `NN_<description>.ipynb`.

---

## Tests

```
tests/
├── unit/       — code correctness (imports, shapes, edge cases, I/O)
├── ml/         — oracle threshold checks, latency benchmarks, regression
└── fixtures/   — shared test data and mocks
```

**`unit/`** -- standard pytest tests written by the Test Engineer. Verify that code works correctly independent of model quality.

**`ml/`** -- oracle-driven tests written by Oracle/QA. Assert that trained models meet threshold metrics (accuracy >= X, latency <= Y). These fail when model quality regresses, not when code breaks.

---

## Docker

```
docker/
├── Dockerfile            — multi-stage build (base + train + serve)
├── docker-compose.yml    — GPU service with volume mounts
└── .dockerignore
```

The Dockerfile uses a multi-stage build: base image with Python + CUDA, training stage with ML dependencies, and an optional serving stage for inference. `docker-compose.yml` mounts `data/`, `models/`, `configs/`, and `src/` as volumes so agents can iterate without rebuilding.

Agents run training inside the container via `docker compose run train`. The Data Engineer sets up the initial container in Phase 1; other agents customize as needed.

---

## STRUCTURE.md

The delivery repo includes a `STRUCTURE.md` at the root. This is the in-repo reference that agents read at the start of each phase to orient themselves. It mirrors this document but lives inside the delivery repo so agents working in `--cwd` mode can access it without referencing the ZO repo.
