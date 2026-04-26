"""Unit tests for dynamic agent creation — plan parsing, phase assignment, and agent rendering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zo.plan import AgentConfig, CustomAgentSpec, _parse_agents


# ------------------------------------------------------------------ #
# Plan parser — custom agent parsing
# ------------------------------------------------------------------ #


class TestParseAgentsCustom:
    def test_parses_active_only(self) -> None:
        body = "**Active agents:** data-engineer, model-builder, oracle-qa\n"
        config = _parse_agents(body)
        assert config.active_agents == ["data-engineer", "model-builder", "oracle-qa"]
        assert config.custom_agents == []

    def test_parses_custom_agents(self) -> None:
        body = (
            "**Active agents:** data-engineer, model-builder\n\n"
            "**Custom agents:**\n"
            "- signal-analyst: Sonnet — Signal processing for vibration data\n"
            "- calibration-expert: Opus — Sensor calibration specialist\n"
        )
        config = _parse_agents(body)
        assert config.active_agents == ["data-engineer", "model-builder"]
        assert len(config.custom_agents) == 2
        assert config.custom_agents[0].name == "signal-analyst"
        assert config.custom_agents[0].model == "claude-sonnet-4-6"
        assert "Signal processing" in config.custom_agents[0].role
        assert config.custom_agents[1].name == "calibration-expert"
        assert config.custom_agents[1].model == "claude-opus-4-6"

    def test_parses_haiku_model(self) -> None:
        body = (
            "**Active agents:** data-engineer\n\n"
            "**Custom agents:**\n"
            "- log-formatter: Haiku — Formats structured logs\n"
        )
        config = _parse_agents(body)
        assert config.custom_agents[0].model == "claude-haiku-4-5-20251001"

    def test_empty_custom_block(self) -> None:
        body = "**Active agents:** data-engineer\n"
        config = _parse_agents(body)
        assert config.custom_agents == []

    def test_custom_with_em_dash(self) -> None:
        body = (
            "**Active agents:** data-engineer\n\n"
            "**Custom agents:**\n"
            "- nlp-expert: Sonnet \u2014 NLP specialist for text preprocessing\n"
        )
        config = _parse_agents(body)
        assert len(config.custom_agents) == 1
        assert config.custom_agents[0].name == "nlp-expert"

    def test_custom_with_en_dash(self) -> None:
        body = (
            "**Active agents:** data-engineer\n\n"
            "**Custom agents:**\n"
            "- geo-analyst: Sonnet \u2013 Geospatial data specialist\n"
        )
        config = _parse_agents(body)
        assert len(config.custom_agents) == 1


# ------------------------------------------------------------------ #
# Phase assignment — custom agents get all phases
# ------------------------------------------------------------------ #


class TestAgentsForPhaseCustom:
    def test_known_agent_filtered_by_phase(self) -> None:
        from zo.orchestrator import Orchestrator

        result = Orchestrator._agents_for_phase(
            "phase_1", ["data-engineer", "model-builder"],
        )
        assert "data-engineer" in result
        assert "model-builder" not in result  # model-builder is phase_3+

    def test_unknown_agent_available_all_phases(self) -> None:
        from zo.orchestrator import Orchestrator

        result = Orchestrator._agents_for_phase(
            "phase_1", ["data-engineer", "signal-analyst"],
        )
        assert "data-engineer" in result
        assert "signal-analyst" in result  # custom — available everywhere

    def test_custom_agent_in_late_phase(self) -> None:
        from zo.orchestrator import Orchestrator

        result = Orchestrator._agents_for_phase(
            "phase_5", ["signal-analyst", "calibration-expert"],
        )
        assert "signal-analyst" in result
        assert "calibration-expert" in result


class TestAgentsForPhaseLowToken:
    """Low-token mode drops research-scout from cross-cutting."""

    def test_low_token_drops_research_scout(self) -> None:
        from zo.orchestrator import Orchestrator

        active = ["data-engineer", "code-reviewer", "research-scout"]
        result = Orchestrator._agents_for_phase(
            "phase_1", active, low_token=True,
        )
        assert "data-engineer" in result
        assert "code-reviewer" in result  # kept — quality drift catcher
        assert "research-scout" not in result  # dropped in low-token

    def test_low_token_off_keeps_research_scout(self) -> None:
        from zo.orchestrator import Orchestrator

        active = ["data-engineer", "code-reviewer", "research-scout"]
        result = Orchestrator._agents_for_phase(
            "phase_1", active, low_token=False,
        )
        assert "research-scout" in result

    def test_low_token_preserves_non_research_scouts(self) -> None:
        from zo.orchestrator import Orchestrator

        # Custom agent named like a scout but not THE research-scout — kept.
        active = ["data-engineer", "data-scout"]
        result = Orchestrator._agents_for_phase(
            "phase_1", active, low_token=True,
        )
        assert "data-engineer" in result
        assert "data-scout" in result


# ------------------------------------------------------------------ #
# Agent rendering
# ------------------------------------------------------------------ #


class TestRenderCustomAgent:
    def test_renders_valid_markdown(self) -> None:
        from zo.orchestrator import _render_custom_agent

        spec = CustomAgentSpec(
            name="signal-analyst",
            model="claude-sonnet-4-6",
            role="Signal processing specialist for vibration and acoustic data.",
        )
        md = _render_custom_agent(spec)
        assert "---" in md
        assert "name: Signal Analyst" in md
        assert "model: claude-sonnet-4-6" in md
        assert "tier: phase-in" in md
        assert "Signal processing specialist" in md
        assert "## Coordination Rules" in md
        assert "## Validation Checklist" in md

    def test_renders_with_hyphenated_name(self) -> None:
        from zo.orchestrator import _render_custom_agent

        spec = CustomAgentSpec(name="nlp-text-expert", role="NLP expert.")
        md = _render_custom_agent(spec)
        assert "name: Nlp Text Expert" in md


# ------------------------------------------------------------------ #
# Ensure custom agents — file creation
# ------------------------------------------------------------------ #


class TestEnsureCustomAgents:
    def test_creates_custom_agent_files(self, tmp_path: Path) -> None:
        from zo.orchestrator import Orchestrator

        # Set up minimal orchestrator with mocks
        plan = MagicMock()
        plan.agents = AgentConfig(
            active_agents=["data-engineer"],
            custom_agents=[
                CustomAgentSpec(
                    name="signal-analyst",
                    model="claude-sonnet-4-6",
                    role="Signal processing specialist.",
                ),
            ],
        )
        plan.workflow = None
        plan.objective = "test"
        plan.source_path = None
        plan.constraints = ""

        comms = MagicMock()
        memory = MagicMock()
        target = MagicMock()
        semantic = MagicMock()

        orch = Orchestrator(
            plan=plan, target=target, memory=memory,
            comms=comms, semantic=semantic,
            zo_root=tmp_path, gate_mode=MagicMock(),
        )

        # Create the agents dir structure
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)

        orch._ensure_custom_agents()

        custom_dir = agents_dir / "custom"
        assert custom_dir.is_dir()
        agent_file = custom_dir / "signal-analyst.md"
        assert agent_file.exists()
        content = agent_file.read_text()
        assert "Signal Analyst" in content
        assert "Signal processing specialist" in content

        # Verify decision was logged
        comms.log_decision.assert_called_once()

    def test_skips_existing_custom_agent(self, tmp_path: Path) -> None:
        from zo.orchestrator import Orchestrator

        plan = MagicMock()
        plan.agents = AgentConfig(
            active_agents=[],
            custom_agents=[
                CustomAgentSpec(name="signal-analyst", role="existing"),
            ],
        )
        plan.objective = "test"
        plan.source_path = None
        plan.constraints = ""

        comms = MagicMock()
        orch = Orchestrator(
            plan=plan, target=MagicMock(), memory=MagicMock(),
            comms=comms, semantic=MagicMock(),
            zo_root=tmp_path, gate_mode=MagicMock(),
        )

        # Pre-create the file
        custom_dir = tmp_path / ".claude" / "agents" / "custom"
        custom_dir.mkdir(parents=True)
        (custom_dir / "signal-analyst.md").write_text("existing content")

        orch._ensure_custom_agents()

        # Should NOT overwrite — should log reuse instead
        comms.log_decision.assert_not_called()
        comms.log_checkpoint.assert_called_once()
        assert (custom_dir / "signal-analyst.md").read_text() == "existing content"

    def test_no_custom_agents_is_noop(self, tmp_path: Path) -> None:
        from zo.orchestrator import Orchestrator

        plan = MagicMock()
        plan.agents = AgentConfig(active_agents=["data-engineer"])
        plan.objective = "test"
        plan.source_path = None
        plan.constraints = ""

        comms = MagicMock()
        orch = Orchestrator(
            plan=plan, target=MagicMock(), memory=MagicMock(),
            comms=comms, semantic=MagicMock(),
            zo_root=tmp_path, gate_mode=MagicMock(),
        )

        orch._ensure_custom_agents()
        comms.log_decision.assert_not_called()


# ------------------------------------------------------------------ #
# Prompt roster — includes custom agents
# ------------------------------------------------------------------ #


class TestPromptRosterCustom:
    def test_roster_includes_custom_agents(self, tmp_path: Path) -> None:
        from zo.orchestrator import Orchestrator

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "data-engineer.md").write_text("core agent")

        custom_dir = agents_dir / "custom"
        custom_dir.mkdir()
        (custom_dir / "signal-analyst.md").write_text("custom agent")
        (custom_dir / "README.md").write_text("readme")

        plan = MagicMock()
        plan.agents = None
        plan.objective = "test"
        plan.source_path = None
        plan.constraints = ""
        orch = Orchestrator(
            plan=plan, target=MagicMock(), memory=MagicMock(),
            comms=MagicMock(), semantic=MagicMock(),
            zo_root=tmp_path, gate_mode=MagicMock(),
        )

        roster = orch._prompt_roster()
        assert "data-engineer" in roster
        assert "signal-analyst" in roster
        assert "Custom Agents" in roster
        # README should be excluded
        assert "readme" not in roster.lower().split("custom agents")[1].split("create")[0]

    def test_roster_no_custom_dir(self, tmp_path: Path) -> None:
        from zo.orchestrator import Orchestrator

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "data-engineer.md").write_text("core agent")

        plan = MagicMock()
        plan.agents = None
        plan.objective = "test"
        plan.source_path = None
        plan.constraints = ""
        orch = Orchestrator(
            plan=plan, target=MagicMock(), memory=MagicMock(),
            comms=MagicMock(), semantic=MagicMock(),
            zo_root=tmp_path, gate_mode=MagicMock(),
        )

        roster = orch._prompt_roster()
        assert "data-engineer" in roster
        assert "Custom Agents" not in roster
