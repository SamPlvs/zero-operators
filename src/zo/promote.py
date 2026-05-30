"""Promote generic, client-sanitized learnings from a project to platform PRIORS.

Self-evolution closes the loop only if learnings discovered *during a project*
can lift the platform for the next one. This module does that promotion —
**automated** (no per-item approval) but **fail-closed**, because the platform
repo is public and client confidentiality is a legal non-negotiable.

A project's ``.zo/memory/PRIORS.md`` is read; each prior is screened and only
the ones that are unambiguously generic reach ``memory/zo-platform/PRIORS.md``:

* Only priors in generic categories (``auto-learning`` / ``evolution``) are
  candidates. Plan-seeded ``domain`` priors are project-specific by
  construction and are never promoted.
* Any prior whose text matches the client blocklist (the same
  ``scripts/.client-blocklist`` ``validate-docs`` uses) is **blocked** — not
  auto-stripped. Stripping a client term out of a sentence leaves garbled,
  misleading text and can miss adjacent project-specific words; refusing is
  safer. Blocked priors are reported so a human can rewrite them generically.
* If no blocklist file is present there is no client-term protection, so
  **nothing is promoted** and the report says why.

Every run returns a :class:`PromotionReport` (promoted / blocked+reason /
skipped-duplicate) so the automated promotion is fully auditable after the fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from zo._memory_formats import parse_priors, render_prior
from zo._memory_models import PriorEntry

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "PromotionReport",
    "load_blocklist",
    "screen_prior",
    "promote_learnings",
    "PROMOTABLE_CATEGORIES",
]

# Prior categories eligible for promotion. Everything else (notably the
# plan-seeded ``domain`` category) is treated as project-specific and skipped.
PROMOTABLE_CATEGORIES: frozenset[str] = frozenset({"auto-learning", "evolution"})

# Evidence markers that flag a prior as plan-seeded / project-local.
_PROJECT_LOCAL_EVIDENCE = ("seeded from plan",)

_BLOCKLIST_RELPATH = ("scripts", ".client-blocklist")


@dataclass
class PromotionReport:
    """Outcome of a promotion run — auditable record of every decision."""

    promoted: list[PriorEntry] = field(default_factory=list)
    blocked: list[tuple[PriorEntry, str]] = field(default_factory=list)
    skipped_duplicate: list[PriorEntry] = field(default_factory=list)
    blocklist_loaded: bool = False
    written: bool = False

    @property
    def summary(self) -> str:
        """One-line human summary."""
        return (
            f"{len(self.promoted)} promoted, {len(self.blocked)} blocked, "
            f"{len(self.skipped_duplicate)} duplicate "
            f"(blocklist {'loaded' if self.blocklist_loaded else 'MISSING'})"
        )


def load_blocklist(zo_root: Path) -> list[str]:
    """Load lowercased client-blocklist patterns from ``scripts/.client-blocklist``.

    Returns an empty list when the file is absent (gitignored / not yet
    configured). Comment (``#``) and blank lines are skipped.
    """
    path = zo_root.joinpath(*_BLOCKLIST_RELPATH)
    if not path.is_file():
        return []
    patterns: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            patterns.append(line.lower())
    return patterns


def _prior_text(prior: PriorEntry) -> str:
    """All free text of a prior, lowercased, for blocklist screening."""
    return f"{prior.category} {prior.statement} {prior.evidence}".lower()


def _matches_blocklist(prior: PriorEntry, blocklist: list[str]) -> str | None:
    """Return the offending pattern if the prior trips the blocklist, else None."""
    text = _prior_text(prior)
    for pattern in blocklist:
        try:
            hit = pattern in text or re.search(pattern, text) is not None
        except re.error:
            hit = pattern in text
        if hit:
            return pattern
    return None


def screen_prior(
    prior: PriorEntry, blocklist: list[str], *, blocklist_loaded: bool,
) -> tuple[bool, str]:
    """Decide whether a single prior may be promoted. Fail-closed.

    Returns ``(ok, reason)``. ``ok`` is True only for an unambiguously
    generic prior that clears the blocklist.
    """
    if not blocklist_loaded:
        return False, "no client blocklist configured — promotion refused"
    if prior.category not in PROMOTABLE_CATEGORIES:
        return False, f"category '{prior.category}' is not promotable (project-specific)"
    if any(m in prior.evidence.lower() for m in _PROJECT_LOCAL_EVIDENCE):
        return False, "plan-seeded prior (project-specific)"
    offending = _matches_blocklist(prior, blocklist)
    if offending is not None:
        return False, f"matches client blocklist pattern {offending!r}"
    return True, "clean"


def _genericized(prior: PriorEntry) -> PriorEntry:
    """Re-tag a promoted prior so no project-specific provenance leaks."""
    return PriorEntry(
        category=f"promoted/{prior.category}",
        statement=prior.statement,
        evidence="promoted from a project (client-sanitized)",
        confidence=prior.confidence,
    )


def promote_learnings(
    delivery_repo: Path, zo_root: Path, *, dry_run: bool = False,
) -> PromotionReport:
    """Promote clean generic priors from a project to platform PRIORS.

    Args:
        delivery_repo: Project/delivery repo root (reads
            ``{delivery_repo}/.zo/memory/PRIORS.md``).
        zo_root: ZO platform repo root (writes
            ``{zo_root}/memory/zo-platform/PRIORS.md``, reads the blocklist).
        dry_run: When True, screen and report but write nothing.

    Returns:
        A :class:`PromotionReport` recording every promote/block/dedup decision.
    """
    report = PromotionReport()
    blocklist = load_blocklist(zo_root)
    report.blocklist_loaded = bool(blocklist)

    src = delivery_repo / ".zo" / "memory" / "PRIORS.md"
    if not src.is_file():
        return report
    project_priors = parse_priors(src.read_text(encoding="utf-8"))

    platform_path = zo_root / "memory" / "zo-platform" / "PRIORS.md"
    existing = (
        parse_priors(platform_path.read_text(encoding="utf-8"))
        if platform_path.is_file() else []
    )
    seen = {p.statement.strip().lower() for p in existing}

    to_write: list[PriorEntry] = []
    for prior in project_priors:
        ok, reason = screen_prior(
            prior, blocklist, blocklist_loaded=report.blocklist_loaded,
        )
        if not ok:
            report.blocked.append((prior, reason))
            continue
        key = prior.statement.strip().lower()
        if key in seen:
            report.skipped_duplicate.append(prior)
            continue
        seen.add(key)
        report.promoted.append(prior)
        to_write.append(_genericized(prior))

    if to_write and not dry_run:
        platform_path.parent.mkdir(parents=True, exist_ok=True)
        with open(platform_path, "a", encoding="utf-8") as fh:
            for entry in to_write:
                if platform_path.stat().st_size > 0:
                    fh.write("\n")
                fh.write(render_prior(entry))
        report.written = True

    return report
