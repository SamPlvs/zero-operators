"""Test report generator for Zero Operators.

Runs pytest against the delivery repo's test suite, parses JUnit XML
results, and writes a structured markdown report to
``{delivery_repo}/reports/test_report.md``.

Called automatically by the orchestrator at every phase gate so there's
always a current test report artifact in the delivery repo.

Typical usage::

    from zo.test_report import generate_test_report
    path = generate_test_report(
        test_dir=delivery_repo / "tests",
        delivery_repo=delivery_repo,
        phase_id="phase_4",
        phase_name="Training and Iteration",
    )
"""

from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "generate_test_report",
    "parse_junit_xml",
    "render_test_report",
    "SuiteResult",
    "CaseResult",
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """Result of a single test case."""

    name: str
    classname: str
    duration: float = 0.0
    status: str = "passed"  # passed | failed | error | skipped
    message: str = ""
    traceback: str = ""

    @property
    def module(self) -> str:
        """Extract the module path from classname (e.g. tests.unit.test_data)."""
        return self.classname.rsplit(".", 1)[0] if "." in self.classname else self.classname


@dataclass
class SuiteResult:
    """Aggregated test suite results parsed from JUnit XML."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total > 0 else 0.0


# ---------------------------------------------------------------------------
# JUnit XML parser
# ---------------------------------------------------------------------------


def parse_junit_xml(xml_path: Path) -> SuiteResult:
    """Parse a JUnit XML file into a :class:`SuiteResult`.

    Handles both ``<testsuites>`` (wrapper) and single ``<testsuite>``
    root elements.  Gracefully handles malformed or empty files.
    """
    if not xml_path.exists():
        return SuiteResult()

    try:
        tree = ET.parse(xml_path)  # noqa: S314 — trusted local file
    except ET.ParseError:
        return SuiteResult()

    root = tree.getroot()
    cases: list[CaseResult] = []

    # Find all <testcase> elements regardless of nesting
    for tc in root.iter("testcase"):
        name = tc.get("name", "unknown")
        classname = tc.get("classname", "")
        duration = float(tc.get("time", "0") or "0")

        status = "passed"
        message = ""
        traceback = ""

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "failed"
            message = failure.get("message", "")
            traceback = (failure.text or "").strip()
        elif error is not None:
            status = "error"
            message = error.get("message", "")
            traceback = (error.text or "").strip()
        elif skipped is not None:
            status = "skipped"
            message = skipped.get("message", "")

        cases.append(CaseResult(
            name=name, classname=classname, duration=duration,
            status=status, message=message, traceback=traceback,
        ))

    total = len(cases)
    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failed")
    errors = sum(1 for c in cases if c.status == "error")
    skipped_count = sum(1 for c in cases if c.status == "skipped")
    total_duration = sum(c.duration for c in cases)

    return SuiteResult(
        total=total, passed=passed, failed=failed,
        errors=errors, skipped=skipped_count,
        duration=total_duration, cases=cases,
    )


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_test_report(
    result: SuiteResult,
    phase_id: str = "",
    phase_name: str = "",
) -> str:
    """Render a :class:`SuiteResult` as a structured markdown report."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    phase_label = f" — Phase {phase_id.removeprefix('phase_')}: {phase_name}" if phase_id else ""

    lines: list[str] = []
    lines.append(f"# Test Report{phase_label}")
    lines.append(f"\nGenerated: {ts}\n")

    # --- Summary table ---
    lines.append("## Summary\n")
    lines.append("| Metric     | Value  |")
    lines.append("|------------|--------|")
    lines.append(f"| Total      | {result.total}    |")
    lines.append(f"| Passed     | {result.passed}    |")
    lines.append(f"| Failed     | {result.failed}    |")
    lines.append(f"| Errors     | {result.errors}    |")
    lines.append(f"| Skipped    | {result.skipped}    |")
    lines.append(f"| Duration   | {result.duration:.1f}s  |")
    lines.append(f"| Pass rate  | {result.pass_rate:.1f}% |")
    lines.append("")

    # --- Results by module ---
    if result.cases:
        modules: dict[str, dict[str, int | float]] = {}
        for case in result.cases:
            mod = case.module
            if mod not in modules:
                modules[mod] = {"total": 0, "passed": 0, "failed": 0,
                                "skipped": 0, "duration": 0.0}
            modules[mod]["total"] += 1
            if case.status == "passed":
                modules[mod]["passed"] += 1
            elif case.status in ("failed", "error"):
                modules[mod]["failed"] += 1
            elif case.status == "skipped":
                modules[mod]["skipped"] += 1
            modules[mod]["duration"] += case.duration

        lines.append("## Results by Module\n")
        lines.append("| Module | Tests | Pass | Fail | Skip | Duration |")
        lines.append("|--------|-------|------|------|------|----------|")
        for mod, stats in sorted(modules.items()):
            lines.append(
                f"| {mod} | {stats['total']} | {stats['passed']} | "
                f"{stats['failed']} | {stats['skipped']} | "
                f"{stats['duration']:.1f}s |"
            )
        lines.append("")

    # --- Failures ---
    failures = [c for c in result.cases if c.status in ("failed", "error")]
    if failures:
        lines.append("## Failures\n")
        for case in failures:
            lines.append(f"### {case.classname}::{case.name}\n")
            if case.message:
                lines.append(f"**{case.status.title()}**: {case.message}\n")
            if case.traceback:
                # Truncate long tracebacks to keep the report readable
                tb_lines = case.traceback.splitlines()
                if len(tb_lines) > 20:
                    tb_text = "\n".join(tb_lines[:10] + ["..."] + tb_lines[-5:])
                else:
                    tb_text = case.traceback
                lines.append(f"```\n{tb_text}\n```\n")
    else:
        lines.append("## Failures\n")
        lines.append("No failures.\n")

    # --- Skipped ---
    skipped_cases = [c for c in result.cases if c.status == "skipped"]
    if skipped_cases:
        lines.append("## Skipped Tests\n")
        for case in skipped_cases:
            reason = f": {case.message}" if case.message else ""
            lines.append(f"- `{case.classname}::{case.name}`{reason}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_test_report(
    test_dir: Path,
    delivery_repo: Path,
    phase_id: str = "",
    phase_name: str = "",
) -> Path | None:
    """Run pytest and generate a structured markdown test report.

    Args:
        test_dir: Directory containing tests (e.g. ``delivery_repo / "tests"``).
        delivery_repo: Delivery repo root — report written to ``reports/test_report.md``.
        phase_id: Current phase ID for the report header.
        phase_name: Current phase name for the report header.

    Returns:
        Path to the generated report, or ``None`` if tests couldn't run.
    """
    if not test_dir.is_dir():
        return _write_no_tests_report(delivery_repo, phase_id, phase_name)

    # Run pytest with JUnit XML output
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        xml_path = Path(tmp.name)

    try:
        subprocess.run(
            ["python", "-m", "pytest", str(test_dir),
             "--tb=short", "-q",
             f"--junitxml={xml_path}"],
            capture_output=True, text=True, timeout=300,
            cwd=str(delivery_repo),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _write_no_tests_report(delivery_repo, phase_id, phase_name)

    # Parse results and render report
    result = parse_junit_xml(xml_path)
    report_md = render_test_report(result, phase_id, phase_name)

    # Clean up temp file
    xml_path.unlink(missing_ok=True)

    # Write report
    report_dir = delivery_repo / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "test_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    return report_path


def _write_no_tests_report(
    delivery_repo: Path, phase_id: str, phase_name: str,
) -> Path:
    """Write a placeholder report when no tests are found."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    phase_label = f" — Phase {phase_id.removeprefix('phase_')}: {phase_name}" if phase_id else ""
    content = (
        f"# Test Report{phase_label}\n\n"
        f"Generated: {ts}\n\n"
        "## Summary\n\n"
        "No test directory found or pytest could not run.\n\n"
        "The test-engineer agent should create tests in `tests/` before "
        "the next gate evaluation.\n"
    )
    report_dir = delivery_repo / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "test_report.md"
    report_path.write_text(content, encoding="utf-8")
    return report_path
