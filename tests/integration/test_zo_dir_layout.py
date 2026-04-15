"""Integration tests for the .zo/ project discovery layer.

Verifies that the CLI correctly detects .zo/config.yaml in delivery
repos, resolves ProjectContext from either .zo/ or legacy layout, and
produces working MemoryManager and TargetConfig instances.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from zo.cli import ProjectContext, _detect_delivery_repo, _load_project_context
from zo.project_config import ProjectConfig, has_zo_dir, save_project_config


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


def _write_config(repo: Path, project_name: str, **overrides: object) -> None:
    """Write a .zo/config.yaml to a directory."""
    config = ProjectConfig(project_name=project_name, **overrides)
    save_project_config(repo, config)


def _write_legacy_target(
    zo_root: Path, project: str, delivery: Path,
) -> None:
    """Write a legacy target file at targets/{project}.target.md."""
    targets = zo_root / "targets"
    targets.mkdir(parents=True, exist_ok=True)
    (targets / f"{project}.target.md").write_text(
        _TARGET_FRONTMATTER.format(project=project, target_repo=str(delivery)),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Tests — _detect_delivery_repo
# ---------------------------------------------------------------------------


class TestDetectDeliveryRepo:
    """Tests for _detect_delivery_repo() — probes cwd for .zo/config.yaml."""

    def test_detect_delivery_repo_finds_zo_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns path when .zo/config.yaml exists in cwd."""
        _write_config(tmp_path, "myproject")
        monkeypatch.chdir(tmp_path)

        result = _detect_delivery_repo()

        assert result is not None
        assert result == tmp_path

    def test_detect_delivery_repo_returns_none_without_zo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns None when no .zo/ directory exists."""
        monkeypatch.chdir(tmp_path)

        result = _detect_delivery_repo()

        assert result is None

    def test_detect_delivery_repo_filters_by_project_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns None when config exists but project_name does not match."""
        _write_config(tmp_path, "foo")
        monkeypatch.chdir(tmp_path)

        # Matching name
        assert _detect_delivery_repo(project_name="foo") is not None

        # Non-matching name
        assert _detect_delivery_repo(project_name="bar") is None


# ---------------------------------------------------------------------------
# Tests — _load_project_context
# ---------------------------------------------------------------------------


class TestLoadProjectContext:
    """Tests for _load_project_context() — resolves project paths."""

    def test_load_project_context_zo_dir(
        self, tmp_path: Path,
    ) -> None:
        """Returns ProjectContext with layout='zo-dir' when .zo/ exists."""
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        _write_config(delivery, "myproject")

        zo_root = tmp_path / "zo-repo"
        zo_root.mkdir()

        with patch("zo.cli._zo_root", return_value=zo_root):
            ctx = _load_project_context("myproject", delivery_repo=delivery)

        assert ctx.layout == "zo-dir"
        assert ctx.project_name == "myproject"
        assert ctx.delivery_repo == delivery
        assert ctx.plan_path == delivery / ".zo" / "plans" / "myproject.md"

    def test_load_project_context_legacy_fallback(
        self, tmp_path: Path,
    ) -> None:
        """Falls back to legacy layout when no .zo/ dir exists."""
        zo_root = tmp_path / "zo-repo"
        delivery = tmp_path / "delivery"
        delivery.mkdir()

        _write_legacy_target(zo_root, "myproject", delivery)

        with (
            patch("zo.cli._zo_root", return_value=zo_root),
            patch("zo.cli._main_repo_root", return_value=zo_root),
        ):
            ctx = _load_project_context("myproject")

        assert ctx.layout == "legacy"
        assert ctx.project_name == "myproject"
        assert ctx.plan_path == zo_root / "plans" / "myproject.md"


# ---------------------------------------------------------------------------
# Tests — ProjectContext.make_memory
# ---------------------------------------------------------------------------


class TestProjectContextMakeMemory:
    """Tests for ProjectContext.make_memory() — MemoryManager factory."""

    def test_project_context_make_memory_zo_dir(
        self, tmp_path: Path,
    ) -> None:
        """make_memory() returns MemoryManager rooted at .zo/memory/ for zo-dir layout."""
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        (delivery / ".zo" / "memory").mkdir(parents=True)

        ctx = ProjectContext(
            layout="zo-dir",
            delivery_repo=delivery,
            plan_path=delivery / ".zo" / "plans" / "proj.md",
            project_name="proj",
            zo_root=tmp_path / "zo-repo",
        )

        mm = ctx.make_memory()

        assert mm.memory_root == delivery / ".zo" / "memory"

    def test_project_context_make_memory_legacy(
        self, tmp_path: Path,
    ) -> None:
        """make_memory() returns MemoryManager at memory/{project}/ for legacy layout."""
        zo_root = tmp_path / "zo-repo"
        zo_root.mkdir()
        delivery = tmp_path / "delivery"
        delivery.mkdir()

        ctx = ProjectContext(
            layout="legacy",
            delivery_repo=delivery,
            plan_path=zo_root / "plans" / "proj.md",
            project_name="proj",
            zo_root=zo_root,
        )

        mm = ctx.make_memory()

        assert mm.memory_root == zo_root / "memory" / "proj"


# ---------------------------------------------------------------------------
# Tests — ProjectContext.make_target
# ---------------------------------------------------------------------------


class TestProjectContextMakeTarget:
    """Tests for ProjectContext.make_target() — TargetConfig factory."""

    def test_project_context_make_target_zo_dir(
        self, tmp_path: Path,
    ) -> None:
        """make_target() loads from .zo/config.yaml for zo-dir layout."""
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        _write_config(
            delivery,
            "myproject",
            branch="develop",
            agent_working_dirs={"data_engineer": "src/data/"},
            git_author_name="ZO Agent",
            git_author_email="zo@test.dev",
        )

        ctx = ProjectContext(
            layout="zo-dir",
            delivery_repo=delivery,
            plan_path=delivery / ".zo" / "plans" / "myproject.md",
            project_name="myproject",
            zo_root=tmp_path / "zo-repo",
        )

        target = ctx.make_target()

        assert target.project == "myproject"
        assert target.target_branch == "develop"
        assert target.target_repo == str(delivery)
        assert target.git_author_name == "ZO Agent"
        assert "data_engineer" in target.agent_working_dirs
