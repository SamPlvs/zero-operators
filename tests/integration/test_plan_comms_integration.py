"""Integration test: Plan Parser + Target Parser + Comms Logger (Modules 1+2+5).

Proves that the three modules work together end-to-end:
  1. Parse a fixture plan.md, validate it, log the decision via CommsLogger.
  2. Parse a fixture target file, check isolation on various paths, log
     errors for violations.
  3. Verify the JSONL output contains the expected events.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zo.comms import (
    CommsLogger,
    DecisionEvent,
    ErrorEvent,
)
from zo.plan import (
    WorkflowMode,
    parse_plan,
    validate_plan,
)
from zo.target import (
    IsolationViolation,
    check_isolation,
    enforce_write,
    parse_target,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_jsonl_lines(log_dir: Path) -> list[dict]:
    """Read every JSONL line from all log files in a directory."""
    lines: list[dict] = []
    for f in sorted(log_dir.glob("*.jsonl")):
        for raw in f.read_text().strip().splitlines():
            if raw:
                lines.append(json.loads(raw))
    return lines


# ---------------------------------------------------------------------------
# Test: parse plan -> validate -> log decision
# ---------------------------------------------------------------------------


class TestPlanValidateAndLog:
    """Parse the fixture plan, validate, and log the result."""

    def test_parse_fixture_plan(self, sample_plan_path: Path) -> None:
        """The fixture plan.md parses without errors."""
        plan = parse_plan(sample_plan_path)

        assert plan.frontmatter.project_name == "churn-prediction"
        assert plan.frontmatter.status == "active"
        assert plan.frontmatter.owner == "TestEngineer"

    def test_fixture_plan_validates(self, sample_plan_path: Path) -> None:
        """The fixture plan passes all validation checks."""
        plan = parse_plan(sample_plan_path)
        report = validate_plan(plan)

        assert report.valid, f"Validation failed: {[i.message for i in report.issues]}"
        assert len(report.issues) == 0

    def test_fixture_plan_structure(self, sample_plan_path: Path) -> None:
        """All expected sections are populated with correct data."""
        plan = parse_plan(sample_plan_path)

        # Oracle
        assert plan.oracle is not None
        assert plan.oracle.primary_metric == "ROC-AUC"
        assert "0.8" in plan.oracle.target_threshold
        assert plan.oracle.evaluation_method
        assert plan.oracle.ground_truth_source
        assert plan.oracle.evaluation_frequency

        # Workflow
        assert plan.workflow is not None
        assert plan.workflow.mode == WorkflowMode.CLASSICAL_ML

        # Data sources — exactly 2
        assert len(plan.data_sources) == 2
        source_names = {s.name for s in plan.data_sources}
        assert "Customer Activity Logs" in source_names
        assert "Billing Records" in source_names

        # Agents
        assert plan.agents is not None
        assert len(plan.agents.active_agents) == 4
        assert "lead-orchestrator" in plan.agents.active_agents
        assert "oracle-qa" in plan.agents.active_agents

        # Domain priors and constraints are non-empty
        assert plan.domain_priors
        assert plan.constraints

    def test_log_plan_validation_decision(
        self,
        sample_plan_path: Path,
        comms_logger: CommsLogger,
    ) -> None:
        """Parse + validate + log a decision — verify the JSONL output."""
        plan = parse_plan(sample_plan_path)
        report = validate_plan(plan)

        # Log the decision
        event = comms_logger.log_decision(
            agent="lead-orchestrator",
            title="Plan validation passed",
            rationale=(
                f"Plan '{plan.frontmatter.project_name}' has all required sections, "
                f"valid oracle definition, {len(plan.data_sources)} data sources, "
                f"and {len(plan.agents.active_agents)} active agents."
            ),
            alternatives=["Reject plan and request revisions"],
            outcome="proceed",
            confidence="high",
        )

        assert isinstance(event, DecisionEvent)
        assert event.title == "Plan validation passed"
        assert event.confidence == "high"

        # Verify JSONL on disk
        log_dir = comms_logger._log_dir
        events = _all_jsonl_lines(log_dir)
        assert len(events) == 1

        record = events[0]
        assert record["event_type"] == "decision"
        assert record["agent"] == "lead-orchestrator"
        assert record["project"] == "churn-prediction"
        assert record["outcome"] == "proceed"
        assert "churn-prediction" in record["rationale"]


# ---------------------------------------------------------------------------
# Test: parse target -> isolation checks -> log errors
# ---------------------------------------------------------------------------


class TestTargetIsolationAndLog:
    """Parse the fixture target, run isolation checks, log violations."""

    def test_parse_fixture_target(self, sample_target_path: Path) -> None:
        """The fixture target.md parses without errors."""
        config = parse_target(sample_target_path)

        assert config.project == "churn-prediction"
        assert config.target_branch == "main"
        assert config.enforce_isolation is True
        assert len(config.zo_only_paths) >= 5

    def test_allowed_paths_pass(self, sample_target_path: Path) -> None:
        """Legitimate delivery repo paths are allowed."""
        config = parse_target(sample_target_path)

        allowed = [
            "src/models/churn_model.py",
            "data/processed/features.parquet",
            "eval/metrics.json",
            "README.md",
            "pyproject.toml",
        ]
        for path in allowed:
            assert check_isolation(path, config) is True, f"Should allow: {path}"

    def test_blocked_paths_fail(self, sample_target_path: Path) -> None:
        """ZO-internal paths are blocked."""
        config = parse_target(sample_target_path)

        blocked = [
            ".claude/settings.json",
            "CLAUDE.md",
            "STATE.md",
            ".zo/config.yaml",
            "memory/session.md",
            "logs/comms/2026-04-09.jsonl",
            "zero-operators/src/zo/plan.py",
        ]
        for path in blocked:
            assert check_isolation(path, config) is False, f"Should block: {path}"

    def test_enforce_write_raises_for_blocked(self, sample_target_path: Path) -> None:
        """enforce_write raises IsolationViolation for blocked paths."""
        config = parse_target(sample_target_path)

        with pytest.raises(IsolationViolation) as exc_info:
            enforce_write("STATE.md", config)
        assert exc_info.value.file_path == "STATE.md"
        assert exc_info.value.matched_pattern == "STATE.md"

    def test_log_isolation_violations(
        self,
        sample_target_path: Path,
        comms_logger: CommsLogger,
    ) -> None:
        """Check isolation on several paths and log errors for violations."""
        config = parse_target(sample_target_path)

        paths_to_check = [
            "src/models/model.py",       # allowed
            ".claude/agents/lead.md",     # blocked
            "data/raw/input.csv",         # allowed
            "STATE.md",                   # blocked
            "logs/comms/today.jsonl",     # blocked
        ]

        violation_count = 0
        for path in paths_to_check:
            if not check_isolation(path, config):
                comms_logger.log_error(
                    agent="lead-orchestrator",
                    error_type="isolation_violation",
                    severity="blocking",
                    description=f"Write to '{path}' blocked by isolation policy.",
                    affected_artifacts=[path],
                    resolution="rejected",
                )
                violation_count += 1

        assert violation_count == 3

        # Verify JSONL contains exactly 3 error events
        log_dir = comms_logger._log_dir
        events = _all_jsonl_lines(log_dir)
        assert len(events) == 3
        assert all(e["event_type"] == "error" for e in events)
        assert all(e["error_type"] == "isolation_violation" for e in events)
        assert all(e["severity"] == "blocking" for e in events)

        # Check specific paths appear in affected_artifacts
        all_artifacts = [e["affected_artifacts"][0] for e in events]
        assert ".claude/agents/lead.md" in all_artifacts
        assert "STATE.md" in all_artifacts
        assert "logs/comms/today.jsonl" in all_artifacts


# ---------------------------------------------------------------------------
# Test: full end-to-end flow — plan + target + comms together
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Full integration: parse both fixtures, validate, log everything."""

    def test_full_pipeline(
        self,
        sample_plan_path: Path,
        sample_target_path: Path,
        comms_logger: CommsLogger,
    ) -> None:
        """Run the complete parse-validate-log pipeline across all modules."""
        # Step 1: parse and validate plan
        plan = parse_plan(sample_plan_path)
        report = validate_plan(plan)
        assert report.valid

        # Step 2: log plan validation decision
        comms_logger.log_decision(
            agent="lead-orchestrator",
            title="Plan accepted",
            rationale="All required sections present and valid.",
            outcome="proceed",
            confidence="high",
        )

        # Step 3: parse target and verify isolation
        config = parse_target(sample_target_path)
        assert config.project == plan.frontmatter.project_name

        # Step 4: simulate an agent attempting writes
        safe_paths = ["src/models/model.py", "data/features.csv"]
        unsafe_paths = [".claude/config.json", "STATE.md"]

        for path in safe_paths:
            enforce_write(path, config)  # should not raise

        for path in unsafe_paths:
            with pytest.raises(IsolationViolation):
                enforce_write(path, config)
            comms_logger.log_error(
                agent="model-builder",
                error_type="isolation_violation",
                severity="blocking",
                description=f"Blocked write to '{path}'.",
                affected_artifacts=[path],
            )

        # Step 5: log a checkpoint after successful setup
        comms_logger.log_checkpoint(
            agent="lead-orchestrator",
            phase="phase-1",
            subtask="project-setup",
            progress="complete",
            target_metric=0.8,
        )

        # Step 6: verify full JSONL trail
        log_dir = comms_logger._log_dir
        events = _all_jsonl_lines(log_dir)

        # 1 decision + 2 errors + 1 checkpoint = 4 events
        assert len(events) == 4

        event_types = [e["event_type"] for e in events]
        assert event_types.count("decision") == 1
        assert event_types.count("error") == 2
        assert event_types.count("checkpoint") == 1

        # All events share the same project and session
        assert all(e["project"] == "churn-prediction" for e in events)
        assert all(e["session_id"] == "test-session-001" for e in events)

    def test_query_logs_after_pipeline(
        self,
        sample_plan_path: Path,
        sample_target_path: Path,
        comms_logger: CommsLogger,
    ) -> None:
        """Verify CommsLogger.query_logs works on the integration trail."""
        plan = parse_plan(sample_plan_path)
        validate_plan(plan)
        config = parse_target(sample_target_path)

        # Log a mix of events
        comms_logger.log_decision(
            agent="lead-orchestrator",
            title="Plan accepted",
            rationale="Valid plan.",
            outcome="proceed",
        )
        comms_logger.log_error(
            agent="model-builder",
            error_type="isolation_violation",
            severity="blocking",
            description="Blocked write to STATE.md.",
        )
        comms_logger.log_message(
            agent="lead-orchestrator",
            message_type="broadcast",
            recipient="all",
            subject="Project setup complete",
            body=f"Plan '{plan.frontmatter.project_name}' validated. "
                 f"Target repo: {config.target_repo}. "
                 f"Beginning phase 1.",
        )

        # Query by type
        decisions = comms_logger.query_logs(event_type="decision")
        assert len(decisions) == 1
        assert isinstance(decisions[0], DecisionEvent)

        errors = comms_logger.query_logs(event_type="error")
        assert len(errors) == 1
        assert isinstance(errors[0], ErrorEvent)

        # Query by agent
        orchestrator_events = comms_logger.query_logs(agent="lead-orchestrator")
        assert len(orchestrator_events) == 2  # decision + message

        # Query all
        all_events = comms_logger.query_logs()
        assert len(all_events) == 3
