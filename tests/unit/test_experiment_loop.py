"""Unit tests for the autonomous experiment loop evaluator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from zo.experiment_loop import (
    DEFAULT_POLICY,
    DeadEndCheck,
    LoopDecision,
    LoopPolicy,
    LoopVerdict,
    check_dead_end,
    evaluate_loop_state,
    resolve_policy,
    tier_meets,
)
from zo.experiments import (
    Experiment,
    ExperimentRegistry,
    ExperimentResult,
    ExperimentStatus,
    PrimaryMetric,
)
from zo.plan import ExperimentLoopSpec

# ---------------------------------------------------------------------------
# tier_meets
# ---------------------------------------------------------------------------


class TestTierMeets:
    def test_must_pass_meets_any(self) -> None:
        assert tier_meets("must_pass", "must_pass") is True
        assert tier_meets("must_pass", "should_pass") is True
        assert tier_meets("must_pass", "could_pass") is True

    def test_should_pass_below_must(self) -> None:
        assert tier_meets("should_pass", "must_pass") is False
        assert tier_meets("should_pass", "should_pass") is True
        assert tier_meets("should_pass", "could_pass") is True

    def test_could_pass_is_lowest_passing(self) -> None:
        assert tier_meets("could_pass", "must_pass") is False
        assert tier_meets("could_pass", "should_pass") is False
        assert tier_meets("could_pass", "could_pass") is True

    def test_fail_meets_nothing(self) -> None:
        assert tier_meets("fail", "could_pass") is False
        assert tier_meets("fail", "should_pass") is False
        assert tier_meets("fail", "must_pass") is False

    def test_unknown_tier_treated_as_fail(self) -> None:
        assert tier_meets("wat", "could_pass") is False


# ---------------------------------------------------------------------------
# Helpers for building registries
# ---------------------------------------------------------------------------


def _exp(
    exp_id: str,
    *,
    phase: str = "phase_4",
    parent_id: str | None = None,
    tier: str | None = None,
    metric_value: float | None = None,
    delta_vs_parent: float | None = None,
    status: ExperimentStatus = ExperimentStatus.COMPLETE,
    minutes_ago: int = 0,
) -> Experiment:
    """Build an Experiment with optional result filled in."""
    created = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    result = None
    if tier is not None:
        result = ExperimentResult(
            oracle_tier=tier,
            primary_metric=PrimaryMetric(
                name="mae",
                value=metric_value if metric_value is not None else 0.5,
                delta_vs_parent=delta_vs_parent,
            ),
        )
    return Experiment(
        id=exp_id, phase=phase, parent_id=parent_id,
        status=status, result=result, created=created,
    )


def _registry(*exps: Experiment) -> ExperimentRegistry:
    return ExperimentRegistry(project="demo", experiments=list(exps))


# ---------------------------------------------------------------------------
# evaluate_loop_state — empty / initial
# ---------------------------------------------------------------------------


class TestLoopInitial:
    def test_empty_registry_continues(self) -> None:
        decision = evaluate_loop_state(_registry(), "phase_4")
        assert decision.verdict == LoopVerdict.CONTINUE
        assert decision.completed_count == 0
        assert decision.last_exp_id is None

    def test_no_complete_experiments_continues(self) -> None:
        reg = _registry(
            _exp("exp-001", status=ExperimentStatus.RUNNING),
        )
        decision = evaluate_loop_state(reg, "phase_4")
        assert decision.verdict == LoopVerdict.CONTINUE
        assert decision.completed_count == 0

    def test_only_counts_requested_phase(self) -> None:
        reg = _registry(
            _exp("exp-001", phase="phase_4", tier="should_pass",
                 minutes_ago=10),
            _exp("exp-002", phase="phase_5", tier="must_pass",
                 minutes_ago=5),
        )
        decision = evaluate_loop_state(reg, "phase_4")
        # exp-002 is in phase_5 — not counted; exp-001 didn't hit target.
        assert decision.verdict == LoopVerdict.CONTINUE
        assert decision.completed_count == 1
        assert decision.last_exp_id == "exp-001"


# ---------------------------------------------------------------------------
# TARGET_HIT priority
# ---------------------------------------------------------------------------


class TestTargetHit:
    def test_must_pass_hits_default_target(self) -> None:
        reg = _registry(_exp("exp-001", tier="must_pass"))
        decision = evaluate_loop_state(reg, "phase_4")
        assert decision.verdict == LoopVerdict.TARGET_HIT
        assert decision.last_exp_id == "exp-001"
        assert "must_pass" in decision.reason

    def test_should_pass_hits_lowered_target(self) -> None:
        reg = _registry(_exp("exp-001", tier="should_pass"))
        policy = LoopPolicy(stop_on_tier="should_pass")
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.TARGET_HIT

    def test_should_pass_does_not_hit_must_pass_target(self) -> None:
        reg = _registry(_exp("exp-001", tier="should_pass"))
        decision = evaluate_loop_state(reg, "phase_4")  # defaults to must_pass
        assert decision.verdict == LoopVerdict.CONTINUE

    def test_latest_only_considered(self) -> None:
        # Earlier exp hit must_pass, later did not — shouldn't target-hit.
        reg = _registry(
            _exp("exp-001", tier="must_pass", minutes_ago=10),
            _exp("exp-002", tier="should_pass", minutes_ago=5),
        )
        decision = evaluate_loop_state(reg, "phase_4")
        assert decision.verdict == LoopVerdict.CONTINUE
        assert decision.last_exp_id == "exp-002"


# ---------------------------------------------------------------------------
# BUDGET_EXHAUSTED
# ---------------------------------------------------------------------------


class TestBudget:
    def test_budget_exhausted_at_limit(self) -> None:
        policy = LoopPolicy(max_iterations=3)
        reg = _registry(*[
            _exp(f"exp-{i:03d}", tier="should_pass", minutes_ago=10 - i)
            for i in range(1, 4)
        ])
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.BUDGET_EXHAUSTED
        assert decision.completed_count == 3

    def test_under_budget_continues(self) -> None:
        policy = LoopPolicy(max_iterations=10)
        reg = _registry(
            _exp("exp-001", tier="should_pass", minutes_ago=5),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.CONTINUE

    def test_target_hit_beats_budget(self) -> None:
        # Budget exhausted AND latest hit target — TARGET_HIT wins (priority).
        policy = LoopPolicy(max_iterations=3)
        reg = _registry(
            _exp("exp-001", tier="fail", minutes_ago=30),
            _exp("exp-002", tier="should_pass", minutes_ago=20),
            _exp("exp-003", tier="must_pass", minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.TARGET_HIT


# ---------------------------------------------------------------------------
# PLATEAU detection
# ---------------------------------------------------------------------------


class TestPlateau:
    def test_three_small_deltas_trigger_plateau(self) -> None:
        # Root + 3 children all with near-zero delta.
        policy = LoopPolicy(plateau_epsilon=0.01, plateau_runs=3)
        reg = _registry(
            _exp("exp-001", tier="fail", delta_vs_parent=None, minutes_ago=40),
            _exp("exp-002", tier="fail", parent_id="exp-001",
                 delta_vs_parent=-0.002, minutes_ago=30),
            _exp("exp-003", tier="fail", parent_id="exp-002",
                 delta_vs_parent=0.001, minutes_ago=20),
            _exp("exp-004", tier="fail", parent_id="exp-003",
                 delta_vs_parent=-0.003, minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.PLATEAU

    def test_large_delta_breaks_plateau(self) -> None:
        policy = LoopPolicy(plateau_epsilon=0.01, plateau_runs=3)
        reg = _registry(
            _exp("exp-001", tier="fail", minutes_ago=40),
            _exp("exp-002", tier="fail", parent_id="exp-001",
                 delta_vs_parent=-0.002, minutes_ago=30),
            _exp("exp-003", tier="fail", parent_id="exp-002",
                 delta_vs_parent=-0.25, minutes_ago=20),  # big improvement
            _exp("exp-004", tier="fail", parent_id="exp-003",
                 delta_vs_parent=-0.003, minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.CONTINUE

    def test_plateau_needs_full_window(self) -> None:
        # Only 2 deltas available but policy asks for 3 — no plateau yet.
        policy = LoopPolicy(plateau_epsilon=0.01, plateau_runs=3)
        reg = _registry(
            _exp("exp-001", tier="fail", minutes_ago=20),
            _exp("exp-002", tier="fail", parent_id="exp-001",
                 delta_vs_parent=-0.001, minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        # Not enough history for plateau.
        assert decision.verdict == LoopVerdict.CONTINUE

    def test_plateau_ignores_missing_deltas(self) -> None:
        # Some children have None deltas — should NOT trigger plateau.
        policy = LoopPolicy(plateau_epsilon=0.01, plateau_runs=3)
        reg = _registry(
            _exp("exp-001", tier="fail", minutes_ago=40),
            _exp("exp-002", tier="fail", parent_id="exp-001",
                 delta_vs_parent=None, minutes_ago=30),
            _exp("exp-003", tier="fail", parent_id="exp-002",
                 delta_vs_parent=-0.001, minutes_ago=20),
            _exp("exp-004", tier="fail", parent_id="exp-003",
                 delta_vs_parent=-0.002, minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.CONTINUE

    def test_dead_end_when_all_recent_duplicate_earlier(self) -> None:
        # Root + 3 children that all rephrase the same earlier hypothesis.
        policy = LoopPolicy(
            plateau_epsilon=0.01, plateau_runs=3, dead_end_threshold=0.35,
        )
        # Avoid plateau by giving each child a large delta.
        reg = ExperimentRegistry(project="demo", experiments=[
            Experiment(
                id="exp-001", phase="phase_4", status=ExperimentStatus.COMPLETE,
                hypothesis="add attention to the recurrent model",
                created=datetime.now(UTC) - timedelta(minutes=50),
                result=ExperimentResult(
                    oracle_tier="fail",
                    primary_metric=PrimaryMetric(name="mae", value=0.5),
                ),
            ),
            Experiment(
                id="exp-002", phase="phase_4", status=ExperimentStatus.COMPLETE,
                hypothesis="add attention to recurrent model",  # near-dup
                created=datetime.now(UTC) - timedelta(minutes=30),
                result=ExperimentResult(
                    oracle_tier="fail",
                    primary_metric=PrimaryMetric(
                        name="mae", value=0.3, delta_vs_parent=-0.2,
                    ),
                ),
            ),
            Experiment(
                id="exp-003", phase="phase_4", status=ExperimentStatus.COMPLETE,
                hypothesis="attention added to recurrent model",  # near-dup
                created=datetime.now(UTC) - timedelta(minutes=20),
                result=ExperimentResult(
                    oracle_tier="fail",
                    primary_metric=PrimaryMetric(
                        name="mae", value=0.1, delta_vs_parent=-0.2,
                    ),
                ),
            ),
            Experiment(
                id="exp-004", phase="phase_4", status=ExperimentStatus.COMPLETE,
                hypothesis="recurrent model with attention added",  # near-dup
                created=datetime.now(UTC) - timedelta(minutes=10),
                result=ExperimentResult(
                    oracle_tier="fail",
                    primary_metric=PrimaryMetric(
                        name="mae", value=0.05, delta_vs_parent=-0.05,
                    ),
                ),
            ),
        ])
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.DEAD_END
        assert "Jaccard" in decision.reason

    def test_plateau_respected_only_after_target_miss(self) -> None:
        # Plateau conditions met AND target hit — TARGET_HIT wins.
        policy = LoopPolicy(plateau_epsilon=0.01, plateau_runs=3)
        reg = _registry(
            _exp("exp-001", tier="fail", minutes_ago=40),
            _exp("exp-002", tier="fail", parent_id="exp-001",
                 delta_vs_parent=-0.001, minutes_ago=30),
            _exp("exp-003", tier="fail", parent_id="exp-002",
                 delta_vs_parent=-0.002, minutes_ago=20),
            _exp("exp-004", tier="must_pass", parent_id="exp-003",
                 delta_vs_parent=-0.003, minutes_ago=10),
        )
        decision = evaluate_loop_state(reg, "phase_4", policy)
        assert decision.verdict == LoopVerdict.TARGET_HIT


# ---------------------------------------------------------------------------
# LoopPolicy defaults
# ---------------------------------------------------------------------------


class TestPolicyDefaults:
    def test_default_policy_values(self) -> None:
        assert DEFAULT_POLICY.max_iterations == 10
        assert DEFAULT_POLICY.plateau_epsilon == 0.01
        assert DEFAULT_POLICY.plateau_runs == 3
        assert DEFAULT_POLICY.stop_on_tier == "must_pass"
        assert DEFAULT_POLICY.dead_end_threshold == 0.9

    def test_policy_validates_stop_on_tier(self) -> None:
        # Invalid tier should fail validation.
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LoopPolicy(stop_on_tier="shrug")


class TestLoopDecisionShape:
    def test_decision_carries_fields(self) -> None:
        d = LoopDecision(
            verdict=LoopVerdict.CONTINUE,
            reason="why",
            last_exp_id="exp-001",
            completed_count=1,
        )
        assert d.verdict == "continue"
        assert d.reason == "why"
        assert d.last_exp_id == "exp-001"
        assert d.completed_count == 1


class TestResolvePolicy:
    def test_none_spec_returns_defaults(self) -> None:
        assert resolve_policy(None) is DEFAULT_POLICY

    def test_empty_spec_returns_defaults(self) -> None:
        assert resolve_policy(ExperimentLoopSpec()) is DEFAULT_POLICY

    def test_partial_spec_overrides_only_set_fields(self) -> None:
        spec = ExperimentLoopSpec(max_iterations=20, stop_on_tier="should_pass")
        policy = resolve_policy(spec)
        assert policy.max_iterations == 20
        assert policy.stop_on_tier == "should_pass"
        # Others unchanged.
        assert policy.plateau_epsilon == DEFAULT_POLICY.plateau_epsilon
        assert policy.plateau_runs == DEFAULT_POLICY.plateau_runs

    def test_full_spec_overrides_all(self) -> None:
        spec = ExperimentLoopSpec(
            max_iterations=5, plateau_epsilon=0.005, plateau_runs=2,
            stop_on_tier="could_pass", dead_end_threshold=0.8,
        )
        policy = resolve_policy(spec)
        assert policy.max_iterations == 5
        assert policy.plateau_epsilon == 0.005
        assert policy.plateau_runs == 2
        assert policy.stop_on_tier == "could_pass"
        assert policy.dead_end_threshold == 0.8


class TestResolvePolicyLowToken:
    """Low-token preset clamps and override precedence."""

    def test_low_token_clamps_when_no_spec(self) -> None:
        """low_token=True clamps max_iterations and stop_on_tier."""
        policy = resolve_policy(None, low_token=True)
        assert policy.max_iterations == 2
        assert policy.stop_on_tier == "could_pass"
        assert policy.low_token is True

    def test_low_token_off_keeps_defaults(self) -> None:
        """low_token=False (default) leaves DEFAULT_POLICY untouched."""
        policy = resolve_policy(None, low_token=False)
        assert policy is DEFAULT_POLICY
        assert policy.max_iterations == 10
        assert policy.stop_on_tier == "must_pass"

    def test_plan_spec_wins_over_low_token_clamp(self) -> None:
        """When low_token is on AND plan sets max_iterations,
        the plan value wins (low_token is a defaults layer, not a ceiling)."""
        spec = ExperimentLoopSpec(max_iterations=8)
        policy = resolve_policy(spec, low_token=True)
        # Plan said 8 — that wins over low_token's clamp of 2.
        assert policy.max_iterations == 8
        # stop_on_tier wasn't in plan — clamp still applies.
        assert policy.stop_on_tier == "could_pass"
        assert policy.low_token is True

    def test_cli_override_wins_over_plan_and_clamp(self) -> None:
        """CLI --max-iterations override beats plan and low_token clamp."""
        spec = ExperimentLoopSpec(max_iterations=8)
        policy = resolve_policy(
            spec, low_token=True, max_iterations_override=3,
        )
        assert policy.max_iterations == 3
        assert policy.stop_on_tier == "could_pass"

    def test_cli_override_alone_no_low_token(self) -> None:
        """--max-iterations works without --low-token."""
        policy = resolve_policy(None, max_iterations_override=4)
        assert policy.max_iterations == 4
        assert policy.stop_on_tier == "must_pass"
        assert policy.low_token is False


class TestParseExperimentLoopFromPlan:
    def test_parses_full_block(self) -> None:
        from zo.plan import _parse_experiment_loop

        body = """\
