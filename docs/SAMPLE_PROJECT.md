# Running ZO: CIFAR-10 Sample Project

A step-by-step guide to running Zero Operators on a CIFAR-10 image classifier. Use this to verify your setup before tackling a real project.

**What you'll validate:** plan parsing, phase persistence, gate handling, artifact generation, notebook output, Docker build, and session continuity.

---

## Prerequisites

```bash
# SSH into your server (or run locally)
ssh your-server
tmux new -s zo

# Verify ZO environment
cd /path/to/zero-operators
bash setup.sh
```

All 10 checks should pass.

---

## Step 1: Initialize the Project

```bash
# ZO-side scaffold (memory, targets, plans)
zo init cifar10-demo

# Delivery repo with Docker + ML layout
mkdir -p ~/projects/cifar10-delivery
cd ~/projects/cifar10-delivery && git init && cd -
zo init cifar10-demo --scaffold-delivery ~/projects/cifar10-delivery
```

**What this creates:**

```
zero-operators/                          ~/projects/cifar10-delivery/
  memory/cifar10-demo/                     data/raw/ data/processed/
    STATE.md                               src/models/ src/pipelines/ src/utils/
    DECISION_LOG.md                        experiments/
    PRIORS.md                              models/
  targets/cifar10-demo.target.md           reports/figures/
  plans/cifar10-demo.md (template)         notebooks/
                                           tests/fixtures/
                                           Dockerfile
                                           docker-compose.yml
                                           pyproject.toml
                                           .gitignore
```

---

## Step 2: Write the Plan

Edit `plans/cifar10-demo.md`:

```markdown
---
project_name: "cifar10-demo"
version: "1.0"
created: "2026-04-12"
status: active
owner: "Sam"
---

## Objective

Build a CIFAR-10 image classifier using PyTorch. Train a CNN that achieves
at least 85% test accuracy. Produce a clean delivery repo with trained model,
inference script, evaluation reports, and test suite.

## Oracle

**Primary metric:** Test accuracy on CIFAR-10 test set (10,000 images)
**Ground truth source:** torchvision.datasets.CIFAR10 (test split)
**Evaluation method:** Forward pass on test set, compute top-1 accuracy
**Target threshold:**
  - Tier 1: >= 0.90
  - Tier 2: >= 0.85
  - Tier 3: >= 0.75
**Evaluation frequency:** After each training iteration
**Secondary metrics:** Per-class accuracy, confusion matrix, inference latency

## Workflow

**Mode:** deep_learning
**Phases:**
  - Phase 1: Data pipeline (CIFAR-10 download, DataLoaders, augmentation)
  - Phase 2: Input representation (normalization, augmentation strategy)
  - Phase 3: Model design (CNN architecture, loss, training strategy)
  - Phase 4: Training and iteration (train, evaluate, iterate)
  - Phase 5: Analysis (explainability, error analysis, ablation)
  - Phase 6: Packaging (inference script, model card, tests)
**Gates:**
  - Gate 1: automated (data pipeline tests pass)
  - Gate 2: blocking (human reviews input representation)
  - Gate 3: automated (architecture defined)
  - Gate 4: automated (oracle threshold met)
  - Gate 5: blocking (human reviews full analysis)
  - Gate 6: automated (packaging complete)
**Iteration budget:** 20 agent sessions
**Human checkpoints:** Gate 2, Gate 5

## Data Sources

### Source 1: CIFAR-10
- **Location:** Auto-downloaded via torchvision
- **Format:** 32x32 RGB images, 10 classes
- **Access:** torchvision.datasets.CIFAR10(download=True)
- **Known issues:** Small images; augmentation important for generalization

## Domain Priors

### Deep Learning Knowledge
- CIFAR-10 SOTA is >96% but simple CNNs reach 85-92%
- ResNet-style skip connections help on CIFAR-10
- Standard augmentation: random crop, horizontal flip, color jitter
- Batch normalization + dropout regularization effective
- Learning rate: 1e-3 with Adam, or 0.1 with SGD + cosine schedule
- Training typically converges in 50-100 epochs

### Expected Relationships
- "airplane" and "bird" occasionally confused (both in sky)
- "cat" and "dog" most commonly confused pair
- "automobile" and "truck" share features

## Agents

**Active agents:** lead-orchestrator, data-engineer, model-builder,
                   oracle-qa, code-reviewer, test-engineer, research-scout
**Phase-in agents:** (none for this demo)

## Constraints

- PyTorch only (no TensorFlow)
- Training must complete in under 30 minutes on single GPU
- All training runs inside Docker container
- Reports with plots in reports/figures/
- Model checkpoint saved as models/best_model.pt
- Inference script at src/inference.py
```

