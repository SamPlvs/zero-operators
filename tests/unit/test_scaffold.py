"""Unit tests for zo.scaffold — delivery repo scaffolding."""

from __future__ import annotations

from pathlib import Path

from zo.scaffold import scaffold_delivery


class TestZoDirectory:
    """Tests for .zo/ directory support in scaffold."""

    def test_zo_directories_created(self, tmp_path: Path) -> None:
        """scaffold_delivery creates .zo/ and its subdirectories."""
        scaffold_delivery(tmp_path, "test-project")

        assert (tmp_path / ".zo").is_dir()
        assert (tmp_path / ".zo" / "memory").is_dir()
        assert (tmp_path / ".zo" / "memory" / "sessions").is_dir()
        assert (tmp_path / ".zo" / "plans").is_dir()

    def test_zo_gitignore_written(self, tmp_path: Path) -> None:
        """.zo/.gitignore is written with correct content."""
        scaffold_delivery(tmp_path, "test-project")

        gitignore = tmp_path / ".zo" / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "local.yaml" in content
        assert "memory/index.db" in content
        assert "memory/draft_index.db" in content

    def test_zo_directories_created_in_adaptive_mode(
        self, tmp_path: Path,
    ) -> None:
        """.zo/ directories are created even in adaptive layout mode."""
        scaffold_delivery(tmp_path, "test-project", layout_mode="adaptive")

        assert (tmp_path / ".zo").is_dir()
        assert (tmp_path / ".zo" / "memory").is_dir()
        assert (tmp_path / ".zo" / "memory" / "sessions").is_dir()
        assert (tmp_path / ".zo" / "plans").is_dir()

        # .zo/.gitignore should also be written in adaptive mode
        gitignore = tmp_path / ".zo" / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "local.yaml" in content
