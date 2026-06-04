"""Consolidate a surrogate session's deltas back into canonical project memory.

A surrogate (see :mod:`zo.surrogate`) accumulates its work in an isolated delta
store and a git branch while the primary session runs. Consolidation folds that
work back into the canonical project in two parts with different safety profiles:

* **Memory** — always, and flock-guarded so it is safe even while the primary
  session is live: append the surrogate's DECISION_LOG entries and
  de-duplicated PRIORS to canonical ``.zo/memory``, and copy its session
  summaries. Canonical STATE / the phase machine is **never** touched. A
  ``.consolidated`` marker makes the fold idempotent (a deferred merge will not
  re-fold memory).
* **Artifacts** — only when no other session is live, because ``git merge``
  mutates the shared working tree: commit any pending worktree changes onto the
  surrogate branch, merge the branch into the delivery repo's current branch,
  then remove the worktree. While another session is live this step is
  *deferred* (the branch + worktree are preserved and merged at the next safe
  consolidation — auto on last-close, or a later ``zo consolidate``).

Auto-consolidation fires when the last live session exits; ``zo consolidate``
triggers it manually. Both go through :func:`consolidate_all`. Everything stays
in the private delivery repo — nothing here touches the public platform repo.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from zo.memory import MemoryManager
from zo.surrogate import (
    SurrogateLayout,
    archive_surrogate,
    commit_worktree,
    live_sessions,
    load_surrogate,
    merge_branch,
    pending_surrogates,
    remove_worktree,
)

__all__ = ["ConsolidationReport", "consolidate_surrogate", "consolidate_all"]

_FOLD_MARKER = ".consolidated"


@dataclass
class ConsolidationReport:
    """Auditable record of one surrogate's consolidation."""

    surrogate_id: str
    decisions_folded: int = 0
    priors_folded: int = 0
    priors_skipped_dup: int = 0
    summaries_copied: int = 0
    merge_status: str = "skipped"  # merged | deferred | conflict | skipped
    worktree_removed: bool = False
    archived: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """One-line human summary."""
        return (
            f"{self.surrogate_id}: {self.decisions_folded} decisions, "
            f"{self.priors_folded} priors (+{self.priors_skipped_dup} dup), "
            f"{self.summaries_copied} summaries, merge={self.merge_status}"
        )


def _canonical_memory(delivery_repo: Path) -> MemoryManager:
    return MemoryManager(
        project_dir=delivery_repo,
        project_name="canonical",
        memory_root=delivery_repo / ".zo" / "memory",
    )


def _fold_marker(surrogate: SurrogateLayout) -> Path:
    return surrogate.memory_root / _FOLD_MARKER


def _copy_summaries(src_files: list[Path], dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_files:
        target = dst_dir / f.name
        if target.exists():
            target = dst_dir / f"{f.stem}-consolidated{f.suffix}"
        shutil.copy2(f, target)


def _fold_memory(
    surrogate: SurrogateLayout,
    delivery_repo: Path,
    *,
    dry_run: bool,
    report: ConsolidationReport,
) -> None:
    """Fold surrogate decisions/priors/summaries into canonical memory."""
    src = MemoryManager(
        project_dir=delivery_repo,
        project_name=surrogate.surrogate_id,
        memory_root=surrogate.memory_root,
    )
    dst = _canonical_memory(delivery_repo)

    decisions = src.read_decisions()
    seen = {p.statement.strip().lower() for p in dst.read_priors()}
    new_priors = []
    for p in src.read_priors():
        key = p.statement.strip().lower()
        if key in seen:
            report.priors_skipped_dup += 1
        else:
            seen.add(key)
            new_priors.append(p)

    sessions_dir = surrogate.memory_root / "sessions"
    src_sessions = (
        sorted(sessions_dir.glob("*.md")) if sessions_dir.is_dir() else []
    )

    report.decisions_folded = len(decisions)
    report.priors_folded = len(new_priors)
    report.summaries_copied = len(src_sessions)

    if dry_run:
        return

    for d in decisions:
        dst.append_decision(d)
    for p in new_priors:
        dst.append_prior(p)
    _copy_summaries(src_sessions, delivery_repo / ".zo" / "memory" / "sessions")
    # Marker last: makes the fold idempotent across deferred re-runs.
    _fold_marker(surrogate).write_text(
        datetime.now(UTC).isoformat() + "\n", encoding="utf-8",
    )


def consolidate_surrogate(
    delivery_repo: Path,
    surrogate_id: str,
    *,
    allow_branch_merge: bool = True,
    dry_run: bool = False,
) -> ConsolidationReport:
    """Fold one surrogate's memory and (when safe) merge its branch.

    Args:
        delivery_repo: The main delivery repo.
        surrogate_id: The surrogate to consolidate.
        allow_branch_merge: When False, never merge the branch (memory only).
        dry_run: Report what would happen without writing anything.

    Returns:
        A :class:`ConsolidationReport`.
    """
    delivery_repo = Path(delivery_repo).resolve()
    report = ConsolidationReport(surrogate_id=surrogate_id)
    surrogate = load_surrogate(delivery_repo, surrogate_id)
    if surrogate is None:
        report.notes.append("unknown surrogate")
        return report

    # 1. Memory fold (idempotent via marker; flock-safe even while primary live).
    if _fold_marker(surrogate).exists():
        report.notes.append("memory already folded in a prior consolidation")
    else:
        _fold_memory(surrogate, delivery_repo, dry_run=dry_run, report=report)

    # 2. Capture any uncommitted artifacts onto the surrogate branch.
    if (
        not dry_run
        and surrogate.worktree.exists()
        and commit_worktree(
            surrogate.worktree, message=f"report: {surrogate_id} artifacts",
        )
    ):
        report.notes.append("committed pending worktree artifacts")

    # 3. Branch merge — only when no other live session (it mutates the tree).
    safe = len(live_sessions(delivery_repo)) == 0
    if not (allow_branch_merge and safe):
        report.merge_status = "deferred"
        report.notes.append(
            "branch merge deferred — another session is live"
            if not safe
            else "branch merge disabled by caller"
        )
    elif dry_run:
        report.merge_status = "merged"  # would merge
    else:
        ok, detail = merge_branch(
            delivery_repo,
            surrogate.branch,
            message=f"consolidate: merge {surrogate.branch}",
        )
        if ok:
            report.merge_status = "merged"
            report.worktree_removed = remove_worktree(delivery_repo, surrogate.worktree)
        else:
            report.merge_status = "conflict"
            report.notes.append(f"merge failed: {detail[:200]}")

    # 4. Archive only when fully merged (deferred/conflict keep their state so a
    #    later consolidation can finish — the fold marker prevents double-fold).
    if not dry_run and report.merge_status == "merged":
        report.archived = archive_surrogate(delivery_repo, surrogate_id) is not None

    return report


def consolidate_all(
    delivery_repo: Path,
    *,
    allow_branch_merge: bool = True,
    dry_run: bool = False,
) -> list[ConsolidationReport]:
    """Consolidate every pending surrogate in the delivery repo."""
    delivery_repo = Path(delivery_repo).resolve()
    return [
        consolidate_surrogate(
            delivery_repo,
            sid,
            allow_branch_merge=allow_branch_merge,
            dry_run=dry_run,
        )
        for sid in pending_surrogates(delivery_repo)
    ]
