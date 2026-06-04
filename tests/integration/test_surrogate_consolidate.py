"""Integration tests for the surrogate-session + consolidation round-trip.

Exercises the real git-worktree / branch-merge / memory-fold path against a
temp git repo (the riskiest part of the `zo report` mechanism).
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from zo import surrogate as sg
from zo.consolidate import consolidate_all, consolidate_surrogate
from zo.memory import DecisionEntry, MemoryManager, PriorEntry, SessionSummary

if TYPE_CHECKING:
    from pathlib import Path

_DEAD_PID = 999999  # well above macOS/Linux max pid; effectively never alive


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    )


def _canonical(repo: Path) -> MemoryManager:
    return MemoryManager(
        project_dir=repo, project_name="prod", memory_root=repo / ".zo" / "memory",
    )


@pytest.fixture
def delivery(tmp_path: Path) -> Path:
    """A temp delivery repo with committed canonical .zo/memory + one prior."""
    repo = tmp_path / "prod"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    mem = repo / ".zo" / "memory"
    mem.mkdir(parents=True)
    cm = _canonical(repo)
    cm.initialize_project()
    cm.append_prior(PriorEntry(category="domain", statement="Existing canonical prior"))

    (repo / "README.md").write_text("# prod\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def test_create_surrogate(delivery: Path) -> None:
    lay = sg.create_surrogate(delivery, surrogate_id="report-test1")

    assert lay.worktree.exists()
    assert (lay.worktree / ".git").exists()  # worktree gitdir pointer
    assert lay.memory_root.is_dir()
    assert (lay.memory_root / "DECISION_LOG.md").exists()
    assert sg._branch_exists(delivery, "report/report-test1")
    assert ".zo/surrogates/" in (delivery / ".gitignore").read_text(encoding="utf-8")


def test_create_surrogate_idempotent_resume(delivery: Path) -> None:
    a = sg.create_surrogate(delivery, surrogate_id="report-rsm")
    b = sg.create_surrogate(delivery, surrogate_id="report-rsm")  # resume, no crash
    assert a.worktree == b.worktree
    assert a.branch == b.branch


def test_liveness_registry(delivery: Path) -> None:
    me = os.getpid()
    sg.register_session(delivery, role="model", pid=me)
    sg.register_session(delivery, role="report", pid=_DEAD_PID)

    live = sg.live_sessions(delivery)
    pids = {s["pid"] for s in live}
    assert me in pids
    assert _DEAD_PID not in pids  # dead PID swept

    assert sg.live_sessions(delivery, exclude_pid=me) == []
    sg.deregister_session(delivery, pid=me)
    assert sg.live_sessions(delivery) == []


def test_consolidate_round_trip(delivery: Path) -> None:
    lay = sg.create_surrogate(delivery, surrogate_id="report-rt")
    smem = MemoryManager(
        project_dir=delivery, project_name="report-rt", memory_root=lay.memory_root,
    )
    smem.append_decision(
        DecisionEntry(title="Verified results", decision="checked metrics", outcome="pass"),
    )
    smem.append_prior(PriorEntry(category="auto-learning", statement="New report insight"))
    smem.append_prior(PriorEntry(category="domain", statement="Existing canonical prior"))
    smem.write_session_summary(SessionSummary(accomplished=["wrote section 1"]))

    (lay.worktree / "paper").mkdir()
    (lay.worktree / "paper" / "report.tex").write_text("\\documentclass{article}", encoding="utf-8")

    reports = consolidate_all(delivery)

    assert len(reports) == 1
    r = reports[0]
    assert r.merge_status == "merged"
    assert r.decisions_folded == 1
    assert r.priors_folded == 1
    assert r.priors_skipped_dup == 1
    assert r.summaries_copied == 1
    assert r.archived is True

    cmem = delivery / ".zo" / "memory"
    assert "Verified results" in (cmem / "DECISION_LOG.md").read_text(encoding="utf-8")
    priors_txt = (cmem / "PRIORS.md").read_text(encoding="utf-8")
    assert "New report insight" in priors_txt
    assert priors_txt.count("Existing canonical prior") == 1  # dedup, not doubled
    assert list((cmem / "sessions").glob("*.md"))  # summary copied
    assert (delivery / "paper" / "report.tex").exists()  # artifact merged to main
    assert "report-rt" not in sg.pending_surrogates(delivery)
    assert (sg.archive_dir(delivery) / "report-rt").is_dir()


def test_deferred_merge_then_complete(delivery: Path) -> None:
    lay = sg.create_surrogate(delivery, surrogate_id="report-def")
    smem = MemoryManager(
        project_dir=delivery, project_name="report-def", memory_root=lay.memory_root,
    )
    smem.append_decision(DecisionEntry(title="Delta decision"))
    (lay.worktree / "paper").mkdir()
    (lay.worktree / "paper" / "r.tex").write_text("x", encoding="utf-8")

    # A live session present -> branch merge deferred, memory still folded.
    sg.register_session(delivery, role="model", pid=os.getpid())
    r1 = consolidate_surrogate(delivery, "report-def")
    assert r1.merge_status == "deferred"
    assert r1.decisions_folded == 1
    assert r1.archived is False
    assert "report-def" in sg.pending_surrogates(delivery)
    dlog = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert dlog.count("Delta decision") == 1

    # Session gone -> consolidation completes with NO double-fold.
    sg.deregister_session(delivery, pid=os.getpid())
    r2 = consolidate_surrogate(delivery, "report-def")
    assert r2.merge_status == "merged"
    assert r2.decisions_folded == 0  # marker prevents re-fold
    assert "already folded" in " ".join(r2.notes)
    dlog2 = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert dlog2.count("Delta decision") == 1  # not duplicated
    assert (delivery / "paper" / "r.tex").exists()
    assert r2.archived is True


def test_unknown_surrogate_is_noop(delivery: Path) -> None:
    r = consolidate_surrogate(delivery, "report-nope")
    assert r.merge_status == "skipped"
    assert "unknown surrogate" in " ".join(r.notes)
