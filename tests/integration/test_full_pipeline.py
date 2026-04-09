"""Integration tests for the full Zero Operators pipeline (Phase 4).

Covers cross-module interaction between:
  - Module 1: Plan Parser (zo.plan)
  - Module 2: Target Parser (zo.target)
  - Module 3: Memory Layer (zo.memory)
  - Module 4: Semantic Index (zo.semantic)
  - Module 5: Comms Logger (zo.comms)
  - Module 6: Orchestrator (zo.orchestrator)

No actual Claude CLI calls are made; wrapper.launch_lead_session is mocked.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zo._memory_models import (
    Confidence,
    DecisionEntry,
    OperatingMode,
    PriorEntry,
    SessionSummary,
)
from zo._orchestrator_models import (
    GateDecision,
    GateMode,
    GateType,
    PhaseStatus,
)
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import parse_plan
from zo.semantic import SemanticIndex
from zo.target import IsolationViolation, check_isolation, enforce_write, parse_target

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"


def _all_jsonl_events(log_dir: Path) -> list[dict]:
    """Read every JSONL event from all daily log files."""
    events: list[dict] = []
    for f in sorted(log_dir.glob("*.jsonl")):
        for raw in f.read_text(encoding="utf-8").strip().splitlines():
            if raw:
                events.append(json.loads(raw))
    return events


def _make_git_repo(path: Path) -> None:
    """Initialise a minimal git repo so MemoryManager._get_git_head() works."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path, capture_output=True,
        env={**__import__("os").environ, "GIT_AUTHOR_NAME": "test",
             "GIT_AUTHOR_EMAIL": "t@t.com",
             "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com"},
        check=True,
    )


def _build_orchestrator(
    tmp_path: Path,
    *,
    gate_mode: GateMode = GateMode.SUPERVISED,
) -> tuple[Orchestrator, CommsLogger, MemoryManager, SemanticIndex]:
    """Create a fully wired Orchestrator with all dependencies pointing at tmp_path."""
    # Prepare directories
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    _make_git_repo(project_dir)

    # Copy fixture files so plan has a source_path
    plan_path = project_dir / "plan.md"
    target_path = project_dir / "target.md"
    shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
    shutil.copy(FIXTURES_DIR / "target.md", target_path)

    plan = parse_plan(plan_path)
    target = parse_target(target_path)

    comms = CommsLogger(
        log_dir=project_dir / "logs" / "comms",
        project=plan.frontmatter.project_name,
        session_id="integ-test-001",
    )
    memory = MemoryManager(
        project_dir=project_dir,
        project_name=plan.frontmatter.project_name,
    )
    memory.initialize_project()

    semantic = SemanticIndex(db_path=project_dir / "memory" / "index.db")

    orch = Orchestrator(
        plan=plan,
        target=target,
        memory=memory,
        comms=comms,
        semantic=semantic,
        zo_root=project_dir,
        gate_mode=gate_mode,
    )
    return orch, comms, memory, semantic


# ---------------------------------------------------------------------------
# 1. test_full_session_lifecycle
# ---------------------------------------------------------------------------


class TestFullSessionLifecycle:
    """Parse plan -> init memory -> orchestrate -> end session -> verify memory."""

    def test_full_session_lifecycle(self, tmp_path: Path) -> None:
        orch, comms, memory, _ = _build_orchestrator(tmp_path)

        # Start session
        state = orch.start_session()
        assert state.mode == OperatingMode.BUILD  # fresh project => build mode

        # Decompose
        decomp = orch.decompose_plan()
        assert len(decomp.phases) > 0

        # Pick the first phase and mark all its subtasks complete
        first_phase = decomp.phases[0]
        for subtask in first_phase.subtasks:
            orch.mark_subtask_complete(first_phase.phase_id, subtask)
        assert set(first_phase.completed_subtasks) == set(first_phase.subtasks)

        # Advance phase (supervised -> HOLD, but state should be updated)
        gate_eval = orch.advance_phase(first_phase.phase_id)
        # In SUPERVISED mode the gate holds for human review
        assert gate_eval.requires_human is True
        assert first_phase.status == PhaseStatus.GATED

        # Apply human decision to proceed
        orch.apply_human_decision(first_phase.phase_id, GateDecision.PROCEED)
        assert first_phase.status == PhaseStatus.COMPLETED

        # End session with a summary
        summary = SessionSummary(
            mode=OperatingMode.BUILD,
            accomplished=["phase 1 complete"],
            decisions_made=["proceed to phase 2"],
            next_steps=["start phase 2"],
        )
        orch.end_session(summary=summary)

        # Verify STATE.md was written
        state_path = memory.memory_root / "STATE.md"
        assert state_path.exists()
        final_state = memory.read_state()
        assert final_state.last_completed_subtask == first_phase.subtasks[-1]

        # Verify DECISION_LOG has entries (gate + human decision)
        decisions = memory.read_decisions()
        assert len(decisions) >= 2
        titles = [d.title for d in decisions]
        assert any(first_phase.phase_id in t for t in titles)

        # Verify session summary file was written
        summaries = memory.read_recent_summaries(count=1)
        assert len(summaries) == 1
        assert "phase 1 complete" in summaries[0].accomplished


