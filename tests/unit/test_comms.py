"""Unit tests for zo.comms — JSONL audit logger."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zo.comms import (
    BaseEvent,
    CheckpointEvent,
    CommsLogger,
    DecisionEvent,
    ErrorEvent,
    EventType,
    GateEvent,
    MessageEvent,
)


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    """Return a temporary log directory."""
    return tmp_path / "logs" / "comms"


@pytest.fixture()
def logger(log_dir: Path) -> CommsLogger:
    """Return a CommsLogger wired to a temp directory."""
    return CommsLogger(log_dir=log_dir, project="test-project", session_id="sess-001")


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


def test_log_dir_created_automatically(tmp_path: Path) -> None:
    """Logger creates the log directory tree if it does not exist."""
    deep = tmp_path / "a" / "b" / "c"
    assert not deep.exists()
    CommsLogger(log_dir=deep, project="p", session_id="s")
    assert deep.is_dir()


# ---------------------------------------------------------------------------
# Event type: message
# ---------------------------------------------------------------------------


def test_log_message_writes_jsonl(logger: CommsLogger, log_dir: Path) -> None:
    """log_message writes one valid JSONL line with correct fields."""
    event = logger.log_message(
        agent="builder",
        message_type="request",
        recipient="data-eng",
        subject="Need loaders",
        body="Please produce regime-segmented loaders.",
        priority="high",
        references=["decision-001"],
    )

    files = list(log_dir.glob("*.jsonl"))
    assert len(files) == 1

    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 1

    data = json.loads(lines[0])
    assert data["event_type"] == "message"
    assert data["message_type"] == "request"
    assert data["recipient"] == "data-eng"
    assert data["subject"] == "Need loaders"
    assert data["priority"] == "high"
    assert data["references"] == ["decision-001"]
    assert data["project"] == "test-project"
    assert data["session_id"] == "sess-001"
    assert isinstance(event, MessageEvent)


# ---------------------------------------------------------------------------
# Event type: decision
# ---------------------------------------------------------------------------


def test_log_decision_writes_jsonl(logger: CommsLogger, log_dir: Path) -> None:
    """log_decision writes a valid decision event."""
    event = logger.log_decision(
        agent="orchestrator",
        title="Proceed to Phase 3",
        rationale="All gates passed.",
        alternatives=["Iterate Phase 2"],
        outcome="proceed",
        confidence="high",
        decision_id="dec-manual-001",
    )

    data = _read_single_event(log_dir)
    assert data["event_type"] == "decision"
    assert data["decision_id"] == "dec-manual-001"
    assert data["title"] == "Proceed to Phase 3"
    assert data["confidence"] == "high"
    assert data["alternatives"] == ["Iterate Phase 2"]
    assert isinstance(event, DecisionEvent)


def test_log_decision_auto_generates_id(logger: CommsLogger, log_dir: Path) -> None:
    """decision_id is auto-generated when not provided."""
    logger.log_decision(
        agent="orchestrator",
        title="Auto ID test",
        rationale="Testing.",
    )
    data = _read_single_event(log_dir)
    assert data["decision_id"].startswith("decision-")


# ---------------------------------------------------------------------------
# Event type: gate
# ---------------------------------------------------------------------------


def test_log_gate_writes_jsonl(logger: CommsLogger, log_dir: Path) -> None:
    """log_gate writes a valid gate event with breakdown."""
    event = logger.log_gate(
        agent="oracle-qa",
        gate_id="gate-3",
        gate_name="Metric Threshold",
        metric_name="RMSE",
        metric_value=0.042,
        threshold=0.05,
        tier=1,
        result="pass",
        breakdown={"regime_a": 0.038},
        notes="Looks good.",
    )

    data = _read_single_event(log_dir)
    assert data["event_type"] == "gate"
    assert data["metric_value"] == 0.042
    assert data["threshold"] == 0.05
    assert data["result"] == "pass"
    assert data["breakdown"] == {"regime_a": 0.038}
    assert isinstance(event, GateEvent)


# ---------------------------------------------------------------------------
# Event type: error
# ---------------------------------------------------------------------------


def test_log_error_writes_jsonl(logger: CommsLogger, log_dir: Path) -> None:
    """log_error writes a valid error event."""
    event = logger.log_error(
        agent="data-eng",
        error_type="data_validation",
        severity="blocking",
        description="45% NaN values",
        affected_artifacts=["sensor_12.parquet"],
        escalated_to="orchestrator",
    )

    data = _read_single_event(log_dir)
    assert data["event_type"] == "error"
    assert data["severity"] == "blocking"
    assert data["affected_artifacts"] == ["sensor_12.parquet"]
    assert data["escalated_to"] == "orchestrator"
    assert isinstance(event, ErrorEvent)


# ---------------------------------------------------------------------------
# Event type: checkpoint
# ---------------------------------------------------------------------------


def test_log_checkpoint_writes_jsonl(logger: CommsLogger, log_dir: Path) -> None:
    """log_checkpoint writes a valid checkpoint event."""
    event = logger.log_checkpoint(
        agent="builder",
        phase="phase-4",
        subtask="iteration-17",
        progress="17/100",
        current_best_metric=0.058,
        target_metric=0.05,
        blockers=["GPU OOM"],
    )

    data = _read_single_event(log_dir)
    assert data["event_type"] == "checkpoint"
    assert data["phase"] == "phase-4"
    assert data["current_best_metric"] == 0.058
    assert data["blockers"] == ["GPU OOM"]
    assert isinstance(event, CheckpointEvent)


# ---------------------------------------------------------------------------
# Append-only: multiple writes
# ---------------------------------------------------------------------------


def test_append_only_multiple_writes(logger: CommsLogger, log_dir: Path) -> None:
    """Multiple writes produce multiple lines in the same file."""
    logger.log_message(
        agent="a", message_type="status", recipient="b", subject="s1", body="b1",
    )
    logger.log_message(
        agent="a", message_type="status", recipient="b", subject="s2", body="b2",
    )
    logger.log_error(
        agent="a", error_type="runtime", severity="info", description="oops",
    )

    files = list(log_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Daily log rotation
# ---------------------------------------------------------------------------


def test_daily_rotation(logger: CommsLogger, log_dir: Path) -> None:
    """Events with different dates land in different daily files."""
    t1 = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)

    e1 = MessageEvent(
        session_id="sess-001",
        agent="a",
        project="test-project",
        message_type="status",
        recipient="b",
        subject="day1",
        body="body1",
        timestamp=t1,
    )
    e2 = MessageEvent(
        session_id="sess-001",
        agent="a",
        project="test-project",
        message_type="status",
        recipient="b",
        subject="day2",
        body="body2",
        timestamp=t2,
    )

    # Use the internal writer directly to control timestamps.
    logger._write_event(e1)
    logger._write_event(e2)

    files = sorted(log_dir.glob("*.jsonl"))
    assert len(files) == 2
    assert files[0].name == "2026-04-08.jsonl"
    assert files[1].name == "2026-04-09.jsonl"


# ---------------------------------------------------------------------------
# Query interface
# ---------------------------------------------------------------------------


def test_query_by_event_type(logger: CommsLogger) -> None:
    """query_logs filters by event_type correctly."""
    logger.log_message(
        agent="a", message_type="status", recipient="b", subject="s", body="x",
    )
    logger.log_error(
        agent="a", error_type="runtime", severity="info", description="fail",
    )
    logger.log_checkpoint(
        agent="a", phase="p1", subtask="s1", progress="50%",
    )

    messages = logger.query_logs(event_type="message")
    assert len(messages) == 1
    assert all(isinstance(e, MessageEvent) for e in messages)

    errors = logger.query_logs(event_type="error")
    assert len(errors) == 1
    assert all(isinstance(e, ErrorEvent) for e in errors)


def test_query_by_agent(logger: CommsLogger) -> None:
    """query_logs filters by agent correctly."""
    logger.log_message(
        agent="builder", message_type="status", recipient="orc", subject="s", body="b",
    )
    logger.log_message(
        agent="oracle", message_type="verdict", recipient="orc", subject="s", body="b",
    )

    results = logger.query_logs(agent="builder")
    assert len(results) == 1
    assert results[0].agent == "builder"


def test_query_by_time_range(logger: CommsLogger, log_dir: Path) -> None:
    """query_logs filters by start/end timestamp."""
    t1 = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)

    for t in (t1, t2, t3):
        evt = CheckpointEvent(
            session_id="sess-001",
            agent="a",
            project="test-project",
            phase="p",
            subtask="s",
            progress="x",
            timestamp=t,
        )
        logger._write_event(evt)

    results = logger.query_logs(start=t2, end=t2)
    assert len(results) == 1

    results_all = logger.query_logs()
    assert len(results_all) == 3

    results_after = logger.query_logs(start=t2)
    assert len(results_after) == 2


def test_query_combined_filters(logger: CommsLogger) -> None:
    """query_logs with multiple filters applied simultaneously."""
    logger.log_message(
        agent="builder", message_type="status", recipient="orc", subject="s", body="b",
    )
    logger.log_error(
        agent="builder", error_type="runtime", severity="info", description="oops",
    )
    logger.log_error(
        agent="oracle", error_type="runtime", severity="info", description="other",
    )

    results = logger.query_logs(event_type="error", agent="builder")
    assert len(results) == 1
    assert isinstance(results[0], ErrorEvent)
    assert results[0].agent == "builder"


def test_query_empty_logs(logger: CommsLogger) -> None:
    """query_logs returns empty list when no events match."""
    results = logger.query_logs(event_type="gate")
    assert results == []


# ---------------------------------------------------------------------------
# Read-back / round-trip
# ---------------------------------------------------------------------------


def test_roundtrip_parse(logger: CommsLogger) -> None:
    """Events can be written and read back with correct types."""
    logger.log_gate(
        agent="oracle",
        gate_id="g1",
        gate_name="Test Gate",
        metric_name="accuracy",
        metric_value=0.95,
        threshold=0.90,
        tier=2,
        result="pass",
    )

    events = logger.query_logs(event_type="gate")
    assert len(events) == 1
    gate = events[0]
    assert isinstance(gate, GateEvent)
    assert gate.metric_value == 0.95
    assert gate.threshold == 0.90
    assert gate.result == "pass"


# ---------------------------------------------------------------------------
# Base fields on every event
# ---------------------------------------------------------------------------


def test_base_fields_present(logger: CommsLogger) -> None:
    """Every event carries timestamp, session_id, event_type, agent, project."""
    logger.log_checkpoint(
        agent="builder", phase="p1", subtask="s1", progress="done",
    )
    events = logger.query_logs()
    evt = events[0]
    assert evt.session_id == "sess-001"
    assert evt.project == "test-project"
    assert evt.agent == "builder"
    assert evt.event_type == "checkpoint"
    assert evt.timestamp is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_single_event(log_dir: Path) -> dict:
    """Read the first (and only expected) line from the single log file."""
    files = list(log_dir.glob("*.jsonl"))
    assert len(files) == 1, f"Expected 1 file, found {len(files)}"
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 1, f"Expected 1 line, found {len(lines)}"
    return json.loads(lines[0])
