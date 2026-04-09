"""Target file parser and isolation enforcer.

Parses YAML frontmatter from `targets/{project-name}.target.md` files,
resolves delivery repository paths, and enforces ZO/delivery isolation
by checking file paths against a configurable blocklist.

Module 2 of the Zero Operators platform.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator


class IsolationViolation(Exception):  # noqa: N818
    """Raised when a file write targets a path reserved for ZO internals."""

    def __init__(self, file_path: str, matched_pattern: str) -> None:
        self.file_path = file_path
        self.matched_pattern = matched_pattern
        super().__init__(
            f"Isolation violation: '{file_path}' matches blocked pattern '{matched_pattern}'"
        )


class TargetConfig(BaseModel):
    """Parsed and validated target file configuration.

    Represents the YAML frontmatter of a `.target.md` file that bridges
    the ZO repository to a delivery repository.

    Attributes:
        project: Unique identifier for this delivery project.
        target_repo: Relative or absolute path to the delivery repository.
        target_branch: Branch on which agents operate.
        worktree_base: Base path for git worktrees enabling parallel agent work.
        git_author_name: Name used in commits from ZO agents.
        git_author_email: Email used in commits from ZO agents.
        agent_working_dirs: Maps each agent role to its subdirectory.
        zo_only_paths: Path prefixes reserved for ZO internals (blocklist).
        enforce_isolation: When True, writes to blocked paths halt execution.
    """

    project: str
    target_repo: str
    target_branch: str
    worktree_base: str
    git_author_name: str
    git_author_email: str
    agent_working_dirs: dict[str, str]
    zo_only_paths: list[str]
    enforce_isolation: bool

    @field_validator("project", "target_repo", "target_branch", "worktree_base")
    @classmethod
    def must_be_nonempty(cls, v: str, info: Any) -> str:
        """Ensure critical string fields are not empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v

    @field_validator("git_author_email")
    @classmethod
    def valid_email_format(cls, v: str) -> str:
        """Basic email format validation."""
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError(f"Invalid email format: {v}")
        return v


# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _extract_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from a target file's text content.

    Args:
        text: Full text content of the `.target.md` file.

    Returns:
        Parsed YAML data as a dictionary.

    Raises:
        ValueError: If no YAML frontmatter block is found.
    """
    match = _FRONTMATTER_RE.search(text)
    if not match:
        raise ValueError("No YAML frontmatter found (expected '---' delimiters)")
    raw_yaml = match.group(1)
    data = yaml.safe_load(raw_yaml)
    if not isinstance(data, dict):
        raise ValueError("Frontmatter must be a YAML mapping, got: " + type(data).__name__)
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_target(path: Path) -> TargetConfig:
    """Parse a `.target.md` file and return a validated TargetConfig.

    Args:
        path: Filesystem path to the target file.

    Returns:
        Validated TargetConfig instance.

    Raises:
        FileNotFoundError: If the target file does not exist.
        ValueError: If frontmatter is missing or malformed.
        pydantic.ValidationError: If required fields are missing or invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Target file not found: {path}")
    text = path.read_text(encoding="utf-8")
    data = _extract_frontmatter(text)
    return TargetConfig(**data)


def resolve_target_repo(config: TargetConfig, base_dir: Path) -> Path:
    """Resolve the target_repo path to an absolute, validated directory.

    Relative paths are resolved against *base_dir* (typically the directory
    containing the target file).  The resolved path is checked for existence
    and for being a git repository (contains a `.git` directory or file).

    Args:
        config: Parsed target configuration.
        base_dir: Base directory for relative path resolution.

    Returns:
        Resolved absolute path to the delivery repository.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
        ValueError: If the resolved path is not a git repository.
    """
    repo_path = Path(config.target_repo)
    if not repo_path.is_absolute():
        repo_path = (base_dir / repo_path).resolve()
    else:
        repo_path = repo_path.resolve()

    if not repo_path.exists():
        raise FileNotFoundError(f"Target repo not found: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"Target repo is not a directory: {repo_path}")

    git_marker = repo_path / ".git"
    if not git_marker.exists():
        raise ValueError(f"Target repo is not a git repository (no .git): {repo_path}")

    return repo_path


def check_isolation(file_path: str, config: TargetConfig) -> bool:
    """Check whether a file path is allowed under the isolation policy.

    A path is **blocked** if it starts with any entry in `zo_only_paths`.
    Matching is performed on the normalized (forward-slash, no leading-slash)
    form of the path.

    Args:
        file_path: The path to check (relative to the delivery repo root).
        config: Parsed target configuration containing the blocklist.

    Returns:
        True if the path is allowed (not blocked), False if blocked.
    """
    if not config.enforce_isolation:
        return True

    normalized = _normalize_path(file_path)
    for pattern in config.zo_only_paths:
        norm_pattern = _normalize_path(pattern)
        if normalized == norm_pattern or normalized.startswith(norm_pattern):
            return False
    return True


def enforce_write(file_path: str, config: TargetConfig) -> None:
    """Enforce isolation policy before a file write.

    If *enforce_isolation* is True and the path matches the blocklist,
    raises `IsolationViolation`.  Otherwise returns silently.

    Args:
        file_path: The path to validate (relative to the delivery repo root).
        config: Parsed target configuration.

    Raises:
        IsolationViolation: If the write is blocked by the isolation policy.
    """
    if not config.enforce_isolation:
        return

    normalized = _normalize_path(file_path)
    for pattern in config.zo_only_paths:
        norm_pattern = _normalize_path(pattern)
        if normalized == norm_pattern or normalized.startswith(norm_pattern):
            raise IsolationViolation(file_path, pattern)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_path(p: str) -> str:
    """Normalize a path for consistent prefix matching.

    Strips leading/trailing whitespace, replaces backslashes with forward
    slashes, and removes a leading ``./`` or ``/`` prefix.

    Args:
        p: Raw path string.

    Returns:
        Normalized path string suitable for prefix comparison.
    """
    p = p.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.startswith("/"):
        p = p[1:]
    return p
