"""Integration tests for zo preflight.

Tests run preflight checks against real fixture plans and the actual
plan parser — no mocking of ValidationReport or ValidationIssue.
This catches attribute name mismatches (PR-025) that unit-test mocks hide.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from zo.preflight import (
    CheckResult,
    PreflightReport,
    _check_agents,
    _check_memory_roundtrip,
    _check_plan,
    run_preflight,
)

FIXTURE_PLAN = Path(__file__).resolve().parent.parent / "fixtures" / "test-project" / "plan.md"
ZO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestCheckPlanIntegration:
    """Run _check_plan against real fixture plans — no mocks."""

    def test_fixture_plan_passes(self) -> None:
        """The test-project fixture plan should pass validation."""
        result = _check_plan(FIXTURE_PLAN)
        assert result.passed, f"Fixture plan failed: {result.message}"
        assert "valid" in result.message.lower()

    def test_missing_plan_fails(self, tmp_path: Path) -> None:
        result = _check_plan(tmp_path / "nonexistent.md")
        assert not result.passed
        assert "not found" in result.message.lower()

    def test_empty_plan_fails(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.md"
        empty.write_text("")
        result = _check_plan(empty)
        assert not result.passed

    def test_plan_with_parenthetical_oracle_fields(self, tmp_path: Path) -> None:
        """Oracle fields with parenthetical suffixes must parse correctly.

        This is the exact bug from PR-025: ``**Target threshold (per-tag RMSE):**``
        failed to match the ``target threshold`` alias because the parser
        didn't strip the parenthetical before lookup.
        """
        plan_text = '''---
project_name: "test-parens"
version: "1.0"
created: "2026-01-01"
last_modified: "2026-01-01"
status: active
owner: "TestEngineer"
---

## Objective

Test that parenthetical oracle field names parse correctly.

## Oracle

**Primary metric:** RMSE
**Ground truth source:** lab data
**Evaluation method:** held-out test set
**Target threshold (per-tag RMSE):** < 0.5 for all tags
**Evaluation frequency:** per training run

## Workflow

**Mode:** classical_ml

## Data Sources

### Source 1
- **Location:** data/raw/
- **Format:** CSV

## Domain Priors

Standard ML priors.

## Agents

**Active agents:** lead-orchestrator, data-engineer, model-builder

## Constraints

None specified.

## Milestones

| Phase | Milestone | Gate |
|-------|-----------|------|
| 1 | Data loaded | Gate 1 |

## Delivery

**Target repo:** ../test-delivery/
'''
        plan_file = tmp_path / "parens-plan.md"
        plan_file.write_text(plan_text)
        result = _check_plan(plan_file)
        assert result.passed, f"Parenthetical oracle field failed: {result.message}"

    def test_validation_failure_shows_section_not_field(self, tmp_path: Path) -> None:
        """When validation fails, the error message must use 'section' attribute."""
        # Plan missing Oracle section entirely
        plan_text = '''---
project_name: "test-missing"
version: "1.0"
created: "2026-01-01"
last_modified: "2026-01-01"
status: active
owner: "Test"
---

## Objective

Test missing sections.

## Workflow

**Mode:** classical_ml

## Data Sources

### Source 1
- **Location:** data/

## Domain Priors

None.

## Agents

**Active agents:** lead-orchestrator

## Constraints

None.

## Milestones

| Phase | Milestone | Gate |
|-------|-----------|------|
| 1 | Done | Gate 1 |

## Delivery

**Target repo:** ../test/
'''
        plan_file = tmp_path / "incomplete.md"
        plan_file.write_text(plan_text)
        result = _check_plan(plan_file)
        # Should either fail validation or pass — but must NOT throw AttributeError
        assert isinstance(result, CheckResult)
        assert isinstance(result.message, str)


class TestCheckAgentsIntegration:
    """Run _check_agents against real agent definitions."""

    def test_fixture_plan_agents_found(self) -> None:
        result = _check_agents(FIXTURE_PLAN, ZO_ROOT)
        assert result.passed, f"Agent check failed: {result.message}"


class TestMemoryRoundtrip:
    """Run _check_memory_roundtrip with real MemoryManager."""

    def test_roundtrip_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = _check_memory_roundtrip(Path(td))
            assert result.passed, f"Memory roundtrip failed: {result.message}"


class TestRunPreflightIntegration:
    """Run the full preflight pipeline against fixture plan."""

    def test_full_preflight_no_attribute_errors(self) -> None:
        """Full preflight must not throw AttributeError on any check."""
        report = run_preflight(FIXTURE_PLAN, ZO_ROOT)
        assert isinstance(report, PreflightReport)
        # Every check must return a valid CheckResult — no exceptions
        for check in report.checks:
            assert isinstance(check, CheckResult)
            assert isinstance(check.name, str)
            assert isinstance(check.passed, bool)
            assert isinstance(check.message, str)

    def test_plan_check_passes_in_full_preflight(self) -> None:
        report = run_preflight(FIXTURE_PLAN, ZO_ROOT)
        plan_checks = [c for c in report.checks if c.name == "Plan"]
        assert len(plan_checks) == 1
        assert plan_checks[0].passed, f"Plan check failed: {plan_checks[0].message}"
