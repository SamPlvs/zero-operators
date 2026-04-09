"""Pydantic models for ZO orchestrator.

Internal module — import from ``zo.orchestrator`` instead.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from zo.plan import WorkflowMode  # noqa: TC001


class GateMode(StrEnum):
    """Controls how phase gates are evaluated.

    SUPERVISED: every phase transition requires human approval.
    AUTO: only gates marked BLOCKING in the plan require human approval.
    FULL_AUTO: no human gates — ZO runs to completion autonomously.
    """

    SUPERVISED = "supervised"
    AUTO = "auto"
    FULL_AUTO = "full_auto"


class PhaseStatus(StrEnum):
    """Lifecycle status of a workflow phase."""

    PENDING = "pending"
    ACTIVE = "active"
    GATED = "gated"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class GateDecision(StrEnum):
    """Outcome of a gate evaluation."""

    PROCEED = "proceed"
    HOLD = "hold"
    ITERATE = "iterate"
    ESCALATE = "escalate"


class GateType(StrEnum):
    """Whether a gate is evaluated automatically or requires human input."""

    AUTOMATED = "automated"
    BLOCKING = "blocking"


class PhaseDefinition(BaseModel):
    """A single phase in the workflow decomposition."""

    phase_id: str
    name: str
    description: str
    subtasks: list[str] = Field(default_factory=list)
    assigned_agents: list[str] = Field(default_factory=list)
    gate_type: GateType
    status: PhaseStatus = PhaseStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    completed_subtasks: list[str] = Field(default_factory=list)


class AgentContract(BaseModel):
    """Integration contract for an agent within a phase."""

    agent_name: str
    phase_id: str
    role_description: str
    ownership: list[str] = Field(default_factory=list)
    off_limits: list[str] = Field(default_factory=list)
    contract_produced: list[str] = Field(default_factory=list)
    contract_consumed: list[str] = Field(default_factory=list)
    validation_checklist: list[str] = Field(default_factory=list)
    coordination_rules: list[str] = Field(default_factory=list)


class GateEvaluation(BaseModel):
    """Result of evaluating a phase gate."""

    phase_id: str
    gate_type: GateType
    decision: GateDecision
    metric_results: dict[str, float] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)
    rationale: str = ""
    requires_human: bool = False


class WorkflowDecomposition(BaseModel):
    """Full workflow decomposition for a project."""

    mode: WorkflowMode
    phases: list[PhaseDefinition] = Field(default_factory=list)
    agent_contracts: list[AgentContract] = Field(default_factory=list)
