"""Integration tests for the experiment capture layer + orchestrator.

Verifies Phase 4 minting, gate enforcement of ``result.md``, and
lineage-preserving iteration.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

from zo._orchestrator_models import GateDecision, GateMode, PhaseStatus
from zo.comms import CommsLogger
from zo.experiments import (
    ExperimentStatus,
    load_registry,
)
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import parse_plan
from zo.semantic import SemanticIndex
from zo.target import parse_target

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "test-project"


def _make_git_repo(path: Path) -> None:
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
    tmp_path: Path,
    *,
    gate_mode: GateMode = GateMode.AUTO,
) -> tuple[Orchestrator, Path]:
    """Build an orchestrator whose delivery repo is a real tmp_path dir.

    Returns (orchestrator, delivery_repo_path).
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    _make_git_repo(project_dir)

    delivery_repo = tmp_path / "delivery"
    delivery_repo.mkdir(parents=True)

    plan_path = project_dir / "plan.md"
    target_path = project_dir / "target.md"
    shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
    # Rewrite target file's target_repo to the real delivery dir.
    fixture_target = (FIXTURES_DIR / "target.md").read_text(encoding="utf-8")
    target_path.write_text(
        fixture_target.replace(
            '../delivery/churn-prediction', str(delivery_repo),
        ),
        encoding="utf-8",
    )

    plan = parse_plan(plan_path)
    target = parse_target(target_path)
    comms = CommsLogger(
        log_dir=project_dir / "logs" / "comms",
        project=plan.frontmatter.project_name,
        session_id="exp-test-001",
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
    return orch, delivery_repo


def _phase_4(orch: Orchestrator):
    """Return the phase_4 definition from a decomposed orchestrator."""
    decomp = orch.decompose_plan()
    for p in decomp.phases:
        if p.phase_id == "phase_4":
            return p
    raise AssertionError("phase_4 not found in decomposition")


def _make_phase_artifacts(delivery_repo: Path, phase_4) -> None:
    """Create the phase_4 required_artifacts so _check_artifacts passes."""
    for artifact in phase_4.required_artifacts:
        path = delivery_repo / artifact
        if artifact.endswith("/"):
            path.mkdir(parents=True, exist_ok=True)
            (path / ".keep").write_text("")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub", encoding="utf-8")


def _write_result_md(
    exp_dir: Path,
    *,
    oracle_tier: str = "should_pass",
    metric_name: str = "mae",
    metric_value: float = 0.3,
) -> None:
    (exp_dir / "result.md").write_text(
        f"""---
exp_id: {exp_dir.name}
oracle_tier: {oracle_tier}
primary_metric:
  name: {metric_name}
  value: {metric_value}
---

# Result

## Shortfalls

- Overfits after epoch 12
""",
        encoding="utf-8",
    )


def _write_training_artifacts(exp_dir: Path) -> None:
    """Write the ZOTrainingCallback artifacts the new gate requires.

    Most Phase-4 gate-pass tests need these alongside ``result.md``.
    Stub content is enough — the gate only checks existence.
    """
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "metrics.jsonl").write_text(
        '{"event": "epoch_end", "epoch": 1}\n', encoding="utf-8",
    )
    (exp_dir / "training_status.json").write_text(
        '{"is_training": false, "epoch": 1}\n', encoding="utf-8",
    )


def _complete_phase4_artifacts(exp_dir: Path, **result_kwargs) -> None:
    """Write all three artifacts the Phase 4 gate now requires."""
    _write_training_artifacts(exp_dir)
    _write_result_md(exp_dir, **result_kwargs)


