"""Pydantic models for ZO evolution engine.

Internal module — import from ``zo.evolution`` instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RootCauseCategory(StrEnum):
    """Categories for root cause analysis."""

    MISSING_RULE = "missing_rule"
    INCOMPLETE_RULE = "incomplete_rule"
    IGNORED_RULE = "ignored_rule"
    NOVEL_CASE = "novel_case"
    REGRESSION = "regression"


class FailureSeverity(StrEnum):
    """Severity levels for failure records."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class FailureRecord(BaseModel):
    """A documented failure event."""

    title: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detected_by: str
    severity: FailureSeverity
    phase: str
    description: str
    immediate_impact: str
    artifacts_affected: list[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}


class RootCauseAnalysis(BaseModel):
    """Result of root cause investigation for a failure."""

    failure: FailureRecord
    root_cause: str
    rule_gap: str
    category: RootCauseCategory
    document_to_update: str

    model_config = {"use_enum_values": True}


class RuleUpdate(BaseModel):
    """A proposed or applied rule update."""

    document_path: str
    change_description: str
    rationale: str
    failure_reference: str
    verified: bool = False
    verification_method: str = ""


class EvolutionEntry(BaseModel):
    """A tracked evolution event in DECISION_LOG."""

    title: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    triggered_by: str
    document_updated: str
    change: str
    rationale: str
    verified: bool
    verification_method: str


class RetrospectiveReport(BaseModel):
    """End-of-project retrospective output."""

    project_name: str
    date: str
    sessions_completed: int
    total_failures: int
    total_rule_updates: int
    failure_distribution: dict[str, int] = Field(default_factory=dict)
    patterns: list[str] = Field(default_factory=list)
    recommended_updates: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
