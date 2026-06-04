"""Edge-case + safety tests for the surrogate/consolidation mechanism.

Covers the claims that the happy-path tests don't: concurrent appends under the
flock (the "consolidate while the model session is live" guarantee), merge
conflicts, resume-after-worktree-prune, and the canonical-STATE-untouched
boundary.
"""

from __future__ import annotations

import subprocess
import threading
from typing import TYPE_CHECKING

import pytest

from zo import surrogate as sg
from zo._memory_formats import parse_decisions
from zo.consolidate import consolidate_surrogate
from zo.memory import DecisionEntry, MemoryManager, SessionState

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    )


@pytest.fixture
def delivery(tmp_path: Path) -> Path:
    repo = tmp_path / "prod"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    mem = repo / ".zo" / "memory"
    mem.mkdir(parents=True)
    MemoryManager(project_dir=repo, project_name="prod", memory_root=mem).initialize_project()
    (repo / "README.md").write_text("# prod\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_concurrent_appends_no_loss_or_corruption(tmp_path: Path) -> None:
    """flock guarantee: parallel appenders never lose or interleave entries."""
    mem = tmp_path / "m"
    mem.mkdir()
    (mem / "DECISION_LOG.md").touch()
    n_threads, per = 8, 20

    def worker(tid: int) -> None:
        m = MemoryManager(project_dir=tmp_path, project_name="x", memory_root=mem)
        for i in range(per):
            m.append_decision(DecisionEntry(title=f"t{tid}-{i}"))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    entries = parse_decisions((mem / "DECISION_LOG.md").read_text(encoding="utf-8"))
    assert len(entries) == n_threads * per  # nothing lost or merged together
    assert len({e.title for e in entries}) == n_threads * per  # all distinct, intact


def test_consolidate_reports_conflict_and_leaves_clean_tree(delivery: Path) -> None:
    """A clashing branch merge is reported as conflict and aborted cleanly."""
    (delivery / "paper").mkdir()
    (delivery / "paper" / "shared.tex").write_text("main v1\n", encoding="utf-8")
    _git(delivery, "add", "-A")
    _git(delivery, "commit", "-qm", "paper")

    lay = sg.create_surrogate(delivery, surrogate_id="report-conf")
    (lay.worktree / "paper" / "shared.tex").write_text("report version\n", encoding="utf-8")
    sg.commit_worktree(lay.worktree, message="report change")

    # main diverges on the SAME file -> merge must conflict
    (delivery / "paper" / "shared.tex").write_text("main v2\n", encoding="utf-8")
    _git(delivery, "add", "-A")
    _git(delivery, "commit", "-qm", "main change")

    r = consolidate_surrogate(delivery, "report-conf")
    assert r.merge_status == "conflict"
    assert not (delivery / ".git" / "MERGE_HEAD").exists()  # merge aborted, tree clean
    assert "report-conf" in sg.pending_surrogates(delivery)  # kept for manual fix


def test_resume_after_worktree_prune_preserves_memory(delivery: Path) -> None:
    """`zo report --resume` core: recreate the worktree, keep the delta memory."""
    lay = sg.create_surrogate(delivery, surrogate_id="report-res")
    MemoryManager(
        project_dir=delivery, project_name="report-res", memory_root=lay.memory_root,
    ).append_decision(DecisionEntry(title="pre-prune delta"))

    sg.remove_worktree(delivery, lay.worktree)
    assert not lay.worktree.exists()

    loaded = sg.load_surrogate(delivery, "report-res")
    assert loaded is not None
    again = sg.create_surrogate(
        delivery, role=loaded.role, surrogate_id=loaded.surrogate_id,
    )
    assert again.worktree.exists()  # recreated on the existing branch
    assert again.branch == "report/report-res"
    dlog = (again.memory_root / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "pre-prune delta" in dlog


def test_consolidation_never_touches_canonical_state(delivery: Path) -> None:
    """The core safety boundary: consolidation never writes canonical STATE.md."""
    canon_state = delivery / ".zo" / "memory" / "STATE.md"
    before = canon_state.read_text(encoding="utf-8")

    lay = sg.create_surrogate(delivery, surrogate_id="report-st")
    smem = MemoryManager(
        project_dir=delivery, project_name="report-st", memory_root=lay.memory_root,
    )
    smem.append_decision(DecisionEntry(title="d"))
    # The surrogate writes its OWN state (for resumability) — it must NOT leak
    # into canonical STATE during consolidation.
    smem.write_state(SessionState(phase="report-writing"))

    consolidate_surrogate(delivery, "report-st")

    assert canon_state.read_text(encoding="utf-8") == before  # byte-for-byte unchanged
