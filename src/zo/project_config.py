"""Project config reader/writer for .zo/ directory in delivery repos.

Handles two config files:
  - `.zo/config.yaml` — portable, committed to the delivery repo
  - `.zo/local.yaml`  — machine-specific, gitignored

Module provides Pydantic models for both configs plus load/save helpers
and a backward-compatibility adapter to TargetConfig.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zo.target import TargetConfig

from pathlib import Path  # noqa: TC003 — used at runtime

import yaml
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ProjectConfig(BaseModel):
    """Portable project config -- committed to delivery repo at .zo/config.yaml.

    Attributes:
        project_name: Human-readable project identifier.
        alias: ZO platform alias (e.g. "prod-001") for logs and memory.
        workflow_mode: Pipeline flavour — classical_ml, deep_learning, or research.
        branch: Delivery repo branch agents operate on.
        agent_working_dirs: Maps agent role to its subdirectory in the repo.
        zo_only_paths: Path prefixes reserved for ZO internals (isolation blocklist).
        git_author_name: Name used in commits from ZO agents.
        git_author_email: Email used in commits from ZO agents.
        enforce_isolation: When True, writes to blocked paths halt execution.
    """

    project_name: str
    alias: str = ""
    workflow_mode: str = "classical_ml"
    branch: str = "main"
    agent_working_dirs: dict[str, str] = {}
    zo_only_paths: list[str] = [".zo/memory/", ".zo/plans/"]
    git_author_name: str = "ZO Agent"
    git_author_email: str = "zo-agent@zero-operators.dev"
    enforce_isolation: bool = True


class LocalConfig(BaseModel):
    """Machine-specific config -- gitignored at .zo/local.yaml.

    Attributes:
        data_dir: Path to the local data directory (if any).
        gpu_count: Number of available GPUs on this machine.
        gpu_names: Human-readable GPU identifiers (e.g. ["A100-80GB"]).
        cuda_version: Installed CUDA toolkit version string.
        docker_available: Whether Docker is usable on this machine.
        gate_mode: How gates are approved — supervised or autonomous.
        zo_repo_path: Back-reference to the ZO install location on this machine.
    """

    data_dir: str | None = None
    gpu_count: int = 0
    gpu_names: list[str] = []
    cuda_version: str | None = None
    docker_available: bool = False
    gate_mode: str = "supervised"
    zo_repo_path: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_zo_dir(path: Path) -> bool:
    """Check if *path* contains a .zo/config.yaml marker.

    Args:
        path: Root of the delivery repository (or any directory to probe).

    Returns:
        True when `.zo/config.yaml` exists as a regular file.
    """
    return (path / ".zo" / "config.yaml").is_file()


def load_project_config(repo: Path) -> ProjectConfig:
    """Read .zo/config.yaml from a delivery repo.

    Args:
        repo: Root of the delivery repository.

    Returns:
        Parsed ProjectConfig.

    Raises:
        FileNotFoundError: If `.zo/config.yaml` does not exist.
    """
    config_path = repo / ".zo" / "config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"Project config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    return ProjectConfig(**data)


def load_local_config(repo: Path) -> LocalConfig | None:
    """Read .zo/local.yaml from a delivery repo.

    Args:
        repo: Root of the delivery repository.

    Returns:
        Parsed LocalConfig, or None if the file does not exist (new machine).
    """
    local_path = repo / ".zo" / "local.yaml"
    if not local_path.is_file():
        return None
    data = yaml.safe_load(local_path.read_text(encoding="utf-8"))
    if data is None:
        data = {}
    return LocalConfig(**data)


def save_project_config(repo: Path, config: ProjectConfig) -> None:
    """Write .zo/config.yaml to a delivery repo.

    Creates the `.zo/` directory if it does not yet exist.

    Args:
        repo: Root of the delivery repository.
        config: ProjectConfig to persist.
    """
    zo_dir = repo / ".zo"
    zo_dir.mkdir(parents=True, exist_ok=True)
    config_path = zo_dir / "config.yaml"
    config_path.write_text(
        yaml.dump(
            config.model_dump(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def save_local_config(repo: Path, config: LocalConfig) -> None:
    """Write .zo/local.yaml to a delivery repo.

    Creates the `.zo/` directory if it does not yet exist.

    Args:
        repo: Root of the delivery repository.
        config: LocalConfig to persist.
    """
    zo_dir = repo / ".zo"
    zo_dir.mkdir(parents=True, exist_ok=True)
    local_path = zo_dir / "local.yaml"
    local_path.write_text(
        yaml.dump(
            config.model_dump(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def to_target_config(project: ProjectConfig, repo: Path) -> TargetConfig:
    """Adapter: produce a TargetConfig from ProjectConfig for backward compat.

    Maps ProjectConfig fields to TargetConfig fields so the orchestrator
    and isolation enforcer work unchanged.

    Args:
        project: Portable project configuration.
        repo: Absolute path to the delivery repository.

    Returns:
        A TargetConfig instance with fields populated from *project*.
    """
    from zo.target import TargetConfig

    return TargetConfig(
        project=project.project_name,
        target_repo=str(repo),
        target_branch=project.branch,
        worktree_base=".worktrees",
        git_author_name=project.git_author_name,
        git_author_email=project.git_author_email,
        agent_working_dirs=project.agent_working_dirs,
        zo_only_paths=project.zo_only_paths,
        enforce_isolation=project.enforce_isolation,
    )
