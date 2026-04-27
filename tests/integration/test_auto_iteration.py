"""Integration tests for the autonomous Phase 4 iteration loop.

Covers the end-to-end flow:
  subtasks done -> result.md parsed -> loop evaluator consulted ->
  CONTINUE (phase stays ACTIVE, ITERATE returned) or stop (PROCEED,
  phase COMPLETED) based on policy.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

from zo._orchestrator_models import GateDecision, GateMode, PhaseStatus
from zo.comms import CommsLogger
from zo.experiment_loop import LoopVerdict
from zo.experiments import load_registry
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import ExperimentLoopSpec, parse_plan
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
    gate_mode: GateMode = GateMode.FULL_AUTO,
    loop_spec: ExperimentLoopSpec | None = None,
) -> tuple[Orchestrator, Path]:
    """Build an orchestrator with a real delivery repo and optional loop policy."""
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    _make_git_repo(project_dir)

    delivery_repo = tmp_path / "delivery"
    delivery_repo.mkdir(parents=True)

    plan_path = project_dir / "plan.md"
    target_path = project_dir / "target.md"
    shutil.copy(FIXTURES_DIR / "plan.md", plan_path)
    fixture_target = (FIXTURES_DIR / "target.md").read_text(encoding="utf-8")
    target_path.write_text(
        fixture_target.replace(
            "../delivery/churn-prediction", str(delivery_repo),
        ),
        encoding="utf-8",
    )

    plan = parse_plan(plan_path)
    if loop_spec is not None:
        plan.experiment_loop = loop_spec

    target = parse_target(target_path)
    comms = CommsLogger(
        log_dir=project_dir / "logs" / "comms",
        project=plan.frontmatter.project_name,
        session_id="auto-iter-001",
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
    decomp = orch.decompose_plan()
    for p in decomp.phases:
        if p.phase_id == "phase_4":
            return p
    raise AssertionError("phase_4 not found")


def _prepare_phase_artifacts(delivery_repo: Path, phase) -> None:
    for artifact in phase.required_artifacts:
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
    metric_value: float = 0.4,
    metric_name: str = "mae",
) -> None:
    """Write the three artifacts the Phase 4 gate now requires.

    - ``metrics.jsonl`` + ``training_status.json``: ZOTrainingCallback
      output (gate fails without these — see PR for `zo watch-training`
      contract enforcement).
    - ``result.md``: Oracle's verdict.
    """
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "metrics.jsonl").write_text(
        '{"event": "epoch_end", "epoch": 1}\n', encoding="utf-8",
    )
    (exp_dir / "training_status.json").write_text(
        '{"is_training": false, "epoch": 1}\n', encoding="utf-8",
    )
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

- needs work
""",
        encoding="utf-8",
    )


def _run_one_iteration(
    orch: Orchestrator, phase, delivery_repo: Path,
    *, exp_id: str, oracle_tier: str, metric_value: float,
) -> GateDecision:
    """Build prompt (mints exp) → complete subtasks → write result → advance."""
    orch.build_lead_prompt(phase)
    for st in phase.subtasks:
        orch.mark_subtask_complete(phase.phase_id, st)
    _write_result_md(
        delivery_repo / ".zo" / "experiments" / exp_id,
        oracle_tier=oracle_tier, metric_value=metric_value,
    )
    ev = orch.advance_phase(phase.phase_id)
    return ev.decision


class TestAutoIterateContinues:
    """Loop verdict CONTINUE → phase stays ACTIVE, gate returns ITERATE."""

    def test_should_pass_below_target_auto_iterates(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        decision = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="should_pass", metric_value=0.5,
        )

        # Auto-iteration → ITERATE (not PROCEED).
        assert decision == GateDecision.ITERATE
        # Phase is kept ACTIVE for the next iteration.
        assert phase.status == PhaseStatus.ACTIVE
        # Subtasks cleared for the next iteration.
        assert phase.completed_subtasks == []

    def test_next_prompt_mints_child_with_parent_id(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        # First iteration — should_pass, below must_pass default target.
        _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="should_pass", metric_value=0.5,
        )
        # Next prompt build mints the child.
        orch.build_lead_prompt(phase)
        reg = load_registry(delivery_repo / ".zo" / "experiments")
        exp_002 = reg.find("exp-002")
        assert exp_002 is not None
        assert exp_002.parent_id == "exp-001"
        # Parent completed, child running.
        assert reg.find("exp-001").status == "complete"
        assert exp_002.status == "running"


class TestAutoIterateStops:
    """Loop stops on TARGET_HIT, PLATEAU, or BUDGET."""

    def test_target_hit_stops_and_proceeds(self, tmp_path: Path) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        decision = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="must_pass", metric_value=0.1,
        )
        assert decision == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED

    def test_budget_exhausted_stops_and_proceeds(
        self, tmp_path: Path,
    ) -> None:
        # Tight budget — only 2 iterations allowed.
        spec = ExperimentLoopSpec(max_iterations=2)
        orch, delivery_repo = _build_orch(tmp_path, loop_spec=spec)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        # First iteration — auto-iterates (below target).
        d1 = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="should_pass", metric_value=0.5,
        )
        assert d1 == GateDecision.ITERATE

        # Second iteration — budget exhausted, must proceed.
        d2 = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-002", oracle_tier="should_pass", metric_value=0.4,
        )
        assert d2 == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED

    def test_plateau_stops_and_proceeds(self, tmp_path: Path) -> None:
        # Small plateau window so test is fast.
        spec = ExperimentLoopSpec(
            max_iterations=10,
            plateau_epsilon=0.1,
            plateau_runs=2,
        )
        orch, delivery_repo = _build_orch(tmp_path, loop_spec=spec)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        # Root run.
        d1 = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="should_pass", metric_value=0.50,
        )
        assert d1 == GateDecision.ITERATE

        # Child with tiny delta (0.50 -> 0.49 = -0.01, within epsilon 0.1).
        d2 = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-002", oracle_tier="should_pass", metric_value=0.49,
        )
        assert d2 == GateDecision.ITERATE

        # Second child with another tiny delta (0.49 -> 0.485, also within 0.1).
        # After this, 2 consecutive tiny deltas triggers plateau.
        d3 = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-003", oracle_tier="should_pass", metric_value=0.485,
        )
        assert d3 == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED


class TestDecisionLogging:
    def test_loop_decision_written_to_decision_log(
        self, tmp_path: Path,
    ) -> None:
        orch, delivery_repo = _build_orch(tmp_path)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="must_pass", metric_value=0.1,
        )

        # DECISION_LOG.md should mention the target_hit verdict.
        decision_log = (
            tmp_path / "project" / "memory" / "churn-prediction" / "DECISION_LOG.md"
        ).read_text(encoding="utf-8")
        assert "target_hit" in decision_log.lower() or "TARGET_HIT" in decision_log


class TestPolicyFromPlan:
    def test_plan_spec_overrides_defaults(self, tmp_path: Path) -> None:
        spec = ExperimentLoopSpec(stop_on_tier="should_pass")
        orch, delivery_repo = _build_orch(tmp_path, loop_spec=spec)
        phase = _phase_4(orch)
        _prepare_phase_artifacts(delivery_repo, phase)

        # With stop_on_tier=should_pass, a single should_pass result stops the loop.
        decision = _run_one_iteration(
            orch, phase, delivery_repo,
            exp_id="exp-001", oracle_tier="should_pass", metric_value=0.3,
        )
        assert decision == GateDecision.PROCEED
        assert phase.status == PhaseStatus.COMPLETED
