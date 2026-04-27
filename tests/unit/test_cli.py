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
        expected = {
            "build", "continue", "init", "status", "draft", "preflight",
            "gates", "watch-training", "migrate", "experiments",
        }
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
        # Branded banner uses uppercase "ZERO OPERATORS" to match the brand SVG.
        assert "zero operators" in result.output.lower()
        # Branded help should include the sectioned headers and the footer hint.
        assert "USAGE" in result.output
        assert "QUICK START" in result.output
        assert "COMMANDS" in result.output
        assert "OPTIONS" in result.output
        assert "--help" in result.output
        # Quick-start sequence must be in the right order (init → draft →
        # preflight → build → continue): preflight validates a plan, so it
        # cannot run until a plan exists.
        init_idx = result.output.index("zo init")
        draft_idx = result.output.index("zo draft")
        pre_idx = result.output.index("zo preflight")
        build_idx = result.output.index("zo build")
        cont_idx = result.output.index("zo continue")
        assert init_idx < draft_idx < pre_idx < build_idx < cont_idx


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
            result = runner.invoke(
                cli, ["init", "test-project", "--no-tmux", "--no-detect"],
            )

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
        # Default branch
        assert "target_branch: main" in content
        # Responsibility-based agent dirs
        assert "data-engineer: src/data/" in content
        assert "model-builder: src/model/" in content

        # Plan template
        plan = tmp_path / "plans" / "test-project.md"
        assert plan.exists()
        content = plan.read_text()
        assert "test-project" in content
        assert "## Objective" in content
        assert "## Oracle Definition" in content
        assert "## Workflow Configuration" in content
        assert "## Environment" in content  # NEW section
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
            result1 = runner.invoke(
                cli, ["init", "test-project", "--no-tmux", "--no-detect"],
            )
            result2 = runner.invoke(
                cli, ["init", "test-project", "--no-tmux", "--no-detect"],
            )

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
                ["init", "my-ml", "--no-tmux", "--no-detect",
                 "--scaffold-delivery", str(delivery)],
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
                ["init", "my-ml", "--no-tmux", "--no-detect",
                 "--scaffold-delivery", str(delivery)],
            )

        assert result.exit_code == 0
        assert (delivery / "README.md").read_text() == "custom content"

    def test_init_without_scaffold_still_works(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Ensure init works without --scaffold-delivery or --existing-repo."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "plain-project", "--no-tmux", "--no-detect"],
            )

        assert result.exit_code == 0
        assert (tmp_path / "plans" / "plain-project.md").exists()


# ---------------------------------------------------------------------------
# init command — failure modes and new flags
# ---------------------------------------------------------------------------


