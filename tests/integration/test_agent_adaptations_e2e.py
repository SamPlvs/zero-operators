"""End-to-end integration test for per-project agent adaptations.

Full pipeline: plan with adaptations + custom agents → parse → decompose →
verify adaptations flow into the lead prompt and agent contracts.

Confirms the dynamic-agents feature (PR #28) and the agent-adaptations
feature coexist — a project can simultaneously add new roles (custom
agents) AND adapt existing ones (adaptations) without either stepping
on the other.

No Claude CLI calls — wrapper is not invoked.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from zo._orchestrator_models import GateMode
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import parse_plan
from zo.semantic import SemanticIndex
from zo.target import parse_target

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"

# A realistic plan: IVL-F5-flavoured project with custom agents AND
# adaptations. Exercises both features simultaneously.
_PLAN = """\
---
project_name: "ivl-f5-like"
version: "1.0"
created: "2026-04-13"
last_modified: "2026-04-13"
status: active
owner: "Tester"
---

## Objective

Predict bearing failure from vibration sensor data, with domain-aware
explainability and domain-evaluation tailored to rotating machinery
failure modes.

## Oracle Definition

**Primary metric:** F1-score (weighted)
**Ground truth source:** maintenance logs with failure timestamps
**Evaluation method:** time-series cross-validation (leave-one-machine-out)
**Target threshold:** > 0.85
**Evaluation frequency:** per training iteration

## Workflow Configuration

**Mode:** deep_learning

## Data Sources

### Sensor readings

- **Location:** data/raw/vibration.parquet
- **Format:** Parquet, ~3M rows, 3-axis accelerometer + tacho
- **Sampling:** 20kHz windows of 2048 samples

## Domain Context and Priors

Rotating machinery vibration signatures. Bearing defects show up as
characteristic frequencies (BPFO, BPFI, BSF, FTF) modulated by shaft
speed. Envelope demodulation is the canonical technique for surfacing
bearing fault frequencies.

## Agent Configuration

**Active agents:** lead-orchestrator, data-engineer, model-builder, oracle-qa, test-engineer, xai-agent, domain-evaluator

**Custom agents:**
- signal-analyst: Sonnet — Signal processing specialist for rotating-machinery vibration data (FFT, envelope demodulation, order tracking)
- failure-mode-expert: Opus — Failure-mode reviewer for bearing/gear faults, cross-checks model predictions against known failure signatures

**Agent adaptations:**

- xai-agent:
  Focus on frequency-domain attribution (FFT/cepstrum), spectrogram
  visualisation, envelope-demodulation plots of high-attribution windows,
  and vibration-mode decomposition. Include per-failure-mode saliency
  breakdowns in the Phase 5 analysis report. Generic SHAP/GradCAM is
  less relevant for time-series vibration data.

- domain-evaluator:
  Apply rotating-machinery priors: bearing defect frequencies (BPFO,
  BPFI, BSF, FTF) modulated by shaft speed, typical modal frequency
  ranges (20-2000Hz for housing-mounted accelerometers), envelope
  demodulation for surfacing bearing fault frequencies. Flag any
  prediction whose attributed frequency band contradicts the machine
  nameplate spec.

- signal-analyst:
  Project scope — 3-axis accelerometer data at 20kHz, 2048-sample
  windows, bearings operating at 1800-3600 RPM. Provide FFT magnitude
  + phase, envelope spectra, and STFT spectrograms.

## Constraints

- GPU training, 4-hour budget.
- Model must handle sensor channel dropout gracefully.
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


