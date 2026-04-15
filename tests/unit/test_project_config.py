"""Unit tests for zo.project_config — .zo/ config reader/writer."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from zo.project_config import (
    LocalConfig,
    ProjectConfig,
    has_zo_dir,
    load_local_config,
    load_project_config,
    save_local_config,
    save_project_config,
    to_target_config,
)

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


class TestProjectConfigDefaults:
    """ProjectConfig model has correct defaults."""

    def test_defaults(self) -> None:
        """All default values match the spec."""
        cfg = ProjectConfig(project_name="my-project")

        assert cfg.project_name == "my-project"
        assert cfg.alias == ""
        assert cfg.workflow_mode == "classical_ml"
        assert cfg.branch == "main"
        assert cfg.agent_working_dirs == {}
        assert cfg.zo_only_paths == [".zo/memory/", ".zo/plans/"]
        assert cfg.git_author_name == "ZO Agent"
        assert cfg.git_author_email == "zo-agent@zero-operators.dev"
        assert cfg.enforce_isolation is True


class TestLocalConfigDefaults:
    """LocalConfig model has correct defaults."""

    def test_defaults(self) -> None:
        """All default values match the spec."""
        cfg = LocalConfig()

        assert cfg.data_dir is None
        assert cfg.gpu_count == 0
        assert cfg.gpu_names == []
        assert cfg.cuda_version is None
        assert cfg.docker_available is False
        assert cfg.gate_mode == "supervised"
        assert cfg.zo_repo_path is None


# ---------------------------------------------------------------------------
# Round-trip: save then load
# ---------------------------------------------------------------------------


class TestProjectConfigRoundTrip:
    """save_project_config + load_project_config produce identical data."""

    def test_defaults_round_trip(self, tmp_path: Path) -> None:
        """A config with only defaults survives a write-then-read cycle."""
        original = ProjectConfig(project_name="round-trip")
        save_project_config(tmp_path, original)
        loaded = load_project_config(tmp_path)

        assert loaded.project_name == original.project_name
        assert loaded.alias == original.alias
        assert loaded.workflow_mode == original.workflow_mode
        assert loaded.branch == original.branch
        assert loaded.agent_working_dirs == original.agent_working_dirs
        assert loaded.zo_only_paths == original.zo_only_paths
        assert loaded.git_author_name == original.git_author_name
        assert loaded.git_author_email == original.git_author_email
        assert loaded.enforce_isolation == original.enforce_isolation

    def test_custom_agent_working_dirs_round_trip(self, tmp_path: Path) -> None:
        """Config with populated agent_working_dirs survives a write-then-read cycle."""
        original = ProjectConfig(
            project_name="agents-test",
            agent_working_dirs={
                "lead_orchestrator": ".",
                "data_engineer": "data/",
                "model_builder": "src/models/",
            },
        )
        save_project_config(tmp_path, original)
        loaded = load_project_config(tmp_path)

        assert loaded.agent_working_dirs == original.agent_working_dirs
        assert loaded.agent_working_dirs["data_engineer"] == "data/"

    def test_empty_alias_round_trip(self, tmp_path: Path) -> None:
        """Config with empty alias string round-trips correctly."""
        original = ProjectConfig(project_name="no-alias", alias="")
        save_project_config(tmp_path, original)
        loaded = load_project_config(tmp_path)

        assert loaded.alias == ""


class TestLocalConfigRoundTrip:
    """save_local_config + load_local_config produce identical data."""

    def test_full_round_trip(self, tmp_path: Path) -> None:
        """A fully populated LocalConfig survives write-then-read."""
        original = LocalConfig(
            data_dir="/data/project",
            gpu_count=4,
            gpu_names=["A100-80GB", "A100-80GB", "A100-80GB", "A100-80GB"],
            cuda_version="12.4",
            docker_available=True,
            gate_mode="autonomous",
            zo_repo_path="/opt/zero-operators",
        )
        save_local_config(tmp_path, original)
        loaded = load_local_config(tmp_path)

        assert loaded is not None
        assert loaded.data_dir == original.data_dir
        assert loaded.gpu_count == original.gpu_count
        assert loaded.gpu_names == original.gpu_names
        assert loaded.cuda_version == original.cuda_version
        assert loaded.docker_available == original.docker_available
        assert loaded.gate_mode == original.gate_mode
        assert loaded.zo_repo_path == original.zo_repo_path


# ---------------------------------------------------------------------------
# Missing file handling
# ---------------------------------------------------------------------------


class TestMissingFiles:
    """Graceful handling of absent config files."""

    def test_load_local_config_returns_none_when_missing(self, tmp_path: Path) -> None:
        """load_local_config returns None for a fresh repo without .zo/local.yaml."""
        assert load_local_config(tmp_path) is None

    def test_load_project_config_raises_when_missing(self, tmp_path: Path) -> None:
        """load_project_config raises FileNotFoundError when .zo/config.yaml is absent."""
        with pytest.raises(FileNotFoundError):
            load_project_config(tmp_path)


# ---------------------------------------------------------------------------
# has_zo_dir
# ---------------------------------------------------------------------------


class TestHasZoDir:
    """Probing for .zo/config.yaml marker."""

    def test_returns_true_when_present(self, tmp_path: Path) -> None:
        """has_zo_dir is True after saving a project config."""
        save_project_config(tmp_path, ProjectConfig(project_name="probe"))
        assert has_zo_dir(tmp_path) is True

    def test_returns_false_when_missing(self, tmp_path: Path) -> None:
        """has_zo_dir is False on a bare directory."""
        assert has_zo_dir(tmp_path) is False


# ---------------------------------------------------------------------------
# to_target_config adapter
# ---------------------------------------------------------------------------


class TestToTargetConfig:
    """Backward-compat adapter to TargetConfig."""

    def test_all_fields_mapped(self, tmp_path: Path) -> None:
        """to_target_config populates every TargetConfig field from ProjectConfig."""
        project = ProjectConfig(
            project_name="adapter-test",
            branch="develop",
            git_author_name="Test Bot",
            git_author_email="bot@test.dev",
            agent_working_dirs={"lead": ".", "data": "data/"},
            zo_only_paths=[".zo/memory/", ".zo/plans/", ".zo/state/"],
            enforce_isolation=False,
        )
        tc = to_target_config(project, tmp_path)

        assert tc.project == "adapter-test"
        assert tc.target_repo == str(tmp_path)
        assert tc.target_branch == "develop"
        assert tc.worktree_base == ".worktrees"
        assert tc.git_author_name == "Test Bot"
        assert tc.git_author_email == "bot@test.dev"
        assert tc.agent_working_dirs == {"lead": ".", "data": "data/"}
        assert tc.enforce_isolation is False

    def test_zo_only_paths_mapped(self, tmp_path: Path) -> None:
        """zo_only_paths from ProjectConfig land in TargetConfig unchanged."""
        custom_paths = [".zo/memory/", ".zo/plans/", "internal/"]
        project = ProjectConfig(
            project_name="paths-test",
            zo_only_paths=custom_paths,
        )
        tc = to_target_config(project, tmp_path)

        assert tc.zo_only_paths == custom_paths


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    """save functions create .zo/ when it does not exist."""

    def test_save_project_config_creates_zo_dir(self, tmp_path: Path) -> None:
        """Saving a project config on a bare repo root creates .zo/ automatically."""
        assert not (tmp_path / ".zo").exists()
        save_project_config(tmp_path, ProjectConfig(project_name="fresh"))
        assert (tmp_path / ".zo").is_dir()
        assert (tmp_path / ".zo" / "config.yaml").is_file()


# ---------------------------------------------------------------------------
# YAML output quality
# ---------------------------------------------------------------------------


class TestYamlOutput:
    """The persisted YAML is human-readable, not Python repr."""

    def test_yaml_is_readable(self, tmp_path: Path) -> None:
        """Saved config.yaml uses block style and contains no Python-specific tokens."""
        config = ProjectConfig(
            project_name="readable",
            agent_working_dirs={"lead": ".", "data": "data/"},
            zo_only_paths=[".zo/memory/", ".zo/plans/"],
        )
        save_project_config(tmp_path, config)

        raw = (tmp_path / ".zo" / "config.yaml").read_text(encoding="utf-8")

        # Should look like block-style YAML, not a Python dict repr
        assert "project_name: readable" in raw
        assert "{" not in raw, "YAML should use block style, not inline/flow style"
        # Verify it round-trips through plain yaml.safe_load
        data = yaml.safe_load(raw)
        assert data["project_name"] == "readable"
        assert isinstance(data["agent_working_dirs"], dict)
