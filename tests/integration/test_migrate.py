"""Integration tests for the ``zo migrate`` CLI command.

Verifies that ``zo migrate PROJECT --repo /path`` correctly copies
project state from the legacy ZO-repo layout (memory/, plans/, targets/)
into the delivery repo's .zo/ directory structure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click.testing
import pytest
import yaml

from zo.cli import cli


@pytest.fixture()
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TARGET_FRONTMATTER = """\
---
project: "{project}"
target_repo: "{target_repo}"
target_branch: "main"
worktree_base: "/tmp/zo-worktrees/{project}"
git_author_name: "ZO Agent"
git_author_email: "zo-agent@zero-operators.dev"
agent_working_dirs:
  data_engineer: "src/data/"
  model_builder: "src/model/"
zo_only_paths:
  - ".zo/"
  - "memory/"
enforce_isolation: true
---

# {project} target
"""

_STATE_MD = """\
# STATE

## Current Phase
Phase 1 — Data Engineering

## Status
In progress

## Known Issues
None
"""

_DECISION_LOG_MD = """\
# Decision Log

## 2024-01-01 — Setup
- Decided on classical ML workflow.
"""

_PRIORS_MD = """\
# Priors

No priors yet.
"""

_PLAN_MD = """\
# Plan: {project}

## Objective
Build a model.

