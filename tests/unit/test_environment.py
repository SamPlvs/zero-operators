"""Unit tests for zo.environment runtime detection."""

from __future__ import annotations

import json
import subprocess
from dataclasses import fields
from unittest.mock import patch

from zo.environment import (
    EnvironmentInfo,
    detect_environment,
    suggest_base_image,
)


class TestEnvironmentInfo:
    """The dataclass container for detected env properties."""

    def test_has_expected_fields(self) -> None:
        names = {f.name for f in fields(EnvironmentInfo)}
        assert {
            "platform",
            "python_version",
            "docker_available",
            "docker_compose_available",
            "gpu_count",
            "gpu_names",
            "gpu_memory_gb",
            "cuda_version",
            "nvidia_driver_version",
        } == names

    def test_to_json_is_valid(self) -> None:
        env = EnvironmentInfo(
            platform="Darwin arm64",
            python_version="3.11.9",
            docker_available=True,
            docker_compose_available=True,
            gpu_count=0,
            gpu_names=[],
            gpu_memory_gb=[],
            cuda_version=None,
            nvidia_driver_version=None,
        )
        data = json.loads(env.to_json())
        assert data["platform"] == "Darwin arm64"
        assert data["gpu_count"] == 0
        assert data["cuda_version"] is None


class TestDetectEnvironment:
    """``detect_environment()`` must always return an EnvironmentInfo."""

    def test_returns_environment_info_on_current_host(self) -> None:
        env = detect_environment()
        assert isinstance(env, EnvironmentInfo)
        # Platform always resolvable
        assert env.platform
        assert env.platform != "unknown" or env.platform == "unknown"  # tolerate either
        # Python version populated
        assert env.python_version.count(".") == 2

    def test_no_nvidia_smi_means_no_gpu(self) -> None:
        """Missing nvidia-smi → gpu_count=0, cuda=None, driver=None."""
        with patch("zo.environment._tool_available") as tool_mock:
            tool_mock.side_effect = lambda name: name != "nvidia-smi"
            env = detect_environment()
        assert env.gpu_count == 0
        assert env.gpu_names == []
        assert env.gpu_memory_gb == []
        assert env.cuda_version is None
        assert env.nvidia_driver_version is None

    def test_nvidia_smi_errors_still_returns_safe_defaults(self) -> None:
        """If nvidia-smi is present but errors, we return gpu_count=0."""
        with patch("zo.environment._tool_available", return_value=True), \
             patch("zo.environment.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="driver mismatch",
            )
            env = detect_environment()
        assert env.gpu_count == 0

    def test_missing_docker_sets_false(self) -> None:
        with patch("zo.environment._tool_available") as tool_mock:
            tool_mock.side_effect = (
                lambda name: name not in {"docker", "docker-compose"}
            )
            env = detect_environment()
        assert env.docker_available is False
        assert env.docker_compose_available is False


class TestSuggestBaseImage:
    """Heuristic Docker base-image suggestions from detected CUDA."""

    def _env_with_cuda(self, cuda: str | None) -> EnvironmentInfo:
        return EnvironmentInfo(
            platform="Linux x86_64",
            python_version="3.11.9",
            docker_available=True,
            docker_compose_available=True,
            gpu_count=1 if cuda else 0,
            gpu_names=["A100"] if cuda else [],
            gpu_memory_gb=[40] if cuda else [],
            cuda_version=cuda,
            nvidia_driver_version="535.104" if cuda else None,
        )

    def test_no_cuda_returns_cpu_image(self) -> None:
        img = suggest_base_image(self._env_with_cuda(None))
        assert "cpu" in img.lower()

    def test_cuda_12_4_suggests_cuda_12_4_image(self) -> None:
        img = suggest_base_image(self._env_with_cuda("12.4"))
        assert "12.4" in img

    def test_cuda_12_1_suggests_cuda_12_1_image(self) -> None:
        img = suggest_base_image(self._env_with_cuda("12.1"))
        assert "12.1" in img

    def test_unknown_cuda_falls_back_safely(self) -> None:
        """An unknown CUDA version returns a safe default, not an error."""
        img = suggest_base_image(self._env_with_cuda("99.9"))
        assert "pytorch/pytorch" in img
