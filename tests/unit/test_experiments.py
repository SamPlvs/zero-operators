"""Unit tests for the experiment capture layer (zo.experiments)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

import pytest
from pydantic import ValidationError

from zo.experiments import (
    REGISTRY_FILENAME,
    SCHEMA_VERSION,
    Experiment,
    ExperimentRegistry,
    ExperimentResult,
    ExperimentStatus,
    PrimaryMetric,
    load_registry,
    mint_experiment,
    next_exp_id,
    parse_hypothesis_md,
    parse_next_md,
    parse_result_md,
    render_hypothesis_md,
    resolve_active_experiment_dir,
    save_registry,
    update_next_ideas,
    update_result,
    update_status,
)

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


class TestExperimentResultModel:
    def test_requires_tier_and_primary(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentResult.model_validate({})  # type: ignore[arg-type]

    def test_rejects_invalid_tier(self) -> None:
        with pytest.raises(ValidationError):
            ExperimentResult.model_validate({
                "oracle_tier": "shrug",
                "primary_metric": {"name": "mae", "value": 0.1},
            })

    def test_accepts_valid_tiers(self) -> None:
        for tier in ("must_pass", "should_pass", "could_pass", "fail"):
            ExperimentResult.model_validate({
                "oracle_tier": tier,
                "primary_metric": {"name": "mae", "value": 0.1},
            })

    def test_primary_metric_delta_default_none(self) -> None:
        result = ExperimentResult.model_validate({
            "oracle_tier": "should_pass",
            "primary_metric": {"name": "mae", "value": 0.1},
        })
        assert result.primary_metric.delta_vs_parent is None


class TestExperimentModel:
    def test_defaults(self) -> None:
        exp = Experiment(id="exp-001", phase="phase_4")
        assert exp.status == ExperimentStatus.RUNNING
        assert exp.parent_id is None
        assert exp.next_ideas == []
        assert exp.result is None

    def test_created_defaults_to_now(self) -> None:
        exp = Experiment(id="exp-001", phase="phase_4")
        assert (datetime.now(UTC) - exp.created).total_seconds() < 5


# ---------------------------------------------------------------------------
# Registry queries
# ---------------------------------------------------------------------------


class TestRegistryQueries:
    def _reg(self) -> ExperimentRegistry:
        e1 = Experiment(id="exp-001", phase="phase_4",
                        created=datetime(2026, 4, 1, tzinfo=UTC))
        e2 = Experiment(id="exp-002", phase="phase_4", parent_id="exp-001",
                        created=datetime(2026, 4, 2, tzinfo=UTC))
        e3 = Experiment(id="exp-003", phase="phase_4", parent_id="exp-001",
                        created=datetime(2026, 4, 3, tzinfo=UTC))
        e4 = Experiment(id="exp-004", phase="phase_3",
                        created=datetime(2026, 4, 4, tzinfo=UTC))
        return ExperimentRegistry(
            project="test", experiments=[e1, e2, e3, e4],
        )

    def test_find(self) -> None:
        reg = self._reg()
        assert reg.find("exp-002").id == "exp-002"
        assert reg.find("exp-999") is None

    def test_children_of(self) -> None:
        reg = self._reg()
        children = reg.children_of("exp-001")
        assert {c.id for c in children} == {"exp-002", "exp-003"}

    def test_latest_in_phase(self) -> None:
        reg = self._reg()
        assert reg.latest_in_phase("phase_4").id == "exp-003"
        assert reg.latest_in_phase("phase_3").id == "exp-004"
        assert reg.latest_in_phase("phase_9") is None

    def test_lineage_root_to_leaf(self) -> None:
        reg = self._reg()
        chain = reg.lineage("exp-002")
        assert [e.id for e in chain] == ["exp-001", "exp-002"]


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------


class TestRegistryIO:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        reg = load_registry(tmp_path, project="demo")
        assert reg.project == "demo"
        assert reg.experiments == []
        assert reg.schema_version == SCHEMA_VERSION

    def test_save_creates_file(self, tmp_path: Path) -> None:
        reg = ExperimentRegistry(project="demo")
        path = save_registry(tmp_path, reg)
        assert path.exists()
        assert path.name == REGISTRY_FILENAME

    def test_save_atomic_replaces_tmp(self, tmp_path: Path) -> None:
        reg = ExperimentRegistry(project="demo")
        save_registry(tmp_path, reg)
        # No leftover .tmp file from atomic write.
        tmps = list(tmp_path.glob(".*.tmp"))
        assert tmps == []

    def test_round_trip_preserves_experiments(self, tmp_path: Path) -> None:
        exp = Experiment(id="exp-001", phase="phase_4",
                         hypothesis="h", rationale="r",
                         artifacts_dir=str(tmp_path / "exp-001"))
        exp.result = ExperimentResult(
            oracle_tier="should_pass",
            primary_metric=PrimaryMetric(name="mae", value=0.3),
            secondary_metrics={"mae_t+1": 0.2},
            shortfalls=["overfits"],
        )
        original = ExperimentRegistry(project="demo", experiments=[exp])
        save_registry(tmp_path, original)
        loaded = load_registry(tmp_path)
        assert loaded.project == "demo"
        assert loaded.find("exp-001").hypothesis == "h"
        assert loaded.find("exp-001").result.shortfalls == ["overfits"]


# ---------------------------------------------------------------------------
# next_exp_id
# ---------------------------------------------------------------------------


class TestNextExpId:
    def test_empty_is_exp_001(self) -> None:
        assert next_exp_id(ExperimentRegistry(project="x")) == "exp-001"

    def test_increments_max_not_count(self) -> None:
        reg = ExperimentRegistry(project="x", experiments=[
            Experiment(id="exp-005", phase="phase_4"),
            Experiment(id="exp-002", phase="phase_4"),
        ])
        assert next_exp_id(reg) == "exp-006"

    def test_zero_padded_to_three_digits(self) -> None:
        reg = ExperimentRegistry(project="x", experiments=[
            Experiment(id=f"exp-{i:03d}", phase="phase_4") for i in range(1, 10)
        ])
        assert next_exp_id(reg) == "exp-010"


# ---------------------------------------------------------------------------
# mint_experiment
# ---------------------------------------------------------------------------


class TestMintExperiment:
    def test_creates_exp_dir(self, tmp_path: Path) -> None:
        exp = mint_experiment(
            tmp_path, project="demo", phase="phase_4",
            hypothesis="h", rationale="r",
        )
        assert (tmp_path / exp.id).is_dir()
        assert exp.artifacts_dir == str(tmp_path / exp.id)

    def test_appends_to_registry(self, tmp_path: Path) -> None:
        mint_experiment(tmp_path, project="demo", phase="phase_4")
        mint_experiment(tmp_path, project="demo", phase="phase_4")
        reg = load_registry(tmp_path)
        assert len(reg.experiments) == 2
        assert [e.id for e in reg.experiments] == ["exp-001", "exp-002"]

    def test_links_parent(self, tmp_path: Path) -> None:
        root = mint_experiment(tmp_path, project="demo", phase="phase_4")
        child = mint_experiment(
            tmp_path, project="demo", phase="phase_4", parent_id=root.id,
        )
        assert child.parent_id == root.id

    def test_status_initially_running(self, tmp_path: Path) -> None:
        exp = mint_experiment(tmp_path, project="demo", phase="phase_4")
        assert exp.status == ExperimentStatus.RUNNING

    def test_project_persisted_on_first_mint(self, tmp_path: Path) -> None:
        mint_experiment(tmp_path, project="demo", phase="phase_4")
        reg = load_registry(tmp_path)
        assert reg.project == "demo"


# ---------------------------------------------------------------------------
# update_result
# ---------------------------------------------------------------------------


class TestUpdateResult:
    def test_attaches_and_marks_complete(self, tmp_path: Path) -> None:
        exp = mint_experiment(tmp_path, project="demo", phase="phase_4")
        result = ExperimentResult(
            oracle_tier="should_pass",
            primary_metric=PrimaryMetric(name="mae", value=0.3),
        )
        updated = update_result(tmp_path, exp.id, result)
        assert updated.status == ExperimentStatus.COMPLETE
        assert updated.result.primary_metric.value == 0.3

    def test_computes_delta_vs_parent(self, tmp_path: Path) -> None:
        root = mint_experiment(tmp_path, project="demo", phase="phase_4")
        update_result(tmp_path, root.id, ExperimentResult(
            oracle_tier="fail",
            primary_metric=PrimaryMetric(name="mae", value=0.5),
        ))
        child = mint_experiment(
            tmp_path, project="demo", phase="phase_4", parent_id=root.id,
        )
        update_result(tmp_path, child.id, ExperimentResult(
            oracle_tier="should_pass",
            primary_metric=PrimaryMetric(name="mae", value=0.3),
        ))
        reg = load_registry(tmp_path)
        delta = reg.find(child.id).result.primary_metric.delta_vs_parent
        assert delta == pytest.approx(-0.2)

    def test_delta_not_overwritten_if_provided(self, tmp_path: Path) -> None:
        root = mint_experiment(tmp_path, project="demo", phase="phase_4")
        update_result(tmp_path, root.id, ExperimentResult(
            oracle_tier="fail",
            primary_metric=PrimaryMetric(name="mae", value=0.5),
        ))
        child = mint_experiment(
            tmp_path, project="demo", phase="phase_4", parent_id=root.id,
        )
        update_result(tmp_path, child.id, ExperimentResult(
            oracle_tier="should_pass",
            primary_metric=PrimaryMetric(
                name="mae", value=0.3, delta_vs_parent=-0.99,
            ),
        ))
        reg = load_registry(tmp_path)
        assert (
            reg.find(child.id).result.primary_metric.delta_vs_parent == -0.99
        )

    def test_delta_none_when_metric_names_differ(self, tmp_path: Path) -> None:
        root = mint_experiment(tmp_path, project="demo", phase="phase_4")
        update_result(tmp_path, root.id, ExperimentResult(
            oracle_tier="fail",
            primary_metric=PrimaryMetric(name="mae", value=0.5),
        ))
        child = mint_experiment(
            tmp_path, project="demo", phase="phase_4", parent_id=root.id,
        )
        update_result(tmp_path, child.id, ExperimentResult(
            oracle_tier="should_pass",
            primary_metric=PrimaryMetric(name="rmse", value=0.3),
        ))
        reg = load_registry(tmp_path)
        assert reg.find(child.id).result.primary_metric.delta_vs_parent is None

    def test_missing_exp_raises(self, tmp_path: Path) -> None:
        (tmp_path / REGISTRY_FILENAME).write_text(
            ExperimentRegistry(project="x").model_dump_json(),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="not found"):
            update_result(tmp_path, "exp-999", ExperimentResult(
                oracle_tier="fail",
                primary_metric=PrimaryMetric(name="mae", value=0.1),
            ))


class TestUpdateStatusAndNext:
    def test_update_status(self, tmp_path: Path) -> None:
        exp = mint_experiment(tmp_path, project="demo", phase="phase_4")
        update_status(tmp_path, exp.id, ExperimentStatus.FAILED)
        reg = load_registry(tmp_path)
        assert reg.find(exp.id).status == ExperimentStatus.FAILED

    def test_update_next_ideas(self, tmp_path: Path) -> None:
        exp = mint_experiment(tmp_path, project="demo", phase="phase_4")
        update_next_ideas(tmp_path, exp.id, ["exp-002: reg", "exp-003: aug"])
        reg = load_registry(tmp_path)
        assert reg.find(exp.id).next_ideas == [
            "exp-002: reg", "exp-003: aug",
        ]


# ---------------------------------------------------------------------------
# Markdown parsers
# ---------------------------------------------------------------------------


RESULT_MD_SAMPLE = """\
---
exp_id: exp-001
oracle_tier: should_pass
primary_metric:
  name: mae_t+3
  value: 0.34
  delta_vs_parent: -0.12
