"""Unit tests for zo.cli module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click.testing
import pytest

from zo.cli import cli


@pytest.fixture()
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


# ---------------------------------------------------------------------------
# CLI group structure
# ---------------------------------------------------------------------------


class TestCliGroup:
    """Tests for the CLI group and its registered commands."""

    def test_cli_group_has_all_commands(self) -> None:
        expected = {"build", "continue", "init", "status", "draft", "preflight"}
        actual = set(cli.commands.keys())
        assert expected == actual

    def test_version_option(self, runner: click.testing.CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        # Exits 0 when package is installed; may error if not pip-installed.
        # Either way, the option must be recognized (not "no such option").
        assert "no such option" not in result.output.lower()
        if result.exit_code == 0:
            assert "version" in result.output.lower()

    def test_help_output(self, runner: click.testing.CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Zero Operators" in result.output


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInitCommand:
    """Tests for the ``zo init`` command."""

    def test_init_creates_directory_structure(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["init", "test-project"])

        assert result.exit_code == 0

        # Memory files
        mem_root = tmp_path / "memory" / "test-project"
        assert mem_root.is_dir()
        assert (mem_root / "STATE.md").exists()
        assert (mem_root / "DECISION_LOG.md").exists()
        assert (mem_root / "PRIORS.md").exists()
        assert (mem_root / "sessions").is_dir()

        # Target template
        target = tmp_path / "targets" / "test-project.target.md"
        assert target.exists()
        content = target.read_text()
        assert "test-project" in content

        # Plan template
        plan = tmp_path / "plans" / "test-project.md"
        assert plan.exists()
        content = plan.read_text()
        assert "test-project" in content
        assert "## Objective" in content
        assert "## Oracle Definition" in content
        assert "## Workflow Configuration" in content
        assert "## Data Sources" in content
        assert "## Domain Context and Priors" in content
        assert "## Agent Configuration" in content
        assert "## Constraints" in content
        assert "## Milestones" in content

    def test_init_idempotent(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result1 = runner.invoke(cli, ["init", "test-project"])
            result2 = runner.invoke(cli, ["init", "test-project"])

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert "already exists" in result2.output

    def test_init_scaffold_delivery_creates_layout(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        zo_root = tmp_path / "zo"
        delivery = tmp_path / "delivery"

        with patch("zo.cli._zo_root", return_value=zo_root), \
             patch("zo.cli._main_repo_root", return_value=zo_root):
            result = runner.invoke(
                cli,
                ["init", "my-ml", "--scaffold-delivery", str(delivery)],
            )

        assert result.exit_code == 0

        # Directories
        for d in (
            "configs/data",
            "configs/model",
            "configs/training",
            "configs/experiment",
            "src/data",
            "src/model",
            "src/engineering",
            "src/inference",
            "src/utils",
            "data/raw",
            "data/processed",
            "models",
            "experiments",
            "reports/figures",
            "notebooks/data",
            "notebooks/model",
            "notebooks/analysis",
            "notebooks/phase",
            "tests/unit",
            "tests/ml",
            "tests/fixtures",
            "docker",
        ):
            assert (delivery / d).is_dir(), f"Missing dir: {d}"
            assert (delivery / d / ".gitkeep").exists()

        # Template files
        for f in (
            "README.md",
            "STRUCTURE.md",
            "pyproject.toml",
            ".gitignore",
            "experiments/README.md",
            "configs/experiment/base.yaml",
            "docker/Dockerfile",
            "docker/docker-compose.yml",
            "docker/.dockerignore",
        ):
            assert (delivery / f).exists(), f"Missing file: {f}"

        # Content interpolation
        readme = (delivery / "README.md").read_text()
        assert "my-ml" in readme

        pyproject = (delivery / "pyproject.toml").read_text()
        assert 'name = "my-ml"' in pyproject

    def test_init_scaffold_delivery_no_overwrite(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        zo_root = tmp_path / "zo"
        delivery = tmp_path / "delivery"
        delivery.mkdir(parents=True)

        # Pre-create a file that should NOT be overwritten
        (delivery / "README.md").write_text("custom content", encoding="utf-8")

        with patch("zo.cli._zo_root", return_value=zo_root), \
             patch("zo.cli._main_repo_root", return_value=zo_root):
            result = runner.invoke(
                cli,
                ["init", "my-ml", "--scaffold-delivery", str(delivery)],
            )

        assert result.exit_code == 0
        assert (delivery / "README.md").read_text() == "custom content"
        assert "already exists" in result.output.lower()

    def test_init_without_scaffold_still_works(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Ensure the flag is optional and init works without it."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["init", "plain-project"])

        assert result.exit_code == 0
        assert (tmp_path / "plans" / "plain-project.md").exists()


# ---------------------------------------------------------------------------
# scaffold module (direct)
# ---------------------------------------------------------------------------


class TestScaffoldDelivery:
    """Tests for the scaffold_delivery function directly."""

    def test_scaffold_creates_dockerfile(self, tmp_path: Path) -> None:
        from zo.scaffold import scaffold_delivery

        scaffold_delivery(tmp_path / "repo", "test-proj")

        dockerfile = (tmp_path / "repo" / "docker" / "Dockerfile").read_text()
        assert "FROM ${BASE_IMAGE} AS base" in dockerfile
        assert "uv sync" in dockerfile

    def test_scaffold_creates_compose(self, tmp_path: Path) -> None:
        from zo.scaffold import scaffold_delivery

        scaffold_delivery(tmp_path / "repo", "test-proj")

        compose = (tmp_path / "repo" / "docker" / "docker-compose.yml").read_text()
        assert "capabilities: [gpu]" in compose

    def test_scaffold_idempotent(self, tmp_path: Path) -> None:
        from zo.scaffold import scaffold_delivery

        repo = tmp_path / "repo"
        scaffold_delivery(repo, "proj")
        # Write custom content into an existing file
        (repo / "README.md").write_text("do not touch", encoding="utf-8")

        # Second run should not overwrite
        scaffold_delivery(repo, "proj")
        assert (repo / "README.md").read_text() == "do not touch"


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for the ``zo status`` command."""

    def test_status_no_project(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["status", "nonexistent"])

        assert result.exit_code == 1
        assert "No STATE.md found" in result.output

    def test_status_shows_state(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        # Create a minimal STATE.md
        mem_root = tmp_path / "memory" / "test-project"
        mem_root.mkdir(parents=True)
        (mem_root / "sessions").mkdir()
        (mem_root / "STATE.md").write_text(
            "---\n"
            "timestamp: 2026-01-01T00:00:00Z\n"
            "mode: build\n"
            "phase: data-pipeline\n"
            "---\n",
            encoding="utf-8",
        )

        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["status", "test-project"])

        assert result.exit_code == 0
        assert "test-project" in result.output


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for the ``zo build`` command."""

    def test_build_invalid_plan_path(
        self, runner: click.testing.CliRunner
    ) -> None:
        result = runner.invoke(cli, ["build", "/nonexistent/plan.md"])
        assert result.exit_code != 0

    def test_build_validates_plan(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        # Create a minimal invalid plan (missing sections)
        plan_path = tmp_path / "bad-plan.md"
        plan_path.write_text(
            "---\n"
            "project_name: bad\n"
            "version: 0.1.0\n"
            "created: 2026-01-01\n"
            "last_modified: 2026-01-01\n"
            "status: active\n"
            "owner: test\n"
            "---\n"
            "## Objective\n\nSomething\n",
            encoding="utf-8",
        )

        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["build", str(plan_path)])

        assert result.exit_code == 1
        assert "validation failed" in result.output.lower()

    def test_build_gate_mode_choices(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")

        for mode in ("supervised", "auto", "full-auto"):
            result = runner.invoke(
                cli, ["build", str(plan_path), "--gate-mode", mode]
            )
            # Will fail on parsing, but the option should be accepted
            assert "Invalid value for '--gate-mode'" not in result.output

    def test_build_invalid_gate_mode(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")

        result = runner.invoke(
            cli, ["build", str(plan_path), "--gate-mode", "yolo"]
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_build_no_tmux_flag(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")

        result = runner.invoke(cli, ["build", str(plan_path), "--no-tmux"])
        # Should accept the flag (will fail on plan parsing, not on flag)
        assert "no such option: --no-tmux" not in result.output


# ---------------------------------------------------------------------------
# continue command
# ---------------------------------------------------------------------------


class TestContinueCommand:
    """Tests for the ``zo continue`` command."""

    def test_continue_missing_plan(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """zo continue fails if no plan file exists for the project."""
        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["continue", "test-project"])

        assert result.exit_code == 1
        assert "Plan not found" in result.output


# ---------------------------------------------------------------------------
# draft command
# ---------------------------------------------------------------------------


class TestDraftCommand:
    """Tests for the ``zo draft`` command."""

    def test_draft_requires_project(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(cli, ["draft", str(tmp_path)])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_draft_indexes_and_generates(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        # Create source docs
        source_dir = tmp_path / "docs"
        source_dir.mkdir()
        (source_dir / "readme.md").write_text(
            "# My Project\n\nThis is a test project.\n",
            encoding="utf-8",
        )

        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        with patch("zo.cli._zo_root", return_value=zo_root):
            result = runner.invoke(
                cli, ["draft", str(source_dir), "--project", "test-draft",
                      "--no-tmux"]
            )

        assert result.exit_code == 0
        assert "Indexed" in result.output
        plan_path = zo_root / "plans" / "test-draft.md"
        assert plan_path.exists()

    def test_draft_from_description(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        with patch("zo.cli._zo_root", return_value=zo_root):
            result = runner.invoke(
                cli,
                ["draft", "--project", "test-desc", "-d",
                 "CIFAR-10 image classification with PyTorch CNN, target 90% accuracy",
                 "--no-tmux"],
            )

        assert result.exit_code == 0
        assert "Drafting plan for" in result.output
        plan_path = zo_root / "plans" / "test-desc.md"
        assert plan_path.exists()
        content = plan_path.read_text()
        assert "deep_learning" in content
        assert "Accuracy" in content
        assert "CIFAR-10" in content

    def test_draft_interactive_prompt(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        with patch("zo.cli._zo_root", return_value=zo_root):
            result = runner.invoke(
                cli,
                ["draft", "--project", "test-interactive", "--no-tmux"],
                input="Random forest classifier for tabular sales data, target RMSE < 0.1\n",
            )

        assert result.exit_code == 0
        plan_path = zo_root / "plans" / "test-interactive.md"
        assert plan_path.exists()
        content = plan_path.read_text()
        assert "classical_ml" in content
        assert "RMSE" in content

    def test_draft_empty_input_aborts(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        with patch("zo.cli._zo_root", return_value=zo_root):
            result = runner.invoke(
                cli,
                ["draft", "--project", "test-empty", "--no-tmux"],
                input="\n",
            )

        assert result.exit_code == 1
        assert "No description provided" in result.output


# ---------------------------------------------------------------------------
# gate-mode mapping
# ---------------------------------------------------------------------------


class TestGateModeMapping:
    """Tests for the gate mode string-to-enum mapping."""

    def test_gate_mode_mapping(self) -> None:
        from zo._orchestrator_models import GateMode
        from zo.cli import _gate_mode_from_str

        assert _gate_mode_from_str("supervised") == GateMode.SUPERVISED
        assert _gate_mode_from_str("auto") == GateMode.AUTO
        assert _gate_mode_from_str("full-auto") == GateMode.FULL_AUTO

    def test_gate_mode_invalid(self) -> None:
        from zo.cli import _gate_mode_from_str

        with pytest.raises(KeyError):
            _gate_mode_from_str("invalid")