class TestInitHeadlessFlags:
    """Tests for the new --no-tmux flag surface on ``zo init``."""

    def test_init_branch_flag_writes_to_target(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "acme-proj", "--no-tmux", "--no-detect",
                 "--branch", "feature-branch"],
            )
        assert result.exit_code == 0
        target = (tmp_path / "targets" / "acme-proj.target.md").read_text()
        assert "target_branch: feature-branch" in target

    def test_init_existing_repo_requires_path_to_exist(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Pointing --existing-repo at a missing path is a UsageError."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "foo", "--no-tmux", "--no-detect",
                 "--existing-repo", str(tmp_path / "does-not-exist")],
            )
        assert result.exit_code != 0

    def test_init_existing_repo_requires_git(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """A plain directory without .git/ is a UsageError."""
        existing = tmp_path / "not-a-repo"
        existing.mkdir()
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "foo", "--no-tmux", "--no-detect",
                 "--existing-repo", str(existing)],
            )
        assert result.exit_code != 0
        assert "not a git repository" in result.output.lower()

    def test_init_scaffold_and_existing_mutually_exclusive(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        existing = tmp_path / "repo"
        existing.mkdir()
        (existing / ".git").mkdir()
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "foo", "--no-tmux", "--no-detect",
                 "--existing-repo", str(existing),
                 "--scaffold-delivery", str(tmp_path / "other")],
            )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_init_adaptive_requires_existing_repo(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """--layout-mode=adaptive only makes sense with --existing-repo."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "foo", "--no-tmux", "--no-detect",
                 "--layout-mode", "adaptive"],
            )
        assert result.exit_code != 0
        assert "adaptive" in result.output.lower()

    def test_init_adaptive_mode_skips_src_dirs(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Adaptive mode must not create src/* or data/* directories."""
        existing = tmp_path / "real-repo"
        existing.mkdir()
        (existing / ".git").mkdir()
        # Pretend the user already has a src-layout
        (existing / "src" / "acme_proj").mkdir(parents=True)
        (existing / "src" / "acme_proj" / "__init__.py").touch()
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "acme-proj", "--no-tmux", "--no-detect",
                 "--existing-repo", str(existing),
                 "--layout-mode", "adaptive",
                 "--branch", "feature-branch"],
            )
        assert result.exit_code == 0, result.output
        # Meta-dirs created
        assert (existing / "configs").is_dir()
        assert (existing / "experiments").is_dir()
        assert (existing / "docker").is_dir()
        assert (existing / "notebooks" / "phase").is_dir()
        # But ZO src/* layout NOT created (user has their own)
        assert not (existing / "src" / "data").exists()
        assert not (existing / "src" / "model").exists()
        # Existing code dir preserved
        assert (existing / "src" / "acme_proj" / "__init__.py").exists()
        # Adaptive also should NOT clobber README / pyproject / .gitignore
        # (skipped in adaptive mode even if missing)
        assert not (existing / "README.md").exists()
        assert not (existing / "pyproject.toml").exists()

    def test_init_adaptive_overlay_does_not_pollute_existing_src(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Existing code in src/ must not receive .gitkeep (no pollution)."""
        existing = tmp_path / "real-repo"
        existing.mkdir()
        (existing / ".git").mkdir()
        code_dir = existing / "src" / "acme_proj"
        code_dir.mkdir(parents=True)
        (code_dir / "trainer.py").write_text("x = 1", encoding="utf-8")
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "acme-proj", "--no-tmux", "--no-detect",
                 "--existing-repo", str(existing),
                 "--layout-mode", "adaptive"],
            )
        assert result.exit_code == 0, result.output
        assert not (code_dir / ".gitkeep").exists()

    def test_init_environment_section_filled_when_detect(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        """Without --no-detect, plan's Environment section is populated."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "foo", "--no-tmux"],
            )
        assert result.exit_code == 0, result.output
        plan = (tmp_path / "plans" / "foo.md").read_text()
        # Platform line filled — not "TODO"
        assert "platform: TODO" not in plan
        assert "python: TODO" not in plan

    def test_init_gpu_host_and_data_path_in_plan(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "foo", "--no-tmux", "--no-detect",
                 "--gpu-host", "gpu-server-01",
                 "--data-path", "gpu-server-01:/mnt/data"],
            )
        assert result.exit_code == 0, result.output
        plan = (tmp_path / "plans" / "foo.md").read_text()
        assert "gpu-server-01" in plan
        assert "/mnt/data" in plan
        # Remote data_layout inferred from host:path
        assert "data_layout: remote" in plan

    def test_init_no_tmux_avoids_tmux_guardrail(
        self, runner: click.testing.CliRunner, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even with tmux missing, --no-tmux should succeed."""
        import shutil

        original_which = shutil.which

        def fake_which(name):
            if name == "tmux":
                return None
            return original_which(name)

        monkeypatch.setattr(shutil, "which", fake_which)
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "foo", "--no-tmux", "--no-detect"],
            )
        assert result.exit_code == 0, result.output

    def test_init_conversational_default_errors_without_tmux(
        self, runner: click.testing.CliRunner, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Default conversational init must give a helpful error when tmux
        is missing rather than silently failing in the wrapper."""
        import shutil

        original_which = shutil.which

        def fake_which(name):
            if name == "tmux":
                return None
            return original_which(name)

        monkeypatch.setattr(shutil, "which", fake_which)
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(cli, ["init", "foo"])
        assert result.exit_code != 0
        assert "tmux" in result.output.lower()
        assert "--no-tmux" in result.output


# ---------------------------------------------------------------------------
# init architect prompt construction
# ---------------------------------------------------------------------------


class TestInitArchitectPrompt:
    """The prompt the Init Architect agent receives on launch."""

    def test_prompt_includes_project_name(self) -> None:
        from zo.cli import _build_init_architect_prompt

        prompt = _build_init_architect_prompt(
            project="acme-proj", hints={},
        )
        assert "acme-proj" in prompt
        assert "init-architect.md" in prompt

    def test_prompt_surfaces_non_none_hints(self) -> None:
        from zo.cli import _build_init_architect_prompt

        prompt = _build_init_architect_prompt(
            project="acme-proj",
            hints={
                "branch": "feature-branch",
                "existing_repo": "/code/acme-proj",
                "gpu_host": None,  # None should be omitted
                "base_image": None,
                "data_path": None,
                "layout_mode": "adaptive",
            },
        )
        assert "branch: feature-branch" in prompt
        assert "existing_repo: /code/acme-proj" in prompt
        assert "layout_mode: adaptive" in prompt
        # None values must NOT appear
        assert "gpu_host: None" not in prompt
        assert "base_image: None" not in prompt

    def test_prompt_reinforces_no_direct_writes(self) -> None:
        """Agent prompt must tell the architect to route writes through CLI."""
        from zo.cli import _build_init_architect_prompt

        prompt = _build_init_architect_prompt(project="foo", hints={})
        assert "--no-tmux" in prompt
        assert "single source of truth" in prompt


# ---------------------------------------------------------------------------
# init dry-run
# ---------------------------------------------------------------------------


class TestInitDryRun:
    """``--dry-run`` must produce a preview without touching the filesystem."""

    def test_dry_run_writes_nothing(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "preview-test", "--no-tmux", "--no-detect",
                 "--dry-run"],
            )
        assert result.exit_code == 0, result.output
        # No artifacts created
        assert not (tmp_path / "memory" / "preview-test").exists()
        assert not (tmp_path / "targets" / "preview-test.target.md").exists()
        assert not (tmp_path / "plans" / "preview-test.md").exists()
        # Preview output mentions dry-run
        assert "DRY RUN" in result.output.upper()

    def test_dry_run_shows_branch_and_layout(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        existing = tmp_path / "repo"
        existing.mkdir()
        (existing / ".git").mkdir()
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli,
                ["init", "acme-proj", "--no-tmux", "--no-detect", "--dry-run",
                 "--existing-repo", str(existing),
                 "--branch", "feature-branch",
                 "--layout-mode", "adaptive"],
            )
        assert result.exit_code == 0, result.output
        # Key decisions surface in the preview
        assert "feature-branch" in result.output
        assert "adaptive" in result.output
        # Still nothing written
        assert not (tmp_path / "targets" / "acme-proj.target.md").exists()

    def test_dry_run_rejected_in_conversational_mode(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """--dry-run without --no-tmux is a UsageError (conversational
        mode has its own preview flow)."""
        # Patch shutil.which so the tmux-availability guardrail (which
        # fires earlier in the same code path) doesn't preempt the
        # --dry-run rejection on hosts where tmux isn't installed.
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path), \
             patch("shutil.which", return_value="/usr/bin/tmux"):
            result = runner.invoke(
                cli, ["init", "foo", "--dry-run"],
            )
        assert result.exit_code != 0
        assert "--dry-run" in result.output
        assert "--no-tmux" in result.output


