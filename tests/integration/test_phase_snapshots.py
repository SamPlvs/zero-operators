"""Integration tests for phase completion snapshots.

Verifies the orchestrator writes a snapshot to ``{memory_root}/snapshots/``
at every gate PROCEED (automated and human paths).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from zo._orchestrator_models import GateDecision, GateMode, PhaseStatus
from zo.comms import CommsLogger
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import parse_plan
from zo.semantic import SemanticIndex
from zo.snapshots import list_snapshots, load_latest_snapshot
from zo.target import parse_target

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"


def _make_git_repo(path: Path) -> None:
    """Initialise a minimal git repo so MemoryManager works."""
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path, capture_output=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com",
        },
        check=True,
    )


def _build_orch(
    tmp_path: Path, *, gate_mode: GateMode = GateMode.AUTO,
) -> tuple[Orchestrator, MemoryManager]:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
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
        session_id="snap-test-001",
    )
    memory = MemoryManager(
        project_dir=project_dir,
        project_name=plan.frontmatter.project_name,
    )
    memory.initialize_project()
    semantic = SemanticIndex(db_path=project_dir / "memory" / "index.db")

    orch = Orchestrator(
        plan=plan, target=target, memory=memory, comms=comms,
        semantic=semantic, zo_root=project_dir, gate_mode=gate_mode,
    )
    return orch, memory


class TestSnapshotGeneratedOnHumanGate:
    def test_human_proceed_writes_snapshot(self, tmp_path: Path) -> None:
        orch, memory = _build_orch(tmp_path, gate_mode=GateMode.SUPERVISED)
        orch.start_session()
        decomp = orch.decompose_plan()
        phase = decomp.phases[0]
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        orch.advance_phase(phase.phase_id)
        assert phase.status == PhaseStatus.GATED

        orch.apply_human_decision(
            phase.phase_id, GateDecision.PROCEED, "looks good",
        )
        assert phase.status == PhaseStatus.COMPLETED

        snaps = list_snapshots(memory.memory_root, phase.phase_id)
        assert len(snaps) == 1
        assert phase.phase_id in snaps[0].name

    def test_snapshot_records_human_gate_decision(self, tmp_path: Path) -> None:
        orch, memory = _build_orch(tmp_path, gate_mode=GateMode.SUPERVISED)
        orch.start_session()
        decomp = orch.decompose_plan()
        phase = decomp.phases[0]
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        orch.advance_phase(phase.phase_id)
        orch.apply_human_decision(phase.phase_id, GateDecision.PROCEED)

        loaded = load_latest_snapshot(memory.memory_root, phase.phase_id)
        assert loaded is not None
        assert loaded.gate_decision == "human"
        # GateDecision.PROCEED stringifies to "proceed" (value) or
        # "GateDecision.PROCEED" (name) depending on serialization — accept both.
        assert "proceed" in loaded.gate_outcome.lower()


class TestSnapshotGeneratedOnAutomatedGate:
    def test_automated_proceed_writes_snapshot(self, tmp_path: Path) -> None:
        orch, memory = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()

        # Pick the first phase; complete subtasks and advance. FULL_AUTO
        # treats all gates as automated — no human path.
        phase = decomp.phases[0]
        # Skip the artifact check by clearing required_artifacts for this test.
        phase.required_artifacts = []
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED

        snaps = list_snapshots(memory.memory_root, phase.phase_id)
        assert len(snaps) == 1
        loaded = load_latest_snapshot(memory.memory_root, phase.phase_id)
        assert loaded is not None
        assert loaded.gate_decision == "automated"


class TestSnapshotContent:
    def test_snapshot_captures_subtask_state(self, tmp_path: Path) -> None:
        orch, memory = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()
        phase = decomp.phases[0]
        phase.required_artifacts = []
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        orch.advance_phase(phase.phase_id)

        loaded = load_latest_snapshot(memory.memory_root, phase.phase_id)
        assert loaded is not None
        assert loaded.subtasks_total == len(phase.subtasks)
        assert loaded.subtasks_completed == len(phase.subtasks)

    def test_snapshot_file_has_valid_yaml_frontmatter(
        self, tmp_path: Path,
    ) -> None:
        orch, memory = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        orch.start_session()
        decomp = orch.decompose_plan()
        phase = decomp.phases[0]
        phase.required_artifacts = []
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        orch.advance_phase(phase.phase_id)

        snaps = list_snapshots(memory.memory_root, phase.phase_id)
        text = snaps[0].read_text(encoding="utf-8")
        assert text.startswith("---\n")
        end = text.index("\n---\n", 4)
        fm = yaml.safe_load(text[4:end])
        assert fm["phase_id"] == phase.phase_id
        assert fm["schema_version"] == 1
