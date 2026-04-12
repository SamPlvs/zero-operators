"""Unit tests for zo.test_report — JUnit XML parsing and markdown generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from zo.test_report import (
    CaseResult,
    SuiteResult,
    generate_test_report,
    parse_junit_xml,
    render_test_report,
)

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

SAMPLE_JUNIT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="1" skipped="1" tests="5" time="2.34">
    <testcase classname="tests.unit.test_data" name="test_load_csv" time="0.12"/>
    <testcase classname="tests.unit.test_data" name="test_schema_valid" time="0.08"/>
    <testcase classname="tests.unit.test_model" name="test_forward_pass" time="0.95"/>
    <testcase classname="tests.unit.test_model" name="test_convergence" time="1.10">
      <failure message="AssertionError: val_loss 0.063 not &lt; 0.05">
assert 0.063 &lt; 0.05
      </failure>
    </testcase>
    <testcase classname="tests.ml.test_gpu" name="test_gpu_training" time="0.09">
      <skipped message="no GPU available"/>
    </testcase>
  </testsuite>
</testsuites>
"""

EMPTY_JUNIT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0" time="0.00">
  </testsuite>
</testsuites>
"""

ALL_PASS_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3" failures="0" errors="0" time="0.50">
  <testcase classname="tests.unit.test_a" name="test_one" time="0.1"/>
  <testcase classname="tests.unit.test_a" name="test_two" time="0.2"/>
  <testcase classname="tests.unit.test_b" name="test_three" time="0.2"/>
</testsuite>
"""


@pytest.fixture()
def xml_path(tmp_path: Path) -> Path:
    p = tmp_path / "results.xml"
    p.write_text(SAMPLE_JUNIT_XML, encoding="utf-8")
    return p


@pytest.fixture()
def delivery_repo(tmp_path: Path) -> Path:
    d = tmp_path / "delivery"
    d.mkdir()
    return d


# ------------------------------------------------------------------ #
# CaseResult
# ------------------------------------------------------------------ #


class TestCaseResult:
    def test_module_extraction(self) -> None:
        tc = CaseResult(name="test_foo", classname="tests.unit.test_data")
        assert tc.module == "tests.unit"

    def test_module_no_dot(self) -> None:
        tc = CaseResult(name="test_foo", classname="test_data")
        assert tc.module == "test_data"


# ------------------------------------------------------------------ #
# parse_junit_xml
# ------------------------------------------------------------------ #


class TestParseJunitXml:
    def test_parses_sample(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        assert result.total == 5
        assert result.passed == 3
        assert result.failed == 1
        assert result.skipped == 1
        assert result.errors == 0
        assert result.duration > 0

    def test_failure_details(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        failures = [c for c in result.cases if c.status == "failed"]
        assert len(failures) == 1
        assert "convergence" in failures[0].name
        assert "0.063" in failures[0].message

    def test_skipped_details(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        skipped = [c for c in result.cases if c.status == "skipped"]
        assert len(skipped) == 1
        assert "GPU" in skipped[0].message

    def test_empty_suite(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.xml"
        p.write_text(EMPTY_JUNIT_XML, encoding="utf-8")
        result = parse_junit_xml(p)
        assert result.total == 0
        assert result.pass_rate == 0.0

    def test_all_pass(self, tmp_path: Path) -> None:
        p = tmp_path / "pass.xml"
        p.write_text(ALL_PASS_XML, encoding="utf-8")
        result = parse_junit_xml(p)
        assert result.total == 3
        assert result.passed == 3
        assert result.pass_rate == 100.0

    def test_missing_file(self, tmp_path: Path) -> None:
        result = parse_junit_xml(tmp_path / "nope.xml")
        assert result.total == 0

    def test_corrupt_file(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.xml"
        p.write_text("not xml at all", encoding="utf-8")
        result = parse_junit_xml(p)
        assert result.total == 0

    def test_single_testsuite_root(self, tmp_path: Path) -> None:
        """Handle <testsuite> as root (no <testsuites> wrapper)."""
        p = tmp_path / "single.xml"
        p.write_text(ALL_PASS_XML, encoding="utf-8")
        result = parse_junit_xml(p)
        assert result.total == 3


# ------------------------------------------------------------------ #
# render_test_report
# ------------------------------------------------------------------ #


class TestRenderTestReport:
    def test_renders_summary_table(self) -> None:
        result = SuiteResult(total=10, passed=9, failed=1, duration=1.5)
        md = render_test_report(result, "phase_4", "Training")
        assert "# Test Report" in md
        assert "Phase 4: Training" in md
        assert "| Total" in md
        assert "90.0%" in md

    def test_renders_failure_section(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        md = render_test_report(result)
        assert "## Failures" in md
        assert "test_convergence" in md
        assert "0.063" in md

    def test_no_failures_message(self) -> None:
        result = SuiteResult(total=5, passed=5)
        md = render_test_report(result)
        assert "No failures" in md

    def test_renders_module_breakdown(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        md = render_test_report(result)
        assert "## Results by Module" in md
        assert "tests.unit" in md

    def test_renders_skipped_section(self, xml_path: Path) -> None:
        result = parse_junit_xml(xml_path)
        md = render_test_report(result)
        assert "## Skipped Tests" in md
        assert "test_gpu_training" in md

    def test_empty_result(self) -> None:
        result = SuiteResult()
        md = render_test_report(result)
        assert "| Total      | 0" in md


# ------------------------------------------------------------------ #
# generate_test_report
# ------------------------------------------------------------------ #


class TestGenerateTestReport:
    def test_no_test_dir_writes_placeholder(self, delivery_repo: Path) -> None:
        path = generate_test_report(
            test_dir=delivery_repo / "tests",
            delivery_repo=delivery_repo,
            phase_id="phase_1",
            phase_name="Data Review",
        )
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "No test directory found" in content

    def test_report_written_to_reports_dir(self, delivery_repo: Path) -> None:
        path = generate_test_report(
            test_dir=delivery_repo / "tests",
            delivery_repo=delivery_repo,
        )
        assert path is not None
        assert path.parent.name == "reports"
        assert path.name == "test_report.md"