# ---------------------------------------------------------------------------
# 2. test_memory_semantic_integration
# ---------------------------------------------------------------------------


class TestMemorySemanticIntegration:
    """Memory decisions/priors flow correctly into the semantic index."""

    def test_memory_semantic_integration(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "mem-sem"
        project_dir.mkdir()
        _make_git_repo(project_dir)

        memory = MemoryManager(project_dir=project_dir, project_name="test-proj")
        memory.initialize_project()

        # Append decisions with distinct keywords
        memory.append_decision(DecisionEntry(
            title="Use gradient boosting for churn model",
            context="model selection phase",
            decision="gradient_boosting",
            rationale="Best AUC on validation split",
            outcome="proceed",
            confidence=Confidence.HIGH,
        ))
        memory.append_decision(DecisionEntry(
            title="Drop PII columns before feature engineering",
            context="data cleaning phase",
            decision="remove_pii",
            rationale="Compliance requirement; customer_id as join key only",
            outcome="proceed",
            confidence=Confidence.HIGH,
        ))

        # Append priors
        memory.append_prior(PriorEntry(
            category="domain",
            statement="Churn rate in SaaS is typically 5-7% per month",
            evidence="industry benchmarks",
            confidence=Confidence.MEDIUM,
        ))

        # Build semantic index from memory
        semantic = SemanticIndex(db_path=project_dir / "index.db")
        decisions = memory.read_decisions()
        priors = memory.read_priors()

        assert len(decisions) == 2
        assert len(priors) == 1

        semantic.rebuild_index(decisions, priors)
        assert semantic.count() == 3

        # Query — should find the gradient boosting decision
        results = semantic.query("gradient boosting model", top_k=3)
        assert len(results) > 0
        summaries = [r.entry.summary for r in results]
        assert any("gradient boosting" in s.lower() for s in summaries)

        # Query — should find the PII decision
        pii_results = semantic.query("PII columns privacy", top_k=3)
        assert len(pii_results) > 0
        pii_summaries = [r.entry.summary for r in pii_results]
        assert any("pii" in s.lower() for s in pii_summaries)

        # All results are SearchResult with score >= 0
        for r in results:
            assert r.score >= 0.0
            assert r.entry.source in {"decision", "prior", "session"}


# ---------------------------------------------------------------------------
# 3. test_orchestrator_gate_modes
# ---------------------------------------------------------------------------


class TestOrchestratorGateModes:
    """Each gate_mode produces the correct gate evaluation behaviour."""

    def _run_all_subtasks(self, orch: Orchestrator, phase_id: str) -> None:
        """Mark every subtask in a phase complete."""
        decomp = orch.workflow
        assert decomp is not None
        phase = next(p for p in decomp.phases if p.phase_id == phase_id)
        for subtask in phase.subtasks:
            orch.mark_subtask_complete(phase_id, subtask)

    def test_supervised_gate_always_holds(self, tmp_path: Path) -> None:
        orch, _, _, _ = _build_orchestrator(tmp_path / "sup", gate_mode=GateMode.SUPERVISED)
        orch.start_session()
        decomp = orch.decompose_plan()
        first_id = decomp.phases[0].phase_id

        self._run_all_subtasks(orch, first_id)
        eval_ = orch.advance_phase(first_id)

        assert eval_.requires_human is True
        assert eval_.gate_type == GateType.BLOCKING
        assert decomp.phases[0].status == PhaseStatus.GATED

    def test_full_auto_gate_proceeds_when_subtasks_done(self, tmp_path: Path) -> None:
        orch, _, _, _ = _build_orchestrator(tmp_path / "fa", gate_mode=GateMode.FULL_AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()
        first_id = decomp.phases[0].phase_id

        self._run_all_subtasks(orch, first_id)
        eval_ = orch.advance_phase(first_id)

        assert eval_.requires_human is False
        assert eval_.gate_type == GateType.AUTOMATED
        assert decomp.phases[0].status == PhaseStatus.COMPLETED

    def test_full_auto_gate_iterates_when_subtasks_incomplete(self, tmp_path: Path) -> None:
        orch, _, _, _ = _build_orchestrator(tmp_path / "fa2", gate_mode=GateMode.FULL_AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()
        first_id = decomp.phases[0].phase_id

        # Do NOT mark any subtasks complete
        eval_ = orch.advance_phase(first_id)

        assert eval_.gate_type == GateType.AUTOMATED
        # Decision should be ITERATE since subtasks are incomplete
        from zo._orchestrator_models import GateDecision
        assert eval_.decision == GateDecision.ITERATE

    def test_auto_respects_plan_gate_type(self, tmp_path: Path) -> None:
        """In AUTO mode the gate decision is driven by the phase's gate_type field."""
        orch, _, _, _ = _build_orchestrator(tmp_path / "auto", gate_mode=GateMode.AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()
        first_id = decomp.phases[0].phase_id

        self._run_all_subtasks(orch, first_id)
        eval_ = orch.advance_phase(first_id)

        # The outcome depends on the plan-defined gate_type for this phase
        phase = decomp.phases[0]
        if phase.gate_type == GateType.BLOCKING:
            assert eval_.requires_human is True
        else:
            assert eval_.requires_human is False


# ---------------------------------------------------------------------------
# 4. test_plan_edit_detection
# ---------------------------------------------------------------------------


class TestPlanEditDetection:
    """Orchestrator detects when plan.md is modified after decomposition."""

    def test_plan_edit_detection(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "edit-detect"
        project_dir.mkdir()
        _make_git_repo(project_dir)

        plan_path = project_dir / "plan.md"
        target_path = project_dir / "target.md"
        shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
        shutil.copy(FIXTURES_DIR / "target.md", target_path)

        plan = parse_plan(plan_path)
        target = parse_target(target_path)
        comms = CommsLogger(
            log_dir=project_dir / "logs" / "comms",
            project=plan.frontmatter.project_name,
            session_id="edit-test",
        )
        memory = MemoryManager(project_dir=project_dir, project_name=plan.frontmatter.project_name)
        memory.initialize_project()
        semantic = SemanticIndex(db_path=project_dir / "index.db")

        orch = Orchestrator(
            plan=plan, target=target, memory=memory,
            comms=comms, semantic=semantic, zo_root=project_dir,
        )
        orch.start_session()
        orch.decompose_plan()

        # Initially no edit
        assert orch.check_plan_edited() is False

        # Modify plan.md on disk
        original = plan_path.read_text(encoding="utf-8")
        plan_path.write_text(
            original + "\n<!-- modified for test -->\n",
            encoding="utf-8",
        )

        # Now the orchestrator should detect the change
        assert orch.check_plan_edited() is True

    def test_replan_resets_hash(self, tmp_path: Path) -> None:
        """After replan() the hash matches the new file and check_plan_edited is False."""
        project_dir = tmp_path / "replan"
        project_dir.mkdir()
        _make_git_repo(project_dir)

        plan_path = project_dir / "plan.md"
        target_path = project_dir / "target.md"
        shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
        shutil.copy(FIXTURES_DIR / "target.md", target_path)

        plan = parse_plan(plan_path)
        target = parse_target(target_path)
        comms = CommsLogger(
            log_dir=project_dir / "logs" / "comms",
            project=plan.frontmatter.project_name,
            session_id="replan-test",
        )
        memory = MemoryManager(project_dir=project_dir, project_name=plan.frontmatter.project_name)
        memory.initialize_project()
        semantic = SemanticIndex(db_path=project_dir / "index.db")

        orch = Orchestrator(
            plan=plan, target=target, memory=memory,
            comms=comms, semantic=semantic, zo_root=project_dir,
        )
        orch.start_session()
        orch.decompose_plan()

        # Mutate plan file
        original = plan_path.read_text(encoding="utf-8")
        plan_path.write_text(original + "\n<!-- v2 -->\n", encoding="utf-8")
        assert orch.check_plan_edited() is True

        # Replan with the updated plan object
        new_plan = parse_plan(plan_path)
        orch.replan(new_plan)

        assert orch.check_plan_edited() is False


# ---------------------------------------------------------------------------
# 5. test_session_recovery_flow
# ---------------------------------------------------------------------------


class TestSessionRecoveryFlow:
    """Writing state at a specific phase => new orchestrator resumes from it."""

    def test_session_recovery_flow(self, tmp_path: Path) -> None:
        from zo._memory_models import SessionState

        project_dir = tmp_path / "recovery"
        project_dir.mkdir()
        _make_git_repo(project_dir)

        plan_path = project_dir / "plan.md"
        target_path = project_dir / "target.md"
        shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
        shutil.copy(FIXTURES_DIR / "target.md", target_path)

        plan = parse_plan(plan_path)
        target = parse_target(target_path)
        project_name = plan.frontmatter.project_name

        # --- Session 1: write state at phase 2 ---
        memory1 = MemoryManager(project_dir=project_dir, project_name=project_name)
        memory1.initialize_project()
        state1 = SessionState(
            mode=OperatingMode.CONTINUE,
            phase="phase-2-feature-engineering",
            last_completed_subtask="data-profiling",
            active_agents=["data-engineer", "model-builder"],
        )
        memory1.write_state(state1)

        # --- Session 2: new orchestrator picks up the saved state ---
        comms2 = CommsLogger(
            log_dir=project_dir / "logs" / "comms",
            project=project_name,
            session_id="recovery-session-002",
        )
        memory2 = MemoryManager(project_dir=project_dir, project_name=project_name)
        semantic2 = SemanticIndex(db_path=project_dir / "index.db")

        orch2 = Orchestrator(
            plan=plan, target=target, memory=memory2,
            comms=comms2, semantic=semantic2, zo_root=project_dir,
        )
        recovered_state = orch2.start_session()

        # Should resume in CONTINUE mode since STATE.md exists with a non-init phase
        assert recovered_state.mode == OperatingMode.CONTINUE
        assert recovered_state.phase == "phase-2-feature-engineering"
        assert recovered_state.last_completed_subtask == "data-profiling"

    def test_fresh_project_starts_in_build_mode(self, tmp_path: Path) -> None:
        """A project with no STATE.md always starts in BUILD mode."""
        orch, _, memory, _ = _build_orchestrator(tmp_path)
        state = orch.start_session()
        assert state.mode == OperatingMode.BUILD


# ---------------------------------------------------------------------------
# 6. test_comms_logging_throughout
# ---------------------------------------------------------------------------


class TestCommsLoggingThroughout:
    """A mini session produces JSONL logs with checkpoint, decision, and gate events."""

    def test_comms_logging_throughout(self, tmp_path: Path) -> None:
        orch, comms, memory, _ = _build_orchestrator(tmp_path)
        project_name = "churn-prediction"

        orch.start_session()
        decomp = orch.decompose_plan()
        first_phase = decomp.phases[0]

        # Mark subtasks complete one by one (produces checkpoint events)
        for subtask in first_phase.subtasks:
            orch.mark_subtask_complete(first_phase.phase_id, subtask)

        # Advance phase (produces decision + memory gate entry)
        orch.advance_phase(first_phase.phase_id)

        # End session
        orch.end_session()

        events = _all_jsonl_events(comms._log_dir)

        event_types = {e["event_type"] for e in events}
        assert "checkpoint" in event_types, "Expected checkpoint events from mark_subtask_complete"
        assert "decision" in event_types, "Expected decision events from orchestrator"

        # Every event carries correct project and session
        for e in events:
            assert e["project"] == project_name
            assert e["session_id"] == "integ-test-001"

        # At least one checkpoint from marking subtasks
        checkpoint_events = [e for e in events if e["event_type"] == "checkpoint"]
        assert len(checkpoint_events) >= len(first_phase.subtasks)
        for cp in checkpoint_events:
            assert "agent" in cp
            assert "phase" in cp

        # At least one decision event from start_session and decompose_plan
        decision_events = [e for e in events if e["event_type"] == "decision"]
        assert len(decision_events) >= 2
        for de in decision_events:
            assert de["agent"] == "orchestrator"

    def test_comms_gate_decision_logged_to_memory(self, tmp_path: Path) -> None:
        """Gate decisions are written to both JSONL and DECISION_LOG.md."""
        orch, _, memory, _ = _build_orchestrator(tmp_path)
        orch.start_session()
        decomp = orch.decompose_plan()
        first_id = decomp.phases[0].phase_id

        for subtask in decomp.phases[0].subtasks:
            orch.mark_subtask_complete(first_id, subtask)
        orch.advance_phase(first_id)

        # Gate decision should be in DECISION_LOG.md
        decisions = memory.read_decisions()
        assert len(decisions) >= 1
        titles = [d.title for d in decisions]
        assert any(first_id in t for t in titles)


# ---------------------------------------------------------------------------
# 7. test_target_isolation_with_orchestrator
# ---------------------------------------------------------------------------


class TestTargetIsolationWithOrchestrator:
    """Target isolation is enforced consistently throughout the session."""

    def test_target_isolation_with_orchestrator(self, tmp_path: Path) -> None:
        orch, _, _, _ = _build_orchestrator(tmp_path)
        orch.start_session()
        orch.decompose_plan()

        # The orchestrator's target config should block ZO-only paths
        target = orch._target  # type: ignore[attr-defined]

        # Paths that agents should be allowed to write
        allowed = [
            "src/models/churn_v1.py",
            "data/processed/features.parquet",
            "eval/metrics.json",
        ]
        for path in allowed:
            assert check_isolation(path, target) is True, f"Should allow: {path}"

        # Paths that are ZO-internal and must be blocked
        blocked = [
            ".claude/settings.json",
            "CLAUDE.md",
            "STATE.md",
            ".zo/internal.yaml",
            "memory/churn-prediction/STATE.md",
            "logs/comms/2026-04-09.jsonl",
        ]
        for path in blocked:
            assert check_isolation(path, target) is False, f"Should block: {path}"

    def test_enforce_write_raises_for_zo_paths(self, tmp_path: Path) -> None:
        """enforce_write raises IsolationViolation for ZO-internal paths."""
        orch, _, _, _ = _build_orchestrator(tmp_path)
        target = orch._target  # type: ignore[attr-defined]

        with pytest.raises(IsolationViolation) as exc_info:
            enforce_write(".claude/agents/lead.md", target)
        assert ".claude/" in exc_info.value.matched_pattern

        with pytest.raises(IsolationViolation):
            enforce_write("memory/state.json", target)

    def test_allowed_paths_do_not_raise(self, tmp_path: Path) -> None:
        """enforce_write is silent for legitimate delivery repo paths."""
        orch, _, _, _ = _build_orchestrator(tmp_path)
        target = orch._target  # type: ignore[attr-defined]

        # Should not raise
        enforce_write("src/train.py", target)
        enforce_write("data/features.parquet", target)
        enforce_write("eval/report.json", target)
        enforce_write("README.md", target)

    def test_isolation_enforced_regardless_of_session_state(self, tmp_path: Path) -> None:
        """Isolation rules apply before and after decompose_plan is called."""
        orch, _, _, _ = _build_orchestrator(tmp_path)
        target = orch._target  # type: ignore[attr-defined]

        # Before decomposition
        assert check_isolation("STATE.md", target) is False
        assert check_isolation("src/model.py", target) is True

        orch.start_session()
        orch.decompose_plan()

        # After decomposition — same rules
        assert check_isolation("STATE.md", target) is False
        assert check_isolation("src/model.py", target) is True
