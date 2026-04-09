"""Unit tests for the orchestrator (zo.orchestrator).

Uses the test fixture at tests/fixtures/test-project/plan.md for
happy-path tests, plus synthetic plans for edge cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zo._orchestrator_models import (
    AgentContract,
    GateDecision,
    GateType,
    PhaseDefinition,
    PhaseStatus,
    WorkflowDecomposition,
)
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import Plan, WorkflowMode, parse_plan
from zo.semantic import SemanticIndex
from zo.target import TargetConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PLAN = REPO_ROOT / "tests" / "fixtures" / "test-project" / "plan.md"


def _make_target() -> TargetConfig:
    """Create a minimal TargetConfig for testing."""
    return TargetConfig(
        project="test-project",
        target_repo="/tmp/fake-repo",
        target_branch="main",
        worktree_base="/tmp/worktrees",
        git_author_name="ZO Test",
        git_author_email="zo@test.dev",
        agent_working_dirs={},
        zo_only_paths=[".zo/"],
        enforce_isolation=False,
    )


@pytest.fixture()
def plan() -> Plan:
    """Parsed plan from the test fixture."""
    assert FIXTURE_PLAN.exists(), f"Fixture not found: {FIXTURE_PLAN}"
    return parse_plan(FIXTURE_PLAN)


@pytest.fixture()
def orchestrator(plan: Plan, tmp_path: Path) -> Orchestrator:
    """Fully wired Orchestrator with temp directories."""
    target = _make_target()
    memory = MemoryManager(
        project_dir=tmp_path, project_name="test-project",
    )
    memory.initialize_project()
    comms = CommsLogger(
        log_dir=tmp_path / "logs" / "comms",
        project="test-project",
        session_id="test-session-001",
    )
    semantic = SemanticIndex(db_path=tmp_path / "index.db")

    # Use the repo root as zo_root so agent roster discovery works
    return Orchestrator(
        plan=plan,
        target=target,
        memory=memory,
        comms=comms,
        semantic=semantic,
        zo_root=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# decompose_plan — all 3 workflow modes
# ---------------------------------------------------------------------------


class TestDecomposePlan:
    """Tests for Orchestrator.decompose_plan()."""

    def test_classical_ml_phases(self, orchestrator: Orchestrator) -> None:
        """classical_ml mode produces 6 phases (phase_1 through phase_6)."""
        decomp = orchestrator.decompose_plan()
        assert isinstance(decomp, WorkflowDecomposition)
        assert decomp.mode == WorkflowMode.CLASSICAL_ML
        assert len(decomp.phases) == 6
        ids = [p.phase_id for p in decomp.phases]
        assert ids == [f"phase_{i}" for i in range(1, 7)]

    def test_deep_learning_phases(
        self, plan: Plan, tmp_path: Path,
    ) -> None:
        """deep_learning mode produces 6 phases with DL-specific names."""
        plan.workflow.mode = WorkflowMode.DEEP_LEARNING  # type: ignore[union-attr]
        orch = _make_orchestrator(plan, tmp_path)
        decomp = orch.decompose_plan()
        assert decomp.mode == WorkflowMode.DEEP_LEARNING
        assert len(decomp.phases) == 6
        assert "Input Representation" in decomp.phases[1].name
        assert "Deep Learning" in decomp.phases[2].name

    def test_research_phases(
        self, plan: Plan, tmp_path: Path,
    ) -> None:
        """research mode adds phase_0 for literature review (7 total)."""
        plan.workflow.mode = WorkflowMode.RESEARCH  # type: ignore[union-attr]
        orch = _make_orchestrator(plan, tmp_path)
        decomp = orch.decompose_plan()
        assert decomp.mode == WorkflowMode.RESEARCH
        assert len(decomp.phases) == 7
        assert decomp.phases[0].phase_id == "phase_0"
        assert "Literature" in decomp.phases[0].name
        # phase_1 depends on phase_0
        assert "phase_0" in decomp.phases[1].depends_on

    def test_agents_assigned_to_phases(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Active agents are assigned to their relevant phases."""
        decomp = orchestrator.decompose_plan()
        # data-engineer should be in phase_1 and phase_2
        phase_1 = decomp.phases[0]
        assert "data-engineer" in phase_1.assigned_agents

    def test_contracts_generated(self, orchestrator: Orchestrator) -> None:
        """Contracts are generated for every agent-phase pair."""
        decomp = orchestrator.decompose_plan()
        assert len(decomp.agent_contracts) > 0
        for c in decomp.agent_contracts:
            assert isinstance(c, AgentContract)
            assert c.agent_name
            assert c.phase_id


