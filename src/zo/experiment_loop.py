"""Autonomous iteration loop for Phase 4 experiments.

After an experiment's `result.md` lands and is finalized, this module
decides whether to auto-mint a child and keep iterating, or stop. The
decision is driven by a ``LoopPolicy`` (defaults or plan-supplied)
evaluated against the experiment registry.

Stop conditions, in priority order:

1. **TARGET_HIT** — latest completed experiment's ``oracle_tier`` meets or
   exceeds ``policy.stop_on_tier``. We've achieved what the plan asked for.
2. **BUDGET_EXHAUSTED** — completed experiment count in the phase has
   reached ``policy.max_iterations``.
3. **PLATEAU** — the last ``policy.plateau_runs`` completed children
   (in chronological order) all have ``|delta_vs_parent|`` below
   ``policy.plateau_epsilon``. No further improvement coming.
4. **DEAD_END** — orchestrator-supplied signal that Model Builder could
   not draft a novel hypothesis (all candidates near-dupe previous
   experiments via semantic match).
5. **CONTINUE** — none of the above; auto-mint the next child.

When the verdict is CONTINUE, the orchestrator keeps the phase ACTIVE
and the next ``build_lead_prompt`` mints a child experiment with
``parent_id`` set to the latest completed exp.

The loop respects the gate mode (see ``zo.orchestrator``):

* ``supervised`` — loop disabled, every gate pauses for a human.
* ``auto`` — loop runs through AUTOMATED gates (phase_4 is automated),
  still pauses at BLOCKING gates (phase_5).
* ``full_auto`` — loop runs uninterrupted.

Typical usage (inside the orchestrator)::

    from zo.experiment_loop import evaluate_loop_state, LoopVerdict
    decision = evaluate_loop_state(registry, phase_id, policy)
    if decision.verdict == LoopVerdict.CONTINUE:
        # keep phase ACTIVE so next build_lead_prompt mints a child
        ...
    else:
        # stop — mark phase COMPLETED, log the verdict, advance
        ...
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from zo.experiments import ExperimentRegistry, ExperimentStatus

__all__ = [
    "LoopVerdict",
    "LoopPolicy",
    "LoopDecision",
    "DeadEndCheck",
    "evaluate_loop_state",
    "resolve_policy",
    "tier_meets",
    "check_dead_end",
    "DEFAULT_POLICY",
]


class LoopVerdict(StrEnum):
    """Stop/continue verdict from the loop evaluator."""

    CONTINUE = "continue"
    TARGET_HIT = "target_hit"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PLATEAU = "plateau"
    DEAD_END = "dead_end"
    HUMAN_STOP = "human_stop"


_TIER_ORDER = {"fail": 0, "could_pass": 1, "should_pass": 2, "must_pass": 3}


def tier_meets(actual: str, target: str) -> bool:
    """Return True when ``actual`` oracle tier meets or exceeds ``target``.

    Tiers ordered: ``fail`` < ``could_pass`` < ``should_pass`` < ``must_pass``.
    An actual of ``must_pass`` meets any target; ``could_pass`` only meets
    ``could_pass`` or below.
    """
    return _TIER_ORDER.get(actual, 0) >= _TIER_ORDER.get(target, 0)


class LoopPolicy(BaseModel):
    """Knobs that govern when the autonomous loop stops.

    Attributes:
        max_iterations: Hard cap on completed experiments per phase.
            When the loop reaches this count, stops with
            ``BUDGET_EXHAUSTED`` even if the oracle target wasn't hit.
        plateau_epsilon: Absolute threshold on ``|delta_vs_parent|``.
            When the last ``plateau_runs`` children all fall below this,
            the loop stops with ``PLATEAU``.
        plateau_runs: How many consecutive small-delta children trigger
            plateau detection. Must be >= 1.
        stop_on_tier: The first oracle tier at which the loop is
            considered "done". When the latest experiment's tier meets
            or exceeds this, the loop stops with ``TARGET_HIT``.
        dead_end_threshold: Cosine-similarity threshold above which a
            candidate hypothesis is treated as a near-duplicate of a
            past one. Used by ``check_dead_end`` in the orchestrator.
    """

    max_iterations: int = 10
    plateau_epsilon: float = 0.01
    plateau_runs: int = 3
    stop_on_tier: Literal["must_pass", "should_pass", "could_pass"] = "must_pass"
    dead_end_threshold: float = 0.9
    low_token: bool = False

    model_config = {"use_enum_values": True}


DEFAULT_POLICY = LoopPolicy()
"""The out-of-box policy used when plan.md does not override."""


# Low-token preset: clamps applied when ``low_token=True`` and the plan
# does not explicitly override the field. Plan overrides win — this is
# a "sensible defaults" layer, not a hard ceiling.
_LOW_TOKEN_LOOP_CLAMPS: dict[str, object] = {
    "max_iterations": 2,
    "stop_on_tier": "could_pass",
}


def resolve_policy(
    spec: object | None,
    *,
    low_token: bool = False,
    max_iterations_override: int | None = None,
) -> LoopPolicy:
    """Merge a plan-declared ``ExperimentLoopSpec`` onto ``DEFAULT_POLICY``.

    Accepts ``Plan.experiment_loop`` (a sparse ``ExperimentLoopSpec``)
    or ``None``. Fields the plan left unset fall back to the defaults.
    Kept as ``object`` in the signature to avoid a circular import on
    ``zo.plan`` — the caller passes whatever the plan parsed.

    Precedence (highest first): CLI overrides > plan spec > low_token
    clamp > base default.

    Args:
        spec: Plan-level ``ExperimentLoopSpec`` (or None).
        low_token: When True, applies the low-token clamps
            (``max_iterations=2``, ``stop_on_tier='could_pass'``)
            BEFORE the plan overrides — so plan fields still win.
        max_iterations_override: Hard cap from a CLI flag
            (``--max-iterations``). Wins over plan spec and clamp.

    Example::

        policy = resolve_policy(plan.experiment_loop, low_token=True)
        decision = evaluate_loop_state(registry, "phase_4", policy)
    """
    base = DEFAULT_POLICY.model_dump()
    if low_token:
        base.update(_LOW_TOKEN_LOOP_CLAMPS)
        base["low_token"] = True

    overrides: dict[str, object] = {}
    if spec is not None:
        for field_name in LoopPolicy.model_fields:
            value = getattr(spec, field_name, None)
            if value is not None:
                overrides[field_name] = value
    if max_iterations_override is not None:
        overrides["max_iterations"] = max_iterations_override
    if not overrides and not low_token:
        return DEFAULT_POLICY
    return LoopPolicy(**{**base, **overrides})


class LoopDecision(BaseModel):
    """Verdict returned by ``evaluate_loop_state``.

    Attributes:
        verdict: The stop/continue decision.
        reason: Human-readable justification logged to DECISION_LOG.
        last_exp_id: ID of the most recent completed experiment in the
            phase, or ``None`` when no experiments exist yet.
        completed_count: How many experiments in the phase have
            ``status == COMPLETE``.
        evaluated_at: Decision timestamp for audit trails.
    """

    verdict: LoopVerdict
    reason: str
    last_exp_id: str | None = None
    completed_count: int = 0
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"use_enum_values": True}


def evaluate_loop_state(
    registry: ExperimentRegistry,
    phase: str,
    policy: LoopPolicy | None = None,
) -> LoopDecision:
    """Evaluate whether to continue iterating or stop.

    Called by the orchestrator after a phase_4 gate finalizes an
    experiment. When the verdict is CONTINUE, the orchestrator should
    keep the phase ACTIVE so the next lead prompt mints a child exp.
    Any other verdict means the phase is done — advance to the next
    phase (and log the verdict to DECISION_LOG).

    Args:
        registry: The experiment registry (loaded from
            ``.zo/experiments/registry.json``).
        phase: Phase identifier, typically ``"phase_4"``.
        policy: Loop knobs. ``None`` uses ``DEFAULT_POLICY``.

    Returns:
        A ``LoopDecision`` with the verdict, a human-readable reason,
        the latest exp id, and the completed experiment count.
    """
    policy = policy or DEFAULT_POLICY

    completed = [
        e for e in registry.experiments
        if e.phase == phase and e.status == ExperimentStatus.COMPLETE
    ]
    if not completed:
        return LoopDecision(
            verdict=LoopVerdict.CONTINUE,
            reason="No completed experiments yet — continue with first iteration.",
            completed_count=0,
        )

    latest = max(completed, key=lambda e: e.created)
    completed_count = len(completed)

    # Priority 1: target tier hit.
    if (
        latest.result is not None
        and tier_meets(latest.result.oracle_tier, policy.stop_on_tier)
    ):
        return LoopDecision(
            verdict=LoopVerdict.TARGET_HIT,
            reason=(
                f"{latest.id} hit oracle tier '{latest.result.oracle_tier}' "
                f"(policy target: '{policy.stop_on_tier}'). "
                f"Completed {completed_count} experiment(s)."
            ),
            last_exp_id=latest.id,
            completed_count=completed_count,
        )

    # Priority 2: budget exhausted.
    if completed_count >= policy.max_iterations:
        return LoopDecision(
            verdict=LoopVerdict.BUDGET_EXHAUSTED,
            reason=(
                f"Reached iteration budget: {completed_count}/"
                f"{policy.max_iterations} completed without hitting "
                f"'{policy.stop_on_tier}'."
            ),
            last_exp_id=latest.id,
            completed_count=completed_count,
        )

    # Priority 3: plateau detection.
    if completed_count >= policy.plateau_runs + 1:
        last_n = sorted(completed, key=lambda e: e.created)[-policy.plateau_runs:]
        deltas: list[float] = [
            e.result.primary_metric.delta_vs_parent
            for e in last_n
            if e.result is not None
            and e.result.primary_metric.delta_vs_parent is not None
        ]
        if (
            len(deltas) == policy.plateau_runs
            and all(abs(d) < policy.plateau_epsilon for d in deltas)
        ):
            return LoopDecision(
                verdict=LoopVerdict.PLATEAU,
                reason=(
                    f"Last {policy.plateau_runs} deltas all < "
                    f"{policy.plateau_epsilon}: "
                    f"{[round(d, 6) for d in deltas]}. "
                    f"No meaningful improvement over the most recent run."
                ),
                last_exp_id=latest.id,
                completed_count=completed_count,
            )

    # Priority 4: dead-end — recent hypotheses all near-duplicates of earlier.
    if completed_count >= policy.plateau_runs + 1:
        last_n = sorted(completed, key=lambda e: e.created)[-policy.plateau_runs:]
        earlier = [
            e for e in sorted(completed, key=lambda e: e.created)
            if e.created < last_n[0].created and e.hypothesis
        ]
        if earlier and all(e.hypothesis for e in last_n):
            # For each recent exp, score against earlier exps; if every
            # recent child scored >= threshold against some earlier
            # hypothesis, Model Builder is stuck rephrasing.
            all_duplicates = True
            matches: list[tuple[str, str, float]] = []
            for recent in last_n:
                best_id: str | None = None
                best_score = 0.0
                recent_tokens = _tokenize(recent.hypothesis)
                for older in earlier:
                    score = _jaccard(recent_tokens, _tokenize(older.hypothesis))
                    if score > best_score:
                        best_score = score
                        best_id = older.id
                if best_score < policy.dead_end_threshold:
                    all_duplicates = False
                    break
                matches.append((recent.id, best_id or "", best_score))
            if all_duplicates:
                match_summary = ", ".join(
                    f"{r}≈{o} ({s:.2f})" for r, o, s in matches
                )
                return LoopDecision(
                    verdict=LoopVerdict.DEAD_END,
                    reason=(
                        f"Last {policy.plateau_runs} hypotheses all "
                        f">= {policy.dead_end_threshold} Jaccard similar "
                        f"to an earlier experiment: {match_summary}. "
                        f"Stuck rephrasing; stop and escalate."
                    ),
                    last_exp_id=latest.id,
                    completed_count=completed_count,
                )

    # Continue by default.
    tier_text = (
        latest.result.oracle_tier if latest.result is not None else "pending"
    )
    return LoopDecision(
        verdict=LoopVerdict.CONTINUE,
        reason=(
            f"Latest: {latest.id} at '{tier_text}' (target: "
            f"'{policy.stop_on_tier}'). Budget: {completed_count}/"
            f"{policy.max_iterations}. Continue."
        ),
        last_exp_id=latest.id,
        completed_count=completed_count,
    )


# ---------------------------------------------------------------------------
# Dead-end detection
# ---------------------------------------------------------------------------


class DeadEndCheck(BaseModel):
    """Result of checking a candidate hypothesis against past experiments.

    Attributes:
        is_dead_end: True when similarity to some past hypothesis >=
            policy threshold.
        nearest_exp_id: ID of the most similar past experiment (or
            ``None`` when the registry is empty).
        score: Similarity in ``[0, 1]`` where 1 is identical.
    """

    is_dead_end: bool
    nearest_exp_id: str | None
    score: float


_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> frozenset[str]:
    """Lowercase word tokens (alphanumeric + underscore)."""
    return frozenset(_WORD_RE.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two token sets; 0 when both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def check_dead_end(
    registry: ExperimentRegistry,
    candidate_text: str,
    *,
    threshold: float = 0.9,
    phase: str | None = None,
    exclude_exp_id: str | None = None,
) -> DeadEndCheck:
    """Check whether ``candidate_text`` is a near-duplicate of a past hypothesis.

    Uses token-set Jaccard similarity — deterministic, dependency-free,
    good enough to catch obvious rephrasings (the common failure mode
    of autonomous proposers recycling past ideas). When ``fastembed``
    is available in the broader system we could upgrade to embedding
    cosine; Jaccard already fires on the cases that matter most.

    Args:
        registry: Experiment registry to compare against.
        candidate_text: The proposed hypothesis (typically the body of
            a freshly-written ``hypothesis.md``).
        threshold: Jaccard similarity at or above which the candidate
            is flagged. ``0.9`` is strict (very close rephrasings).
        phase: Restrict comparison to experiments in this phase. When
            ``None``, compares against the whole registry.
        exclude_exp_id: Skip this exp when comparing (useful when the
            candidate has already been written into some exp's
            ``hypothesis.md`` and we don't want self-match).

    Returns:
        A ``DeadEndCheck`` with ``is_dead_end`` flag, nearest match id,
        and the similarity score.
    """
    cand_tokens = _tokenize(candidate_text)
    if not cand_tokens:
        return DeadEndCheck(is_dead_end=False, nearest_exp_id=None, score=0.0)

    best_id: str | None = None
    best_score = 0.0
    for exp in registry.experiments:
        if exp.id == exclude_exp_id:
            continue
        if phase is not None and exp.phase != phase:
            continue
        if not exp.hypothesis:
            continue
        score = _jaccard(cand_tokens, _tokenize(exp.hypothesis))
        if score > best_score:
            best_score = score
            best_id = exp.id

    return DeadEndCheck(
        is_dead_end=best_score >= threshold,
        nearest_exp_id=best_id,
        score=round(best_score, 4),
    )
