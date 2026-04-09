"""Unit tests for zo.target — target file parser and isolation enforcer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from zo.target import (
    IsolationViolation,
    TargetConfig,
    check_isolation,
    enforce_write,
    parse_target,
    resolve_target_repo,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_FRONTMATTER = textwrap.dedent("""\
    ---
    project: "project-alpha"
    target_repo: "../delivery/project-alpha"
    target_branch: "main"
    worktree_base: "/tmp/zo-worktrees/project-alpha"
    git_author_name: "Zero Operators Agent"
    git_author_email: "agents@zero-operators.local"
    agent_working_dirs:
      lead_orchestrator: "."
      data_engineer: "data/"
      model_builder: "src/models/"
    zo_only_paths:
      - ".claude/"
      - "CLAUDE.md"
      - "STATE.md"
      - "zero-operators/"
      - ".zo/"
      - "memory/"
      - "logs/"
    enforce_isolation: true
    ---

    # Project Alpha Target

    Additional notes can appear below the frontmatter.
""")


@pytest.fixture()
def target_file(tmp_path: Path) -> Path:
    """Write a valid target file and return its path."""
    p = tmp_path / "project-alpha.target.md"
    p.write_text(VALID_FRONTMATTER)
    return p


@pytest.fixture()
def config(target_file: Path) -> TargetConfig:
    """Parse the valid target file fixture."""
    return parse_target(target_file)


@pytest.fixture()
def delivery_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository directory."""
    repo = tmp_path / "delivery" / "project-alpha"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return repo


# ---------------------------------------------------------------------------
# parse_target
# ---------------------------------------------------------------------------


