"""Unit tests for the plan parser and validator (zo.plan).

Uses the real zero-operators-build.md as a fixture for happy-path tests,
plus synthetic plan strings for edge cases and failure modes.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from zo.plan import (
    Plan,
    PlanStatus,
    ValidationIssue,
    ValidationReport,
    WorkflowMode,
    parse_frontmatter,
    parse_plan,
    validate_plan,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_PLAN_PATH = REPO_ROOT / "plans" / "zero-operators-build.md"


@pytest.fixture
def real_plan_path() -> Path:
    """Path to the real zero-operators-build.md plan file."""
    assert REAL_PLAN_PATH.exists(), f"Fixture not found: {REAL_PLAN_PATH}"
    return REAL_PLAN_PATH


@pytest.fixture
def real_plan(real_plan_path: Path) -> Plan:
    """Parsed Plan from the real plan file."""
    return parse_plan(real_plan_path)


def _write_plan(tmp_path: Path, content: str) -> Path:
    """Helper: write a plan string to a temp file and return its path."""
    p = tmp_path / "plan.md"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


MINIMAL_VALID_PLAN = """\
---
project_name: "test-project"
version: "1.0"
created: "2026-01-01"
last_modified: "2026-01-01"
status: active
owner: "Tester"
---

## Objective

Build something useful.

## Oracle

**Primary metric:** Accuracy
**Ground truth source:** test dataset
**Evaluation method:** holdout split
**Target threshold:** >90%
**Evaluation frequency:** per iteration

## Workflow

**Mode:** classical_ml

## Data Sources

### Source 1: Test Data
- **Location:** /data/test.csv

## Domain Priors

Some domain knowledge here.

## Agents

**Active agents:** lead-orchestrator, data-engineer

## Constraints

