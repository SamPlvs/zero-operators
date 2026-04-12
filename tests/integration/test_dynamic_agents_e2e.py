"""End-to-end integration test for dynamic agent creation.

Full pipeline: plan with custom agents → parse → decompose → verify
agent files created, roster includes them, phase assignment works,
contracts generated, prompt includes custom agents.

No Claude CLI calls — wrapper is not invoked.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from zo._orchestrator_models import GateDecision, GateMode, PhaseStatus
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import CustomAgentSpec, parse_plan
from zo.semantic import SemanticIndex
from zo.target import parse_target

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"

# Plan with custom agents — extends the fixture plan
_PLAN_WITH_CUSTOM_AGENTS = """\
---
project_name: "sensor-anomaly"
version: "1.0"
created: "2026-04-13"
last_modified: "2026-04-13"
status: active
owner: "TestEngineer"
---

## Objective

Build an anomaly detection model for industrial sensor data. The model
should flag abnormal vibration and temperature patterns that precede
equipment failure.

## Oracle Definition

**Primary metric:** F1-score
**Ground truth source:** maintenance logs with failure timestamps
**Evaluation method:** time-series aware cross-validation
**Target threshold:** > 0.85
**Evaluation frequency:** per training iteration

## Workflow Configuration

**Mode:** deep_learning

## Data Sources

### Sensor Readings

- **Location:** data/raw/sensors.parquet
- **Format:** Parquet, ~2M rows, 50 features
- **Key columns:** timestamp, sensor_id, vibration, temperature, pressure

## Domain Context and Priors

- Vibration spectral features (FFT) are the strongest predictors.
- Sensor drift requires calibration correction before modeling.
- Class imbalance expected: <2% anomaly rate.

## Agent Configuration

**Active agents:** data-engineer, model-builder, oracle-qa, test-engineer

**Custom agents:**
- signal-analyst: Sonnet — Signal processing specialist for vibration and acoustic FFT analysis, spectral feature extraction, and filtering strategies
- calibration-expert: Opus — Sensor calibration and drift correction specialist, reviews data-engineer output and advises on regime-aware features
- anomaly-researcher: Sonnet — Reviews anomaly detection literature, suggests architectures (autoencoders, isolation forests, transformers) and evaluation strategies

## Constraints