max_iterations: 15
plateau_epsilon: 0.005
plateau_runs: 4
stop_on_tier: should_pass
dead_end_threshold: 0.85
"""
        spec = _parse_experiment_loop(body)
        assert spec.max_iterations == 15
        assert spec.plateau_epsilon == 0.005
        assert spec.plateau_runs == 4
        assert spec.stop_on_tier == "should_pass"
        assert spec.dead_end_threshold == 0.85

    def test_parses_partial_block(self) -> None:
        from zo.plan import _parse_experiment_loop

        spec = _parse_experiment_loop("max_iterations: 7\n")
        assert spec.max_iterations == 7
        assert spec.stop_on_tier is None

    def test_ignores_invalid_numeric(self) -> None:
        from zo.plan import _parse_experiment_loop

        spec = _parse_experiment_loop("max_iterations: not-a-number\n")
        assert spec.max_iterations is None

    def test_ignores_unknown_keys(self) -> None:
        from zo.plan import _parse_experiment_loop

        spec = _parse_experiment_loop("nonsense: 42\nmax_iterations: 3\n")
        assert spec.max_iterations == 3

    def test_full_parse_plan_picks_up_experiment_loop_section(
        self, tmp_path,
    ) -> None:
        from zo.plan import parse_plan

        plan_text = """\
