"""Unit tests for zo.evolution — the ZO self-evolution engine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from zo._evolution_models import (
    EvolutionEntry,
    FailureRecord,
    FailureSeverity,
    RetrospectiveReport,
    RootCauseAnalysis,
    RootCauseCategory,
    RuleUpdate,
)
from zo.comms import CommsLogger
from zo.evolution import EvolutionEngine
from zo.memory import MemoryManager

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2026, 4, 9, 12, 0, 0, tzinfo=UTC)


def _make_failure(**overrides: object) -> FailureRecord:
    defaults: dict[str, object] = {
        "title": "Data validation failed",
        "timestamp": _TS,
        "detected_by": "data-eng",
        "severity": FailureSeverity.MAJOR,
        "phase": "data-prep",
        "description": "Schema mismatch in raw data",
        "immediate_impact": "Pipeline blocked",
        "artifacts_affected": ["data/raw.csv"],
    }
    defaults.update(overrides)
    return FailureRecord(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def mm(tmp_project: Path) -> MemoryManager:
    mgr = MemoryManager(project_dir=tmp_project, project_name="test-proj")
    mgr.initialize_project()
    return mgr


@pytest.fixture()
def comms(tmp_project: Path) -> CommsLogger:
    log_dir = tmp_project / "logs" / "comms"
    return CommsLogger(log_dir=log_dir, project="test-proj", session_id="s-001")


@pytest.fixture()
def engine(mm: MemoryManager, comms: CommsLogger, tmp_project: Path) -> EvolutionEngine:
    return EvolutionEngine(memory=mm, comms=comms, zo_root=tmp_project)


# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestModels:
    """All evolution models validate correctly."""

    def test_failure_record_defaults(self) -> None:
        f = FailureRecord(
            title="oops",
            detected_by="builder",
            severity=FailureSeverity.MINOR,
            phase="build",
            description="broke",
            immediate_impact="nothing",
        )
        assert f.artifacts_affected == []
        assert f.severity == "minor"

    def test_root_cause_analysis(self) -> None:
        f = _make_failure()
        rca = RootCauseAnalysis(
            failure=f,
            root_cause="missing check",
            rule_gap="specs/workflow.md",
            category=RootCauseCategory.MISSING_RULE,
            document_to_update="PRIORS.md",
        )
        assert rca.category == "missing_rule"

    def test_rule_update(self) -> None:
        u = RuleUpdate(
            document_path="PRIORS.md",
            change_description="add rule",
            rationale="prevent failure",
            failure_reference="Failure: oops",
        )
        assert u.verified is False
        assert u.verification_method == ""

    def test_evolution_entry(self) -> None:
        e = EvolutionEntry(
            title="evo",
            triggered_by="failure-ref",
            document_updated="PRIORS.md",
            change="added rule",
            rationale="because",
            verified=True,
            verification_method="structural",
        )
        assert e.verified is True

    def test_retrospective_report(self) -> None:
        r = RetrospectiveReport(
            project_name="alpha",
            date="2026-04-09",
            sessions_completed=5,
            total_failures=3,
            total_rule_updates=2,
        )
        assert r.failure_distribution == {}
        assert r.patterns == []

    def test_root_cause_category_values(self) -> None:
        assert list(RootCauseCategory) == [
            "missing_rule", "incomplete_rule", "ignored_rule",
            "novel_case", "regression",
        ]

    def test_failure_severity_values(self) -> None:
        assert list(FailureSeverity) == ["critical", "major", "minor"]


# ---------------------------------------------------------------------------
# record_failure
# ---------------------------------------------------------------------------


class TestRecordFailure:
    """Step 1: Document the failure to DECISION_LOG."""

    def test_writes_to_decision_log(self, engine: EvolutionEngine, mm: MemoryManager) -> None:
        failure = _make_failure()
        engine.record_failure(failure)

        decisions = mm.read_decisions()
        assert len(decisions) == 1
        assert decisions[0].title == "Failure: Data validation failed"
        assert "data-eng" in decisions[0].context
        assert decisions[0].outcome == "failure_recorded"

    def test_logs_error_to_comms(
        self, engine: EvolutionEngine, comms: CommsLogger,
    ) -> None:
        failure = _make_failure()
        engine.record_failure(failure)

        events = comms.query_logs(event_type="error")
        assert len(events) == 1
        assert events[0].description == "Schema mismatch in raw data"


# ---------------------------------------------------------------------------
# analyze_root_cause
# ---------------------------------------------------------------------------


class TestAnalyzeRootCause:
    """Step 2: Produces correct RootCauseAnalysis."""

    def test_returns_analysis(self, engine: EvolutionEngine) -> None:
        failure = _make_failure()
        rca = engine.analyze_root_cause(
            failure,
            root_cause="No schema validation step",
            rule_gap="specs/workflow.md",
            category=RootCauseCategory.MISSING_RULE,
        )
        assert isinstance(rca, RootCauseAnalysis)
        assert rca.category == "missing_rule"
        assert rca.root_cause == "No schema validation step"

    def test_logs_to_decision_log(self, engine: EvolutionEngine, mm: MemoryManager) -> None:
        failure = _make_failure()
        engine.analyze_root_cause(
            failure,
            root_cause="missing check",
            rule_gap="workflow.md",
            category=RootCauseCategory.INCOMPLETE_RULE,
        )
        decisions = mm.read_decisions()
        assert any(d.title.startswith("Root Cause:") for d in decisions)

    def test_incomplete_rule_sets_spec_doc(self, engine: EvolutionEngine) -> None:
        failure = _make_failure()
        rca = engine.analyze_root_cause(
            failure,
            root_cause="threshold too high",
            rule_gap="specs/oracle.md",
            category=RootCauseCategory.INCOMPLETE_RULE,
        )
        assert rca.document_to_update == "specs/oracle.md"

    def test_ignored_rule_sets_agent_doc(self, engine: EvolutionEngine) -> None:
        failure = _make_failure(detected_by="builder")
        rca = engine.analyze_root_cause(
            failure,
            root_cause="agent skipped check",
            rule_gap="validation checklist",
            category=RootCauseCategory.IGNORED_RULE,
        )
        assert "agents/builder.md" in rca.document_to_update


# ---------------------------------------------------------------------------
# propose_rule_update
# ---------------------------------------------------------------------------


class TestProposeRuleUpdate:
    """Step 4: Maps categories to correct documents."""

    def test_missing_rule_targets_priors(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        failure = _make_failure()
        rca = RootCauseAnalysis(
            failure=failure,
            root_cause="no rule existed",
            rule_gap="schema validation",
            category=RootCauseCategory.MISSING_RULE,
            document_to_update="PRIORS.md",
        )
        update = engine.propose_rule_update(rca)
        assert "PRIORS.md" in update.document_path

    def test_novel_case_targets_priors(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        failure = _make_failure()
        rca = RootCauseAnalysis(
            failure=failure,
            root_cause="never seen before",
            rule_gap="new edge case",
            category=RootCauseCategory.NOVEL_CASE,
            document_to_update="PRIORS.md",
        )
        update = engine.propose_rule_update(rca)
        assert "PRIORS.md" in update.document_path

    def test_ignored_rule_targets_agent_def(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        failure = _make_failure()
        rca = RootCauseAnalysis(
            failure=failure,
            root_cause="agent skipped",
            rule_gap="checklist item",
            category=RootCauseCategory.IGNORED_RULE,
            document_to_update="agents/data-eng.md",
        )
        update = engine.propose_rule_update(rca)
        assert "agents" in update.document_path
        assert "Strengthen instruction" in update.change_description

    def test_incomplete_rule_targets_spec(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        failure = _make_failure()
        rca = RootCauseAnalysis(
            failure=failure,
            root_cause="threshold wrong",
            rule_gap="specs/oracle.md",
            category=RootCauseCategory.INCOMPLETE_RULE,
            document_to_update="specs/oracle.md",
        )
        update = engine.propose_rule_update(rca)
        assert "specs/oracle.md" in update.document_path
        assert "Expand rule" in update.change_description

    def test_regression_targets_priors(self, engine: EvolutionEngine) -> None:
        failure = _make_failure()
        rca = RootCauseAnalysis(
            failure=failure,
            root_cause="same bug again",
            rule_gap="regression guard",
            category=RootCauseCategory.REGRESSION,
            document_to_update="PRIORS.md",
        )
        update = engine.propose_rule_update(rca)
        assert "PRIORS.md" in update.document_path
        assert "regression guard" in update.change_description


# ---------------------------------------------------------------------------
# apply_rule_update
# ---------------------------------------------------------------------------


class TestApplyRuleUpdate:
    """apply_rule_update writes to the correct target."""

    def test_appends_to_priors_for_novel_case(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        update = RuleUpdate(
            document_path=str(mm.memory_root / "PRIORS.md"),
            change_description="New edge case: sensor drift",
            rationale="sensor 12 unreliable",
            failure_reference="Failure: sensor drift",
        )
        engine.apply_rule_update(update)

        priors = mm.read_priors()
        assert len(priors) == 1
        assert priors[0].category == "evolution"
        assert "sensor drift" in priors[0].statement

    def test_appends_changelog_for_spec(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        spec_path = tmp_project / "specs" / "oracle.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text("# Oracle Spec\n", encoding="utf-8")

        update = RuleUpdate(
            document_path=str(spec_path),
            change_description="Lower VIF threshold to 5",
            rationale="multicollinearity caused instability",
            failure_reference="Failure: model instability",
        )
        engine.apply_rule_update(update)

        content = spec_path.read_text(encoding="utf-8")
        assert "## Changelog" in content
        assert "Lower VIF threshold" in content

    def test_appends_checklist_for_agent_def(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        agent_dir = tmp_project / ".claude" / "agents"
        agent_dir.mkdir(parents=True, exist_ok=True)
        agent_file = agent_dir / "agents" / "data-eng.md"
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text("# Data Engineer\n", encoding="utf-8")

        update = RuleUpdate(
            document_path=str(agent_file),
            change_description="Check correlation matrix before proceeding",
            rationale="ignored correlation check",
            failure_reference="Failure: bad features",
        )
        engine.apply_rule_update(update)

        content = agent_file.read_text(encoding="utf-8")
        assert "- [ ]" in content
        assert "Check correlation matrix" in content

    def test_logs_evolution_to_decision_log(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        update = RuleUpdate(
            document_path=str(mm.memory_root / "PRIORS.md"),
            change_description="Add guard",
            rationale="prevent recurrence",
            failure_reference="Failure: test",
        )
        engine.apply_rule_update(update)

        decisions = mm.read_decisions()
        assert any(d.title.startswith("Evolution:") for d in decisions)


# ---------------------------------------------------------------------------
# verify_update
# ---------------------------------------------------------------------------


class TestVerifyUpdate:
    """Step 5: Verify update would have caught the failure."""

    def test_passes_when_content_present(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        # First apply an update so the content exists
        update = RuleUpdate(
            document_path=str(mm.memory_root / "PRIORS.md"),
            change_description="Verify schema before load",
            rationale="schema mismatch",
            failure_reference="Failure: schema",
        )
        engine.apply_rule_update(update)

        failure = _make_failure()
        result = engine.verify_update(update, failure)
        assert result is True
        assert update.verified is True

    def test_fails_when_doc_missing(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        update = RuleUpdate(
            document_path=str(tmp_project / "nonexistent.md"),
            change_description="something",
            rationale="reason",
            failure_reference="Failure: x",
        )
        failure = _make_failure()
        result = engine.verify_update(update, failure)
        assert result is False

    def test_fails_when_content_not_found(
        self, engine: EvolutionEngine, tmp_project: Path,
    ) -> None:
        doc = tmp_project / "empty_spec.md"
        doc.write_text("# Empty\n", encoding="utf-8")

        update = RuleUpdate(
            document_path=str(doc),
            change_description="unique rule XYZ",
            rationale="reason",
            failure_reference="Failure: unique-ref-ABC",
        )
        failure = _make_failure()
        result = engine.verify_update(update, failure)
        assert result is False


# ---------------------------------------------------------------------------
# run_postmortem (full pipeline)
# ---------------------------------------------------------------------------


class TestRunPostmortem:
    """Full post-mortem executes all 5 steps."""

    def test_returns_evolution_entry(self, engine: EvolutionEngine) -> None:
        failure = _make_failure()
        entry = engine.run_postmortem(
            failure,
            root_cause="No schema check",
            rule_gap="missing validation",
            category=RootCauseCategory.MISSING_RULE,
        )
        assert isinstance(entry, EvolutionEntry)
        assert entry.verified is True
        assert "Failure: Data validation failed" in entry.triggered_by

    def test_creates_all_decision_entries(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        failure = _make_failure()
        engine.run_postmortem(
            failure,
            root_cause="missing rule",
            rule_gap="schema check",
            category=RootCauseCategory.NOVEL_CASE,
        )
        decisions = mm.read_decisions()
        titles = [d.title for d in decisions]
        assert any(t.startswith("Failure:") for t in titles)
        assert any(t.startswith("Root Cause:") for t in titles)
        assert any(t.startswith("Evolution:") for t in titles)

    def test_creates_prior_entry(
        self, engine: EvolutionEngine, mm: MemoryManager,
    ) -> None:
        failure = _make_failure()
        engine.run_postmortem(
            failure,
            root_cause="novel edge case",
            rule_gap="undocumented scenario",
            category=RootCauseCategory.NOVEL_CASE,
        )
        priors = mm.read_priors()
        assert len(priors) >= 1
        assert priors[0].category == "evolution"


# ---------------------------------------------------------------------------
# run_retrospective
# ---------------------------------------------------------------------------


class TestRunRetrospective:
    """Retrospective scans decisions and produces a report."""

    def test_empty_project(self, engine: EvolutionEngine) -> None:
        report = engine.run_retrospective("test-proj")
        assert isinstance(report, RetrospectiveReport)
        assert report.total_failures == 0
        assert report.total_rule_updates == 0
        assert "No failures recorded" in report.lessons[0]

    def test_after_postmortems(self, engine: EvolutionEngine) -> None:
        # Run two postmortems
        for title in ("fail-1", "fail-2"):
            failure = _make_failure(title=title)
            engine.run_postmortem(
                failure,
                root_cause="missing check",
                rule_gap="validation",
                category=RootCauseCategory.MISSING_RULE,
            )

        report = engine.run_retrospective("test-proj")
        assert report.total_failures == 2
        assert report.total_rule_updates == 2
        assert report.failure_distribution.get("missing_rule", 0) == 2

    def test_identifies_phase_patterns(self, engine: EvolutionEngine) -> None:
        # Two failures in same phase
        for i in range(2):
            failure = _make_failure(title=f"fail-{i}", phase="data-prep")
            engine.run_postmortem(
                failure,
                root_cause="data issue",
                rule_gap="check",
                category=RootCauseCategory.NOVEL_CASE,
            )

        report = engine.run_retrospective("test-proj")
        assert any("data-prep" in p for p in report.patterns)


# ---------------------------------------------------------------------------
# get_evolution_metrics
# ---------------------------------------------------------------------------


class TestGetEvolutionMetrics:
    """Metrics extraction from DECISION_LOG."""

    def test_empty_returns_zeros(self, engine: EvolutionEngine) -> None:
        metrics = engine.get_evolution_metrics()
        assert metrics["total_rule_updates"] == 0
        assert metrics["regression_rate"] == 0.0

    def test_after_postmortem(self, engine: EvolutionEngine) -> None:
        failure = _make_failure()
        engine.run_postmortem(
            failure,
            root_cause="missing rule",
            rule_gap="check",
            category=RootCauseCategory.MISSING_RULE,
        )
        metrics = engine.get_evolution_metrics()
        assert metrics["total_rule_updates"] == 1
        assert metrics.get("category_missing_rule", 0) == 1

    def test_regression_rate(self, engine: EvolutionEngine) -> None:
        # One regression out of two
        engine.run_postmortem(
            _make_failure(title="novel"),
            root_cause="new case",
            rule_gap="none",
            category=RootCauseCategory.NOVEL_CASE,
        )
        engine.run_postmortem(
            _make_failure(title="regressed"),
            root_cause="same bug",
            rule_gap="guard missing",
            category=RootCauseCategory.REGRESSION,
        )
        metrics = engine.get_evolution_metrics()
        assert metrics["regression_rate"] == pytest.approx(0.5)
        assert metrics["total_rule_updates"] == 2