---

## Step 3: Edit the Target File

Edit `targets/cifar10-demo.target.md`:

```markdown
---
project: "cifar10-demo"
target_repo: "/home/sam/projects/cifar10-delivery"
target_branch: "main"
worktree_base: "/tmp/zo-worktrees/cifar10-demo"
git_author_name: "Zero Operators Agent"
git_author_email: "agents@zero-operators.local"
agent_working_dirs:
  lead_orchestrator: "."
  data_engineer: "data/"
  model_builder: "src/"
  oracle_qa: "reports/"
  code_reviewer: "."
  test_engineer: "tests/"
zo_only_paths:
  - ".claude/"
  - "CLAUDE.md"
  - "STATE.md"
  - "memory/"
  - "logs/"
  - "zero-operators/"
enforce_isolation: true
---
```

> **Note:** Update `/home/sam/projects/cifar10-delivery` to your actual path.

---

## Step 4: Build Docker Container

```bash
cd ~/projects/cifar10-delivery

# Add PyTorch to the delivery repo's dependencies
cat >> pyproject.toml << 'EOF'

[project.optional-dependencies]
ml = [
    "torch>=2.0",
    "torchvision>=0.15",
    "matplotlib>=3.7",
    "seaborn>=0.12",
    "pandas>=2.0",
    "numpy>=1.24",
]
EOF

# Build the container (~2 min first time)
docker compose build
```

---

## Step 5: Preflight Check

```bash
cd /path/to/zero-operators
zo preflight plans/cifar10-demo.md --target-repo ~/projects/cifar10-delivery
```

Expected output:
```
  PASS  Claude CLI: Found at /usr/local/bin/claude
  PASS  tmux: Found at /usr/bin/tmux
  PASS  Plan: All 8 sections valid
  PASS  Agents: All 7 agent definitions found
  PASS  Target Repo: Git repo at /home/sam/projects/cifar10-delivery
  PASS  Delivery Structure: All directories present
  PASS  Dockerfile: Dockerfile present
  PASS  Memory: Write/read round-trip OK
  PASS  Docker: Docker version 24.x.x
  WARN  GPU: nvidia-smi not found (if on Mac, this is expected)

  9/10 passed, 1 warnings, 0 failures

  Ready for zo build.
```

---

## Step 6: Launch

```bash
# Supervised mode -- approve every gate (recommended for first run)
zo build plans/cifar10-demo.md --gate-mode supervised
```

**What happens:**

1. ZO brand panel displays: project name, mode, phase count, gate info
2. Phase review shows all 6 phases with subtasks and agents
3. You're prompted for additional instructions (optional, press Enter to skip)
4. Lead Orchestrator spawns in a tmux pane
5. Agent team begins Phase 1 (data pipeline)

---

## Step 7: Monitor Progress

```bash
# In another tmux pane (Ctrl-b c for new pane)
zo status cifar10-demo

# View live comms log
tail -f logs/comms/$(date +%Y-%m-%d).jsonl | python -m json.tool

# Check delivery repo artifacts
ls ~/projects/cifar10-delivery/reports/
ls ~/projects/cifar10-delivery/notebooks/
```

---

## Step 8: Approve Gates

ZO pauses at blocking gates (Gate 2 and Gate 5 in this plan).