class TestPhase4MintsExperimentOnPrompt:
    def test_lead_prompt_mints_experiment(self, tmp_path: Path) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        prompt = orch.build_lead_prompt(phase)

        assert "Experiment Capture Layer" in prompt
        assert "exp-001" in prompt
        # Registry file should exist under the delivery repo.
        assert (delivery_repo / ".zo" / "experiments" / "registry.json").exists()
        # Experiment dir created.
        assert (delivery_repo / ".zo" / "experiments" / "exp-001").is_dir()

    def test_lead_prompt_reuses_running_experiment(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        prompt1 = orch.build_lead_prompt(phase)
        prompt2 = orch.build_lead_prompt(phase)

        assert "exp-001" in prompt1
        assert "exp-001" in prompt2
        # Should NOT mint exp-002 on second call.
        reg = load_registry(delivery_repo / ".zo" / "experiments")
        assert [e.id for e in reg.experiments] == ["exp-001"]

    def test_non_phase_4_does_not_mint(self, tmp_path: Path) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        decomp = orch.decompose_plan()
        phase_1 = decomp.phases[0]
        assert phase_1.phase_id != "phase_4"
        prompt = orch.build_lead_prompt(phase_1)

        assert "Experiment Capture Layer" not in prompt
        assert not (delivery_repo / ".zo" / "experiments").exists()


class TestPhase4GateBlocksOnMissingResult:
    def test_missing_result_md_blocks_automated_gate(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        # Mint an experiment via lead prompt.
        orch.build_lead_prompt(phase)
        # Complete subtasks but DON'T write result.md.
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.ITERATE
        assert "result.md" in ev.rationale
        assert phase.status != PhaseStatus.COMPLETED

    def test_result_md_allows_automated_gate(
        self, tmp_path: Path,
    ) -> None:
        """When result hits must_pass, loop says TARGET_HIT → PROCEED."""
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        # All three artifacts: metrics.jsonl + training_status.json + result.md
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        _complete_phase4_artifacts(exp_dir, oracle_tier="must_pass")

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED

    def test_supervised_mode_disables_auto_iteration(
        self, tmp_path: Path,
    ) -> None:
        """Supervised mode ignores the loop evaluator — phase gates for human."""
        orch, delivery_repo = _build_orch(
            tmp_path, gate_mode=GateMode.SUPERVISED,
        )
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        _write_result_md(exp_dir, oracle_tier="should_pass")

        ev = orch.advance_phase(phase.phase_id)
        # Supervised gate holds for human regardless of loop state.
        assert ev.requires_human is True
        assert phase.status == PhaseStatus.GATED

    def test_gate_pass_marks_experiment_complete(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        _complete_phase4_artifacts(
            exp_dir, metric_name="mae", metric_value=0.42,
        )

        orch.advance_phase(phase.phase_id)
        reg = load_registry(delivery_repo / ".zo" / "experiments")
        exp = reg.find("exp-001")
        assert exp.status == ExperimentStatus.COMPLETE
        assert exp.result is not None
        assert exp.result.primary_metric.value == 0.42


class TestPhase4IterateMintsChild:
    def test_iterate_aborts_running_and_next_prompt_mints_child(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(
            tmp_path, gate_mode=GateMode.SUPERVISED,
        )
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)  # mints exp-001
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        # Supervised mode holds; human iterates.
        orch.advance_phase(phase.phase_id)
        orch.apply_human_decision(
            phase.phase_id, GateDecision.ITERATE, "needs tuning",
        )

        reg_after_iterate = load_registry(
            delivery_repo / ".zo" / "experiments",
        )
        exp_001 = reg_after_iterate.find("exp-001")
        assert exp_001.status == ExperimentStatus.ABORTED

        # Next prompt build should mint exp-002 with parent_id=exp-001.
        orch.build_lead_prompt(phase)
        reg_after_mint = load_registry(
            delivery_repo / ".zo" / "experiments",
        )
        exp_002 = reg_after_mint.find("exp-002")
        assert exp_002 is not None
        assert exp_002.parent_id == "exp-001"
        assert exp_002.status == ExperimentStatus.RUNNING

    def test_delta_vs_parent_computed_on_child_result(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)

        # exp-001 run
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        _complete_phase4_artifacts(
            delivery_repo / ".zo" / "experiments" / "exp-001",
            metric_name="mae", metric_value=0.5,
        )
        orch.advance_phase(phase.phase_id)

        # Force another exp_4 run — reset phase status + subtasks + mint child.
        phase.status = PhaseStatus.ACTIVE
        phase.completed_subtasks.clear()
        orch.build_lead_prompt(phase)  # mints exp-002 with parent_id=exp-001

        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        _complete_phase4_artifacts(
            delivery_repo / ".zo" / "experiments" / "exp-002",
            metric_name="mae", metric_value=0.3,
        )
        orch.advance_phase(phase.phase_id)

        reg = load_registry(delivery_repo / ".zo" / "experiments")
        exp_002 = reg.find("exp-002")
        assert exp_002.parent_id == "exp-001"
        # 0.3 - 0.5 = -0.2
        assert abs(
            exp_002.result.primary_metric.delta_vs_parent - (-0.2),
        ) < 1e-9


class TestPromptContent:
    def test_prompt_mentions_artifacts_dir_and_factory(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        prompt = orch.build_lead_prompt(phase)
        assert "hypothesis.md" in prompt
        assert "result.md" in prompt
        assert "next.md" in prompt
        assert "ZOTrainingCallback.for_experiment" in prompt

    def test_prompt_marks_root_vs_child(self, tmp_path: Path) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        prompt_root = orch.build_lead_prompt(phase)
        assert "root experiment" in prompt_root

        # Complete exp-001 and reset phase to force exp-002 mint.
        _make_phase_artifacts(delivery_repo, phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        _complete_phase4_artifacts(
            delivery_repo / ".zo" / "experiments" / "exp-001",
        )
        orch.advance_phase(phase.phase_id)

        phase.status = PhaseStatus.ACTIVE
        phase.completed_subtasks.clear()
        prompt_child = orch.build_lead_prompt(phase)
        assert "Parent: `exp-001`" in prompt_child


class TestPhase4GateRequiresTrainingArtifacts:
    """The Phase-4 gate fails when ZOTrainingCallback wasn't used.

    Without ``metrics.jsonl`` and ``training_status.json`` in the
    experiment dir, ``zo watch-training`` is blank and the autonomous
    loop has nothing to evaluate. The gate must catch this contract
    violation, not silently pass.
    """

    def test_missing_metrics_jsonl_blocks_gate(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        # Write training_status.json + result.md but skip metrics.jsonl.
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        (exp_dir / "training_status.json").write_text(
            '{"is_training": false}\n', encoding="utf-8",
        )
        _write_result_md(exp_dir, oracle_tier="must_pass")

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.ITERATE
        assert "metrics.jsonl" in ev.rationale
        assert "ZOTrainingCallback not used" in ev.rationale
        assert phase.status != PhaseStatus.COMPLETED

    def test_missing_training_status_blocks_gate(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        # Write metrics.jsonl + result.md but skip training_status.json.
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        (exp_dir / "metrics.jsonl").write_text(
            '{"event": "epoch_end"}\n', encoding="utf-8",
        )
        _write_result_md(exp_dir, oracle_tier="must_pass")

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.ITERATE
        assert "training_status.json" in ev.rationale
        assert phase.status != PhaseStatus.COMPLETED

    def test_all_three_artifacts_present_passes_gate(
        self, tmp_path: Path,
    ) -> None:
        """Sanity: with all three required artifacts, the gate proceeds."""
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        exp_dir = delivery_repo / ".zo" / "experiments" / "exp-001"
        _complete_phase4_artifacts(exp_dir, oracle_tier="must_pass")

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.PROCEED

    def test_rationale_lists_all_missing_artifacts(
        self, tmp_path: Path,
    ) -> None:
        """When result.md AND metrics.jsonl are both missing, both
        appear in the rationale so the model-builder knows what to do.
        """
        orch, delivery_repo = _build_orch(tmp_path, gate_mode=GateMode.FULL_AUTO)
        phase = _phase_4(orch)
        _make_phase_artifacts(delivery_repo, phase)
        orch.build_lead_prompt(phase)
        for st in phase.subtasks:
            orch.mark_subtask_complete(phase.phase_id, st)
        # Write nothing in the experiment dir.

        ev = orch.advance_phase(phase.phase_id)
        assert ev.decision == GateDecision.ITERATE
        assert "metrics.jsonl" in ev.rationale
        assert "training_status.json" in ev.rationale
        assert "result.md" in ev.rationale
