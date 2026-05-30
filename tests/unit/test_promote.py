"""Unit tests for the learnings promotion sanitizer (zo.promote).

The promoter writes to the PUBLIC platform repo, so these tests are
adversarial: a client identifier in a prior must be BLOCKED, project-local
priors must never promote, and with no blocklist configured nothing
promotes (fail-closed).
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

from zo._memory_formats import render_prior
from zo._memory_models import Confidence, PriorEntry
from zo.promote import (
    PROMOTABLE_CATEGORIES,
    load_blocklist,
    promote_learnings,
    screen_prior,
)


def _prior(
    category: str, statement: str, evidence: str = "",
) -> PriorEntry:
    return PriorEntry(
        category=category, statement=statement, evidence=evidence,
        confidence=Confidence.MEDIUM,
    )


def _setup(
    tmp_path: Path,
    priors: list[PriorEntry],
    *,
    blocklist: tuple[str, ...] | None = ("acme", "widgetco"),
    platform_existing: tuple[PriorEntry, ...] = (),
) -> tuple[Path, Path]:
    """Build a delivery repo + zo_root; return (delivery_repo, zo_root)."""
    zo_root = tmp_path / "zo"
    (zo_root / "scripts").mkdir(parents=True)
    if blocklist is not None:
        (zo_root / "scripts" / ".client-blocklist").write_text(
            "# client blocklist\n" + "\n".join(blocklist) + "\n",
            encoding="utf-8",
        )
    platform = zo_root / "memory" / "zo-platform"
    platform.mkdir(parents=True)
    (platform / "PRIORS.md").write_text(
        "\n".join(render_prior(p) for p in platform_existing), encoding="utf-8",
    )
    delivery = tmp_path / "proj"
    mem = delivery / ".zo" / "memory"
    mem.mkdir(parents=True)
    (mem / "PRIORS.md").write_text(
        "\n".join(render_prior(p) for p in priors), encoding="utf-8",
    )
    return delivery, zo_root


class TestLoadBlocklist:
    def test_reads_patterns_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / ".client-blocklist").write_text(
            "# header\nAcme\n\nWidgetCo\n", encoding="utf-8",
        )
        assert load_blocklist(tmp_path) == ["acme", "widgetco"]

    def test_absent_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_blocklist(tmp_path) == []


class TestScreenPrior:
    def test_clean_generic_passes(self) -> None:
        ok, _ = screen_prior(
            _prior("auto-learning", "Diversify the approach earlier"),
            ["acme"], blocklist_loaded=True,
        )
        assert ok is True

    def test_domain_category_blocked(self) -> None:
        ok, reason = screen_prior(
            _prior("domain", "anything"), ["acme"], blocklist_loaded=True,
        )
        assert ok is False
        assert "not promotable" in reason

    def test_plan_seeded_blocked(self) -> None:
        ok, reason = screen_prior(
            _prior("auto-learning", "x", evidence="seeded from plan.md"),
            ["acme"], blocklist_loaded=True,
        )
        assert ok is False
        assert "plan-seeded" in reason

    def test_blocklist_hit_in_statement_blocked(self) -> None:
        ok, reason = screen_prior(
            _prior("auto-learning", "On Acme the model overfit"),
            ["acme"], blocklist_loaded=True,
        )
        assert ok is False
        assert "blocklist" in reason

    def test_blocklist_hit_case_insensitive(self) -> None:
        ok, _ = screen_prior(
            _prior("auto-learning", "ACME had an issue"),
            ["acme"], blocklist_loaded=True,
        )
        assert ok is False

    def test_no_blocklist_blocks_everything(self) -> None:
        ok, reason = screen_prior(
            _prior("auto-learning", "totally generic learning"),
            [], blocklist_loaded=False,
        )
        assert ok is False
        assert "no client blocklist" in reason

    def test_promotable_categories_exclude_domain(self) -> None:
        assert "auto-learning" in PROMOTABLE_CATEGORIES
        assert "domain" not in PROMOTABLE_CATEGORIES


class TestPromoteLearnings:
    def test_clean_prior_promoted_and_genericized(self, tmp_path: Path) -> None:
        delivery, zo_root = _setup(
            tmp_path,
            [_prior("auto-learning", "Diversify approach earlier", "phase_4 dead_end")],
        )
        report = promote_learnings(delivery, zo_root)
        assert len(report.promoted) == 1
        assert report.written is True
        platform = (zo_root / "memory" / "zo-platform" / "PRIORS.md").read_text(
            encoding="utf-8",
        )
        assert "Diversify approach earlier" in platform
        # Provenance genericized — the project-specific evidence is gone.
        assert "promoted from a project" in platform
        assert "phase_4 dead_end" not in platform

    def test_domain_and_blocklisted_blocked(self, tmp_path: Path) -> None:
        delivery, zo_root = _setup(tmp_path, [
            _prior("auto-learning", "Clean generic learning"),
            _prior("domain", "Bearing BPFO is diagnostic", "seeded from plan.md"),
            _prior("auto-learning", "Acme reactor overfit fast"),
        ])
        report = promote_learnings(delivery, zo_root)
        assert len(report.promoted) == 1
        assert len(report.blocked) == 2

    def test_no_blocklist_promotes_nothing(self, tmp_path: Path) -> None:
        delivery, zo_root = _setup(
            tmp_path, [_prior("auto-learning", "generic")], blocklist=None,
        )
        report = promote_learnings(delivery, zo_root)
        assert report.promoted == []
        assert report.blocklist_loaded is False
        assert len(report.blocked) == 1

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        delivery, zo_root = _setup(
            tmp_path, [_prior("auto-learning", "generic learning")],
        )
        platform_path = zo_root / "memory" / "zo-platform" / "PRIORS.md"
        before = platform_path.read_text(encoding="utf-8")
        report = promote_learnings(delivery, zo_root, dry_run=True)
        assert len(report.promoted) == 1
        assert report.written is False
        assert platform_path.read_text(encoding="utf-8") == before

    def test_dedup_against_existing_platform(self, tmp_path: Path) -> None:
        existing = (_prior("promoted/auto-learning", "Diversify earlier", "x"),)
        delivery, zo_root = _setup(
            tmp_path, [_prior("auto-learning", "Diversify earlier")],
            platform_existing=existing,
        )
        report = promote_learnings(delivery, zo_root)
        assert report.promoted == []
        assert len(report.skipped_duplicate) == 1

    def test_missing_source_priors_empty_report(self, tmp_path: Path) -> None:
        zo_root = tmp_path / "zo"
        (zo_root / "scripts").mkdir(parents=True)
        (zo_root / "scripts" / ".client-blocklist").write_text(
            "acme\n", encoding="utf-8",
        )
        (zo_root / "memory" / "zo-platform").mkdir(parents=True)
        delivery = tmp_path / "proj"
        delivery.mkdir()
        report = promote_learnings(delivery, zo_root)
        assert report.promoted == []
        assert report.blocked == []
