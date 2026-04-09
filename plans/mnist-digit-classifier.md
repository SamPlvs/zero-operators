# MNIST Digit Classifier

---
project_name: "mnist-digit-classifier"
version: "1.0"
created: "2026-04-09"
last_modified: "2026-04-09"
status: active
owner: "Sam"
---

## Objective

Build a PyTorch CNN that classifies handwritten digits (0-9) from the MNIST dataset with >95% test accuracy. This is a toy project to validate the Zero Operators pipeline end-to-end — every phase, gate, memory operation, and agent contract must exercise correctly.

Deliverables: trained model checkpoint, inference script, validation report with confusion matrix, model card, and test suite.

## Oracle

**Primary metric:** Test accuracy on MNIST test set (10,000 images)
**Ground truth source:** MNIST test labels (torchvision.datasets.MNIST, train=False)
**Evaluation method:** Forward pass on full test set, compute accuracy = correct / total
**Target threshold:** Accuracy >= 0.95 (Tier 1), Accuracy >= 0.90 (Tier 2), Accuracy >= 0.80 (Tier 3)
**Evaluation frequency:** After every training run
**Secondary metrics:** Per-digit accuracy, confusion matrix, inference latency (ms/image)

## Workflow

**Mode:** deep_learning
**Phases:** default
**Gates:**
  - Gate 1: automated (data pipeline verified)
  - Gate 2: blocking (human reviews input representation)
  - Gate 3: automated (architecture defined)
  - Gate 4: automated (oracle threshold met)
  - Gate 5: blocking (human reviews model and validation report)
  - Gate 6: automated (packaging complete)

**Iteration budget:** 20 training runs or 30 minutes wall time, whichever comes first
**Human checkpoints:** After input representation (Gate 2), after validation (Gate 5)

## Data Sources

### Source 1: MNIST Dataset
- **Location:** `torchvision.datasets.MNIST(root='data/raw', download=True)`
- **Format:** 28x28 grayscale images, labels 0-9
- **Time range:** Static dataset (no temporal component)
- **Access:** Auto-download via torchvision
- **Known issues:** None. Well-understood benchmark.

## Domain Priors

### ML Knowledge
- MNIST is a solved benchmark — simple CNNs achieve >99% accuracy
- Two conv layers + two FC layers is sufficient; no need for ResNet/VGG
- Batch normalization and dropout improve generalization
- Learning rate 1e-3 with Adam is a reliable starting point
- Data augmentation (rotation, translation) helps but isn't necessary for >95%

### Expected Relationships
- Digits 4 and 9 are most commonly confused
- Digits 1 and 7 can be confused depending on writing style
- Simple architectures are preferable for this toy project — complexity is not the goal

### Known Risks
- Overfitting is unlikely with 60k training samples
- CPU training should complete in under 5 minutes for a simple CNN
- This is a validation exercise for ZO, not a research project

## Agents

**Active agents:** lead-orchestrator, data-engineer, model-builder, oracle-qa, code-reviewer, test-engineer
**Phase-in agents:** None (toy project, core team only)
**Inactive agents:** xai-agent, domain-evaluator, ml-engineer, infra-engineer

## Constraints

- **PyTorch only:** All models must use PyTorch
- **CPU only:** No GPU required. Training must complete on CPU in under 5 minutes
- **Simple architecture:** Max 2 conv layers, 2 FC layers. No pre-trained models
- **Reproducibility:** Fixed random seed (42) for all experiments
- **Delivery repo clean:** No ZO artifacts in the delivery repository
- **This is a ZO validation exercise:** The goal is to exercise every phase of the pipeline, not to achieve state-of-the-art accuracy

## Milestones

| Phase | Milestone | Gate |
|-------|-----------|------|
| 1 | MNIST loaded, DataLoader working, EDA complete | Gate 1 (auto) |
| 2 | Input normalization defined, no augmentation needed | Gate 2 (human) |
| 3 | CNN architecture defined, loss and optimizer chosen | Gate 3 (auto) |
| 4 | Model trained, accuracy > 95% on test set | Gate 4 (auto) |
| 5 | Confusion matrix, per-digit accuracy, model validated | Gate 5 (human) |
| 6 | Inference script, model card, test suite packaged | Gate 6 (auto) |

## Delivery

**Target repo:** ../mnist-delivery/
**Target branch:** main
**Delivery structure:**
  - src/model.py — CNN architecture definition
  - src/train.py — training script
  - src/inference.py — prediction pipeline
  - data/raw/ — MNIST auto-download location
  - models/checkpoint.pt — trained model
  - reports/validation_report.md — accuracy, confusion matrix
  - reports/model_card.md — model documentation
  - tests/test_model.py — unit tests for model
  - tests/test_inference.py — inference pipeline tests

## Environment

**Python version:** 3.11+
**Key dependencies:** torch>=2.0, torchvision
**Hardware:** CPU only
**Package manager:** uv
**Linting:** ruff
