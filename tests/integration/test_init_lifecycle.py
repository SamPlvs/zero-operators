"""End-to-end integration test for the conversational ``zo init`` lifecycle.

Exercises the full loop a real user (or the Init Architect) walks through:

    1. dry-run on a fresh project          (preview only, no writes)
    2. commit (no dry-run)                  (writes memory + target + plan + scaffold)
    3. dry-run again                         (shows existing files preserved)
    4. reset                                 (deletes ZO artifacts only)
    5. re-init with different flags          (clean fresh start)

The test simulates the production scenario the user asked about:
"existing IVL F5 repo on branch samtukra, training on a remote GPU host,
data path on that GPU host, src-layout already in place." It verifies the
agent's adaptive-mode path produces a working scaffold without polluting
the existing src/ tree.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click.testing
import pytest

from zo.cli import cli


@pytest.fixture()
def runner() -> click.testing.CliRunner:
    return click.testing.CliRunner()


@pytest.fixture()
def existing_repo(tmp_path: Path) -> Path:
    """A pre-existing local git repo with src-layout and user code."""
    repo = tmp_path / "ivl-f5-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    pkg = repo / "src" / "ivl_f5"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("__version__ = '0.1.0'\n")
    (pkg / "trainer.py").write_text(
        "def train():\n    return 'real user code'\n", encoding="utf-8",
    )
    (repo / "README.md").write_text("# IVL F5\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "ivl-f5"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    return repo


class TestInitLifecycle:
    """Full conversational-init lifecycle on a realistic existing repo."""

    def _run(
        self,
        runner: click.testing.CliRunner,
        zo_root: Path,
        *args: str,
    ) -> click.testing.Result:
        with patch("zo.cli._zo_root", return_value=zo_root), \
             patch("zo.cli._main_repo_root", return_value=zo_root):
            return runner.invoke(cli, list(args))

    def test_full_lifecycle(
        self,
        runner: click.testing.CliRunner,
        tmp_path: Path,
        existing_repo: Path,
    ) -> None:
        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        # ------------------------------------------------------------------
        # Step 1: dry-run — must not write anything
        # ------------------------------------------------------------------
        dry = self._run(
            runner, zo_root,
            "init", "ivl-f5",
            "--no-tmux", "--no-detect", "--dry-run",
            "--existing-repo", str(existing_repo),
            "--branch", "samtukra",
            "--layout-mode", "adaptive",
            "--gpu-host", "gpu-server-01",
            "--data-path", "gpu-server-01:/mnt/data/ivl/f5",
        )
        assert dry.exit_code == 0, dry.output
        assert "DRY RUN" in dry.output.upper()
        assert "samtukra" in dry.output
        assert "adaptive" in dry.output
        assert "gpu-server-01" in dry.output  # in plan Environment preview
        # ZO artifacts NOT yet on disk
        assert not (zo_root / "memory" / "ivl-f5").exists()
        assert not (zo_root / "targets" / "ivl-f5.target.md").exists()
        assert not (zo_root / "plans" / "ivl-f5.md").exists()
        # Existing repo NOT touched
        assert not (existing_repo / "configs").exists()
        assert (existing_repo / "src" / "ivl_f5" / "trainer.py").read_text() \
            == "def train():\n    return 'real user code'\n"

        # ------------------------------------------------------------------
        # Step 2: commit — re-run without --dry-run
        # ------------------------------------------------------------------
        commit = self._run(
            runner, zo_root,
            "init", "ivl-f5",
            "--no-tmux", "--no-detect",
            "--existing-repo", str(existing_repo),
            "--branch", "samtukra",
            "--layout-mode", "adaptive",
            "--gpu-host", "gpu-server-01",
            "--data-path", "gpu-server-01:/mnt/data/ivl/f5",
        )
        assert commit.exit_code == 0, commit.output

        # Memory + target + plan landed in ZO repo
        assert (zo_root / "memory" / "ivl-f5" / "STATE.md").exists()
        assert (zo_root / "memory" / "ivl-f5" / "DECISION_LOG.md").exists()
        assert (zo_root / "memory" / "ivl-f5" / "PRIORS.md").exists()
        target_text = (zo_root / "targets" / "ivl-f5.target.md").read_text()
        assert "target_branch: samtukra" in target_text
        assert str(existing_repo) in target_text
        plan_text = (zo_root / "plans" / "ivl-f5.md").read_text()
        assert "## Environment" in plan_text
        assert "gpu-server-01" in plan_text
        assert "data_layout: remote" in plan_text

        # Adaptive mode added meta-dirs only
        assert (existing_repo / "configs" / "data").is_dir()
        assert (existing_repo / "experiments").is_dir()
        assert (existing_repo / "docker" / "Dockerfile").exists()
        assert (existing_repo / "STRUCTURE.md").exists()
        # Adaptive mode preserved user code AND skipped src/* dirs
        assert (existing_repo / "src" / "ivl_f5" / "trainer.py").read_text() \
            == "def train():\n    return 'real user code'\n"
        assert not (existing_repo / "src" / "data").exists()
        assert not (existing_repo / "src" / "model").exists()
        # Adaptive mode skipped pyproject/README (user already has them)
        assert (existing_repo / "pyproject.toml").read_text().startswith(
            "[project]\nname = \"ivl-f5\""
        )

        # ------------------------------------------------------------------
        # Step 3: dry-run AGAIN — should report existing files preserved
        # ------------------------------------------------------------------
        dry2 = self._run(
            runner, zo_root,
            "init", "ivl-f5",
            "--no-tmux", "--no-detect", "--dry-run",
            "--existing-repo", str(existing_repo),
            "--branch", "samtukra",
            "--layout-mode", "adaptive",
        )
        assert dry2.exit_code == 0, dry2.output
        # Output mentions "exists" or "preserved" for the things we just wrote
        assert (
            "exists" in dry2.output.lower()
            or "preserved" in dry2.output.lower()
        )

        # ------------------------------------------------------------------
        # Step 4: reset — delete ZO artifacts, leave delivery repo alone
        # ------------------------------------------------------------------
        reset = self._run(
            runner, zo_root,
            "init", "ivl-f5", "--reset", "--yes",
        )
        assert reset.exit_code == 0, reset.output

        # ZO-side artifacts gone
        assert not (zo_root / "memory" / "ivl-f5").exists()
        assert not (zo_root / "targets" / "ivl-f5.target.md").exists()
        assert not (zo_root / "plans" / "ivl-f5.md").exists()
        # Delivery repo, user code, and the meta-dirs ZO added are ALL preserved
        # (reset never touches the delivery repo)
        assert (existing_repo / "src" / "ivl_f5" / "trainer.py").exists()
        assert (existing_repo / "configs" / "data").is_dir()
        assert (existing_repo / "STRUCTURE.md").exists()
        assert (existing_repo / "pyproject.toml").exists()

        # ------------------------------------------------------------------
        # Step 5: re-init with different flags — fresh start
        # ------------------------------------------------------------------
        reinit = self._run(
            runner, zo_root,
            "init", "ivl-f5",
            "--no-tmux", "--no-detect",
            "--existing-repo", str(existing_repo),
            "--branch", "feature/different",
            "--layout-mode", "adaptive",
        )
        assert reinit.exit_code == 0, reinit.output
        target_text2 = (zo_root / "targets" / "ivl-f5.target.md").read_text()
        # New branch landed on the second pass — confirms reset gave a true
        # blank slate (target file was rewritten, not appended-to).
        assert "target_branch: feature/different" in target_text2
        # Memory was re-initialised cleanly
        assert (zo_root / "memory" / "ivl-f5" / "STATE.md").exists()

    def test_dry_run_then_commit_match(
        self,
        runner: click.testing.CliRunner,
        tmp_path: Path,
        existing_repo: Path,
    ) -> None:
        """The directories the dry-run claims it WILL create must match
        the ones the commit run ACTUALLY creates. Catches drift between
        the preview path and the write path."""
        zo_root = tmp_path / "zo"
        zo_root.mkdir()

        dry = self._run(
            runner, zo_root,
            "init", "match-test",
            "--no-tmux", "--no-detect", "--dry-run",
            "--existing-repo", str(existing_repo),
            "--branch", "main",
            "--layout-mode", "standard",
        )
        assert dry.exit_code == 0

        # Extract the dirs the dry-run promised (lines starting with "+")
        promised_dirs = [
            line.strip().lstrip("+").strip().rstrip("/")
            for line in dry.output.splitlines()
            if line.strip().startswith("+")
            and line.strip().endswith("/")
        ]
        assert promised_dirs, "dry-run produced no '+ dir/' lines"

        # Now actually commit
        commit = self._run(
            runner, zo_root,
            "init", "match-test",
            "--no-tmux", "--no-detect",
            "--existing-repo", str(existing_repo),
            "--branch", "main",
            "--layout-mode", "standard",
        )
        assert commit.exit_code == 0

        # Every relative dir the dry-run promised should exist on disk now,
        # either under the delivery repo or under the ZO root.
        for rel in promised_dirs:
            # Promised paths are either absolute (memory/sessions, etc.)
            # or relative to delivery repo. Check both candidate roots.
            if (existing_repo / rel).exists() or (zo_root / rel).exists():
                continue
            # Also tolerate already-existing src/ dirs in the user repo
            if (existing_repo / rel).is_dir():
                continue
            pytest.fail(
                f"dry-run promised '{rel}' but commit did not create it",
            )
