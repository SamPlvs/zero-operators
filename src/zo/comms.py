"""Structured JSONL comms logger for Zero Operators.

Writes append-only audit events to daily log files at
``logs/comms/{YYYY-MM-DD}.jsonl``.  Every agent action, message,
and decision flows through this module so the JSONL trail is the
single source of truth for *what happened and why*.

Typical usage::

    from zo.comms import CommsLogger
    logger = CommsLogger(log_dir=Path("logs/comms"), project="alpha", session_id="s-001")
    logger.log_message(agent="builder", message_type="request", recipient="data-eng", ...)
"""

from __future__ import annotations

import fcntl
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(StrEnum):
    """The five canonical event types in the ZO audit trail."""

    MESSAGE = "message"
    DECISION = "decision"
    GATE = "gate"
    ERROR = "error"
    CHECKPOINT = "checkpoint"


class MessageType(StrEnum):
    """Peer-to-peer message subtypes."""

    REQUEST = "request"
    RESPONSE = "response"
    STATUS = "status"
    ESCALATION = "escalation"
    BROADCAST = "broadcast"
    VERDICT = "verdict"


class Priority(StrEnum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Severity(StrEnum):
    """Error severity levels."""

    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"
    CRITICAL = "critical"


class Confidence(StrEnum):
    """Decision confidence levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GateResult(StrEnum):
    """Oracle gate evaluation outcomes."""

    PASS = "pass"
    FAIL = "fail"


# ---------------------------------------------------------------------------
# Event models
# ---------------------------------------------------------------------------

class BaseEvent(BaseModel):
    """Fields present on every JSONL audit entry."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str
    event_type: EventType
    agent: str
    project: str

    model_config = {"use_enum_values": True}


class MessageEvent(BaseEvent):
    """Agent-to-agent communication event."""

    event_type: EventType = EventType.MESSAGE
    message_type: MessageType
    recipient: str
    subject: str
    body: str
    priority: Priority = Priority.NORMAL
    references: list[str] = Field(default_factory=list)


class DecisionEvent(BaseEvent):
    """Significant decision made by an agent or orchestrator."""

    event_type: EventType = EventType.DECISION
    decision_id: str = Field(default_factory=lambda: f"decision-{uuid.uuid4().hex[:12]}")
    title: str
    rationale: str
    alternatives: list[str] = Field(default_factory=list)
    outcome: str
    confidence: Confidence = Confidence.MEDIUM


class GateEvent(BaseEvent):
    """Oracle gate evaluation result."""

    event_type: EventType = EventType.GATE
    gate_id: str
    gate_name: str
    metric_name: str
    metric_value: float
    threshold: float
    tier: int
    result: GateResult
    breakdown: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class ErrorEvent(BaseEvent):
    """Failure / error event."""

    event_type: EventType = EventType.ERROR
    error_type: str
    severity: Severity
    description: str
    affected_artifacts: list[str] = Field(default_factory=list)
    resolution: str = "pending"
    escalated_to: str = ""


class CheckpointEvent(BaseEvent):
    """Periodic progress checkpoint."""

    event_type: EventType = EventType.CHECKPOINT
    phase: str
    subtask: str
    progress: str
    current_best_metric: float | None = None
    target_metric: float | None = None
    blockers: list[str] = Field(default_factory=list)


# Mapping for deserialization
_EVENT_TYPE_MAP: dict[str, type[BaseEvent]] = {
    EventType.MESSAGE: MessageEvent,
    EventType.DECISION: DecisionEvent,
    EventType.GATE: GateEvent,
    EventType.ERROR: ErrorEvent,
    EventType.CHECKPOINT: CheckpointEvent,
}


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class CommsLogger:
    """Append-only JSONL comms logger with daily rotation.

    Args:
        log_dir: Root directory for daily log files.
        project: Project identifier written into every event.
        session_id: Current session identifier.
    """

    def __init__(self, log_dir: Path, project: str, session_id: str) -> None:
        self._log_dir = Path(log_dir)
        self._project = project
        self._session_id = session_id
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # -- helpers ----------------------------------------------------------

    def _log_file_for(self, dt: datetime) -> Path:
        """Return the JSONL path for a given timestamp's date."""
        date_str = dt.strftime("%Y-%m-%d")
        return self._log_dir / f"{date_str}.jsonl"

    def _write_event(self, event: BaseEvent) -> None:
        """Atomically append a single JSONL line with file-level locking."""
        path = self._log_file_for(event.timestamp)
        line = event.model_dump_json() + "\n"
        with open(path, "a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(line)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _base_kwargs(self, agent: str) -> dict[str, Any]:
        """Return the common keyword arguments for event construction."""
        return {
            "session_id": self._session_id,
            "agent": agent,
            "project": self._project,
        }

    # -- public API -------------------------------------------------------

    def log_message(
        self,
        agent: str,
        message_type: str,
        recipient: str,
        subject: str,
        body: str,
        *,
        priority: str = "normal",
        references: list[str] | None = None,
    ) -> MessageEvent:
        """Log an agent-to-agent message event.

        Args:
            agent: Sending agent identifier.
            message_type: One of request, response, status, escalation,
                broadcast, verdict.
            recipient: Receiving agent identifier.
            subject: Short description of the message.
            body: Full message body.
            priority: Message priority (low, normal, high, critical).
            references: Optional list of related decision/event IDs.

        Returns:
            The constructed MessageEvent.
        """
        event = MessageEvent(
            **self._base_kwargs(agent),
            message_type=message_type,
            recipient=recipient,
            subject=subject,
            body=body,
            priority=priority,
            references=references or [],
        )
        self._write_event(event)
        return event

    def log_decision(
        self,
        agent: str,
        title: str,
        rationale: str,
        *,
        alternatives: list[str] | None = None,
        outcome: str = "proceed",
        confidence: str = "medium",
        decision_id: str | None = None,
    ) -> DecisionEvent:
        """Log a significant decision.

        Args:
            agent: Agent making the decision.
            title: Short decision title.
            rationale: Explanation of why this decision was made.
            alternatives: Other options considered.
            outcome: What was decided.
            confidence: Confidence level (low, medium, high).
            decision_id: Optional explicit ID; auto-generated if omitted.

        Returns:
            The constructed DecisionEvent.
        """
        kwargs: dict[str, Any] = {
            **self._base_kwargs(agent),
            "title": title,
            "rationale": rationale,
            "alternatives": alternatives or [],
            "outcome": outcome,
            "confidence": confidence,
        }
        if decision_id is not None:
            kwargs["decision_id"] = decision_id
        event = DecisionEvent(**kwargs)
        self._write_event(event)
        return event

    def log_gate(
        self,
        agent: str,
        gate_id: str,
        gate_name: str,
        metric_name: str,
        metric_value: float,
        threshold: float,
        tier: int,
        result: str,
        *,
        breakdown: dict[str, Any] | None = None,
        notes: str = "",
    ) -> GateEvent:
        """Log an oracle gate evaluation.

        Args:
            agent: Evaluating agent (usually oracle-qa).
            gate_id: Unique gate identifier.
            gate_name: Human-readable gate name.
            metric_name: Name of the metric evaluated.
            metric_value: Observed metric value.
            threshold: Required threshold.
            tier: Gate tier (1, 2, 3).
            result: "pass" or "fail".
            breakdown: Optional per-segment metric breakdown.
            notes: Free-text notes.

        Returns:
            The constructed GateEvent.
        """
        event = GateEvent(
            **self._base_kwargs(agent),
            gate_id=gate_id,
            gate_name=gate_name,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
            tier=tier,
            result=result,
            breakdown=breakdown or {},
            notes=notes,
        )
        self._write_event(event)
        return event

    def log_error(
        self,
        agent: str,
        error_type: str,
        severity: str,
        description: str,
        *,
        affected_artifacts: list[str] | None = None,
        resolution: str = "pending",
        escalated_to: str = "",
    ) -> ErrorEvent:
        """Log a failure or error.

        Args:
            agent: Agent that encountered the error.
            error_type: Category of error (e.g. data_validation).
            severity: One of info, warning, blocking, critical.
            description: What went wrong.
            affected_artifacts: Paths / identifiers of affected files.
            resolution: Current resolution status.
            escalated_to: Agent the error was escalated to, if any.

        Returns:
            The constructed ErrorEvent.
        """
        event = ErrorEvent(
            **self._base_kwargs(agent),
            error_type=error_type,
            severity=severity,
            description=description,
            affected_artifacts=affected_artifacts or [],
            resolution=resolution,
            escalated_to=escalated_to,
        )
        self._write_event(event)
        return event

    def log_checkpoint(
        self,
        agent: str,
        phase: str,
        subtask: str,
        progress: str,
        *,
        current_best_metric: float | None = None,
        target_metric: float | None = None,
        blockers: list[str] | None = None,
    ) -> CheckpointEvent:
        """Log a periodic progress checkpoint.

        Args:
            agent: Reporting agent.
            phase: Current project phase.
            subtask: Current subtask identifier.
            progress: Human-readable progress string.
            current_best_metric: Best metric achieved so far.
            target_metric: Target metric value.
            blockers: List of current blockers.

        Returns:
            The constructed CheckpointEvent.
        """
        event = CheckpointEvent(
            **self._base_kwargs(agent),
            phase=phase,
            subtask=subtask,
            progress=progress,
            current_best_metric=current_best_metric,
            target_metric=target_metric,
            blockers=blockers or [],
        )
        self._write_event(event)
        return event

    # -- query interface --------------------------------------------------

    def query_logs(
        self,
        *,
        event_type: str | None = None,
        agent: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[BaseEvent]:
        """Query the JSONL logs with optional filters.

        Reads all daily log files that overlap with the requested time
        range (or all files if no range is given) and returns matching
        events.

        Args:
            event_type: Filter to a single event type.
            agent: Filter to events from a specific agent.
            start: Inclusive lower bound on timestamp.
            end: Inclusive upper bound on timestamp.

        Returns:
            List of matching events, sorted by timestamp ascending.
        """
        results: list[BaseEvent] = []
        log_files = sorted(self._log_dir.glob("*.jsonl"))

        for path in log_files:
            # Quick date-based pruning: skip files outside the range.
            file_date_str = path.stem  # YYYY-MM-DD
            if start and file_date_str < start.strftime("%Y-%m-%d"):
                continue
            if end and file_date_str > end.strftime("%Y-%m-%d"):
                continue

            results.extend(self._parse_file(path, event_type, agent, start, end))

        results.sort(key=lambda e: e.timestamp)
        return results

    @staticmethod
    def _parse_file(
        path: Path,
        event_type: str | None,
        agent: str | None,
        start: datetime | None,
        end: datetime | None,
    ) -> list[BaseEvent]:
        """Parse a single JSONL file and return matching events."""
        events: list[BaseEvent] = []
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)

                # Apply filters on raw dict before constructing models.
                if event_type and raw.get("event_type") != event_type:
                    continue
                if agent and raw.get("agent") != agent:
                    continue

                ts = datetime.fromisoformat(raw["timestamp"])
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue

                cls = _EVENT_TYPE_MAP.get(raw["event_type"], BaseEvent)
                events.append(cls.model_validate(raw))

        return events