secondary_metrics:
  mae_t+1: 0.21
  mae_t+6: 0.48
evaluated_at: 2026-04-20T16:30:00+00:00
---

# Result

## Primary metric

MAE @ t+3: 0.34 — meets should_pass tier.

## Shortfalls

- Overfit after epoch 12
- Weak on regime-shift samples (<0.6 confidence on 15% of test set)
"""


class TestParseResultMd:
    def test_parses_primary_and_secondary(self, tmp_path: Path) -> None:
        path = tmp_path / "result.md"
        path.write_text(RESULT_MD_SAMPLE, encoding="utf-8")
        result = parse_result_md(path)
        assert result.oracle_tier == "should_pass"
        assert result.primary_metric.name == "mae_t+3"
        assert result.primary_metric.value == 0.34
        assert result.primary_metric.delta_vs_parent == -0.12
        assert result.secondary_metrics["mae_t+1"] == 0.21

    def test_parses_shortfalls_bullets(self, tmp_path: Path) -> None:
        path = tmp_path / "result.md"
        path.write_text(RESULT_MD_SAMPLE, encoding="utf-8")
        result = parse_result_md(path)
        assert len(result.shortfalls) == 2
        assert "Overfit" in result.shortfalls[0]

    def test_missing_frontmatter_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "result.md"
        path.write_text("# Result\n\njust markdown\n", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_result_md(path)

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "result.md"
        path.write_text(
            "---\noracle_tier: fail\n---\n# no primary metric\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="primary_metric"):
            parse_result_md(path)


HYPOTHESIS_MD_SAMPLE = """\
---
exp_id: exp-001
parent_id: null
created: 2026-04-20T15:15:00+00:00
---