- No live access.
"""


@pytest.fixture
def minimal_plan_path(tmp_path: Path) -> Path:
    """A minimal but fully valid plan file."""
    return _write_plan(tmp_path, MINIMAL_VALID_PLAN)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

class TestFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_parse_real_frontmatter(self, real_plan_path: Path) -> None:
        text = real_plan_path.read_text()
        fm = parse_frontmatter(text)
        assert fm.project_name == "zero-operators-build"
        assert fm.version == "2.0"
        assert fm.status == PlanStatus.ACTIVE
        assert fm.owner == "Sam"

    def test_parse_minimal_frontmatter(self, minimal_plan_path: Path) -> None:
        text = minimal_plan_path.read_text()
        fm = parse_frontmatter(text)
        assert fm.project_name == "test-project"
        assert fm.version == "1.0"
        assert fm.status == PlanStatus.ACTIVE
        assert fm.owner == "Tester"

    def test_missing_frontmatter_raises(self, tmp_path: Path) -> None:
        p = _write_plan(tmp_path, "# No frontmatter here\n\nJust text.")
        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_frontmatter(p.read_text())

    def test_incomplete_frontmatter_raises(self, tmp_path: Path) -> None:
        content = """\
        ---
        project_name: "test"
        version: "1.0"
        ---

        ## Objective

        Something.
        """
        p = _write_plan(tmp_path, content)
        with pytest.raises(ValueError, match="missing required keys"):
            parse_frontmatter(p.read_text())


# ---------------------------------------------------------------------------
# Full plan parsing (real fixture)
# ---------------------------------------------------------------------------

class TestParsePlanReal:
    """Parse the real zero-operators-build.md and verify structure."""

    def test_frontmatter(self, real_plan: Plan) -> None:
        assert real_plan.frontmatter.project_name == "zero-operators-build"

    def test_objective_present(self, real_plan: Plan) -> None:
        assert real_plan.objective
        assert "Zero Operators" in real_plan.objective

    def test_oracle_parsed(self, real_plan: Plan) -> None:
        assert real_plan.oracle is not None
        assert real_plan.oracle.primary_metric
        assert real_plan.oracle.ground_truth_source
        assert real_plan.oracle.evaluation_method
        assert real_plan.oracle.target_threshold
        assert real_plan.oracle.evaluation_frequency

    def test_workflow_mode(self, real_plan: Plan) -> None:
        assert real_plan.workflow is not None
        assert real_plan.workflow.mode == WorkflowMode.CLASSICAL_ML

    def test_data_sources_non_empty(self, real_plan: Plan) -> None:
        assert len(real_plan.data_sources) >= 1

    def test_domain_priors_present(self, real_plan: Plan) -> None:
        assert real_plan.domain_priors

    def test_agents_parsed(self, real_plan: Plan) -> None:
        assert real_plan.agents is not None
        assert len(real_plan.agents.active_agents) >= 1
        assert "software-architect" in real_plan.agents.active_agents

    def test_constraints_present(self, real_plan: Plan) -> None:
        assert real_plan.constraints

    def test_optional_sections_detected(self, real_plan: Plan) -> None:
        # The real plan has Milestones, Delivery, Environment.
        assert real_plan.milestones is not None
        assert real_plan.delivery is not None
        assert real_plan.environment is not None

    def test_source_path_set(self, real_plan: Plan) -> None:
        assert real_plan.source_path == REAL_PLAN_PATH


# ---------------------------------------------------------------------------
# Full plan parsing (minimal fixture)
# ---------------------------------------------------------------------------

class TestParsePlanMinimal:
    """Parse the minimal valid plan and verify structure."""

    def test_parses_successfully(self, minimal_plan_path: Path) -> None:
        plan = parse_plan(minimal_plan_path)
        assert plan.frontmatter.project_name == "test-project"
        assert plan.objective
        assert plan.oracle is not None
        assert plan.workflow is not None
        assert len(plan.data_sources) == 1
        assert plan.agents is not None
        assert len(plan.agents.active_agents) == 2

    def test_optional_sections_absent(self, minimal_plan_path: Path) -> None:
        plan = parse_plan(minimal_plan_path)
        assert plan.milestones is None
        assert plan.delivery is None
        assert plan.environment is None
        assert plan.open_questions is None


# ---------------------------------------------------------------------------
# Validation — happy path
# ---------------------------------------------------------------------------

class TestValidationValid:
    """Validation passes for well-formed plans."""

    def test_real_plan_valid(self, real_plan: Plan) -> None:
        report = validate_plan(real_plan)
        assert report.valid, f"Issues: {[i.message for i in report.issues]}"
        assert len(report.issues) == 0

    def test_minimal_plan_valid(self, minimal_plan_path: Path) -> None:
        plan = parse_plan(minimal_plan_path)
        report = validate_plan(plan)
        assert report.valid, f"Issues: {[i.message for i in report.issues]}"


# ---------------------------------------------------------------------------
# Validation — missing required sections
# ---------------------------------------------------------------------------

class TestValidationMissingSections:
    """Validation detects missing required sections."""

    def test_missing_objective(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "## Objective\n\nBuild something useful.\n\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Objective" in i.message for i in report.issues)

    def test_missing_oracle(self, tmp_path: Path) -> None:
        # Remove the entire Oracle section.
        lines = MINIMAL_VALID_PLAN.split("\n")
        filtered: list[str] = []
        skip = False
        for line in lines:
            if line.startswith("## Oracle"):
                skip = True
                continue
            if skip and line.startswith("## "):
                skip = False
            if not skip:
                filtered.append(line)
        content = "\n".join(filtered)
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Oracle" in i.message for i in report.issues)

    def test_missing_constraints(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "## Constraints\n\n- No live access.\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Constraints" in i.message for i in report.issues)

    def test_missing_agents(self, tmp_path: Path) -> None:
        lines = MINIMAL_VALID_PLAN.split("\n")
        filtered: list[str] = []
        skip = False
        for line in lines:
            if line.startswith("## Agents"):
                skip = True
                continue
            if skip and line.startswith("## "):
                skip = False
            if not skip:
                filtered.append(line)
        content = "\n".join(filtered)
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Agent" in i.message for i in report.issues)

    def test_missing_data_sources(self, tmp_path: Path) -> None:
        lines = MINIMAL_VALID_PLAN.split("\n")
        filtered: list[str] = []
        skip = False
        for line in lines:
            if line.startswith("## Data Sources"):
                skip = True
                continue
            if skip and line.startswith("## "):
                skip = False
            if not skip:
                filtered.append(line)
        content = "\n".join(filtered)
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("data source" in i.message.lower() for i in report.issues)

    def test_missing_domain_priors(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "## Domain Priors\n\nSome domain knowledge here.\n\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Domain" in i.message or "Priors" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# Validation — invalid workflow mode
# ---------------------------------------------------------------------------

class TestValidationWorkflowMode:
    """Validation catches invalid workflow modes."""

    def test_invalid_mode_raises_on_parse(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Mode:** classical_ml",
            "**Mode:** invalid_mode",
        )
        with pytest.raises(ValueError, match="Invalid workflow mode"):
            parse_plan(_write_plan(tmp_path, content))

    def test_deep_learning_mode_accepted(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Mode:** classical_ml",
            "**Mode:** deep_learning",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.workflow is not None
        assert plan.workflow.mode == WorkflowMode.DEEP_LEARNING

    def test_research_mode_accepted(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Mode:** classical_ml",
            "**Mode:** research",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.workflow is not None
        assert plan.workflow.mode == WorkflowMode.RESEARCH


# ---------------------------------------------------------------------------
# Validation — oracle field completeness
# ---------------------------------------------------------------------------

class TestValidationOracleFields:
    """Validation detects missing oracle required fields."""

    def test_missing_primary_metric(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Primary metric:** Accuracy\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Primary metric" in i.message for i in report.issues)

    def test_missing_ground_truth(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Ground truth source:** test dataset\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Ground truth" in i.message for i in report.issues)

    def test_missing_target_threshold(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Target threshold:** >90%\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Target threshold" in i.message for i in report.issues)

    def test_missing_evaluation_frequency(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Evaluation frequency:** per iteration\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Evaluation frequency" in i.message for i in report.issues)

    def test_missing_evaluation_method(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Evaluation method:** holdout split\n",
            "",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("Evaluation method" in i.message for i in report.issues)


# ---------------------------------------------------------------------------
# Validation — empty agent list
# ---------------------------------------------------------------------------

class TestValidationAgents:
    """Validation catches empty active agent lists."""

    def test_agents_section_but_no_active(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Inactive agents:** all",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        report = validate_plan(plan)
        assert not report.valid
        assert any("active agent" in i.message.lower() for i in report.issues)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Miscellaneous edge-case coverage."""

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_plan(Path("/nonexistent/plan.md"))

    def test_validation_report_model(self) -> None:
        report = ValidationReport(valid=True, issues=[])
        assert report.valid
        assert report.issues == []

    def test_validation_issue_model(self) -> None:
        issue = ValidationIssue(
            section="Oracle",
            severity="error",
            message="Missing field.",
        )
        assert issue.section == "Oracle"
        assert issue.severity == "error"

    def test_plan_status_enum(self) -> None:
        assert PlanStatus.ACTIVE.value == "active"
        assert PlanStatus.PAUSED.value == "paused"
        assert PlanStatus.COMPLETED.value == "completed"

    def test_workflow_mode_enum(self) -> None:
        assert WorkflowMode.CLASSICAL_ML.value == "classical_ml"
        assert WorkflowMode.DEEP_LEARNING.value == "deep_learning"
        assert WorkflowMode.RESEARCH.value == "research"

    def test_workflow_mode_with_annotation(self, tmp_path: Path) -> None:
        """Mode with parenthetical annotation like 'classical_ml (adapted ...)'."""
        content = MINIMAL_VALID_PLAN.replace(
            "**Mode:** classical_ml",
            "**Mode:** classical_ml (adapted — software build)",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.workflow is not None


# ---------------------------------------------------------------------------
# Agent adaptations parsing
# ---------------------------------------------------------------------------


class TestAgentAdaptations:
    """Parser coverage for the ``**Agent adaptations:**`` block."""

    def test_no_adaptations_block_means_empty_list(
        self, tmp_path: Path,
    ) -> None:
        plan = parse_plan(_write_plan(tmp_path, MINIMAL_VALID_PLAN))
        assert plan.agents is not None
        assert plan.agents.adaptations == []
        assert plan.agents.adaptation_for("xai-agent") is None

    def test_single_line_adaptation(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent: Focus on time-series attribution for vibration "
            "sensor data.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        assert len(plan.agents.adaptations) == 1
        a = plan.agents.adaptations[0]
        assert a.agent_name == "xai-agent"
        assert "time-series attribution" in a.adaptation

    def test_multi_line_adaptation(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent:\n"
            "  Focus on frequency-domain attribution and spectrograms.\n"
            "  Generic SHAP/GradCAM is less relevant for time-series data.\n"
            "  Include bearing failure envelope plots in the Phase 5 report.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        assert len(plan.agents.adaptations) == 1
        a = plan.agents.adaptations[0]
        assert a.agent_name == "xai-agent"
        assert "frequency-domain" in a.adaptation
        assert "bearing failure envelope" in a.adaptation

    def test_multiple_adaptations(self, tmp_path: Path) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent, domain-evaluator\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent:\n"
            "  Focus on frequency-domain attribution.\n"
            "\n"
            "- domain-evaluator:\n"
            "  Apply IVL F5 vibration priors.\n"
            "  Flag predictions contradicting bearing failure signatures.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        assert len(plan.agents.adaptations) == 2
        names = [a.agent_name for a in plan.agents.adaptations]
        assert "xai-agent" in names
        assert "domain-evaluator" in names
        dom = plan.agents.adaptation_for("domain-evaluator")
        assert dom is not None
        assert "IVL F5" in dom
        assert "bearing failure" in dom

    def test_adaptation_for_missing_agent_returns_none(
        self, tmp_path: Path,
    ) -> None:
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent: Single-line adaptation.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        assert plan.agents.adaptation_for("unknown-agent") is None

    def test_adaptation_coexists_with_custom_agents(
        self, tmp_path: Path,
    ) -> None:
        """Custom agents AND adaptations in the same plan, both parsed."""
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent\n"
            "\n"
            "**Custom agents:**\n"
            "- signal-analyst: Sonnet — Signal processing specialist\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent:\n"
            "  Focus on frequency-domain attribution.\n"
            "\n"
            "- signal-analyst:\n"
            "  Project scope: vibration data sampled at 20kHz, 2048-sample windows.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        # Custom agent parsed
        assert len(plan.agents.custom_agents) == 1
        assert plan.agents.custom_agents[0].name == "signal-analyst"
        # Both adaptations parsed
        assert len(plan.agents.adaptations) == 2
        # Adaptation for a custom agent also works
        sa = plan.agents.adaptation_for("signal-analyst")
        assert sa is not None
        assert "20kHz" in sa

    def test_empty_adaptation_body_is_skipped(self, tmp_path: Path) -> None:
        """An entry with no body text is dropped, not parsed as empty."""
        content = MINIMAL_VALID_PLAN.replace(
            "**Active agents:** lead-orchestrator, data-engineer",
            "**Active agents:** lead-orchestrator, data-engineer, xai-agent\n"
            "\n"
            "**Agent adaptations:**\n"
            "\n"
            "- xai-agent:\n"
            "\n"
            "- domain-evaluator: Real adaptation here.",
        )
        plan = parse_plan(_write_plan(tmp_path, content))
        assert plan.agents is not None
        names = [a.agent_name for a in plan.agents.adaptations]
        assert "xai-agent" not in names  # empty body skipped
        assert "domain-evaluator" in names
        assert plan.workflow.mode == WorkflowMode.CLASSICAL_ML