# ---------------------------------------------------------------------------
# generate_agent_contract
# ---------------------------------------------------------------------------


class TestGenerateAgentContract:
    """Tests for Orchestrator.generate_agent_contract()."""

    def test_contract_structure(self, orchestrator: Orchestrator) -> None:
        """Generated contract has all required fields populated."""
        phase = PhaseDefinition(
            phase_id="phase_1",
            name="Test Phase",
            description="Testing",
            subtasks=["task1"],
            gate_type=GateType.AUTOMATED,
        )
        contract = orchestrator.generate_agent_contract("data-engineer", phase)
        assert contract.agent_name == "data-engineer"
        assert contract.phase_id == "phase_1"
        assert contract.role_description
        assert len(contract.ownership) > 0
        assert len(contract.validation_checklist) > 0
        assert len(contract.coordination_rules) > 0

    def test_unknown_agent_gets_default(
        self, orchestrator: Orchestrator,
    ) -> None:
        """An unrecognised agent name still produces a valid contract."""
        phase = PhaseDefinition(
            phase_id="phase_1",
            name="Test",
            description="Test",
            subtasks=[],
            gate_type=GateType.AUTOMATED,
        )
        contract = orchestrator.generate_agent_contract("custom-agent", phase)
        assert contract.agent_name == "custom-agent"
        assert "custom-agent" in contract.role_description


# ---------------------------------------------------------------------------
# build_lead_prompt
# ---------------------------------------------------------------------------