- Training must complete within 4 hours on a single GPU.
- Model must handle sensor dropout (missing channels) gracefully.
"""


def _make_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path, capture_output=True,
        env={**__import__("os").environ, "GIT_AUTHOR_NAME": "test",
             "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com"},
        check=True,
    )


def _build_e2e(tmp_path: Path) -> tuple[Orchestrator, CommsLogger, Path]:
    """Build a fully wired orchestrator from the custom-agents plan."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    _make_git_repo(project_dir)

    # Write plan with custom agents
    plan_path = project_dir / "plan.md"
    plan_path.write_text(_PLAN_WITH_CUSTOM_AGENTS, encoding="utf-8")

    # Copy target fixture (just need valid target)
    target_path = project_dir / "target.md"
    shutil.copy(FIXTURES_DIR / "target.md", target_path)

    # Create .claude/agents/ dir (simulates ZO repo structure)
    agents_dir = project_dir / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    # Add a few core agents so roster isn't empty
    for name in ["lead-orchestrator", "data-engineer", "model-builder",
                 "oracle-qa", "test-engineer"]:
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\nmodel: claude-sonnet-4-6\n"
            f"role: Core agent\ntier: launch\nteam: project\n---\n",
            encoding="utf-8",
        )

    # Create delivery repo dir (needed for artifact checks)
    target = parse_target(target_path)
    delivery_dir = Path(target.target_repo)
    delivery_dir.mkdir(parents=True, exist_ok=True)

    plan = parse_plan(plan_path)
    comms = CommsLogger(
        log_dir=project_dir / "logs" / "comms",
        project=plan.frontmatter.project_name,
        session_id="e2e-dynamic-agents",
    )
    memory = MemoryManager(
        project_dir=project_dir,
        project_name=plan.frontmatter.project_name,
    )
    memory.initialize_project()
    semantic = SemanticIndex(db_path=project_dir / "memory" / "index.db")

    orch = Orchestrator(
        plan=plan, target=target, memory=memory, comms=comms,
        semantic=semantic, zo_root=project_dir,
        gate_mode=GateMode.FULL_AUTO,
    )
    return orch, comms, project_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDynamicAgentsE2E:
    """Full end-to-end: plan → parse → decompose → verify custom agents."""

    def test_plan_parses_custom_agents(self, tmp_path: Path) -> None:
        """Step 1: plan parser extracts custom agent specs."""
        plan_path = tmp_path / "plan.md"
        plan_path.write_text(_PLAN_WITH_CUSTOM_AGENTS, encoding="utf-8")
        plan = parse_plan(plan_path)

        assert plan.agents is not None
        assert len(plan.agents.custom_agents) == 3

        names = [a.name for a in plan.agents.custom_agents]
        assert "signal-analyst" in names
        assert "calibration-expert" in names
        assert "anomaly-researcher" in names

        # Model aliases resolved
        signal = next(a for a in plan.agents.custom_agents if a.name == "signal-analyst")
        assert signal.model == "claude-sonnet-4-6"
        calibration = next(a for a in plan.agents.custom_agents if a.name == "calibration-expert")
        assert calibration.model == "claude-opus-4-6"

        # Roles captured
        assert "FFT" in signal.role
        assert "calibration" in calibration.role.lower()

    def test_decompose_creates_custom_agent_files(self, tmp_path: Path) -> None:
        """Step 2: orchestrator creates .md files in custom/ on decompose."""
        orch, comms, project_dir = _build_e2e(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()

        custom_dir = project_dir / ".claude" / "agents" / "custom"
        assert custom_dir.is_dir()

        # All 3 custom agents should have .md files
        assert (custom_dir / "signal-analyst.md").exists()
        assert (custom_dir / "calibration-expert.md").exists()
        assert (custom_dir / "anomaly-researcher.md").exists()

        # Files have valid YAML frontmatter
        content = (custom_dir / "signal-analyst.md").read_text()
        assert "name: Signal Analyst" in content
        assert "model: claude-sonnet-4-6" in content
        assert "tier: phase-in" in content
        assert "FFT" in content

        content = (custom_dir / "calibration-expert.md").read_text()
        assert "model: claude-opus-4-6" in content

    def test_custom_agents_in_active_list(self, tmp_path: Path) -> None:
        """Step 3: custom agents are added to the active agent list."""
        orch, _, _ = _build_e2e(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()

        # Custom agents should appear in phase assignments
        # Since they're not in AGENT_PHASE_MAP, they should be
        # available for ALL phases
        for phase in decomp.phases:
            agent_names = phase.assigned_agents
            assert "signal-analyst" in agent_names, (
                f"signal-analyst missing from {phase.phase_id}: {agent_names}"
            )
            assert "calibration-expert" in agent_names
            assert "anomaly-researcher" in agent_names

    def test_contracts_generated_for_custom_agents(self, tmp_path: Path) -> None:
        """Step 4: agent contracts are generated for custom agents."""
        orch, _, _ = _build_e2e(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()

        custom_contracts = [
            c for c in decomp.agent_contracts
            if c.agent_name in ("signal-analyst", "calibration-expert", "anomaly-researcher")
        ]
        # Should have contracts across multiple phases
        assert len(custom_contracts) > 0

        # Each custom agent should have at least one contract
        contract_agents = {c.agent_name for c in custom_contracts}
        assert "signal-analyst" in contract_agents
        assert "calibration-expert" in contract_agents
        assert "anomaly-researcher" in contract_agents

    def test_roster_prompt_includes_custom_agents(self, tmp_path: Path) -> None:
        """Step 5: the lead prompt roster section lists custom agents."""
        orch, _, _ = _build_e2e(tmp_path)
        orch.start_session()
        orch.decompose_plan()

        roster = orch._prompt_roster()
        assert "Core Agents" in roster
        assert "Custom Agents" in roster
        assert "signal-analyst" in roster
        assert "calibration-expert" in roster
        assert "anomaly-researcher" in roster

    def test_lead_prompt_includes_custom_contracts(self, tmp_path: Path) -> None:
        """Step 6: the full lead prompt references custom agent contracts."""
        orch, _, _ = _build_e2e(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()

        phase = decomp.phases[0]
        prompt = orch.build_lead_prompt(phase)

        # Custom agents should appear in the prompt
        assert "signal-analyst" in prompt
        assert "calibration-expert" in prompt

    def test_decisions_logged_for_custom_agents(self, tmp_path: Path) -> None:
        """Step 7: DECISION_LOG entries are created for each custom agent."""
        orch, comms, project_dir = _build_e2e(tmp_path)
        orch.start_session()
        orch.decompose_plan()

        # Read comms log
        log_dir = project_dir / "logs" / "comms"
        events = []
        for f in sorted(log_dir.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").strip().splitlines():
                if line:
                    events.append(json.loads(line))

        decision_events = [e for e in events if e.get("event_type") == "decision"]
        agent_creation_decisions = [
            e for e in decision_events
            if "custom agent" in e.get("title", "").lower()
        ]

        # Should have 3 creation decisions (one per custom agent)
        assert len(agent_creation_decisions) == 3

    def test_reuse_existing_custom_agents(self, tmp_path: Path) -> None:
        """Step 8: existing custom agents are reused, not overwritten."""
        orch, comms, project_dir = _build_e2e(tmp_path)

        # Pre-create one custom agent with different content
        custom_dir = project_dir / ".claude" / "agents" / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)
        existing = custom_dir / "signal-analyst.md"
        existing.write_text("# Existing custom agent\nDo not overwrite!", encoding="utf-8")

        orch.start_session()
        orch.decompose_plan()

        # Existing file should NOT be overwritten
        assert existing.read_text() == "# Existing custom agent\nDo not overwrite!"

        # Other two should be created
        assert (custom_dir / "calibration-expert.md").exists()
        assert (custom_dir / "anomaly-researcher.md").exists()

    def test_full_pipeline_with_phase_advancement(self, tmp_path: Path) -> None:
        """Step 9: full pipeline — decompose, advance through phase 1."""
        orch, _, project_dir = _build_e2e(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()

        phase = orch.get_current_phase()
        assert phase is not None
        assert phase.phase_id == "phase_1"

        # Custom agents should be in phase_1's assigned agents
        assert "signal-analyst" in phase.assigned_agents

        # Mark all subtasks complete
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)

        # Create required artifacts so gate passes
        delivery = Path(orch._target.target_repo)
        delivery.mkdir(parents=True, exist_ok=True)
        (delivery / "reports").mkdir(parents=True, exist_ok=True)
        (delivery / "reports" / "data_quality_report.md").write_text("ok")
        (delivery / "reports" / "figures").mkdir(parents=True, exist_ok=True)
        (delivery / "reports" / "figures" / "eda_summary.png").write_text("ok")
        (delivery / "data").mkdir(parents=True, exist_ok=True)
        (delivery / "data" / "processed").mkdir(parents=True, exist_ok=True)
        (delivery / "data" / "processed" / "train.csv").write_text("ok")
        # test_report needs tests/ dir or it writes "no tests found"
        (delivery / "tests").mkdir(parents=True, exist_ok=True)

        # Advance — should pass in full-auto mode
        ev = orch.advance_phase("phase_1")
        assert ev.decision.value in ("proceed", "hold"), f"Unexpected: {ev.decision}"