# Hypothesis

TFT beats LSTM on long-horizon forecasts.

## Rationale

LSTM degrades past horizon-3 on this data.
The attention mechanism should capture longer dependencies.
"""


class TestParseHypothesisMd:
    def test_parses_hypothesis_and_rationale(self, tmp_path: Path) -> None:
        path = tmp_path / "hypothesis.md"
        path.write_text(HYPOTHESIS_MD_SAMPLE, encoding="utf-8")
        hypothesis, rationale = parse_hypothesis_md(path)
        assert "TFT beats LSTM" in hypothesis
        assert "attention mechanism" in rationale


NEXT_MD_SAMPLE = """\
# Next experiments

## exp-002
- Add weight decay 1e-4 and early stop at epoch 10
- Rationale: addresses overfit shortfall from exp-001

## exp-003
- Augment training with regime-shift oversampling
"""


class TestParseNextMd:
    def test_parses_per_exp_sections(self, tmp_path: Path) -> None:
        path = tmp_path / "next.md"
        path.write_text(NEXT_MD_SAMPLE, encoding="utf-8")
        ideas = parse_next_md(path)
        assert len(ideas) == 2
        assert ideas[0].startswith("exp-002:")
        assert "weight decay" in ideas[0]

    def test_falls_back_to_top_level_bullets(self, tmp_path: Path) -> None:
        path = tmp_path / "next.md"
        path.write_text(
            "# Next experiments\n\n- try bigger model\n- try smaller lr\n",
            encoding="utf-8",
        )
        ideas = parse_next_md(path)
        assert ideas == ["try bigger model", "try smaller lr"]


class TestRenderHypothesisMd:
    def test_round_trip_parses_back(self, tmp_path: Path) -> None:
        exp = Experiment(
            id="exp-001", phase="phase_4",
            hypothesis="TFT beats LSTM.",
            rationale="LSTM weak on long horizon.",
        )
        rendered = render_hypothesis_md(exp)
        path = tmp_path / "hypothesis.md"
        path.write_text(rendered, encoding="utf-8")
        h, r = parse_hypothesis_md(path)
        assert h == "TFT beats LSTM."
        assert r == "LSTM weak on long horizon."

    def test_placeholder_when_empty(self, tmp_path: Path) -> None:
        exp = Experiment(id="exp-001", phase="phase_4")
        rendered = render_hypothesis_md(exp)
        assert "TODO" in rendered


class TestResolveActiveExperimentDir:
    """Resolution rules for `zo watch-training` and the wrapper auto-split.

    The dashboard needs to point at the directory where ZOTrainingCallback
    is writing for the live (or most recently completed) Phase 4 run.
    """

    def _registry_dir(self, delivery: Path) -> Path:
        return delivery / ".zo" / "experiments"

    def test_returns_none_when_no_zo_dir(self, tmp_path: Path) -> None:
        # No .zo/ at all (delivery repo not yet initialised).
        assert resolve_active_experiment_dir(tmp_path) is None

    def test_returns_none_when_registry_missing(self, tmp_path: Path) -> None:
        # .zo/experiments/ exists but no registry.json yet.
        self._registry_dir(tmp_path).mkdir(parents=True)
        assert resolve_active_experiment_dir(tmp_path) is None

    def test_returns_none_when_registry_empty(self, tmp_path: Path) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        save_registry(reg_dir, ExperimentRegistry(project="demo"))
        assert resolve_active_experiment_dir(tmp_path) is None

    def test_returns_running_experiment(self, tmp_path: Path) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        exp = mint_experiment(reg_dir, project="demo", phase="phase_4")
        result = resolve_active_experiment_dir(tmp_path)
        assert result == Path(exp.artifacts_dir)

    def test_prefers_most_recent_running(self, tmp_path: Path) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        # Two running experiments; resolver picks the newest by `created`.
        first = mint_experiment(reg_dir, project="demo", phase="phase_4")
        second = mint_experiment(
            reg_dir, project="demo", phase="phase_4", parent_id=first.id,
        )
        # Force a strictly later created timestamp on `second` so the
        # comparison is deterministic regardless of system clock resolution.
        registry = load_registry(reg_dir)
        registry.find(second.id).created = datetime.now(UTC).replace(
            microsecond=999_999,
        )
        save_registry(reg_dir, registry)
        result = resolve_active_experiment_dir(tmp_path)
        assert result == Path(second.artifacts_dir)

    def test_falls_back_to_most_recent_complete(
        self, tmp_path: Path,
    ) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        exp = mint_experiment(reg_dir, project="demo", phase="phase_4")
        update_result(
            reg_dir,
            exp.id,
            ExperimentResult(
                oracle_tier="should_pass",
                primary_metric=PrimaryMetric(name="acc", value=0.95),
            ),
        )
        # No RUNNING experiments now — fall back to COMPLETE.
        result = resolve_active_experiment_dir(tmp_path)
        assert result == Path(exp.artifacts_dir)

    def test_running_preferred_over_complete(self, tmp_path: Path) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        # First experiment: complete.
        first = mint_experiment(reg_dir, project="demo", phase="phase_4")
        update_result(
            reg_dir,
            first.id,
            ExperimentResult(
                oracle_tier="could_pass",
                primary_metric=PrimaryMetric(name="acc", value=0.90),
            ),
        )
        # Second experiment: running. Resolver should pick this one even
        # though the complete one might be more recently mutated.
        second = mint_experiment(
            reg_dir, project="demo", phase="phase_4", parent_id=first.id,
        )
        result = resolve_active_experiment_dir(tmp_path)
        assert result == Path(second.artifacts_dir)

    def test_skips_failed_and_aborted(self, tmp_path: Path) -> None:
        reg_dir = self._registry_dir(tmp_path)
        reg_dir.mkdir(parents=True)
        failed = mint_experiment(reg_dir, project="demo", phase="phase_4")
        update_status(reg_dir, failed.id, ExperimentStatus.FAILED)
        aborted = mint_experiment(
            reg_dir, project="demo", phase="phase_4", parent_id=failed.id,
        )
        update_status(reg_dir, aborted.id, ExperimentStatus.ABORTED)
        # No RUNNING and no COMPLETE — return None, don't silently
        # surface a failed/aborted experiment as "active".
        assert resolve_active_experiment_dir(tmp_path) is None
