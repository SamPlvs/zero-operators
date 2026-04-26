# CIFAR-10 Image Classifier

---
project_name: "cifar10-classifier"
version: "1.0"
created: "2026-04-26"
last_modified: "2026-04-26"
status: active
owner: "Sam"
---

## Objective

Build a PyTorch CNN that classifies 32x32 colour images from the CIFAR-10 dataset across 10 classes (airplane, automobile, bird, cat, deer, dog, frog, horse, ship, truck) with >70% test accuracy. This is the second validation project for Zero Operators — proves the platform handles a different dataset shape, more classes, and harder visual features than MNIST.

Deliverables: trained model checkpoint, inference script, validation report with per-class accuracy and confusion matrix, model card, ONNX export, drift detection scaffold, and packaging test suite.

## Oracle Definition

**Primary metric:** Test accuracy on CIFAR-10 test set (10,000 images)
**Ground truth source:** CIFAR-10 test labels (torchvision.datasets.CIFAR10, train=False)
**Evaluation method:** Forward pass on full test set, compute accuracy = correct / total
**Target threshold:** Accuracy >= 0.70 (Tier 1 — must-pass), Accuracy >= 0.80 (Tier 2 — should-pass), Accuracy >= 0.85 (Tier 3 — could-pass)
**Evaluation frequency:** After every training run
**Secondary metrics:** Per-class accuracy, confusion matrix, inference latency (ms/image), parameter count

## Workflow Configuration

**Mode:** deep_learning
**Phases:** default
**Gates:**
  - Gate 1: automated (data pipeline verified)
  - Gate 2: blocking (human reviews input representation)
  - Gate 3: automated (architecture defined)
  - Gate 4: automated (oracle threshold met)
  - Gate 5: blocking (human reviews model and validation report)
  - Gate 6: automated (packaging complete)

**Iteration budget:** 30 training runs or 60 minutes wall time, whichever comes first
**Human checkpoints:** After input representation (Gate 2), after validation (Gate 5)

## Environment

Populated by `zo init` from host detection.

**Host (where ZO runs):**
- platform: Darwin arm64
- python: 3.12.4
- docker_available: yes
- gpu_available: no (Apple Silicon — MPS available natively)
- gpu_count: 0
- cuda_version: (none detected)

**Training target:**
- gpu_host: local (same host as ZO)
- base_image: pytorch/pytorch:2.4.0-cpu
- accelerator: MPS (Apple Silicon Metal Performance Shaders)

**Data:**
- data_layout: local
- data_path: data/raw (auto-downloaded by torchvision)

## Data Sources

### Source 1: CIFAR-10 Dataset
- **Location:** `torchvision.datasets.CIFAR10(root='data/raw', download=True)`
- **Format:** 32x32 RGB images, labels 0-9 across 10 balanced classes (~6000/class total, 5000 train + 1000 test per class)
- **Time range:** Static dataset (no temporal component)
- **Access:** Auto-download via torchvision (~170MB)
- **Known issues:** None. Well-understood benchmark; class balance is exact.

## Domain Context and Priors

### ML Knowledge
- CIFAR-10 is a standard benchmark — simple CNNs reach 70-75%, deeper VGG-style nets reach 85-90%, ResNet-18 reaches ~93%
- Three conv blocks (with batch norm + max pool) followed by two FC layers is sufficient for >75%
- Data augmentation (random crop, horizontal flip) is critical — typically adds 5-8 percentage points
- Cosine annealing or step LR schedule is standard
- 50-100 epochs is typical with the simple architecture; longer with deeper networks
- Normalisation: per-channel mean/std (CIFAR-10 statistics are well-documented)

### Expected Relationships
- Cat-dog confusion is the classic CIFAR-10 failure mode (similar fur, similar pose)
- Car-truck and ship-airplane share some confusion due to angular similarity
- Animal classes (bird, cat, deer, dog, frog, horse) are harder than vehicle classes (airplane, automobile, ship, truck) due to pose variation

### Known Risks
- Overfitting WITHOUT augmentation — small dataset (50k train) and high capacity nets memorise quickly
- LR too high → divergence early in training; too low → slow convergence
- Forgetting to normalise → scrambled gradient flow, poor convergence

## Agent Configuration

**Active agents:** lead-orchestrator, data-engineer, model-builder, oracle-qa, code-reviewer, test-engineer, xai-agent
**Phase-in agents:** None (toy project, core team only)
**Inactive agents:** domain-evaluator, ml-engineer, infra-engineer

## Constraints

- **PyTorch only:** All models must use PyTorch
- **Apple Silicon MPS or CPU:** No CUDA. Training must complete on this hardware in under 60 minutes
- **Simple architecture:** ≤3 conv blocks, ≤2 FC layers. No pre-trained models, no torch hub fetches
- **Determinism:** Fix all random seeds. Reproducible results required for the validation report
- **Reproducibility budget:** Full re-run of the entire pipeline (data → model → eval) must complete in ≤90 minutes wall time

## Milestones and Timeline

| Milestone | Target |
|-----------|--------|
| Data pipeline complete | Phase 1 deliverable |
| Architecture finalised | Phase 3 deliverable |
| Oracle Tier 1 met (≥70%) | Phase 4 deliverable |
| Validation report ready | Phase 5 deliverable |
| Packaging artifacts complete | Phase 6 deliverable |

## Delivery Specification

**Target repo:** `/Users/sam102xoptukra1103/Documents/code/personal/cifar10-classifier-delivery`
**Target branch:** main
**Delivery structure:** ZO standard (configs/, src/, experiments/, reports/, notebooks/, docker/, .zo/)

Production-ready outputs:
- `models/cifar10_cnn.pt` — trained checkpoint (state_dict)
- `models/cifar10_cnn.onnx` — ONNX export for cross-runtime inference
- `src/inference/predict.py` — production inference script
- `reports/data_quality_report.md` — Phase 1 output
- `reports/training_report.md` — Phase 4 output
- `reports/analysis_report.md` — Phase 5 output (per-class breakdown, confusion matrix, error analysis)
- `reports/model_card.md` — Phase 6 deliverable
- `reports/validation_report.md` — Phase 6 deliverable
- `tests/unit/` — code correctness tests
- `tests/ml/` — oracle threshold and benchmark tests
