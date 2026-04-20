"""Integration tests for the ``zo experiments`` CLI group."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

import click.testing
import pytest

from zo.cli import cli
from zo.experiments import (
    ExperimentResult,
    PrimaryMetric,
    mint_experiment,
    update_result,
)
from zo.project_config import ProjectConfig, save_project_config

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"


def _make_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path, capture_output=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com",
        },
        check=True,
    )


@pytest.fixture()
def project(tmp_path: Path) -> tuple[str, Path, Path]:
    """Set up a project using the portable .zo/ layout.

    Returns (project_name, zo_root, delivery_repo). The delivery repo
    contains a valid ``.zo/config.yaml`` so ``_load_project_context``
    resolves via the zo-dir layout (no legacy-fallback to the ZO repo).
    """
    zo_root = tmp_path / "zo"
    zo_root.mkdir()
    _make_git_repo(zo_root)

    delivery = tmp_path / "delivery"
    delivery.mkdir()

    # Write .zo/config.yaml so _load_project_context takes the zo-dir path.
    save_project_config(
        delivery,
        ProjectConfig(
            project_name="churn-prediction",
            alias="churn-prediction",
            branch="main",
        ),
    )
    # Copy the plan into the delivery repo's .zo/plans/ so discovery works.
    (delivery / ".zo" / "plans").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        FIXTURES_DIR / "plan.md",
        delivery / ".zo" / "plans" / "churn-prediction.md",
    )
    (delivery / ".zo" / "memory").mkdir(parents=True, exist_ok=True)
    return "churn-prediction", zo_root, delivery


@pytest.fixture()
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


def _seed_experiments(delivery: Path) -> Path:
    """Mint exp-001 (complete) + exp-002 (child, complete) for CLI tests.

    Returns the experiments dir.
    """
    exp_dir = delivery / ".zo" / "experiments"
    exp_001 = mint_experiment(
        exp_dir, project="churn-prediction", phase="phase_4",
        hypothesis="LSTM baseline beats naïve.",
        rationale="Baseline sanity check.",
    )
    update_result(exp_dir, exp_001.id, ExperimentResult(
        oracle_tier="should_pass",
        primary_metric=PrimaryMetric(name="mae", value=0.50),
        secondary_metrics={"rmse": 0.68},
        shortfalls=["weak on horizon>3", "overfit after epoch 10"],
    ))
    exp_002 = mint_experiment(
        exp_dir, project="churn-prediction", phase="phase_4",
        hypothesis="TFT beats LSTM on long horizon.",
        rationale="Attention addresses horizon>3 shortfall.",
        parent_id=exp_001.id,
    )
    update_result(exp_dir, exp_002.id, ExperimentResult(
        oracle_tier="must_pass",
        primary_metric=PrimaryMetric(name="mae", value=0.30),
        secondary_metrics={"rmse": 0.45},
        shortfalls=["weak on regime-shift samples"],
    ))
    return exp_dir


class TestExperimentsListCommand:
    def test_empty_registry_prints_hint(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        result = runner.invoke(
            cli, ["experiments", "list", "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code == 0
        assert (
            "No experiments yet" in result.output
            or "No experiments match" in result.output
        )

    def test_lists_both_experiments(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "list", "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code == 0
        assert "exp-001" in result.output
        assert "exp-002" in result.output
        assert "mae=0.5" in result.output
        assert "mae=0.3" in result.output

    def test_shows_delta_for_child(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "list", "-p", name, "--repo", str(delivery)],
        )
        # delta_vs_parent for exp-002 should be negative (improvement).
        assert "-0.2" in result.output

    def test_phase_filter(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, [
                "experiments", "list", "-p", name, "--repo", str(delivery),
                "--phase", "phase_99",
            ],
        )
        assert result.exit_code == 0
        assert "No experiments match" in result.output


class TestExperimentsShowCommand:
    def test_shows_experiment_details(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "show", "exp-001",
                  "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code == 0
        assert "exp-001" in result.output
        assert "should_pass" in result.output
        assert "weak on horizon" in result.output

    def test_unknown_id_errors(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "show", "exp-999",
                  "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestExperimentsDiffCommand:
    def test_diff_shows_metric_delta(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "diff", "exp-001", "exp-002",
                  "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code == 0
        assert "exp-001" in result.output
        assert "exp-002" in result.output
        # Primary metric delta: 0.3 - 0.5 = -0.2
        assert "-0.2" in result.output

    def test_diff_shows_shortfall_diff(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "diff", "exp-001", "exp-002",
                  "-p", name, "--repo", str(delivery)],
        )
        # regime-shift is only in exp-002; overfit only in exp-001.
        assert "regime-shift" in result.output
        assert "overfit" in result.output

    def test_diff_missing_id_errors(
        self,
        runner: click.testing.CliRunner,
        project: tuple[str, Path, Path],
    ) -> None:
        name, _, delivery = project
        _seed_experiments(delivery)
        result = runner.invoke(
            cli, ["experiments", "diff", "exp-001", "exp-999",
                  "-p", name, "--repo", str(delivery)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