# ---------------------------------------------------------------------------
# init --reset
# ---------------------------------------------------------------------------


class TestInitReset:
    """``--reset`` must delete ZO artifacts safely and only on confirmation."""

    def _init_a_project(
        self, runner: click.testing.CliRunner, tmp_path: Path, name: str,
    ) -> None:
        """Helper: create a complete init state for *name* in tmp_path."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", name, "--no-tmux", "--no-detect"],
            )
        assert result.exit_code == 0, result.output

    def test_reset_deletes_init_artifacts(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        self._init_a_project(runner, tmp_path, "doomed")
        # Confirm artifacts exist
        assert (tmp_path / "memory" / "doomed").is_dir()
        assert (tmp_path / "targets" / "doomed.target.md").exists()
        assert (tmp_path / "plans" / "doomed.md").exists()

        # Reset with -y to skip confirmation
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "doomed", "--reset", "--yes"],
            )
        assert result.exit_code == 0, result.output

        # All artifacts gone
        assert not (tmp_path / "memory" / "doomed").exists()
        assert not (tmp_path / "targets" / "doomed.target.md").exists()
        assert not (tmp_path / "plans" / "doomed.md").exists()

    def test_reset_does_not_touch_delivery_repo(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """The delivery repo MUST survive --reset — it may contain user code."""
        zo_root = tmp_path / "zo"
        delivery = tmp_path / "delivery"
        with patch("zo.cli._zo_root", return_value=zo_root), \
             patch("zo.cli._main_repo_root", return_value=zo_root):
            runner.invoke(
                cli,
                ["init", "keep-delivery", "--no-tmux", "--no-detect",
                 "--scaffold-delivery", str(delivery)],
            )
        assert (delivery / "STRUCTURE.md").exists()
        # Put "user code" into the delivery repo
        user_file = delivery / "src" / "data" / "loader.py"
        user_file.write_text("# user code", encoding="utf-8")

        # Reset
        with patch("zo.cli._zo_root", return_value=zo_root), \
             patch("zo.cli._main_repo_root", return_value=zo_root):
            result = runner.invoke(
                cli, ["init", "keep-delivery", "--reset", "--yes"],
            )
        assert result.exit_code == 0, result.output

        # ZO artifacts gone
        assert not (zo_root / "memory" / "keep-delivery").exists()
        # Delivery repo AND user code preserved
        assert delivery.exists()
        assert user_file.exists()
        assert user_file.read_text() == "# user code"

    def test_reset_on_nonexistent_project_is_safe(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Reset on a project that doesn't exist is a no-op with
        a clear 'nothing to reset' message — not an error."""
        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "ghost", "--reset", "--yes"],
            )
        assert result.exit_code == 0
        assert "nothing to reset" in result.output.lower()

    def test_reset_refuses_when_confirmation_mismatches(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Without --yes, reset requires typing the project name."""
        self._init_a_project(runner, tmp_path, "guarded")

        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "guarded", "--reset"],
                input="wrong-name\n",
            )
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()
        # Artifacts STILL exist — confirmation protected them
        assert (tmp_path / "memory" / "guarded").exists()
        assert (tmp_path / "targets" / "guarded.target.md").exists()

    def test_reset_accepts_matching_confirmation(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        self._init_a_project(runner, tmp_path, "confirmed")

        with patch("zo.cli._zo_root", return_value=tmp_path), \
             patch("zo.cli._main_repo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["init", "confirmed", "--reset"],
                input="confirmed\n",
            )
        assert result.exit_code == 0
        assert not (tmp_path / "memory" / "confirmed").exists()
        assert not (tmp_path / "targets" / "confirmed.target.md").exists()


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

        # Force GPU compose so this test is host-independent. Auto-detect
        # behavior is covered by tests/unit/test_scaffold.py::TestPlatformAwareCompose.
        scaffold_delivery(tmp_path / "repo", "test-proj", gpu_enabled=True)

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

    def test_scaffold_gitkeep_only_in_empty_dirs(
        self, tmp_path: Path,
    ) -> None:
        """.gitkeep must not land in a dir that already has files."""
        from zo.scaffold import scaffold_delivery

        repo = tmp_path / "repo"
        repo.mkdir()
        # Simulate an existing code dir with real files
        src_data = repo / "src" / "data"
        src_data.mkdir(parents=True)
        (src_data / "loader.py").write_text("# real code", encoding="utf-8")

        scaffold_delivery(repo, "proj")

        # Real code dir gets no .gitkeep
        assert not (src_data / ".gitkeep").exists()
        assert (src_data / "loader.py").exists()
        # A freshly-created empty dir still gets .gitkeep
        assert (repo / "configs" / "data" / ".gitkeep").exists()

    def test_scaffold_adaptive_skips_src_and_data(
        self, tmp_path: Path,
    ) -> None:
        from zo.scaffold import scaffold_delivery

        repo = tmp_path / "repo"
        scaffold_delivery(repo, "proj", layout_mode="adaptive")

        # Meta-dirs still created
        assert (repo / "configs" / "data").is_dir()
        assert (repo / "experiments").is_dir()
        assert (repo / "docker").is_dir()
        assert (repo / "notebooks" / "phase").is_dir()
        assert (repo / "reports" / "figures").is_dir()
        # src/* and data/* NOT created
        assert not (repo / "src" / "data").exists()
        assert not (repo / "src" / "model").exists()
        assert not (repo / "data" / "raw").exists()
        assert not (repo / "models").exists()
        # README / pyproject / .gitignore omitted (user has own)
        assert not (repo / "README.md").exists()
        assert not (repo / "pyproject.toml").exists()
        assert not (repo / ".gitignore").exists()
        # But STRUCTURE.md and Dockerfile still written
        assert (repo / "STRUCTURE.md").exists()
        assert (repo / "docker" / "Dockerfile").exists()

    def test_scaffold_rejects_invalid_layout_mode(
        self, tmp_path: Path,
    ) -> None:
        from zo.scaffold import scaffold_delivery

        with pytest.raises(ValueError):
            scaffold_delivery(
                tmp_path / "repo", "proj", layout_mode="custom",
            )

    def test_scaffold_overlay_logs_added_vs_preserved(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Overlay logging should call out added/preserved counts."""
        from zo.scaffold import scaffold_delivery

        repo = tmp_path / "repo"
        repo.mkdir()
        # Pre-existing content in one dir
        (repo / "configs" / "data").mkdir(parents=True)
        (repo / "configs" / "data" / "dataset.yaml").write_text(
            "existing", encoding="utf-8",
        )

        scaffold_delivery(repo, "proj", overlay=True)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        # Rich prints to stdout; tolerate either stream.
        assert "Overlay applied" in combined or "overlay" in combined.lower()


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


class TestLowTokenFlags:
    """Tests for ``--low-token`` and the override flags it composes with."""

    def test_low_token_flag_accepted(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")
        result = runner.invoke(cli, ["build", str(plan_path), "--low-token"])
        assert "no such option: --low-token" not in result.output

    def test_lead_model_flag_choices(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")
        for model in ("opus", "sonnet", "haiku"):
            result = runner.invoke(
                cli, ["build", str(plan_path), "--lead-model", model],
            )
            assert "Invalid value for '--lead-model'" not in result.output

    def test_lead_model_invalid_choice_rejected(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")
        result = runner.invoke(
            cli, ["build", str(plan_path), "--lead-model", "gpt"],
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_max_iterations_accepted(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")
        result = runner.invoke(
            cli, ["build", str(plan_path), "--max-iterations", "3"],
        )
        assert "no such option: --max-iterations" not in result.output

    def test_no_headlines_flag_accepted(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        plan_path = tmp_path / "plan.md"
        plan_path.write_text("empty", encoding="utf-8")
        result = runner.invoke(
            cli, ["build", str(plan_path), "--no-headlines"],
        )
        assert "no such option: --no-headlines" not in result.output

    def test_resolve_lead_model_precedence(self) -> None:
        """CLI > plan field > preset (when low_token) > base 'opus'."""
        from zo.cli import _resolve_lead_model

        # CLI flag wins over everything.
        assert _resolve_lead_model(
            cli_lead_model="opus", plan_lead_model="haiku", low_token=True,
        ) == "opus"
        # Plan field wins when CLI not set.
        assert _resolve_lead_model(
            cli_lead_model=None, plan_lead_model="haiku", low_token=True,
        ) == "haiku"
        # Low-token preset applies when neither CLI nor plan set.
        assert _resolve_lead_model(
            cli_lead_model=None, plan_lead_model=None, low_token=True,
        ) == "sonnet"
        # Base default (opus) when nothing else applies.
        assert _resolve_lead_model(
            cli_lead_model=None, plan_lead_model=None, low_token=False,
        ) == "opus"

    def test_resolve_gate_mode_precedence(self) -> None:
        from zo.cli import _resolve_gate_mode

        # CLI flag wins.
        assert _resolve_gate_mode(
            cli_gate_mode="supervised", low_token=True,
        ) == "supervised"
        # Low-token swaps default to full-auto.
        assert _resolve_gate_mode(
            cli_gate_mode=None, low_token=True,
        ) == "full-auto"
        # Default supervised when no flags.
        assert _resolve_gate_mode(
            cli_gate_mode=None, low_token=False,
        ) == "supervised"

    def test_low_token_preset_constant_shape(self) -> None:
        """The preset has the documented keys with documented values."""
        from zo.cli import _LOW_TOKEN_PRESET

        assert _LOW_TOKEN_PRESET["lead_model"] == "sonnet"
        assert _LOW_TOKEN_PRESET["max_iterations"] == 2
        assert _LOW_TOKEN_PRESET["stop_on_tier"] == "could_pass"
        assert _LOW_TOKEN_PRESET["drop_research_scout"] is True
        assert _LOW_TOKEN_PRESET["headlines_disabled"] is True
        assert _LOW_TOKEN_PRESET["gate_mode"] == "full-auto"
        assert _LOW_TOKEN_PRESET["compact_threshold"] == "60"

    def test_banner_renders_low_token_badge(
        self, runner: click.testing.CliRunner
    ) -> None:
        """``_show_banner(low_token=True)`` includes the badge text."""
        from io import StringIO
        from rich.console import Console
        import zo.cli as cli_module

        # Redirect zo.cli.console to a buffer so we can inspect output.
        buf = StringIO()
        original = cli_module.console
        cli_module.console = Console(
            file=buf, force_terminal=True, color_system="truecolor",
            width=100, highlight=False, emoji=False,
        )
        try:
            cli_module._show_banner(project="demo", low_token=True)
        finally:
            cli_module.console = original
        out = buf.getvalue()
        assert "low-token" in out


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
        result = runner.invoke(cli, ["draft"])
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
                cli, ["draft", "--docs", str(source_dir),
                      "--project", "test-draft", "--no-tmux"]
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
# draft prompt construction
# ---------------------------------------------------------------------------


class TestBuildDraftPrompt:
    """Tests for _build_draft_prompt — the Plan Architect's prompt."""

    def test_includes_role_and_team_setup(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="test project",
            data_paths=(), zo_root=Path("/tmp"),
        )
        assert "Plan Architect" in prompt
        assert "TeamCreate" in prompt
        assert "draft-test" in prompt

    def test_data_scout_spawned_with_data_paths(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="",
            data_paths=(Path("/data/train.csv"), Path("/data/test.csv")),
            zo_root=Path("/tmp"),
        )
        assert "data-scout" in prompt
        assert "/data/train.csv" in prompt
        assert "/data/test.csv" in prompt

    def test_data_scout_not_spawned_without_data(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="a project",
            data_paths=(), zo_root=Path("/tmp"),
        )
        assert "data-scout" not in prompt
        assert "No data paths were provided" in prompt

    def test_research_scout_always_spawned(self) -> None:
        from zo.cli import _build_draft_prompt

        for data in ((), (Path("/data"),)):
            prompt = _build_draft_prompt(
                project="test", plan_path=Path("/tmp/plan.md"),
                doc_context="", description="test",
                data_paths=data, zo_root=Path("/tmp"),
            )
            assert "research-scout" in prompt

    def test_doc_context_included(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="Summary of requirements docs",
            description="", data_paths=(), zo_root=Path("/tmp"),
        )
        assert "Indexed Document Context" in prompt
        assert "Summary of requirements docs" in prompt

    def test_description_included(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="CNN for CIFAR-10",
            data_paths=(), zo_root=Path("/tmp"),
        )
        assert "CNN for CIFAR-10" in prompt

    def test_build_command_in_completion(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="my-proj", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="test",
            data_paths=(), zo_root=Path("/tmp"),
        )
        assert "zo build plans/my-proj.md" in prompt

    def test_conversation_flow_steps(self) -> None:
        from zo.cli import _build_draft_prompt

        prompt = _build_draft_prompt(
            project="test", plan_path=Path("/tmp/plan.md"),
            doc_context="", description="test",
            data_paths=(), zo_root=Path("/tmp"),
        )
        assert "objective" in prompt.lower()
        assert "oracle" in prompt.lower() or "metric" in prompt.lower()
        assert "constraint" in prompt.lower()
        assert "specs/plan.md" in prompt


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


# ---------------------------------------------------------------------------
# gates set command
# ---------------------------------------------------------------------------


class TestGatesSetCommand:
    """Tests for the ``zo gates set`` command."""

    def test_gates_set_writes_mode_file(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        # Set up minimal memory directory
        mem_root = tmp_path / "memory" / "test-project"
        mem_root.mkdir(parents=True)

        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["gates", "set", "auto", "--project", "test-project"]
            )

        assert result.exit_code == 0
        assert "Gate mode set to" in result.output

        gate_file = mem_root / "gate_mode"
        assert gate_file.exists()
        assert gate_file.read_text().strip() == "auto"

    def test_gates_set_full_auto(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        mem_root = tmp_path / "memory" / "test-project"
        mem_root.mkdir(parents=True)

        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["gates", "set", "full-auto", "--project", "test-project"]
            )

        assert result.exit_code == 0
        gate_file = mem_root / "gate_mode"
        assert gate_file.read_text().strip() == "full_auto"

    def test_gates_set_supervised(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        mem_root = tmp_path / "memory" / "test-project"
        mem_root.mkdir(parents=True)

        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["gates", "set", "supervised", "--project", "test-project"]
            )

        assert result.exit_code == 0
        gate_file = mem_root / "gate_mode"
        assert gate_file.read_text().strip() == "supervised"

    def test_gates_set_invalid_mode(
        self, runner: click.testing.CliRunner
    ) -> None:
        result = runner.invoke(
            cli, ["gates", "set", "yolo", "--project", "test-project"]
        )
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_gates_set_missing_project(
        self, runner: click.testing.CliRunner, tmp_path: Path
    ) -> None:
        with patch("zo.cli._zo_root", return_value=tmp_path):
            result = runner.invoke(
                cli, ["gates", "set", "auto", "--project", "nonexistent"]
            )

        assert result.exit_code == 1
        assert "No memory found" in result.output

    def test_gates_set_requires_project_option(
        self, runner: click.testing.CliRunner
    ) -> None:
        result = runner.invoke(cli, ["gates", "set", "auto"])
        assert result.exit_code != 0


class TestWatchTrainingPathResolution:
    """`zo watch-training` must point at the active experiment's dir.

    Regression: prior to this fix, the command hardcoded
    ``<delivery>/logs/training/`` which never matched what
    ``ZOTrainingCallback.for_experiment()`` actually writes (under
    ``.zo/experiments/<exp_id>/``). The dashboard rendered "Waiting…"
    forever even mid-training.
    """

    def _make_delivery_with_zo_dir(
        self, tmp_path: Path, project: str = "demo",
    ) -> Path:
        """Create a minimal delivery repo with .zo/config.yaml."""
        from zo.project_config import ProjectConfig, save_project_config

        delivery = tmp_path / "delivery"
        delivery.mkdir()
        save_project_config(delivery, ProjectConfig(project_name=project))
        # Plan placeholder so the parse_plan branch in watch_training
        # doesn't error (it's wrapped in try/except, but still).
        (delivery / ".zo" / "plans").mkdir(parents=True, exist_ok=True)
        return delivery

    def test_resolves_running_experiment_dir(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """A running experiment's artifacts_dir is passed to run_live_display."""
        from zo.experiments import mint_experiment

        delivery = self._make_delivery_with_zo_dir(tmp_path)
        reg_dir = delivery / ".zo" / "experiments"
        reg_dir.mkdir(parents=True)
        exp = mint_experiment(reg_dir, project="demo", phase="phase_4")

        # Stub run_live_display so the test doesn't hang on the live loop.
        with patch("zo.training_display.run_live_display") as mock_live:
            result = runner.invoke(
                cli,
                ["watch-training", "-p", "demo", "--repo", str(delivery)],
            )
        assert result.exit_code == 0, result.output
        mock_live.assert_called_once()
        log_dir = mock_live.call_args[0][0]
        assert Path(log_dir) == Path(exp.artifacts_dir)

    def test_falls_back_to_experiments_root_when_empty(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Without a registry, the dashboard renders "Waiting…" instead of
        crashing. The CLI passes the experiments root so the live display
        has somewhere to poll.
        """
        delivery = self._make_delivery_with_zo_dir(tmp_path)

        with patch("zo.training_display.run_live_display") as mock_live:
            result = runner.invoke(
                cli,
                ["watch-training", "-p", "demo", "--repo", str(delivery)],
            )
        assert result.exit_code == 0, result.output
        mock_live.assert_called_once()
        log_dir = mock_live.call_args[0][0]
        # Falls back to .zo/experiments/ root (no active experiment yet)
        assert Path(log_dir) == delivery / ".zo" / "experiments"

    def test_does_not_use_legacy_logs_training_path(
        self, runner: click.testing.CliRunner, tmp_path: Path,
    ) -> None:
        """Regression guard: the legacy ``logs/training/`` path must not
        be passed to ``run_live_display`` — that was the bug.
        """
        from zo.experiments import mint_experiment

        delivery = self._make_delivery_with_zo_dir(tmp_path)
        reg_dir = delivery / ".zo" / "experiments"
        reg_dir.mkdir(parents=True)
        mint_experiment(reg_dir, project="demo", phase="phase_4")
        # Create the legacy dir to make the regression sharper — even if
        # it exists, the resolver must prefer the experiment dir.
        (delivery / "logs" / "training").mkdir(parents=True)

        with patch("zo.training_display.run_live_display") as mock_live:
            runner.invoke(
                cli,
                ["watch-training", "-p", "demo", "--repo", str(delivery)],
            )
        log_dir = mock_live.call_args[0][0]
        assert "logs/training" not in str(log_dir)
        assert ".zo/experiments" in str(log_dir).replace("\\", "/")
