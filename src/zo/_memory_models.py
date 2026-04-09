"""Pydantic models for ZO memory layer.

Internal module — import from ``zo.memory`` instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OperatingMode(StrEnum):
    """ZO operating modes."""

    BUILD = "build"
    CONTINUE = "continue"
    MAINTAIN = "maintain"


class Confidence(StrEnum):
    """Confidence levels for decisions and priors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SessionState(BaseModel):
    """Parsed representation of STATE.md."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: OperatingMode = OperatingMode.BUILD
    phase: str = "init"
    last_completed_subtask: str | None = None
    active_blockers: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    active_agents: list[str] = Field(default_factory=list)
    git_head: str | None = None
    context_window_usage: str = "not tracked in v1"

    model_config = {"use_enum_values": True}


class DecisionEntry(BaseModel):
    """One entry in DECISION_LOG.md."""

    title: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context: str = ""
    decision: str = ""
    rationale: str = ""
    alternatives_considered: str = ""
    outcome: str = "pending"
    confidence: Confidence = Confidence.MEDIUM

    model_config = {"use_enum_values": True}


class PriorEntry(BaseModel):
    """One entry in PRIORS.md."""

    category: str
    statement: str
    evidence: str = ""
    confidence: Confidence = Confidence.MEDIUM
    superseded_by: str | None = None

    model_config = {"use_enum_values": True}


class SessionSummary(BaseModel):
    """One session summary file."""

    date: str = Field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d"))
    duration: str = ""
    mode: OperatingMode = OperatingMode.BUILD
    agent: str = "orchestrator"
    accomplished: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    blockers_hit: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    estimated_completion: str = ""
    open_questions: list[str] = Field(default_factory=list)
    recommended_next_phase: str = ""

    model_config = {"use_enum_values": True}