---
project_name: "demo"
version: "1.0"
created: "2026-04-20"
last_modified: "2026-04-20"
status: active
owner: "test"
---

## Objective

Demo.

## Oracle

**Primary metric:** acc
**Ground truth source:** labels
**Evaluation method:** holdout
**Target threshold:** > 0.9
**Evaluation frequency:** per-run

## Workflow

**Mode:** classical_ml

## Data Sources

### Source 1: primary
- **Location:** /data

## Domain Context and Priors

TODO.

## Agents

**Active agents:** data-engineer

## Constraints

TODO.

## Experiment Loop

max_iterations: 5
stop_on_tier: should_pass
"""
        plan_path = tmp_path / "plan.md"
        plan_path.write_text(plan_text, encoding="utf-8")
        plan = parse_plan(plan_path)
        assert plan.experiment_loop is not None
        assert plan.experiment_loop.max_iterations == 5
        assert plan.experiment_loop.stop_on_tier == "should_pass"


# ---------------------------------------------------------------------------
# check_dead_end
# ---------------------------------------------------------------------------


class TestCheckDeadEnd:
    def _registry_with_hypotheses(
        self, *hypotheses: tuple[str, str],
    ) -> ExperimentRegistry:
        """Build a registry from (exp_id, hypothesis) pairs."""
        exps = [
            Experiment(id=eid, phase="phase_4", hypothesis=h)
            for eid, h in hypotheses
        ]
        return ExperimentRegistry(project="demo", experiments=exps)

    def test_empty_registry_never_dead_end(self) -> None:
        reg = ExperimentRegistry(project="demo")
        check = check_dead_end(reg, "TFT beats LSTM on long horizon")
        assert check.is_dead_end is False
        assert check.nearest_exp_id is None
        assert check.score == 0.0

    def test_empty_candidate_returns_not_dead_end(self) -> None:
        reg = self._registry_with_hypotheses(("exp-001", "TFT beats LSTM"))
        check = check_dead_end(reg, "   ")
        assert check.is_dead_end is False

    def test_exact_duplicate_flagged(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "TFT beats LSTM on long horizon forecasts"),
        )
        check = check_dead_end(
            reg, "TFT beats LSTM on long horizon forecasts",
            threshold=0.9,
        )
        assert check.is_dead_end is True
        assert check.nearest_exp_id == "exp-001"
        assert check.score == 1.0

    def test_minor_rephrase_flagged(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "TFT beats LSTM on long horizon forecasts"),
        )
        # Same words rearranged + a filler — still very close.
        check = check_dead_end(
            reg, "On long horizon forecasts TFT beats LSTM",
            threshold=0.9,
        )
        assert check.is_dead_end is True

    def test_substantially_different_not_flagged(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "TFT beats LSTM on long horizon forecasts"),
        )
        check = check_dead_end(
            reg,
            "Adding regularization and early stopping reduces overfitting",
            threshold=0.9,
        )
        assert check.is_dead_end is False
        assert check.score < 0.5

    def test_lower_threshold_is_stricter(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "attention improves long horizon"),
        )
        # "attention helps long sequences" vs "attention improves long horizon":
        # intersection = {attention, long}, union = 6 tokens → Jaccard ≈ 0.33.
        # Threshold 0.3 flags, threshold 0.9 does not.
        check_strict = check_dead_end(
            reg, "attention helps long sequences", threshold=0.3,
        )
        check_lenient = check_dead_end(
            reg, "attention helps long sequences", threshold=0.9,
        )
        assert check_strict.is_dead_end is True
        assert check_lenient.is_dead_end is False

    def test_returns_best_match_not_first(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "completely unrelated claim about data"),
            ("exp-002", "TFT beats LSTM"),
        )
        check = check_dead_end(reg, "TFT beats LSTM on horizon")
        assert check.nearest_exp_id == "exp-002"

    def test_phase_filter(self) -> None:
        reg = ExperimentRegistry(
            project="demo",
            experiments=[
                Experiment(
                    id="exp-001", phase="phase_3",
                    hypothesis="TFT beats LSTM",
                ),
                Experiment(
                    id="exp-002", phase="phase_4",
                    hypothesis="TFT beats LSTM",
                ),
            ],
        )
        # Both experiments match perfectly; phase filter controls which wins.
        check = check_dead_end(
            reg, "TFT beats LSTM", phase="phase_4",
        )
        assert check.nearest_exp_id == "exp-002"
        assert check.is_dead_end is True

    def test_phase_filter_without_match_returns_none(self) -> None:
        reg = ExperimentRegistry(
            project="demo",
            experiments=[
                Experiment(
                    id="exp-001", phase="phase_3",
                    hypothesis="TFT beats LSTM",
                ),
            ],
        )
        # No phase_4 experiments to compare against.
        check = check_dead_end(
            reg, "TFT beats LSTM", phase="phase_4",
        )
        assert check.nearest_exp_id is None
        assert check.is_dead_end is False

    def test_exclude_exp_id_skips_self(self) -> None:
        reg = self._registry_with_hypotheses(
            ("exp-001", "TFT beats LSTM"),
            ("exp-002", "TFT beats LSTM"),
        )
        # Without exclude, would match exp-001. With exclude, skips it.
        check = check_dead_end(
            reg, "TFT beats LSTM", exclude_exp_id="exp-001",
        )
        assert check.nearest_exp_id == "exp-002"

    def test_dead_end_check_shape(self) -> None:
        check = DeadEndCheck(
            is_dead_end=True, nearest_exp_id="exp-001", score=0.95,
        )
        assert check.is_dead_end is True
        assert check.nearest_exp_id == "exp-001"
        assert check.score == 0.95