## Oracle Definition
RMSE < 0.5
"""


def _mock_env() -> object:
    """Return a mock EnvironmentInfo with no GPU."""
    from zo.environment import EnvironmentInfo

    return EnvironmentInfo(
        platform="Darwin arm64",
        python_version="3.11.9",
        docker_available=False,
        docker_compose_available=False,
        gpu_count=0,
        gpu_names=[],
        gpu_memory_gb=[],
        cuda_version=None,
        nvidia_driver_version=None,
    )


def _setup_legacy(
    zo_root: Path,
    project: str,
    delivery: Path,
    *,
    with_sessions: bool = False,
    with_gate_mode: bool = False,
) -> None:
    """Create the legacy ZO repo layout for a project.

    Writes memory files, plan, and target file under ``zo_root``.
    """
    # Memory directory
    mem = zo_root / "memory" / project
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "STATE.md").write_text(_STATE_MD, encoding="utf-8")
    (mem / "DECISION_LOG.md").write_text(_DECISION_LOG_MD, encoding="utf-8")
    (mem / "PRIORS.md").write_text(_PRIORS_MD, encoding="utf-8")

    if with_sessions:
        sessions = mem / "sessions"
        sessions.mkdir(exist_ok=True)
        (sessions / "session-001.md").write_text("# Session 1\n", encoding="utf-8")
        (sessions / "session-002.md").write_text("# Session 2\n", encoding="utf-8")

    if with_gate_mode:
        (mem / "gate_mode").write_text("autonomous", encoding="utf-8")

    # Plan
    plans = zo_root / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / f"{project}.md").write_text(
        _PLAN_MD.format(project=project), encoding="utf-8",
    )

    # Target
    targets = zo_root / "targets"
    targets.mkdir(parents=True, exist_ok=True)
    (targets / f"{project}.target.md").write_text(
        _TARGET_FRONTMATTER.format(project=project, target_repo=str(delivery)),
        encoding="utf-8",
    )

    # Delivery repo must exist
    delivery.mkdir(parents=True, exist_ok=True)


def _invoke_migrate(
    runner: click.testing.CliRunner,
    zo_root: Path,
    project: str,
    delivery: Path,
    *,
    clean: bool = False,
) -> click.testing.Result:
    """Invoke ``zo migrate`` with monkeypatched roots."""
    args = ["migrate", project, "--repo", str(delivery)]
    if clean:
        args.append("--clean")

    with (
        patch("zo.cli._main_repo_root", return_value=zo_root),
        patch("zo.cli._zo_root", return_value=zo_root),
        patch("zo.environment.detect_environment", return_value=_mock_env()),
    ):
        return runner.invoke(cli, args)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrateCommand:
    """Integration tests for ``zo migrate``."""

    def test_migrate_copies_memory_files(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Memory files (STATE.md, DECISION_LOG.md, PRIORS.md) are copied to .zo/memory/."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        zo_mem = delivery / ".zo" / "memory"
        assert zo_mem.is_dir()
        assert (zo_mem / "STATE.md").exists()
        assert (zo_mem / "DECISION_LOG.md").exists()
        assert (zo_mem / "PRIORS.md").exists()

        # Verify content was actually copied, not just touched
        assert "Phase 1" in (zo_mem / "STATE.md").read_text()
        assert "Decision Log" in (zo_mem / "DECISION_LOG.md").read_text()

    def test_migrate_copies_plan(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Plan file is copied to .zo/plans/{project}.md."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        plan = delivery / ".zo" / "plans" / "test-proj.md"
        assert plan.exists()
        content = plan.read_text()
        assert "# Plan: test-proj" in content
        assert "Oracle Definition" in content

    def test_migrate_creates_config_from_target(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Config.yaml is generated from the legacy target file fields."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        config_path = delivery / ".zo" / "config.yaml"
        assert config_path.exists()

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["project_name"] == "test-proj"
        assert data["branch"] == "main"
        assert "data_engineer" in data["agent_working_dirs"]
        assert data["git_author_name"] == "ZO Agent"
        assert data["enforce_isolation"] is True

    def test_migrate_creates_local_yaml(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Local.yaml is written when gate_mode is present in legacy memory."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery, with_gate_mode=True)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        local_path = delivery / ".zo" / "local.yaml"
        assert local_path.exists()

        data = yaml.safe_load(local_path.read_text(encoding="utf-8"))
        assert data["gate_mode"] == "autonomous"
        # Environment detection mock returns 0 GPUs
        assert data["gpu_count"] == 0

    def test_migrate_creates_gitignore(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """A .zo/.gitignore is written with local.yaml listed."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        gitignore = delivery / ".zo" / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "local.yaml" in content

    def test_migrate_copies_sessions(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Session files from memory/{project}/sessions/ appear in .zo/memory/sessions/."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery, with_sessions=True)

        result = _invoke_migrate(runner, zo_root, "test-proj", delivery)

        assert result.exit_code == 0, result.output

        sessions_dir = delivery / ".zo" / "memory" / "sessions"
        assert sessions_dir.is_dir()
        session_files = sorted(f.name for f in sessions_dir.iterdir())
        assert "session-001.md" in session_files
        assert "session-002.md" in session_files
        assert (sessions_dir / "session-001.md").read_text().strip() == "# Session 1"

    def test_migrate_idempotent(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Running migrate twice produces no errors or duplicate files."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery, with_sessions=True)

        result1 = _invoke_migrate(runner, zo_root, "test-proj", delivery)
        assert result1.exit_code == 0, result1.output

        result2 = _invoke_migrate(runner, zo_root, "test-proj", delivery)
        assert result2.exit_code == 0, result2.output

        # Files should still exist exactly once
        zo_mem = delivery / ".zo" / "memory"
        assert (zo_mem / "STATE.md").exists()
        assert (zo_mem / "DECISION_LOG.md").exists()

        # Second run should mention "already exists"
        assert "already exists" in result2.output.lower() or "already has" in result2.output.lower()

        # Session count should not double
        sessions_dir = zo_mem / "sessions"
        session_files = list(sessions_dir.iterdir())
        assert len(session_files) == 2

    def test_migrate_clean_removes_legacy(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Running with --clean removes the legacy memory, plan, and target files."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        _setup_legacy(zo_root, "test-proj", delivery, with_sessions=True)

        # Verify legacy files exist before migrate
        assert (zo_root / "memory" / "test-proj" / "STATE.md").exists()
        assert (zo_root / "plans" / "test-proj.md").exists()
        assert (zo_root / "targets" / "test-proj.target.md").exists()

        result = _invoke_migrate(
            runner, zo_root, "test-proj", delivery, clean=True,
        )

        assert result.exit_code == 0, result.output

        # Legacy artifacts should be gone
        assert not (zo_root / "memory" / "test-proj").exists()
        assert not (zo_root / "plans" / "test-proj.md").exists()
        assert not (zo_root / "targets" / "test-proj.target.md").exists()

        # But .zo/ should have the migrated files
        assert (delivery / ".zo" / "memory" / "STATE.md").exists()
        assert (delivery / ".zo" / "plans" / "test-proj.md").exists()
        assert (delivery / ".zo" / "config.yaml").exists()