**Gate 2 (after Phase 2):** Review input representation and augmentation strategy.
```bash
# Check what agents produced
cat ~/projects/cifar10-delivery/reports/feature_selection_report.md
# Open the auto-generated notebook
jupyter notebook ~/projects/cifar10-delivery/notebooks/

# Satisfied? Run zo build again to continue
zo build plans/cifar10-demo.md --gate-mode supervised
```

**Gate 5 (after Phase 5):** Review full analysis package.
```bash
cat ~/projects/cifar10-delivery/reports/analysis_report.md
ls ~/projects/cifar10-delivery/reports/figures/
# Check confusion matrix, training curves, etc.
```

---

## Step 9: Test Phase Persistence

This is key -- verify that stopping and restarting works:

```bash
# During any phase, Ctrl-C to stop
# Then restart:
zo build plans/cifar10-demo.md --gate-mode supervised

# ZO should resume from the current phase, not restart from Phase 1
zo status cifar10-demo
# Should show: phase = phase_N (where N > 1)
```

---

## Step 10: Check Final Artifacts

After all 6 phases complete:

```bash
# Delivery repo structure
tree ~/projects/cifar10-delivery/

# Expected:
cifar10-delivery/
  data/
    raw/                    # CIFAR-10 auto-downloaded
    processed/              # Preprocessed tensors
  src/
    models/model.py         # CNN architecture
    pipelines/train.py      # Training script
    inference.py            # Inference pipeline
  models/
    best_model.pt           # Trained checkpoint
  reports/
    data_quality_report.md  # Phase 1
    feature_selection_report.md  # Phase 2
    architecture_rationale.md    # Phase 3
    training_report.md      # Phase 4
    analysis_report.md      # Phase 5
    model_card.md           # Phase 6
    validation_report.md    # Phase 6
    figures/
      eda_summary.png
      feature_importance.png
      training_curves.png
      confusion_matrix.png
  notebooks/
    phase_1_data_review.ipynb
    phase_2_features.ipynb
    phase_3_model_design.ipynb
    phase_4_training.ipynb
    phase_5_analysis.ipynb
    phase_6_packaging.ipynb
  tests/
    test_model.py
    test_inference.py
  Dockerfile
  docker-compose.yml
  pyproject.toml
```

---

## Step 11: Disconnect and Reconnect

```bash
# Detach tmux (ZO keeps running in background)
Ctrl-b d

# Later, reconnect:
tmux attach -t zo
# Agent team is still working
```

---

## Validation Checklist

| Feature | How to verify |
|---------|---------------|
| Plan parsing | `zo preflight` passes plan validation |
| Phase persistence | Stop mid-run, `zo build` again, check `zo status` shows correct phase |
| Gate handling | Supervised mode pauses at Gate 2 and Gate 5 |
| Artifact contracts | Reports appear in `reports/`, figures in `reports/figures/` |
| Notebook generation | `.ipynb` files in `notebooks/` after each phase |
| Docker | `docker compose build` succeeds, training runs in container |
| Memory | `zo status` shows accurate state after each phase |
| Comms logging | JSONL events in `logs/comms/` |
| Repo isolation | No ZO files (STATE.md, memory/, .claude/) in delivery repo |
| Session continuity | tmux detach + reattach, agents still working |

---

## Troubleshooting

**`zo build` appears stuck:** Check the tmux pane — agents may be waiting for permission. Review `.claude/settings.json` allow rules.

**Phase restarts from 1:** Verify `memory/cifar10-demo/STATE.md` has a `## Phases` section. If not, the old STATE.md format is being used.

**Docker GPU not available:** On Mac, NVIDIA GPUs aren't supported. Training falls back to CPU (slower but works). On Linux, verify `nvidia-smi` works and NVIDIA Container Toolkit is installed.

**Agents ask too many permission prompts:** Broaden `.claude/settings.json` allow patterns. See PR-002 in `memory/zo-platform/PRIORS.md`.
