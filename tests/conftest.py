"""Shared pytest fixtures for the Zero Operators test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from zo.comms import CommsLogger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "test-project"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_plan_path() -> Path:
    """Path to the test-project fixture plan.md."""
    p = FIXTURES_DIR / "plan.md"
    assert p.exists(), f"Fixture not found: {p}"
    return p


@pytest.fixture()
def sample_target_path() -> Path:
    """Path to the test-project fixture target.md."""
    p = FIXTURES_DIR / "target.md"
    assert p.exists(), f"Fixture not found: {p}"
    return p


@pytest.fixture()
def tmp_project_dir(tmp_path: Path) -> Path:
    """A temporary directory simulating a ZO project.

    Copies the fixture files into a temp tree so tests can mutate
    freely without affecting the real fixtures.
    """
    project = tmp_path / "test-project"
    project.mkdir()

    # Copy fixture files
    shutil.copy(FIXTURES_DIR / "plan.md", project / "plan.md")
    shutil.copy(FIXTURES_DIR / "target.md", project / "target.md")

    # Create ancillary directories a real project would have
    (project / "logs" / "comms").mkdir(parents=True)
    (project / "memory").mkdir()

    return project


@pytest.fixture()
def comms_logger(tmp_path: Path) -> CommsLogger:
    """A CommsLogger writing to a temporary directory."""
    log_dir = tmp_path / "logs" / "comms"
    return CommsLogger(
        log_dir=log_dir,
        project="churn-prediction",
        session_id="test-session-001",
    )
