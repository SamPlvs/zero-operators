"""Unit tests for zo.scaffold — delivery repo scaffolding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from zo.environment import EnvironmentInfo
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


class TestPlatformAwareCompose:
    """``docker/docker-compose.yml`` adapts to host GPU availability.

    The ``deploy.resources.reservations.devices`` block requires the
    NVIDIA Container Toolkit and is meaningless on macOS (Docker
    Desktop has no GPU passthrough) and on Linux hosts without an
    NVIDIA GPU. The scaffolder must omit it in those cases.
    """

    def _read_compose(self, root: Path) -> str:
        compose = root / "docker" / "docker-compose.yml"
        assert compose.exists(), "scaffold did not write docker-compose.yml"
        return compose.read_text(encoding="utf-8")

    def _env(self, *, gpu_count: int) -> EnvironmentInfo:
        return EnvironmentInfo(
            platform="Linux x86_64" if gpu_count else "Darwin arm64",
            python_version="3.11.9",
            docker_available=True,
            docker_compose_available=True,
            gpu_count=gpu_count,
            gpu_names=["A100"] if gpu_count else [],
            gpu_memory_gb=[40] if gpu_count else [],
            cuda_version="12.4" if gpu_count else None,
            nvidia_driver_version="535.104" if gpu_count else None,
        )

    def test_gpu_enabled_emits_deploy_block(self, tmp_path: Path) -> None:
        scaffold_delivery(tmp_path, "test-project", gpu_enabled=True)
        content = self._read_compose(tmp_path)
        assert "deploy:" in content
        assert "capabilities: [gpu]" in content
        assert "cuda" in content.lower()

    def test_gpu_disabled_omits_deploy_block(self, tmp_path: Path) -> None:
        scaffold_delivery(tmp_path, "test-project", gpu_enabled=False)
        content = self._read_compose(tmp_path)
        assert "deploy:" not in content
        assert "capabilities: [gpu]" not in content
        # CPU template uses the explicit CPU base image.
        assert "pytorch:2.4.0-cpu" in content
        # CPU template includes a comment explaining when it is used.
        assert "macOS" in content or "CPU-only" in content

    def test_auto_detect_no_gpu_emits_cpu_compose(
        self, tmp_path: Path,
    ) -> None:
        """``gpu_enabled=None`` (default) probes detect_environment."""
        with patch(
            "zo.environment.detect_environment",
            return_value=self._env(gpu_count=0),
        ):
            scaffold_delivery(tmp_path, "test-project")
        content = self._read_compose(tmp_path)
        assert "deploy:" not in content

    def test_auto_detect_gpu_present_emits_gpu_compose(
        self, tmp_path: Path,
    ) -> None:
        """When detection finds a GPU, the GPU template is used."""
        with patch(
            "zo.environment.detect_environment",
            return_value=self._env(gpu_count=1),
        ):
            scaffold_delivery(tmp_path, "test-project")
        content = self._read_compose(tmp_path)
        assert "capabilities: [gpu]" in content

    def test_detection_failure_falls_back_to_gpu_template(
        self, tmp_path: Path,
    ) -> None:
        """Detection errors must not break scaffolding.

        On a Linux build server, the safest default is the GPU
        template — emitting the CPU template would silently leave
        the model on CPU when a GPU was actually available but the
        probe failed for an unrelated reason.
        """
        with patch(
            "zo.environment.detect_environment",
            side_effect=RuntimeError("nvidia-smi missing"),
        ):
            scaffold_delivery(tmp_path, "test-project")
        content = self._read_compose(tmp_path)
        assert "capabilities: [gpu]" in content

    def test_cpu_compose_keeps_volumes_and_service_name(
        self, tmp_path: Path,
    ) -> None:
        """CPU mode must keep service name + volumes for README parity."""
        scaffold_delivery(tmp_path, "test-project", gpu_enabled=False)
        content = self._read_compose(tmp_path)
        # README quickstart references the ``gpu`` service name; keeping
        # it identical across templates avoids a per-platform README.
        assert "  gpu:" in content
        # All four volume mounts still present.
        assert "../data:/project/data" in content
        assert "../models:/project/models" in content
        assert "../reports:/project/reports" in content
        assert "../notebooks:/project/notebooks" in content
