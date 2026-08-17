"""Tests for nonce-verified gate approvals (v2 WS-A5, plan oracle check 5).

Seeded forgery: an approval WITHOUT the minted nonce must be rejected;
the genuine nonce-tagged approval must pass; nonces are single-use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zo._orchestrator_models import GateDecision, GateMode, PhaseStatus
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import parse_plan
from zo.semantic import SemanticIndex
from zo.target import TargetConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PLAN = REPO_ROOT / "tests" / "fixtures" / "test-project" / "plan.md"


@pytest.fixture()
def wired(tmp_path: Path):
    """Supervised-mode orchestrator plus its memory manager."""
    memory = MemoryManager(project_dir=tmp_path, project_name="test-project")
    memory.initialize_project()
    orch = Orchestrator(
        plan=parse_plan(FIXTURE_PLAN),
        target=TargetConfig(
            project="test-project", target_repo=str(tmp_path / "delivery"),
            target_branch="main", worktree_base=str(tmp_path / "wt"),
            git_author_name="ZO Test", git_author_email="zo@test.dev",
            agent_working_dirs={}, zo_only_paths=[".zo/"],
            enforce_isolation=False,
        ),
        memory=memory,
        comms=CommsLogger(
            log_dir=tmp_path / "logs" / "comms", project="test-project",
            session_id="nonce-test",
        ),
        semantic=SemanticIndex(db_path=tmp_path / "index.db"),
        zo_root=REPO_ROOT,
        gate_mode=GateMode.SUPERVISED,
    )
    return orch, memory


def _gate_first_phase(orch: Orchestrator) -> str:
    decomp = orch.decompose_plan()
    phase = decomp.phases[0]
    for subtask in phase.subtasks:
        orch.mark_subtask_complete(phase.phase_id, subtask)
    evaluation = orch.advance_phase(phase.phase_id)
    assert evaluation.requires_human
    assert phase.status == PhaseStatus.GATED
    return phase.phase_id


class TestNonceLifecycle:
    def test_nonce_minted_when_phase_gates(self, wired) -> None:
        orch, memory = wired
        _gate_first_phase(orch)
        assert memory.read_gate_nonce()

    def test_nonce_surfaced_in_gate_review(self, wired) -> None:
        orch, memory = wired
        phase_id = _gate_first_phase(orch)
        review = orch.prepare_gate_review(phase_id)
        assert review["approval_nonce"] == memory.read_gate_nonce()

    def test_forged_approval_without_nonce_rejected(self, wired) -> None:
        """The seeded forgery of oracle check 5."""
        orch, _ = wired
        phase_id = _gate_first_phase(orch)
        with pytest.raises(PermissionError, match="nonce"):
            orch.apply_human_decision(phase_id, GateDecision.PROCEED, "lgtm")

    def test_wrong_nonce_rejected(self, wired) -> None:
        orch, _ = wired
        phase_id = _gate_first_phase(orch)
        with pytest.raises(PermissionError):
            orch.apply_human_decision(
                phase_id, GateDecision.PROCEED, "lgtm", nonce="deadbeef",
            )

    def test_genuine_nonce_passes_and_is_single_use(self, wired) -> None:
        orch, memory = wired
        phase_id = _gate_first_phase(orch)
        orch.apply_human_decision(
            phase_id, GateDecision.PROCEED, "lgtm",
            nonce=memory.read_gate_nonce(),
        )
        assert orch.get_phase_status(phase_id) == PhaseStatus.COMPLETED
        assert memory.read_gate_nonce() is None  # cleared — replay impossible

    def test_legacy_path_without_stored_nonce_unaffected(self, wired) -> None:
        """Directly-GATED phases (no mint) keep the pre-WS-A5 behaviour."""
        orch, memory = wired
        decomp = orch.decompose_plan()
        phase = decomp.phases[1]
        phase.status = PhaseStatus.GATED
        assert memory.read_gate_nonce() is None
        orch.apply_human_decision(phase.phase_id, GateDecision.PROCEED, "ok")
        assert phase.status == PhaseStatus.COMPLETED


class TestGateDecisionFile:
    def test_cli_recorded_decision_consumed_on_next_decompose(self, wired) -> None:
        orch, memory = wired
        orch.start_session()
        phase_id = _gate_first_phase(orch)
        orch.end_session()  # persists phase_states (GATED) to STATE.md
        # Simulate `zo gates approve`: nonce verified there, then cleared.
        memory.clear_gate_nonce()
        memory.write_gate_decision(phase_id, "proceed", "approved via CLI")
        # Fresh session / replan path: recover state, re-decompose.
        orch.start_session()
        orch.decompose_plan()
        assert orch.get_phase_status(phase_id) == PhaseStatus.COMPLETED
        assert memory.read_gate_decision() is None  # consumed

    def test_stale_decision_for_unknown_phase_discarded(self, wired) -> None:
        orch, memory = wired
        memory.write_gate_decision("phase_99", "proceed", "stale")
        orch.decompose_plan()
        assert memory.read_gate_decision() is None


class TestLedgerOracleFlip:
    """Check 9 (landing half): the nonce-verified gate path flips the ledger."""

    def test_nonce_approval_marks_ledger_phase_passed(self, wired) -> None:
        from zo.ledger import LEDGER_FILENAME, load_ledger, summarize

        orch, memory = wired
        phase_id = _gate_first_phase(orch)
        ledger = load_ledger(memory.memory_root / LEDGER_FILENAME)
        assert ledger is not None  # emitted at decompose
        passed, total = summarize(ledger).get(phase_id, (0, 0))
        assert passed == 0  # nothing passes before the oracle path runs

        orch.apply_human_decision(
            phase_id, GateDecision.PROCEED, "verified",
            nonce=memory.read_gate_nonce(),
        )
        ledger = load_ledger(memory.memory_root / LEDGER_FILENAME)
        passed, total = summarize(ledger)[phase_id]
        assert passed == total > 0
        assert ledger.phase_status[phase_id] == "completed"

    def test_iterate_resets_ledger(self, wired) -> None:
        from zo.ledger import LEDGER_FILENAME, load_ledger, summarize

        orch, memory = wired
        phase_id = _gate_first_phase(orch)
        orch.apply_human_decision(
            phase_id, GateDecision.ITERATE, "rework the audit",
            nonce=memory.read_gate_nonce(),
        )
        ledger = load_ledger(memory.memory_root / LEDGER_FILENAME)
        passed, _ = summarize(ledger)[phase_id]
        assert passed == 0
        assert ledger.phase_status[phase_id] == "active"
        entry = next(e for e in ledger.entries if e.phase_id == phase_id)
        assert "rework the audit" in (entry.last_failure or "")