class TestBuildLeadPrompt:
    """Tests for Orchestrator.build_lead_prompt()."""

    def test_includes_required_sections(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt includes all 9 required sections."""
        decomp = orchestrator.decompose_plan()
        prompt = orchestrator.build_lead_prompt(decomp.phases[0])

        assert "# Role" in prompt
        assert "# Plan Context" in prompt
        assert "# Current Phase" in prompt
        assert "# Agent Roster" in prompt
        assert "# Memory Context" in prompt
        assert "# Coordination Instructions" in prompt
        assert "# Gate Criteria" in prompt
        assert "# Constraints" in prompt

    def test_includes_project_name(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt contains the project name from plan frontmatter."""
        decomp = orchestrator.decompose_plan()
        prompt = orchestrator.build_lead_prompt(decomp.phases[0])
        assert "churn-prediction" in prompt

    def test_includes_phase_info(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt contains the current phase name and subtasks."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]
        prompt = orchestrator.build_lead_prompt(phase)
        assert phase.name in prompt
        assert phase.phase_id in prompt
        for subtask in phase.subtasks[:3]:
            assert subtask in prompt

    def test_includes_agent_roster(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt lists available agents from .claude/agents/."""
        decomp = orchestrator.decompose_plan()
        prompt = orchestrator.build_lead_prompt(decomp.phases[0])
        assert "data-engineer" in prompt
        assert "model-builder" in prompt

    def test_includes_coordination_instructions(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt includes TeamCreate and SendMessage instructions."""
        decomp = orchestrator.decompose_plan()
        prompt = orchestrator.build_lead_prompt(decomp.phases[0])
        assert "TeamCreate" in prompt
        assert "SendMessage" in prompt

    def test_includes_oracle_info(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Prompt includes oracle metric and threshold."""
        decomp = orchestrator.decompose_plan()
        prompt = orchestrator.build_lead_prompt(decomp.phases[0])
        assert "ROC-AUC" in prompt


# ---------------------------------------------------------------------------
# start_session — fresh vs recovered
# ---------------------------------------------------------------------------


class TestStartSession:
    """Tests for session lifecycle."""

    def test_fresh_session(self, orchestrator: Orchestrator) -> None:
        """Fresh session starts in BUILD mode at init phase."""
        state = orchestrator.start_session()
        assert state.mode == "build"
        assert state.phase == "init"

    def test_recovered_session(
        self, plan: Plan, tmp_path: Path,
    ) -> None:
        """Recovered session continues from previous state."""
        orch = _make_orchestrator(plan, tmp_path)
        # Write a non-init state first
        from zo._memory_models import SessionState

        prior_state = SessionState(phase="phase_2", mode="continue")
        orch._memory.write_state(prior_state)

        state = orch.start_session()
        assert state.mode == "continue"
        assert state.phase == "phase_2"


# ---------------------------------------------------------------------------
# advance_phase — automated and blocking gates
# ---------------------------------------------------------------------------


class TestAdvancePhase:
    """Tests for Orchestrator.advance_phase()."""

    def test_automated_gate_pass(self, orchestrator: Orchestrator) -> None:
        """Automated gate with all subtasks done -> PROCEED."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]  # phase_1, automated gate
        # Complete all subtasks
        for subtask in phase.subtasks:
            orchestrator.mark_subtask_complete(phase.phase_id, subtask)

        result = orchestrator.advance_phase(phase.phase_id)
        assert result.decision == GateDecision.PROCEED
        assert result.requires_human is False
        assert phase.status == PhaseStatus.COMPLETED

    def test_automated_gate_fail(self, orchestrator: Orchestrator) -> None:
        """Automated gate with incomplete subtasks -> ITERATE."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]
        # Complete only first subtask
        orchestrator.mark_subtask_complete(phase.phase_id, phase.subtasks[0])

        result = orchestrator.advance_phase(phase.phase_id)
        assert result.decision == GateDecision.ITERATE
        assert result.requires_human is False

    def test_blocking_gate_returns_hold(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Blocking gate always returns HOLD, even when subtasks complete."""
        decomp = orchestrator.decompose_plan()
        # phase_2 is a blocking gate
        phase_2 = decomp.phases[1]
        for subtask in phase_2.subtasks:
            orchestrator.mark_subtask_complete(phase_2.phase_id, subtask)

        result = orchestrator.advance_phase(phase_2.phase_id)
        assert result.decision == GateDecision.HOLD
        assert result.requires_human is True
        assert phase_2.status == PhaseStatus.GATED


# ---------------------------------------------------------------------------
# mark_subtask_complete
# ---------------------------------------------------------------------------


class TestMarkSubtaskComplete:
    """Tests for Orchestrator.mark_subtask_complete()."""

    def test_marks_subtask(self, orchestrator: Orchestrator) -> None:
        """Subtask is added to completed list."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]
        orchestrator.mark_subtask_complete(phase.phase_id, phase.subtasks[0])
        assert phase.subtasks[0] in phase.completed_subtasks

    def test_idempotent(self, orchestrator: Orchestrator) -> None:
        """Marking the same subtask twice doesn't duplicate."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]
        orchestrator.mark_subtask_complete(phase.phase_id, phase.subtasks[0])
        orchestrator.mark_subtask_complete(phase.phase_id, phase.subtasks[0])
        assert phase.completed_subtasks.count(phase.subtasks[0]) == 1

    def test_invalid_subtask_raises(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Unknown subtask name raises ValueError."""
        orchestrator.decompose_plan()
        with pytest.raises(ValueError, match="not found"):
            orchestrator.mark_subtask_complete("phase_1", "nonexistent-task")


# ---------------------------------------------------------------------------
# check_plan_edited
# ---------------------------------------------------------------------------


class TestCheckPlanEdited:
    """Tests for Orchestrator.check_plan_edited()."""

    def test_unchanged(self, orchestrator: Orchestrator) -> None:
        """Returns False when plan hasn't changed."""
        assert orchestrator.check_plan_edited() is False

    def test_detects_change(
        self, orchestrator: Orchestrator, tmp_path: Path,
    ) -> None:
        """Returns True when plan source file is modified."""
        # Mutate the objective to change the hash
        orchestrator._plan.objective = "COMPLETELY NEW OBJECTIVE"
        orchestrator._plan.source_path = None  # force fallback to objective
        assert orchestrator.check_plan_edited() is True


# ---------------------------------------------------------------------------
# get_current_phase — dependency respect
# ---------------------------------------------------------------------------


class TestGetCurrentPhase:
    """Tests for Orchestrator.get_current_phase()."""

    def test_returns_first_pending(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Returns the first phase with met dependencies."""
        orchestrator.decompose_plan()
        phase = orchestrator.get_current_phase()
        assert phase is not None
        assert phase.phase_id == "phase_1"

    def test_skips_blocked_dependency(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Does not return phase_2 until phase_1 is completed."""
        orchestrator.decompose_plan()
        # phase_2 depends on phase_1 which is still PENDING
        # So get_current_phase should return phase_1, not phase_2
        phase = orchestrator.get_current_phase()
        assert phase is not None
        assert phase.phase_id == "phase_1"

    def test_advances_after_completion(
        self, orchestrator: Orchestrator,
    ) -> None:
        """After completing phase_1, get_current_phase returns phase_2."""
        decomp = orchestrator.decompose_plan()
        decomp.phases[0].status = PhaseStatus.COMPLETED
        phase = orchestrator.get_current_phase()
        assert phase is not None
        assert phase.phase_id == "phase_2"

    def test_returns_none_when_all_done(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Returns None when all phases are completed."""
        decomp = orchestrator.decompose_plan()
        for p in decomp.phases:
            p.status = PhaseStatus.COMPLETED
        assert orchestrator.get_current_phase() is None

    def test_returns_none_without_decomposition(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Returns None when workflow hasn't been decomposed."""
        assert orchestrator.get_current_phase() is None


# ---------------------------------------------------------------------------
# Phase status transitions
# ---------------------------------------------------------------------------


class TestPhaseStatusTransitions:
    """Tests for phase status management."""

    def test_initial_status_is_pending(
        self, orchestrator: Orchestrator,
    ) -> None:
        """All phases start as PENDING."""
        decomp = orchestrator.decompose_plan()
        for phase in decomp.phases:
            assert phase.status == PhaseStatus.PENDING

    def test_automated_gate_sets_completed(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Passing an automated gate sets status to COMPLETED."""
        decomp = orchestrator.decompose_plan()
        phase = decomp.phases[0]
        for s in phase.subtasks:
            orchestrator.mark_subtask_complete(phase.phase_id, s)
        orchestrator.advance_phase(phase.phase_id)
        assert phase.status == PhaseStatus.COMPLETED

    def test_blocking_gate_sets_gated(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Blocking gate with all subtasks done sets status to GATED."""
        decomp = orchestrator.decompose_plan()
        phase_2 = decomp.phases[1]
        for s in phase_2.subtasks:
            orchestrator.mark_subtask_complete(phase_2.phase_id, s)
        orchestrator.advance_phase(phase_2.phase_id)
        assert phase_2.status == PhaseStatus.GATED

    def test_human_proceed_sets_completed(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Human PROCEED decision completes a gated phase."""
        decomp = orchestrator.decompose_plan()
        phase_2 = decomp.phases[1]
        phase_2.status = PhaseStatus.GATED
        orchestrator.apply_human_decision(
            phase_2.phase_id, GateDecision.PROCEED, "Looks good",
        )
        assert phase_2.status == PhaseStatus.COMPLETED

    def test_human_iterate_resets(
        self, orchestrator: Orchestrator,
    ) -> None:
        """Human ITERATE decision resets phase to ACTIVE."""
        decomp = orchestrator.decompose_plan()
        phase_2 = decomp.phases[1]
        phase_2.status = PhaseStatus.GATED
        phase_2.completed_subtasks = list(phase_2.subtasks)
        orchestrator.apply_human_decision(
            phase_2.phase_id, GateDecision.ITERATE, "Needs work",
        )
        assert phase_2.status == PhaseStatus.ACTIVE
        assert phase_2.completed_subtasks == []

    def test_get_phase_status(self, orchestrator: Orchestrator) -> None:
        """get_phase_status returns the correct status."""
        decomp = orchestrator.decompose_plan()
        assert orchestrator.get_phase_status("phase_1") == PhaseStatus.PENDING
        decomp.phases[0].status = PhaseStatus.ACTIVE
        assert orchestrator.get_phase_status("phase_1") == PhaseStatus.ACTIVE

    def test_get_phase_status_invalid(
        self, orchestrator: Orchestrator,
    ) -> None:
        """get_phase_status raises for unknown phase_id."""
        orchestrator.decompose_plan()
        with pytest.raises(ValueError, match="not found"):
            orchestrator.get_phase_status("phase_99")


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------


class TestEndSession:
    """Tests for Orchestrator.end_session()."""

    def test_end_session_writes_state(
        self, orchestrator: Orchestrator,
    ) -> None:
        """end_session persists state and logs decision."""
        orchestrator.start_session()
        orchestrator.end_session()
        # State file should exist
        state_path = orchestrator._memory.memory_root / "STATE.md"
        assert state_path.exists()

    def test_end_session_with_summary(
        self, orchestrator: Orchestrator,
    ) -> None:
        """end_session writes a session summary when provided."""
        from zo._memory_models import SessionSummary

        orchestrator.start_session()
        summary = SessionSummary(
            accomplished=["Completed phase 1"],
            next_steps=["Start phase 2"],
        )
        orchestrator.end_session(summary=summary)
        sessions_dir = orchestrator._memory.memory_root / "sessions"
        summaries = list(sessions_dir.glob("session-*.md"))
        assert len(summaries) == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_orchestrator(plan: Plan, tmp_path: Path) -> Orchestrator:
    """Create an Orchestrator with temp directories."""
    target = _make_target()
    memory = MemoryManager(
        project_dir=tmp_path, project_name="test-project",
    )
    memory.initialize_project()
    comms = CommsLogger(
        log_dir=tmp_path / "logs" / "comms",
        project="test-project",
        session_id="test-session-001",
    )
    semantic = SemanticIndex(db_path=tmp_path / "index.db")
    return Orchestrator(
        plan=plan,
        target=target,
        memory=memory,
        comms=comms,
        semantic=semantic,
        zo_root=REPO_ROOT,
    )