class TestParseTarget:
    """Tests for parse_target()."""

    def test_valid_parse(self, config: TargetConfig) -> None:
        """All fields are populated from a well-formed target file."""
        assert config.project == "project-alpha"
        assert config.target_repo == "../delivery/project-alpha"
        assert config.target_branch == "main"
        assert config.worktree_base == "/tmp/zo-worktrees/project-alpha"
        assert config.git_author_name == "Zero Operators Agent"
        assert config.git_author_email == "agents@zero-operators.local"
        assert "lead_orchestrator" in config.agent_working_dirs
        assert ".claude/" in config.zo_only_paths
        assert config.enforce_isolation is True

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError for a missing file."""
        with pytest.raises(FileNotFoundError):
            parse_target(tmp_path / "nonexistent.target.md")

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        """Raises ValueError when frontmatter delimiters are absent."""
        p = tmp_path / "bad.target.md"
        p.write_text("No frontmatter here.\n")
        with pytest.raises(ValueError, match="No YAML frontmatter found"):
            parse_target(p)

    def test_missing_required_field(self, tmp_path: Path) -> None:
        """Raises ValidationError when a required field is omitted."""
        incomplete = textwrap.dedent("""\
            ---
            project: "test"
            target_repo: "/some/path"
            ---
        """)
        p = tmp_path / "incomplete.target.md"
        p.write_text(incomplete)
        with pytest.raises(ValidationError):
            parse_target(p)

    def test_empty_project_rejected(self, tmp_path: Path) -> None:
        """Raises ValidationError when project is an empty string."""
        bad = textwrap.dedent("""\
            ---
            project: ""
            target_repo: "/some/path"
            target_branch: "main"
            worktree_base: "/tmp/wt"
            git_author_name: "Agent"
            git_author_email: "a@b.com"
            agent_working_dirs: {}
            zo_only_paths: []
            enforce_isolation: false
            ---
        """)
        p = tmp_path / "empty_project.target.md"
        p.write_text(bad)
        with pytest.raises(ValidationError, match="must not be empty"):
            parse_target(p)

    def test_invalid_email_rejected(self, tmp_path: Path) -> None:
        """Raises ValidationError for a malformed email."""
        bad = textwrap.dedent("""\
            ---
            project: "test"
            target_repo: "/some/path"
            target_branch: "main"
            worktree_base: "/tmp/wt"
            git_author_name: "Agent"
            git_author_email: "not-an-email"
            agent_working_dirs: {}
            zo_only_paths: []
            enforce_isolation: false
            ---
        """)
        p = tmp_path / "bad_email.target.md"
        p.write_text(bad)
        with pytest.raises(ValidationError, match="Invalid email"):
            parse_target(p)


# ---------------------------------------------------------------------------
# resolve_target_repo
# ---------------------------------------------------------------------------


class TestResolveTargetRepo:
    """Tests for resolve_target_repo()."""

    def test_relative_path_resolved(self, tmp_path: Path) -> None:
        """Relative target_repo is resolved against the provided base_dir."""
        # Create delivery repo inside tmp_path
        repo = tmp_path / "repos" / "my-project"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()

        # base_dir is a sibling directory; relative path goes ../repos/my-project
        base_dir = tmp_path / "targets"
        base_dir.mkdir()

        cfg = TargetConfig(
            project="test",
            target_repo="../repos/my-project",
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[],
            enforce_isolation=False,
        )
        resolved = resolve_target_repo(cfg, base_dir)
        assert resolved == repo.resolve()
        assert resolved.is_absolute()

    def test_absolute_path_resolved(self, delivery_repo: Path) -> None:
        """Absolute target_repo is used directly."""
        cfg = TargetConfig(
            project="test",
            target_repo=str(delivery_repo),
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[],
            enforce_isolation=False,
        )
        resolved = resolve_target_repo(cfg, Path("/ignored"))
        assert resolved == delivery_repo.resolve()

    def test_missing_repo_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when the resolved directory is absent."""
        cfg = TargetConfig(
            project="test",
            target_repo="/nonexistent/repo",
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[],
            enforce_isolation=False,
        )
        with pytest.raises(FileNotFoundError, match="Target repo not found"):
            resolve_target_repo(cfg, tmp_path)

    def test_not_a_git_repo_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when the directory has no .git marker."""
        plain_dir = tmp_path / "not-a-repo"
        plain_dir.mkdir()
        cfg = TargetConfig(
            project="test",
            target_repo=str(plain_dir),
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[],
            enforce_isolation=False,
        )
        with pytest.raises(ValueError, match="not a git repository"):
            resolve_target_repo(cfg, tmp_path)


# ---------------------------------------------------------------------------
# check_isolation
# ---------------------------------------------------------------------------


class TestCheckIsolation:
    """Tests for check_isolation()."""

    def test_blocked_paths(self, config: TargetConfig) -> None:
        """Paths matching zo_only_paths are blocked."""
        assert check_isolation(".claude/settings.json", config) is False
        assert check_isolation("CLAUDE.md", config) is False
        assert check_isolation("STATE.md", config) is False
        assert check_isolation("zero-operators/src/main.py", config) is False
        assert check_isolation(".zo/data", config) is False
        assert check_isolation("memory/project/STATE.md", config) is False
        assert check_isolation("logs/comms/2026-04-09.jsonl", config) is False

    def test_allowed_paths(self, config: TargetConfig) -> None:
        """Legitimate delivery repo paths are allowed."""
        assert check_isolation("src/models/model.py", config) is True
        assert check_isolation("data/raw/input.csv", config) is True
        assert check_isolation("README.md", config) is True
        assert check_isolation("tests/test_main.py", config) is True
        assert check_isolation("pyproject.toml", config) is True

    def test_leading_dot_slash_normalized(self, config: TargetConfig) -> None:
        """Paths with leading './' are normalized before checking."""
        assert check_isolation("./CLAUDE.md", config) is False
        assert check_isolation("./.claude/agents/lead.md", config) is False

    def test_enforce_isolation_false_allows_everything(self) -> None:
        """When enforce_isolation is False, all paths are allowed."""
        cfg = TargetConfig(
            project="test",
            target_repo="/some/repo",
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[".claude/", "STATE.md"],
            enforce_isolation=False,
        )
        assert check_isolation(".claude/settings.json", cfg) is True
        assert check_isolation("STATE.md", cfg) is True


# ---------------------------------------------------------------------------
# enforce_write
# ---------------------------------------------------------------------------


class TestEnforceWrite:
    """Tests for enforce_write()."""

    def test_allowed_write_passes(self, config: TargetConfig) -> None:
        """No exception for writes to allowed paths."""
        enforce_write("src/models/model.py", config)  # should not raise

    def test_blocked_write_raises(self, config: TargetConfig) -> None:
        """IsolationViolation raised for writes to blocked paths."""
        with pytest.raises(IsolationViolation) as exc_info:
            enforce_write(".claude/settings.json", config)
        assert exc_info.value.file_path == ".claude/settings.json"
        assert exc_info.value.matched_pattern == ".claude/"

    def test_blocked_exact_match(self, config: TargetConfig) -> None:
        """IsolationViolation raised for exact file matches."""
        with pytest.raises(IsolationViolation) as exc_info:
            enforce_write("CLAUDE.md", config)
        assert exc_info.value.matched_pattern == "CLAUDE.md"

    def test_enforce_false_allows_blocked(self) -> None:
        """No exception when enforce_isolation is False."""
        cfg = TargetConfig(
            project="test",
            target_repo="/some/repo",
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Agent",
            git_author_email="a@b.com",
            agent_working_dirs={},
            zo_only_paths=[".claude/", "STATE.md"],
            enforce_isolation=False,
        )
        enforce_write(".claude/settings.json", cfg)  # should not raise
        enforce_write("STATE.md", cfg)  # should not raise

    def test_violation_message(self, config: TargetConfig) -> None:
        """The exception message contains both the path and matched pattern."""
        with pytest.raises(IsolationViolation, match="Isolation violation"):
            enforce_write("STATE.md", config)


# ---------------------------------------------------------------------------
# TargetConfig model
# ---------------------------------------------------------------------------


class TestTargetConfigModel:
    """Tests for the TargetConfig pydantic model directly."""

    def test_minimal_valid_config(self) -> None:
        """Model accepts the minimal set of valid fields."""
        cfg = TargetConfig(
            project="minimal",
            target_repo="/repo",
            target_branch="dev",
            worktree_base="/tmp/wt",
            git_author_name="Bot",
            git_author_email="bot@test.io",
            agent_working_dirs={},
            zo_only_paths=[],
            enforce_isolation=False,
        )
        assert cfg.project == "minimal"

    def test_agent_working_dirs_mapping(self) -> None:
        """agent_working_dirs correctly stores key-value pairs."""
        cfg = TargetConfig(
            project="test",
            target_repo="/repo",
            target_branch="main",
            worktree_base="/tmp/wt",
            git_author_name="Bot",
            git_author_email="bot@test.io",
            agent_working_dirs={"lead": ".", "data": "data/"},
            zo_only_paths=[],
            enforce_isolation=True,
        )
        assert cfg.agent_working_dirs["lead"] == "."
        assert cfg.agent_working_dirs["data"] == "data/"
