"""Runtime environment detection for Zero Operators.

Detects host properties that ZO agents and the Init Architect need to
populate the ``## Environment`` section of a ``plan.md`` — platform,
Python version, Docker availability, GPU presence, CUDA version.

Detection is best-effort and non-fatal: missing tools return ``None``
rather than raising. Used at ``zo init`` time so the user reviews and
confirms the detected values before they land in the plan.

Typical usage::

    from zo.environment import detect_environment
    env = detect_environment()
    # {"platform": "Darwin arm64", "python_version": "3.11.9",
    #  "cuda_version": None, "gpu_count": 0, ...}
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass


@dataclass
class EnvironmentInfo:
    """Detected runtime environment properties.

    All fields are best-effort. ``None`` means the detection failed
    (tool not installed, command errored, or output unparseable).
    """

    platform: str  # e.g. "Darwin arm64", "Linux x86_64"
    python_version: str  # e.g. "3.11.9"
    docker_available: bool
    docker_compose_available: bool
    gpu_count: int  # 0 when no GPU detected
    gpu_names: list[str]  # empty when no GPU
    gpu_memory_gb: list[int]  # empty when no GPU
    cuda_version: str | None
    nvidia_driver_version: str | None

    def to_dict(self) -> dict:
        """Return a plain dict suitable for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Return pretty-printed JSON — Init Architect parses this."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def detect_environment() -> EnvironmentInfo:
    """Detect the current runtime environment.

    Safe to call in any environment — individual probes are wrapped in
    try/except and return sensible defaults on failure.

    Returns:
        ``EnvironmentInfo`` with all probe results.
    """
    gpu_count, gpu_names, gpu_memory = _detect_gpus()
    return EnvironmentInfo(
        platform=_detect_platform(),
        python_version=_detect_python_version(),
        docker_available=_tool_available("docker"),
        docker_compose_available=_docker_compose_available(),
        gpu_count=gpu_count,
        gpu_names=gpu_names,
        gpu_memory_gb=gpu_memory,
        cuda_version=_detect_cuda_version(),
        nvidia_driver_version=_detect_nvidia_driver(),
    )


def suggest_base_image(env: EnvironmentInfo) -> str:
    """Suggest a PyTorch Docker base image for the detected CUDA.

    Falls back to a CPU image when no GPU/CUDA is detected. The
    suggestion is a starting point — users can override in the plan.
    """
    if env.cuda_version is None:
        return "pytorch/pytorch:2.4.0-cpu"
    # Pick the nearest published PyTorch image for the host CUDA.
    # The list intentionally small — agents customize in plan.md if needed.
    cuda_major_minor = ".".join(env.cuda_version.split(".")[:2])
    cuda_to_image = {
        "12.4": "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime",
        "12.1": "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime",
        "11.8": "pytorch/pytorch:2.2.0-cuda11.8-cudnn8-runtime",
    }
    return cuda_to_image.get(
        cuda_major_minor,
        "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime",  # safe default
    )


# ---------------------------------------------------------------------------
# Individual probes — each is wrapped so one failure doesn't break detection.
# ---------------------------------------------------------------------------


def _detect_platform() -> str:
    """Return a short human-readable platform string."""
    try:
        return f"{platform.system()} {platform.machine()}"
    except Exception:  # noqa: BLE001
        return "unknown"


def _detect_python_version() -> str:
    """Return the active Python interpreter version (major.minor.patch)."""
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _tool_available(binary: str) -> bool:
    """Return True if *binary* is on PATH."""
    return shutil.which(binary) is not None


def _docker_compose_available() -> bool:
    """Return True if ``docker compose`` subcommand works.

    Covers both the modern ``docker compose`` (plugin) and legacy
    ``docker-compose`` (standalone binary).
    """
    if _tool_available("docker-compose"):
        return True
    if not _tool_available("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _detect_gpus() -> tuple[int, list[str], list[int]]:
    """Detect GPU count, names, and memory via nvidia-smi.

    Returns:
        ``(count, names, memory_gb)``. Empty lists / zero when no GPU.
    """
    if not _tool_available("nvidia-smi"):
        return (0, [], [])
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return (0, [], [])
        names: list[str] = []
        memory: list[int] = []
        for raw_line in result.stdout.strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            names.append(parts[0])
            try:
                # Output is in MiB; round up to GB for display.
                memory.append(int(parts[1]) // 1024)
            except ValueError:
                memory.append(0)
        return (len(names), names, memory)
    except Exception:  # noqa: BLE001
        return (0, [], [])


def _detect_cuda_version() -> str | None:
    """Return the CUDA runtime version advertised by the driver, or None."""
    if not _tool_available("nvidia-smi"):
        return None
    try:
        # The CUDA runtime version lives in the plain `nvidia-smi`
        # header, e.g. "... CUDA Version: 12.4 ..."; scrape it.
        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if "CUDA Version" in line:
                # Format: "... CUDA Version: 12.4 ..."
                parts = line.split("CUDA Version:")
                if len(parts) >= 2:
                    tail = parts[1].strip()
                    version = tail.split()[0].rstrip("|").strip()
                    return version or None
        return None
    except Exception:  # noqa: BLE001
        return None


def _detect_nvidia_driver() -> str | None:
    """Return the NVIDIA driver version string, or None if unavailable."""
    if not _tool_available("nvidia-smi"):
        return None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        return first.strip() or None
    except Exception:  # noqa: BLE001
        return None
