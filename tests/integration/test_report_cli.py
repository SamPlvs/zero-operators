"""End-to-end CLI tests for `zo report` / `zo consolidate` and the
`_launch_and_monitor` surrogate wiring (registration, auto-consolidation, and
liveness-gated overlay cleanup) — with the actual Claude launch stubbed.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from click.testing import CliRunner

from zo import surrogate as sg
from zo.cli import _launch_and_monitor, cli
from zo.memory import DecisionEntry, MemoryManager
from zo.project_config import ProjectConfig, save_project_config

if TYPE_CHECKING:
    from pathlib import Path


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
    """A real .zo/ delivery repo (config + canonical memory, committed)."""
    repo = tmp_path / "prod"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@e.com")
    _git(repo, "config", "user.name", "T")
    save_project_config(repo, ProjectConfig(project_name="prod"))
    (repo / ".zo" / "memory").mkdir(parents=True, exist_ok=True)
    _canonical(repo).initialize_project()
    (repo / "README.md").write_text("# prod\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


class _FakeProcess:
    tmux_pane_id = None
    pid = 4242
    team_name = "zo-prod"
    status = "completed"

    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)


class _FakeWrapper:
    """Stands in for LifecycleWrapper so no real Claude session is spawned."""

    def __init__(self) -> None:
        self.launched: dict = {}

    def launch_lead_session(self, prompt: str, **kw: object) -> _FakeProcess:
        self.launched = {"prompt": prompt, **kw}
        return _FakeProcess()

    def wait_for_completion(self, process: _FakeProcess, **kw: object) -> _FakeProcess:
        return process

    def read_task_list(self, team_name: str) -> list:
        return []


def _pending_surrogate(delivery: Path, sid: str = "report-cli") -> sg.SurrogateLayout:
    lay = sg.create_surrogate(delivery, surrogate_id=sid)
    MemoryManager(
        project_dir=delivery, project_name=sid, memory_root=lay.memory_root,
    ).append_decision(DecisionEntry(title="CLI delta decision"))
    (lay.worktree / "paper").mkdir()
    (lay.worktree / "paper" / "r.tex").write_text("x", encoding="utf-8")
    return lay


# --- zo report --------------------------------------------------------------


def test_report_command_creates_surrogate_and_launches(
    delivery: Path, tmp_path: Path,
) -> None:
    runner = CliRunner()
    with mock.patch("zo.cli._zo_root", return_value=tmp_path / "zo"), \
         mock.patch("zo.cli._launch_and_monitor") as lam:
        result = runner.invoke(
            cli,
            ["report", "--repo", str(delivery), "--no-tmux",
             "--objective", "verify phase 4 only"],
        )

    assert result.exit_code == 0, result.output
    kw = lam.call_args.kwargs
    assert kw["model"] == "opus"
    assert kw["session_role"] == "report"
    assert kw["surrogate_id"].startswith("report-")
    assert kw["surrogate_worktree"].exists()
    assert kw["add_dirs"] == [str(kw["surrogate_worktree"]), str(delivery.resolve())]
    assert kw["team_name"].endswith("-report")
    assert kw["consolidate_on_exit"] is True  # auto-consolidate by default
    assert "verify phase 4 only" in kw["prompt"]  # --objective plumbs through
    for marker in ("Report Lead", "oracle-qa", "data-engineer", 'model="opus"'):
        assert marker in kw["prompt"]
    assert sg._branch_exists(delivery, f"report/{kw['surrogate_id']}")
    assert (sg.surrogates_root(delivery) / kw["surrogate_id"]).is_dir()


def test_report_requires_zo_dir(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = CliRunner().invoke(
        cli, ["report", "prod", "--repo", str(plain), "--no-tmux"],
    )
    assert result.exit_code != 0
    assert ".zo" in result.output


def test_report_resume_unknown_errors(delivery: Path) -> None:
    result = CliRunner().invoke(
        cli,
        ["report", "prod", "--repo", str(delivery), "--resume", "report-nope", "--no-tmux"],
    )
    assert result.exit_code != 0
    assert "report-nope" in result.output


# --- zo consolidate ---------------------------------------------------------


def test_consolidate_command_merges(delivery: Path) -> None:
    _pending_surrogate(delivery)
    result = CliRunner().invoke(cli, ["consolidate", "prod", "--repo", str(delivery)])

    assert result.exit_code == 0, result.output
    assert "Consolidated" in result.output
    assert "report-cli" in result.output
    dlog = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "CLI delta decision" in dlog
    assert (delivery / "paper" / "r.tex").exists()
    assert "report-cli" not in sg.pending_surrogates(delivery)


def test_consolidate_dry_run_writes_nothing(delivery: Path) -> None:
    _pending_surrogate(delivery, sid="report-dry")
    result = CliRunner().invoke(
        cli, ["consolidate", "prod", "--repo", str(delivery), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "Would consolidate" in result.output
    dlog = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "CLI delta decision" not in dlog
    assert "report-dry" in sg.pending_surrogates(delivery)


# --- _launch_and_monitor wiring --------------------------------------------


def test_launch_and_monitor_auto_consolidates_on_exit(
    delivery: Path, tmp_path: Path,
) -> None:
    lay = sg.create_surrogate(delivery, surrogate_id="report-auto")
    MemoryManager(
        project_dir=delivery, project_name="report-auto", memory_root=lay.memory_root,
    ).append_decision(DecisionEntry(title="Auto delta"))
    (lay.worktree / "paper").mkdir()
    (lay.worktree / "paper" / "a.tex").write_text("y", encoding="utf-8")

    _launch_and_monitor(
        wrapper=_FakeWrapper(),
        prompt="P",
        team_name="zo-prod",
        zo_root=tmp_path / "zo",
        no_tmux=True,
        model="opus",
        project_name="prod",
        delivery_repo=delivery,
        session_role="model",
    )

    assert "report-auto" not in sg.pending_surrogates(delivery)
    dlog = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "Auto delta" in dlog
    assert (delivery / "paper" / "a.tex").exists()


def test_launch_and_monitor_skips_overlay_cleanup_when_peer_live(
    delivery: Path, tmp_path: Path,
) -> None:
    with mock.patch(
        "zo.surrogate.live_sessions", return_value=[{"pid": 99, "surrogate_id": None}],
    ), mock.patch("zo.permissions_overlay.cleanup_stale_overlay") as clean:
        _launch_and_monitor(
            wrapper=_FakeWrapper(),
            prompt="P",
            team_name="zo-prod",
            zo_root=tmp_path / "zo",
            no_tmux=True,
            model="opus",
            project_name="prod",
            delivery_repo=delivery,
            session_role="report",
            surrogate_id="report-x",
        )
    clean.assert_not_called()


def test_launch_and_monitor_cleans_overlay_when_alone(
    delivery: Path, tmp_path: Path,
) -> None:
    with mock.patch("zo.surrogate.live_sessions", return_value=[]), \
         mock.patch(
             "zo.permissions_overlay.cleanup_stale_overlay", return_value=False,
         ) as clean:
        _launch_and_monitor(
            wrapper=_FakeWrapper(),
            prompt="P",
            team_name="zo-prod",
            zo_root=tmp_path / "zo",
            no_tmux=True,
            model="opus",
            project_name="prod",
            delivery_repo=delivery,
            session_role="model",
        )
    clean.assert_called_once()


def test_report_no_consolidate_flag(delivery: Path, tmp_path: Path) -> None:
    with mock.patch("zo.cli._zo_root", return_value=tmp_path / "zo"), \
         mock.patch("zo.cli._launch_and_monitor") as lam:
        result = CliRunner().invoke(
            cli, ["report", "--repo", str(delivery), "--no-tmux", "--no-consolidate"],
        )
    assert result.exit_code == 0, result.output
    assert lam.call_args.kwargs["consolidate_on_exit"] is False


def test_report_session_never_cleans_overlay(delivery: Path, tmp_path: Path) -> None:
    # Even with NO peer registered, a surrogate (report) session must never
    # touch the shared permission overlay — a model session predating the
    # registry could be live and own it.
    with mock.patch("zo.surrogate.live_sessions", return_value=[]), \
         mock.patch("zo.permissions_overlay.cleanup_stale_overlay") as clean:
        _launch_and_monitor(
            wrapper=_FakeWrapper(),
            prompt="P",
            team_name="zo-prod-report",
            zo_root=tmp_path / "zo",
            no_tmux=True,
            model="opus",
            project_name="prod",
            delivery_repo=delivery,
            session_role="report",
            surrogate_id="report-x",
        )
    clean.assert_not_called()


def test_launch_and_monitor_no_consolidate_skips_merge(
    delivery: Path, tmp_path: Path,
) -> None:
    lay = sg.create_surrogate(delivery, surrogate_id="report-skip")
    MemoryManager(
        project_dir=delivery, project_name="report-skip", memory_root=lay.memory_root,
    ).append_decision(DecisionEntry(title="skip delta"))

    _launch_and_monitor(
        wrapper=_FakeWrapper(),
        prompt="P",
        team_name="zo-prod",
        zo_root=tmp_path / "zo",
        no_tmux=True,
        model="opus",
        project_name="prod",
        delivery_repo=delivery,
        session_role="model",
        consolidate_on_exit=False,
    )

    # Consolidation suppressed: surrogate still pending, nothing folded.
    assert "report-skip" in sg.pending_surrogates(delivery)
    dlog = (delivery / ".zo" / "memory" / "DECISION_LOG.md").read_text(encoding="utf-8")
    assert "skip delta" not in dlog