def _build_orchestrator(tmp_path: Path) -> Orchestrator:
    """Fully wired orchestrator for the vibration project."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    _make_git_repo(project_dir)

    plan_path = project_dir / "plan.md"
    plan_path.write_text(_PLAN, encoding="utf-8")

    target_path = project_dir / "target.md"
    shutil.copy(FIXTURES_DIR / "target.md", target_path)

    agents_dir = project_dir / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    for name in ["lead-orchestrator", "data-engineer", "model-builder",
                 "oracle-qa", "test-engineer", "xai-agent", "domain-evaluator"]:
        (agents_dir / f"{name}.md").write_text(
            f"---\nname: {name}\nmodel: claude-sonnet-4-6\n"
            f"role: Core agent\ntier: launch\nteam: project\n---\n"
            f"Base instructions for {name}.\n",
            encoding="utf-8",
        )

    target = parse_target(target_path)
    delivery_dir = Path(target.target_repo)
    delivery_dir.mkdir(parents=True, exist_ok=True)

    plan = parse_plan(plan_path)
    comms = CommsLogger(
        log_dir=project_dir / "logs" / "comms",
        project=plan.frontmatter.project_name,
        session_id="e2e-adaptations",
    )
    memory = MemoryManager(
        project_dir=project_dir,
        project_name=plan.frontmatter.project_name,
    )
    memory.initialize_project()
    semantic = SemanticIndex(db_path=project_dir / "memory" / "index.db")

    return Orchestrator(
        plan=plan, target=target, memory=memory, comms=comms,
        semantic=semantic, zo_root=project_dir,
        gate_mode=GateMode.FULL_AUTO,
    )


class TestAgentAdaptationsE2E:
    """Adaptations + custom agents end-to-end on a realistic plan."""

    def test_plan_parses_both_custom_and_adaptations(
        self, tmp_path: Path,
    ) -> None:
        orch = _build_orchestrator(tmp_path)
        assert orch._plan.agents is not None
        # Custom agents (2)
        assert len(orch._plan.agents.custom_agents) == 2
        custom_names = [a.name for a in orch._plan.agents.custom_agents]
        assert "signal-analyst" in custom_names
        assert "failure-mode-expert" in custom_names
        # Adaptations (3 — two core + one custom)
        assert len(orch._plan.agents.adaptations) == 3
        adapt_names = [a.agent_name for a in orch._plan.agents.adaptations]
        assert "xai-agent" in adapt_names
        assert "domain-evaluator" in adapt_names
        assert "signal-analyst" in adapt_names

    def test_decompose_creates_custom_agent_files(
        self, tmp_path: Path,
    ) -> None:
        """Dynamic agents feature still works — plan-declared custom
        agents get `.md` files created."""
        orch = _build_orchestrator(tmp_path)
        orch.decompose_plan()
        custom_dir = orch._zo_root / ".claude" / "agents" / "custom"
        assert (custom_dir / "signal-analyst.md").exists()
        assert (custom_dir / "failure-mode-expert.md").exists()

    def test_phase_5_lead_prompt_embeds_adaptations(
        self, tmp_path: Path,
    ) -> None:
        """Phase 5 lead prompt surfaces xai-agent + domain-evaluator
        adaptations (Phase 5 is where explainability + domain review
        happen in the deep_learning workflow)."""
        orch = _build_orchestrator(tmp_path)
        decomp = orch.decompose_plan()
        phase_5 = next(p for p in decomp.phases if p.phase_id == "phase_5")
        prompt = orch.build_lead_prompt(phase_5)

        # Dedicated top-level section
        assert "# Per-project Agent Adaptations" in prompt
        # Both adapted core agents surfaced
        assert "## xai-agent" in prompt
        assert "## domain-evaluator" in prompt
        # Domain priors flowed in verbatim. Check word-by-word since the
        # adaptation body is a reflowed paragraph — words may be split
        # across line boundaries in the source plan.
        assert "BPFO" in prompt
        assert "envelope" in prompt
        assert "demodulation" in prompt

    def test_phase_1_contracts_include_adaptation_for_active_agents(
        self, tmp_path: Path,
    ) -> None:
        """Contracts in Phase 1 for agents with adaptations show the
        adaptation inline, so the Lead has it adjacent to the contract."""
        orch = _build_orchestrator(tmp_path)
        decomp = orch.decompose_plan()
        phase_1 = next(p for p in decomp.phases if p.phase_id == "phase_1")
        contracts_text = orch._prompt_contracts(phase_1)

        # domain-evaluator is active on phase_1 per AGENT_PHASE_MAP
        # and has an adaptation — should show inline
        if "domain-evaluator" in phase_1.assigned_agents:
            assert "Project-specific adaptation" in contracts_text
            assert "bearing defect frequencies" in contracts_text

    def test_custom_agent_adaptation_flows_through(
        self, tmp_path: Path,
    ) -> None:
        """Adaptations work for custom agents too — not just core ones."""
        orch = _build_orchestrator(tmp_path)
        decomp = orch.decompose_plan()
        # Custom agents are available in all phases; pick phase_1
        phase_1 = next(p for p in decomp.phases if p.phase_id == "phase_1")
        prompt = orch.build_lead_prompt(phase_1)

        # signal-analyst adaptation surfaces in the Adaptations section
        assert "## signal-analyst" in prompt
        assert "20kHz" in prompt
        assert "2048-sample" in prompt

    def test_plan_architect_protocol_mentions_adaptations(self) -> None:
        """The Plan Architect agent definition tells the architect to
        propose adaptations — so drafts actually populate this section."""
        protocol = (
            Path(__file__).resolve().parents[2]
            / ".claude" / "agents" / "plan-architect.md"
        ).read_text(encoding="utf-8")
        assert "Agent adaptations:" in protocol
        assert "xai-agent" in protocol
        assert "domain-evaluator" in protocol

    def test_lead_orchestrator_protocol_uses_adaptations(self) -> None:
        """The Lead Orchestrator definition instructs the Lead to apply
        adaptations when spawning agents."""
        protocol = (
            Path(__file__).resolve().parents[2]
            / ".claude" / "agents" / "lead-orchestrator.md"
        ).read_text(encoding="utf-8")
        assert "Per-project Agent Adaptations" in protocol
        assert "spawn prompt" in protocol.lower()
