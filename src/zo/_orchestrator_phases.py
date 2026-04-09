"""Phase template factories for ZO orchestrator.

Internal module — defines workflow phase templates per mode.
Import from ``zo.orchestrator`` instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from zo._orchestrator_models import GateType, PhaseDefinition
from zo.plan import WorkflowMode

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Agent-to-phase mapping
# ---------------------------------------------------------------------------

AGENT_PHASE_MAP: dict[str, list[str]] = {
    "data-engineer": ["phase_0", "phase_1", "phase_2"],
    "model-builder": ["phase_3", "phase_4", "phase_5"],
    "oracle-qa": ["phase_3", "phase_4", "phase_5"],
    "code-reviewer": [
        "phase_1", "phase_2", "phase_3", "phase_4", "phase_5", "phase_6",
    ],
    "test-engineer": [
        "phase_1", "phase_2", "phase_3", "phase_4", "phase_5", "phase_6",
    ],
    "xai-agent": ["phase_5"],
    "domain-evaluator": ["phase_5"],
    "ml-engineer": ["phase_4", "phase_5", "phase_6"],
    "infra-engineer": ["phase_1", "phase_6"],
    "lead-orchestrator": [],
}


# ---------------------------------------------------------------------------
# Phase templates per workflow mode
# ---------------------------------------------------------------------------


def classical_ml_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the classical_ml workflow."""
    return [
        PhaseDefinition(
            phase_id="phase_1",
            name="Data Review and Pipeline",
            description="Validate raw data, profile, clean, version, build loaders.",
            subtasks=[
                "Raw data audit", "Data hygiene", "Exclusion filters",
                "Data alignment", "EDA", "Data versioning", "Data loader",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=[],
        ),
        PhaseDefinition(
            phase_id="phase_2",
            name="Feature Engineering and Selection",
            description="Engineer features, filter, prune multicollinearity, rank.",
            subtasks=[
                "Feature engineering", "Section filter", "Statistical filter",
                "Multicollinearity pruning", "Domain validation", "Feature ranking",
            ],
            gate_type=GateType.BLOCKING,
            depends_on=["phase_1"],
        ),
        PhaseDefinition(
            phase_id="phase_3",
            name="Model Design",
            description=(
                "Select architecture, design loss, define training strategy, "
                "set up oracle and experiment tracking."
            ),
            subtasks=[
                "Architecture selection", "Loss function design",
                "Training strategy", "Regime segmentation",
                "Oracle setup", "Experiment tracking",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_2"],
        ),
        PhaseDefinition(
            phase_id="phase_4",
            name="Training and Iteration",
            description="Train, iterate, cross-validate, ensemble exploration.",
            subtasks=[
                "Baseline training", "Iteration protocol",
                "Cross-validation", "Ensemble exploration",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_3"],
        ),
        PhaseDefinition(
            phase_id="phase_5",
            name="Analysis and Validation",
            description=(
                "Explainability, domain consistency, error analysis, "
                "ablation, statistical significance."
            ),
            subtasks=[
                "Feature attribution", "Domain consistency",
                "Data corroboration", "Magnitude plausibility",
                "Error analysis", "Ablation study",
                "Significance testing", "Reproducibility",
                "Report assembly",
            ],
            gate_type=GateType.BLOCKING,
            depends_on=["phase_4"],
        ),
        PhaseDefinition(
            phase_id="phase_6",
            name="Packaging",
            description="Inference pipeline, model card, validation report, tests.",
            subtasks=[
                "Inference pipeline", "Model card",
                "Validation report", "Drift detection", "Test suite",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_5"],
        ),
    ]


def deep_learning_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the deep_learning workflow."""
    phases = classical_ml_phases()
    # Phase 2: input representation focus
    phases[1] = PhaseDefinition(
        phase_id="phase_2",
        name="Input Representation Design",
        description=(
            "Design input representations, transfer learning assessment, "
            "augmentation strategy."
        ),
        subtasks=[
            "Input representation design", "Transfer learning assessment",
            "Augmentation strategy",
        ],
        gate_type=GateType.BLOCKING,
        depends_on=["phase_1"],
    )
    # Phase 3: expanded architecture search
    phases[2] = PhaseDefinition(
        phase_id="phase_3",
        name="Model Design (Deep Learning)",
        description=(
            "Architecture search, loss design, training strategy with LR "
            "scheduling and gradient diagnostics, oracle and tracking setup."
        ),
        subtasks=[
            "Architecture selection", "Loss function design",
            "Training strategy", "Gradient diagnostics plan",
            "Regime segmentation", "Oracle setup", "Experiment tracking",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_2"],
    )
    # Phase 4: add training diagnostics subtask
    phases[3] = PhaseDefinition(
        phase_id="phase_4",
        name="Training and Iteration (Deep Learning)",
        description="Train with diagnostics, iterate, cross-validate, ensemble.",
        subtasks=[
            "Baseline training", "Training diagnostics",
            "Iteration protocol", "Cross-validation", "Ensemble exploration",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_3"],
    )
    return phases


def research_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the research workflow."""
    phase_0 = PhaseDefinition(
        phase_id="phase_0",
        name="Literature Review and Prior Art",
        description="Survey prior art, define baselines and evaluation protocol.",
        subtasks=["Prior art survey", "Baseline definition"],
        gate_type=GateType.AUTOMATED,
        depends_on=[],
    )
    base = deep_learning_phases()
    # Shift dependency: phase_1 now depends on phase_0
    base[0].depends_on = ["phase_0"]
    # Phase 5: expand with ablation and reproducibility
    base[4] = PhaseDefinition(
        phase_id="phase_5",
        name="Analysis and Validation (Research)",
        description=(
            "Full analysis with ablation studies, statistical significance, "
            "reproducibility verification."
        ),
        subtasks=[
            "Feature attribution", "Domain consistency",
            "Data corroboration", "Magnitude plausibility",
            "Error analysis", "Ablation study",
            "Significance testing", "Reproducibility",
            "Report assembly",
        ],
        gate_type=GateType.BLOCKING,
        depends_on=["phase_4"],
    )
    # Phase 6: add research artifacts
    base[5] = PhaseDefinition(
        phase_id="phase_6",
        name="Packaging (Research)",
        description=(
            "Inference pipeline, model card, validation report, tests, "
            "paper-ready figures and reproducibility bundle."
        ),
        subtasks=[
            "Inference pipeline", "Model card", "Validation report",
            "Drift detection", "Test suite", "Research artifacts",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_5"],
    )
    return [phase_0, *base]


MODE_PHASE_FACTORY: dict[WorkflowMode, Callable[[], list[PhaseDefinition]]] = {
    WorkflowMode.CLASSICAL_ML: classical_ml_phases,
    WorkflowMode.DEEP_LEARNING: deep_learning_phases,
    WorkflowMode.RESEARCH: research_phases,
}
