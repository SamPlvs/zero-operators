"""Unit tests for zo.wrapper, zo._wrapper_models and zo._wrapper_watchdog.

WS-C execution substrate (plan oracle checks 11-12): the watchdog is an
external checker ticked from BOTH poll loops. Every mechanism has a
seeded-failure test (plants the condition, asserts the mechanism catches it)
and a wiring test (proves the runtime path invokes it).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from zo._wrapper_models import (
    AgentStatus,
    LeadProcess,
    TeamMember,
    TeamStatus,
)
from zo._wrapper_watchdog import TICK_TRACE_FILENAME, WatchdogRunner
from zo.comms import CommsLogger
from zo.watchdog import (
    HeartbeatRecord,
    StallAction,
    StallVerdict,
    WatchdogConfig,
    load_state,
    write_heartbeat,
)
from zo.wrapper import LifecycleWrapper

if TYPE_CHECKING:
    from collections.abc import Callable

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def tmp_log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs" / "wrapper"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def comms(tmp_path: Path) -> CommsLogger:
    return CommsLogger(
        log_dir=tmp_path / "comms",
        project="test-project",
        session_id="test-session",
    )


@pytest.fixture()
def wrapper(comms: CommsLogger, tmp_log_dir: Path) -> LifecycleWrapper:
    return LifecycleWrapper(comms, log_dir=tmp_log_dir)


# ------------------------------------------------------------------ #
# Watchdog test helpers (WS-C, oracle checks 11-12)
# ------------------------------------------------------------------ #

T0 = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
POLL = 60.0  # virtual seconds per poll (sleep is patched to advance the clock)

# Neutral pane: some output + the idle prompt (nudge-ready, no never-block).
IDLE_PANE = "Reading files\nRunning tests\n\n\u276f \n"
# The real Claude Code usage-limit banner (rate_limit never-block).
BANNER_PANE = "You've hit your usage limit \u00b7 resets at 10:05\n\n\u276f \n"
# Permission dialog (awaiting_input never-block).
DIALOG_PANE = "Do you want to proceed?\n\u276f 1. Yes\n  2. No\n"
# Busy pane: active task, no idle prompt (nudge guard must skip).
BUSY_PANE = "\u273b Thinking\u2026 (esc to interrupt)\n"


class FakeClock:
    """Injectable wall + monotonic clock; ``sleep`` advances both."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start
        self.mono = 0.0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += timedelta(seconds=secs)
        self.mono += secs

    def sleep(self, secs: float) -> None:
        self.advance(secs)

    def monotonic(self) -> float:
        return self.mono


class _StatusSpy:
    """Records ``process.status`` after every ``_watchdog_tick`` call."""

    def __init__(self, wrapper: LifecycleWrapper) -> None:
        self._wrapper = wrapper
        self.statuses: list[AgentStatus] = []
        self.calls = 0
        self._orig = wrapper._watchdog_tick

    def _spy(self, process: LeadProcess, **kw: object) -> object:
        verdict = self._orig(process, **kw)
        self.calls += 1
        self.statuses.append(process.status)
        return verdict

    def __enter__(self) -> _StatusSpy:
        self._patch = mock.patch.object(self._wrapper, "_watchdog_tick", side_effect=self._spy)
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


class _TmuxScenario:
    """Scripted pane: text per poll index; alive for the first N polls."""

    def __init__(self, *, alive_polls: int, text_for_poll: Callable[[int], str]) -> None:
        self.alive_polls = alive_polls
        self.text_for_poll = text_for_poll
        self.polls = 0

    def capture(self, pane_id: str, lines: int = 50) -> str:
        text = self.text_for_poll(self.polls)
        self.polls += 1
        return text

    def alive(self, pane_id: str) -> bool:
        # capture() runs first in each poll, so polls == index + 1 here.
        return self.polls <= self.alive_polls


def _wd_config(**overrides: object) -> WatchdogConfig:
    base = dict(stall_threshold_sec=600, startup_grace_sec=0, nudge_delay_sec=0,
                escalate_grace_sec=0)
    base.update(overrides)
    return WatchdogConfig(**base)  # type: ignore[arg-type]


def _plant_heartbeat(memory_root: Path, *, tick_count: int, at: datetime) -> None:
    write_heartbeat(memory_root, HeartbeatRecord(
        agent_key="lead-s1", session_id="s1", last_tick_at=at, tick_count=tick_count,
    ))


def _comms_events(tmp_path: Path) -> list[dict]:
    events: list[dict] = []
    for path in sorted((tmp_path / "comms").glob("*.jsonl")):
        events.extend(json.loads(ln) for ln in path.read_text().splitlines() if ln.strip())
    return events


def _tick_trace(memory_root: Path) -> list[dict]:
    path = memory_root / "heartbeats" / TICK_TRACE_FILENAME
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def memory_root(tmp_path: Path) -> Path:
    root = tmp_path / "memory"
    root.mkdir()
    return root


@pytest.fixture()
def wd_wrapper(comms: CommsLogger, tmp_log_dir: Path, clock: FakeClock) -> LifecycleWrapper:
    # tz=UTC pins banner clock times ("resets at 10:05") to the fake clock's zone.
    return LifecycleWrapper(comms, log_dir=tmp_log_dir, clock=clock, tz=UTC)


def _run_tmux(
    wrapper: LifecycleWrapper, clock: FakeClock, scenario: _TmuxScenario, *,
    watchdog: WatchdogConfig | None, memory_root: Path | None, timeout: float | None = None,
    on_status: Callable | None = None, patch_monotonic: bool = False,
) -> tuple[LeadProcess, mock.MagicMock, mock.MagicMock]:
    """Drive ``_wait_tmux`` with class-patched tmux helpers; returns (result, paste, capture)."""
    lead = LeadProcess(tmux_pane_id="%5", team_name="alpha", status=AgentStatus.SPAWNING)
    patches = [
        mock.patch.object(LifecycleWrapper, "_tmux_pane_alive", side_effect=scenario.alive),
        mock.patch.object(LifecycleWrapper, "_tmux_claude_running", return_value=True),
        mock.patch.object(LifecycleWrapper, "_kill_tmux_window"),
        mock.patch.object(wrapper, "monitor_team", return_value=TeamStatus(team_name="alpha")),
        mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep),
    ]
    if patch_monotonic:
        patches.append(mock.patch("zo.wrapper.time.monotonic", side_effect=clock.monotonic))
    capture = mock.patch.object(LifecycleWrapper, "_capture_tmux_pane",
                                side_effect=scenario.capture)
    paste = mock.patch.object(LifecycleWrapper, "_paste_and_submit")
    for p in patches:
        p.start()
    try:
        with capture as capture_mock, paste as paste_mock:
            result = wrapper.wait_for_completion(
                lead, poll_interval=POLL, timeout=timeout,
                on_status=on_status or (lambda *_: None),
                watchdog=watchdog, memory_root=memory_root, zo_session_id="zo-s1",
            )
    finally:
        for p in reversed(patches):
            p.stop()
    return result, paste_mock, capture_mock


def _headless_setup(
    wrapper: LifecycleWrapper, tmp_log_dir: Path, *, poll: object, stdout_text: str,
) -> LeadProcess:
    """Wire a fake Popen + stdout log for ``_wait_headless``; returns the LeadProcess."""
    mock_proc = mock.MagicMock()
    if callable(poll) or isinstance(poll, list):
        mock_proc.poll.side_effect = poll
    else:
        mock_proc.poll.return_value = poll
    mock_proc.wait.return_value = None
    wrapper._proc = mock_proc
    wrapper._stdout_fh = mock.MagicMock()
    wrapper._stderr_fh = mock.MagicMock()
    stdout_file = tmp_log_dir / "alpha-stdout.log"
    stdout_file.write_text(stdout_text)
    stderr_file = tmp_log_dir / "alpha-stderr.log"
    stderr_file.write_text("")
    return LeadProcess(pid=99, team_name="alpha", stdout_log=stdout_file, stderr_log=stderr_file)



# ------------------------------------------------------------------ #
# Model tests
# ------------------------------------------------------------------ #


class TestModels:
    def test_agent_status_values(self) -> None:
        assert AgentStatus.SPAWNING == "spawning"
        assert AgentStatus.RATE_LIMITED == "rate_limited"

    def test_lead_process_defaults(self) -> None:
        lp = LeadProcess()
        assert lp.pid is None
        assert lp.status == AgentStatus.SPAWNING
        assert lp.exit_code is None
        assert lp.team_name == ""

    def test_agent_status_watchdog_values(self) -> None:
        assert AgentStatus.PAUSED_RATE_LIMIT == "paused_rate_limit"
        assert AgentStatus.STALLED == "stalled"

    def test_lead_process_watchdog_defaults(self) -> None:
        lp = LeadProcess()
        assert lp.pid_start_identity is None
        assert lp.nudges_used == 0
        assert lp.stalled is False
        assert lp.paused_until is None
        assert lp.resume_at is None
        assert lp.pause_total_sec == 0.0

    def test_lead_process_with_values(self) -> None:
        lp = LeadProcess(
            pid=1234,
            status=AgentStatus.RUNNING,
            team_name="alpha",
            stdout_log=Path("/tmp/out.log"),
        )
        assert lp.pid == 1234
        assert lp.stdout_log == Path("/tmp/out.log")

    def test_team_member_defaults(self) -> None:
        m = TeamMember(name="builder")
        assert m.agent_type == ""
        assert m.status == "unknown"

    def test_team_status_defaults(self) -> None:
        ts = TeamStatus(team_name="alpha")
        assert ts.members == []
        assert ts.tasks_total == 0
        assert ts.is_active is True


# ------------------------------------------------------------------ #
# launch_lead_session
# ------------------------------------------------------------------ #


class TestLaunchLeadSession:
    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_headless_builds_correct_command(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """When use_tmux=False with bypass_permissions=True, launches
        headless with --print and --dangerously-skip-permissions."""
        mock_popen.return_value.pid = 42

        result = wrapper.launch_lead_session(
            "do the thing",
            cwd="/target",
            team_name="alpha",
            model="opus",
            max_turns=100,
            use_tmux=False,
            bypass_permissions=True,
        )

        # call_args_list[0] is the claude launch (the identity probe may
        # spawn ``ps`` through the same patched Popen afterwards).
        args = mock_popen.call_args_list[0]
        cmd = args[0][0]
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--max-turns" in cmd
        assert "100" in cmd
        assert "--add-dir" in cmd
        assert "/target" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert "-p" in cmd
        assert "do the thing" in cmd

        assert result.pid == 42
        assert result.status == AgentStatus.SPAWNING
        assert result.team_name == "alpha"
        assert result.stdout_log is not None
        assert result.tmux_pane_id is None

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_headless_omits_skip_flag_when_bypass_false(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """When bypass_permissions=False, --dangerously-skip-permissions
        must NOT be in the Claude command. Prompts are expected to fire
        for each tool call."""
        mock_popen.return_value.pid = 43

        wrapper.launch_lead_session(
            "do the thing",
            cwd="/target",
            team_name="beta",
            model="opus",
            max_turns=50,
            use_tmux=False,
            bypass_permissions=False,
        )

        cmd = mock_popen.call_args_list[0][0][0]
        assert "--dangerously-skip-permissions" not in cmd
        # Sanity: rest of the command is still well-formed
        assert "--print" in cmd
        assert "-p" in cmd

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_headless_default_bypass_is_false(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """Default (no bypass_permissions arg) is the safe behavior:
        --dangerously-skip-permissions is NOT included."""
        mock_popen.return_value.pid = 44

        wrapper.launch_lead_session(
            "do the thing",
            cwd="/target",
            team_name="gamma",
            use_tmux=False,
        )

        cmd = mock_popen.call_args_list[0][0][0]
        assert "--dangerously-skip-permissions" not in cmd

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_add_dir_flag_present(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        mock_popen.return_value.pid = 10
        wrapper.launch_lead_session(
            "prompt", cwd="/my/delivery", team_name="t", use_tmux=False
        )

        cmd = mock_popen.call_args_list[0][0][0]
        assert "--add-dir" in cmd
        assert "/my/delivery" in cmd

    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_launch_creates_pane(
        self, mock_run: mock.MagicMock, mock_sleep: mock.MagicMock,
        wrapper: LifecycleWrapper,
    ) -> None:
        """When inside tmux, creates window, starts claude, pastes prompt."""
        mock_run.return_value = mock.MagicMock(
            stdout="%5\n", returncode=0
        )

        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}):
            result = wrapper.launch_lead_session(
                "do the thing",
                cwd="/target",
                team_name="alpha",
                model="opus",
                max_turns=100,
                use_tmux=True,
            )

        # Calls: which + new-window + send-keys(cmd) + load-buffer +
        #        paste-buffer + send-keys(Enter)
        calls = mock_run.call_args_list
        tmux_calls = [c for c in calls if c[0][0][0] == "tmux"]
        actions = [c[0][0][1] for c in tmux_calls]
        assert "new-window" in actions
        assert "send-keys" in actions
        assert "load-buffer" in actions
        assert "paste-buffer" in actions

        assert result.tmux_pane_id == "%5"
        assert result.pid is None
        assert result.status == AgentStatus.SPAWNING
        assert result.team_name == "alpha"

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_tmux_falls_back_headless_when_not_in_tmux(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """use_tmux=True but not inside tmux -> headless fallback."""
        mock_popen.return_value.pid = 42

        with mock.patch.dict(os.environ, {}, clear=True):
            result = wrapper.launch_lead_session(
                "prompt", cwd="/target", team_name="t", use_tmux=True
            )

        assert result.pid == 42
        assert result.tmux_pane_id is None
        assert mock_popen.called

    @mock.patch("zo.wrapper.atexit.register")
    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_with_bypass_applies_overlay(
        self,
        mock_run: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_atexit: mock.MagicMock,
        wrapper: LifecycleWrapper,
        tmp_path: Path,
    ) -> None:
        """tmux + bypass_permissions=True writes the settings overlay
        and registers a restore callback with atexit before launching."""
        mock_run.return_value = mock.MagicMock(stdout="%9\n", returncode=0)

        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}):
            wrapper.launch_lead_session(
                "prompt",
                cwd=str(tmp_path),
                team_name="overlay-team",
                use_tmux=True,
                bypass_permissions=True,
            )

        # Overlay should be on disk during launch
        settings = tmp_path / ".claude" / "settings.local.json"
        assert settings.exists()
        content = json.loads(settings.read_text())
        assert content["permissions"]["defaultMode"] == "bypassPermissions"

        # Restore was registered with atexit
        assert mock_atexit.called
        # The wrapper holds a reference so an explicit restore is possible
        assert wrapper._bypass_restore_fn is not None  # noqa: SLF001

    @mock.patch("zo.wrapper.atexit.register")
    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_without_bypass_skips_overlay(
        self,
        mock_run: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_atexit: mock.MagicMock,
        wrapper: LifecycleWrapper,
        tmp_path: Path,
    ) -> None:
        """tmux without bypass_permissions does NOT touch
        settings.local.json or register any atexit handler."""
        mock_run.return_value = mock.MagicMock(stdout="%10\n", returncode=0)

        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}):
            wrapper.launch_lead_session(
                "prompt",
                cwd=str(tmp_path),
                team_name="no-overlay",
                use_tmux=True,
                bypass_permissions=False,
            )

        # No overlay was written
        settings = tmp_path / ".claude" / "settings.local.json"
        assert not settings.exists()
        # No atexit handler was registered for an overlay
        assert not mock_atexit.called
        assert wrapper._bypass_restore_fn is None  # noqa: SLF001


# ------------------------------------------------------------------ #
# monitor_team / read_task_list
# ------------------------------------------------------------------ #


class TestMonitorTeam:
    def test_returns_empty_when_no_dir(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        with mock.patch("zo.wrapper.Path.home", return_value=tmp_path):
            status = wrapper.monitor_team("nonexistent")
            assert status.team_name == "nonexistent"
            assert status.members == []
            assert status.tasks_total == 0
            assert status.is_active is True

    def test_reads_team_config_and_tasks(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        team_dir = tmp_path / ".claude" / "teams" / "alpha"
        team_dir.mkdir(parents=True)
        config = {
            "members": [
                {"name": "builder", "agent_type": "backend", "status": "running"},
                {"name": "oracle", "agent_type": "qa", "status": "idle"},
            ]
        }
        (team_dir / "config.json").write_text(json.dumps(config))

        tasks_dir = tmp_path / ".claude" / "tasks" / "alpha"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "task-1.json").write_text(
            json.dumps({"id": "1", "status": "completed", "owner": "builder", "content": "do X"})
        )
        (tasks_dir / "task-2.json").write_text(
            json.dumps({"id": "2", "status": "in_progress", "owner": "oracle", "content": "do Y"})
        )
        (tasks_dir / "task-3.json").write_text(
            json.dumps({"id": "3", "status": "pending", "owner": "", "content": "do Z"})
        )

        with mock.patch("zo.wrapper.Path.home", return_value=tmp_path):
            status = wrapper.monitor_team("alpha")

        assert len(status.members) == 2
        assert status.members[0].name == "builder"
        assert status.tasks_total == 3
        assert status.tasks_completed == 1
        assert status.tasks_in_progress == 1
        assert status.tasks_pending == 1
        assert status.is_active is True


class TestReadTaskList:
    def test_handles_missing_dir(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        with mock.patch("zo.wrapper.Path.home", return_value=tmp_path):
            assert wrapper.read_task_list("ghost") == []

    def test_handles_empty_dir(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".claude" / "tasks" / "empty"
        tasks_dir.mkdir(parents=True)
        with mock.patch("zo.wrapper.Path.home", return_value=tmp_path):
            assert wrapper.read_task_list("empty") == []

    def test_skips_invalid_json(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / ".claude" / "tasks" / "bad"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "task-1.json").write_text("not json")
        (tasks_dir / "task-2.json").write_text(json.dumps({"id": "2", "status": "pending"}))

        with mock.patch("zo.wrapper.Path.home", return_value=tmp_path):
            result = wrapper.read_task_list("bad")
        assert len(result) == 1
        assert result[0]["id"] == "2"


# ------------------------------------------------------------------ #
# observe_tmux_panes
# ------------------------------------------------------------------ #


class TestObserveTmuxPanes:
    def test_returns_empty_when_not_in_tmux(
        self, wrapper: LifecycleWrapper
    ) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert wrapper.observe_tmux_panes() == {}

    def test_captures_panes_when_in_tmux(
        self, wrapper: LifecycleWrapper
    ) -> None:
        with (
            mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,123,0"}),
            mock.patch.object(
                LifecycleWrapper,
                "_list_tmux_panes",
                return_value=[{"id": "%0", "title": "main"}, {"id": "%1", "title": "agent"}],
            ),
            mock.patch.object(
                LifecycleWrapper,
                "_capture_tmux_pane",
                side_effect=["output-0", "output-1"],
            ),
        ):
            result = wrapper.observe_tmux_panes()
            assert result == {"%0": "output-0", "%1": "output-1"}


# ------------------------------------------------------------------ #
# _tmux_pane_alive
# ------------------------------------------------------------------ #


class TestTmuxPaneAlive:
    @mock.patch("zo.wrapper.subprocess.run")
    def test_returns_true_when_pane_exists(
        self, mock_run: mock.MagicMock
    ) -> None:
        mock_run.return_value = mock.MagicMock(
            stdout="%0\n%5\n%7\n", returncode=0
        )
        assert LifecycleWrapper._tmux_pane_alive("%5") is True

    @mock.patch("zo.wrapper.subprocess.run")
    def test_returns_false_when_pane_gone(
        self, mock_run: mock.MagicMock
    ) -> None:
        mock_run.return_value = mock.MagicMock(
            stdout="%0\n%7\n", returncode=0
        )
        assert LifecycleWrapper._tmux_pane_alive("%5") is False

    def test_returns_false_for_empty_id(self) -> None:
        assert LifecycleWrapper._tmux_pane_alive("") is False

    @mock.patch("zo.wrapper.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_tmux_missing(
        self, mock_run: mock.MagicMock
    ) -> None:
        assert LifecycleWrapper._tmux_pane_alive("%5") is False


# ------------------------------------------------------------------ #
# wait_for_completion
# ------------------------------------------------------------------ #


class TestWaitForCompletion:
    def test_detects_normal_completion(
        self, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = 0
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        lead = LeadProcess(
            pid=99,
            team_name="alpha",
            stdout_log=tmp_log_dir / "alpha-stdout.log",
        )
        (tmp_log_dir / "alpha-stdout.log").write_text("")

        result = wrapper.wait_for_completion(lead, poll_interval=0.01)
        assert result.status == AgentStatus.COMPLETED
        assert result.exit_code == 0

    def test_detects_error_exit(
        self, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = 1
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        lead = LeadProcess(
            pid=99,
            team_name="alpha",
            stdout_log=tmp_log_dir / "alpha-stdout.log",
        )
        (tmp_log_dir / "alpha-stdout.log").write_text("")

        result = wrapper.wait_for_completion(lead, poll_interval=0.01)
        assert result.status == AgentStatus.ERRORED
        assert result.exit_code == 1

    @mock.patch("zo.wrapper.time.sleep")
    def test_running_process_with_rate_limit_text_pauses_without_backoff(
        self, mock_sleep: mock.MagicMock, comms: CommsLogger, tmp_log_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Rewritten (WS-C): a RUNNING process whose output carries a
        rate-limit banner is PAUSED by the watchdog — no blocking backoff
        sleep, no in-wrapper retries. Sleep is only ever the poll interval."""
        wrapper = LifecycleWrapper(comms, log_dir=tmp_log_dir, clock=FakeClock(), tz=UTC)
        mock_proc = mock.MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        stdout_file = tmp_log_dir / "alpha-stdout.log"
        stdout_file.write_text("Error 429 Too Many Requests\n")
        lead = LeadProcess(pid=99, team_name="alpha", stdout_log=stdout_file)
        memory_root = tmp_path / "memory"

        seen = _StatusSpy(wrapper)
        with seen:
            result = wrapper.wait_for_completion(
                lead, poll_interval=0.01, watchdog=_wd_config(),
                memory_root=memory_root,
            )
        assert AgentStatus.PAUSED_RATE_LIMIT in seen.statuses
        # No exponential backoff: every sleep is exactly the poll interval.
        assert {c.args[0] for c in mock_sleep.call_args_list} == {0.01}
        # Exited while paused → RATE_LIMITED for the driver to relaunch.
        assert result.status == AgentStatus.RATE_LIMITED

    @mock.patch("zo.wrapper.time.sleep")
    def test_exited_process_with_rate_limit_text_is_rate_limited_with_resume_at(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        """Rewritten (WS-C): an EXITED process whose final output carries a
        rate-limit banner is classified RATE_LIMITED with a parsed
        ``resume_at`` — no retries in the wrapper (works without a runner)."""
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = 1
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        stdout_file = tmp_log_dir / "alpha-stdout.log"
        stdout_file.write_text("rate limit exceeded; try again in 5 minutes\n")
        lead = LeadProcess(pid=99, team_name="alpha", stdout_log=stdout_file)

        result = wrapper.wait_for_completion(lead, poll_interval=0.01)
        assert result.status == AgentStatus.RATE_LIMITED
        assert result.resume_at is not None
        assert result.exit_code == 1
        assert not mock_sleep.called

    @mock.patch("zo.wrapper.time.sleep")
    def test_tmux_wait_completes_when_pane_closes(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """tmux mode: session completes once exit is *confirmed*.

        With ``_STARTUP_GRACE_POLLS=2`` and ``_DEAD_CONFIRM_POLLS=2``,
        a pane that is dead from the start is ignored for the grace
        polls, then needs the confirmation polls before we conclude —
        so completion lands on the 4th poll, not the 1st.
        """
        lead = LeadProcess(
            tmux_pane_id="%5", team_name="alpha",
            status=AgentStatus.SPAWNING,
        )

        alive = mock.patch.object(
            LifecycleWrapper, "_tmux_pane_alive", return_value=False,
        )
        kill = mock.patch.object(LifecycleWrapper, "_kill_tmux_window")
        with alive as alive_mock, kill, mock.patch.object(
            wrapper, "monitor_team",
            return_value=TeamStatus(team_name="alpha"),
        ):
            result = wrapper.wait_for_completion(
                lead, poll_interval=0.01, on_status=lambda *_: None
            )

        assert result.status == AgentStatus.COMPLETED
        assert result.exit_code == 0
        # 2 grace polls (ignored) + 2 confirmation polls = 4 polls.
        assert alive_mock.call_count == 4

    @mock.patch("zo.wrapper.time.sleep")
    def test_tmux_wait_ignores_negative_during_startup_grace(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """A negative reading on the very first poll must NOT complete.

        Regression for the ~15ms teardown: the first liveness poll fires
        immediately after launch, before Claude's TUI has claimed the
        pane.  The startup grace must absorb that.
        """
        lead = LeadProcess(
            tmux_pane_id="%5", team_name="alpha",
            status=AgentStatus.SPAWNING,
        )

        # Dead on poll 0 (grace, ignored), then alive and running forever —
        # the only way the loop terminates is via the timeout path, which
        # proves the early negative did NOT complete the session.
        with mock.patch.object(
            LifecycleWrapper, "_tmux_pane_alive",
            side_effect=[False] + [True] * 50,
        ), mock.patch.object(
            LifecycleWrapper, "_tmux_claude_running", return_value=True,
        ), mock.patch.object(
            wrapper, "monitor_team",
            return_value=TeamStatus(team_name="alpha"),
        ):
            result = wrapper.wait_for_completion(
                lead, poll_interval=0.01, timeout=-1,
                on_status=lambda *_: None,
            )

        # Hit the timeout branch rather than completing on the first negative.
        assert result.status == AgentStatus.TIMED_OUT

    @mock.patch("zo.wrapper.time.sleep")
    def test_tmux_wait_debounces_transient_negative(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        """A single post-grace negative, then alive again, must NOT complete."""
        lead = LeadProcess(
            tmux_pane_id="%5", team_name="alpha",
            status=AgentStatus.SPAWNING,
        )

        # polls: grace,grace, dead(1), alive(reset), dead(1), dead(2)->complete
        running_seq = [True, True, False, True, False, False]
        with mock.patch.object(
            LifecycleWrapper, "_tmux_pane_alive", return_value=True,
        ), mock.patch.object(
            LifecycleWrapper, "_tmux_claude_running",
            side_effect=running_seq,
        ), mock.patch.object(
            LifecycleWrapper, "_kill_tmux_window",
        ), mock.patch.object(
            wrapper, "monitor_team",
            return_value=TeamStatus(team_name="alpha"),
        ) as _mt, mock.patch.object(
            LifecycleWrapper, "_capture_tmux_pane", return_value="",
        ):
            result = wrapper.wait_for_completion(
                lead, poll_interval=0.01, on_status=lambda *_: None
            )

        assert result.status == AgentStatus.COMPLETED


# ------------------------------------------------------------------ #
# kill_session
# ------------------------------------------------------------------ #


class TestKillSession:
    @mock.patch("zo.wrapper.os.kill")
    def test_sends_sigterm_then_sigkill(
        self, mock_kill: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        mock_proc = mock.MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=5)
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        lead = LeadProcess(pid=555, team_name="alpha")
        result = wrapper.kill_session(lead)

        calls = mock_kill.call_args_list
        assert calls[0] == mock.call(555, signal.SIGTERM)
        assert calls[1] == mock.call(555, signal.SIGKILL)
        assert result.status == AgentStatus.ERRORED
        assert result.exit_code == -9

    @mock.patch("zo.wrapper.os.kill")
    def test_handles_already_dead_process(
        self, mock_kill: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        mock_kill.side_effect = ProcessLookupError
        mock_proc = mock.MagicMock()
        mock_proc.wait.return_value = None
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        lead = LeadProcess(pid=999, team_name="alpha")
        result = wrapper.kill_session(lead)
        assert result.status == AgentStatus.ERRORED


# ------------------------------------------------------------------ #
# parse_session_result
# ------------------------------------------------------------------ #


class TestParseSessionResult:
    def test_parses_valid_json(
        self, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        stdout_file = tmp_log_dir / "out.log"
        stdout_file.write_text(
            json.dumps({"result": "done", "cost_usd": 0.12, "model": "opus", "num_turns": 5})
        )
        lead = LeadProcess(stdout_log=stdout_file)
        parsed = wrapper.parse_session_result(lead)
        assert parsed["result"] == "done"
        assert parsed["cost_usd"] == "0.12"
        assert parsed["model"] == "opus"
        assert parsed["num_turns"] == "5"

    def test_falls_back_to_raw_text(
        self, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        stdout_file = tmp_log_dir / "out.log"
        stdout_file.write_text("not json at all")
        lead = LeadProcess(stdout_log=stdout_file)
        parsed = wrapper.parse_session_result(lead)
        assert parsed["result"] == "not json at all"

    def test_handles_missing_file(self, wrapper: LifecycleWrapper) -> None:
        lead = LeadProcess(stdout_log=Path("/nonexistent/file.log"))
        parsed = wrapper.parse_session_result(lead)
        assert parsed == {"result": ""}

    def test_handles_no_log_path(self, wrapper: LifecycleWrapper) -> None:
        lead = LeadProcess()
        parsed = wrapper.parse_session_result(lead)
        assert parsed == {"result": ""}


# ------------------------------------------------------------------ #
# _detect_rate_limit
# ------------------------------------------------------------------ #


class TestDetectRateLimit:
    """Exit-classification matcher, tightened to the watchdog patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "HTTP 429 rate limit response",
            "rate limit exceeded",
            "rate limited by server",
            "too many requests",
            "You've hit your usage limit · resets at 3pm",
        ],
    )
    def test_catches_known_patterns(self, text: str) -> None:
        assert LifecycleWrapper._detect_rate_limit(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "All tasks completed successfully.",
            "val_loss 0.4291",
            "step 4290 done",
            "GPU overloaded, reducing batch size",
        ],
    )
    def test_no_bare_429_or_overloaded_false_positives(self, text: str) -> None:
        assert LifecycleWrapper._detect_rate_limit(text) is False


# ------------------------------------------------------------------ #
# _is_in_tmux
# ------------------------------------------------------------------ #


class TestIsInTmux:
    def test_true_when_tmux_env_set(self) -> None:
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}):
            assert LifecycleWrapper._is_in_tmux() is True

    def test_false_when_tmux_env_missing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert LifecycleWrapper._is_in_tmux() is False


# ------------------------------------------------------------------ #
# monitor_session_logs
# ------------------------------------------------------------------ #


class TestMonitorSessionLogs:
    def test_reads_jsonl_files(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        log_dir = tmp_path / "session"
        log_dir.mkdir()
        (log_dir / "events.jsonl").write_text(
            '{"event": "a"}\n{"event": "b"}\n'
        )
        result = wrapper.monitor_session_logs(log_dir)
        assert len(result) == 2
        assert result[0]["event"] == "a"

    def test_handles_missing_dir(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        assert wrapper.monitor_session_logs(tmp_path / "nope") == []

    def test_skips_invalid_lines(
        self, wrapper: LifecycleWrapper, tmp_path: Path
    ) -> None:
        log_dir = tmp_path / "session"
        log_dir.mkdir()
        (log_dir / "events.jsonl").write_text(
            '{"ok": true}\nnot-json\n{"ok": false}\n'
        )
        result = wrapper.monitor_session_logs(log_dir)
        assert len(result) == 2


class TestMaybeOpenTrainingPane:
    """The auto-split tmux pane must look at .zo/experiments/<exp_id>/.

    Regression: previously hardcoded ``logs/training/training_status.json``,
    which never matched the path ZOTrainingCallback writes.
    """

    def test_skips_when_no_zo_experiments_dir(
        self, comms: CommsLogger, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        wrapper = LifecycleWrapper(comms, log_dir=tmp_log_dir)
        # These attributes are set by wait_for_completion(); poke them in
        # directly so we can unit-test _maybe_open_training_pane in isolation.
        wrapper._project_name = "demo"
        wrapper._delivery_repo = delivery
        wrapper._training_pane_id = None
        # Force "in tmux" so we test the metrics-file branch, not
        # the tmux check.
        with mock.patch.object(
            LifecycleWrapper, "_is_in_tmux", return_value=True,
        ), mock.patch("subprocess.run") as mock_run:
            wrapper._maybe_open_training_pane()
        mock_run.assert_not_called()
        assert wrapper._training_pane_id is None

    def test_skips_when_no_active_experiment(
        self, comms: CommsLogger, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        delivery = tmp_path / "delivery"
        (delivery / ".zo" / "experiments").mkdir(parents=True)
        wrapper = LifecycleWrapper(comms, log_dir=tmp_log_dir)
        # These attributes are set by wait_for_completion(); poke them in
        # directly so we can unit-test _maybe_open_training_pane in isolation.
        wrapper._project_name = "demo"
        wrapper._delivery_repo = delivery
        wrapper._training_pane_id = None
        with mock.patch.object(
            LifecycleWrapper, "_is_in_tmux", return_value=True,
        ), mock.patch("subprocess.run") as mock_run:
            wrapper._maybe_open_training_pane()
        mock_run.assert_not_called()

    def test_opens_pane_when_active_exp_has_status_json(
        self, comms: CommsLogger, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        from zo.experiments import mint_experiment

        delivery = tmp_path / "delivery"
        delivery.mkdir()
        reg_dir = delivery / ".zo" / "experiments"
        reg_dir.mkdir(parents=True)
        exp = mint_experiment(reg_dir, project="demo", phase="phase_4")
        # Drop the status file in the experiment dir — this is what
        # ZOTrainingCallback.for_experiment() writes.
        (Path(exp.artifacts_dir) / "training_status.json").write_text(
            '{"is_training": true, "epoch": 1}\n', encoding="utf-8",
        )

        wrapper = LifecycleWrapper(comms, log_dir=tmp_log_dir)
        # These attributes are set by wait_for_completion(); poke them in
        # directly so we can unit-test _maybe_open_training_pane in isolation.
        wrapper._project_name = "demo"
        wrapper._delivery_repo = delivery
        wrapper._training_pane_id = None
        with mock.patch.object(
            LifecycleWrapper, "_is_in_tmux", return_value=True,
        ), mock.patch(
            "subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="%pane-1\n"),
        ) as mock_run:
            wrapper._maybe_open_training_pane()

        assert wrapper._training_pane_id == "%pane-1"
        # Verify the spawned watch-training got --repo so it can resolve
        # the same active experiment without cwd detection.
        cmd = mock_run.call_args[0][0]
        assert "watch-training" in cmd
        assert "--repo" in cmd

    def test_does_not_check_legacy_logs_training_path(
        self, comms: CommsLogger, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        """Sanity: even if `<delivery>/logs/training/training_status.json`
        exists, the wrapper ignores it (the path is no longer authoritative).
        """
        delivery = tmp_path / "delivery"
        # Old-style legacy file present, but no .zo/experiments registry.
        (delivery / "logs" / "training").mkdir(parents=True)
        (delivery / "logs" / "training" / "training_status.json").write_text(
            '{"is_training": true}\n', encoding="utf-8",
        )
        wrapper = LifecycleWrapper(comms, log_dir=tmp_log_dir)
        # These attributes are set by wait_for_completion(); poke them in
        # directly so we can unit-test _maybe_open_training_pane in isolation.
        wrapper._project_name = "demo"
        wrapper._delivery_repo = delivery
        wrapper._training_pane_id = None
        with mock.patch.object(
            LifecycleWrapper, "_is_in_tmux", return_value=True,
        ), mock.patch("subprocess.run") as mock_run:
            wrapper._maybe_open_training_pane()
        # Legacy file should NOT trigger the dashboard.
        mock_run.assert_not_called()


# ------------------------------------------------------------------ #
# WS-C watchdog integration (plan oracle checks 11-12)
# ------------------------------------------------------------------ #


class TestWatchdogWiring:
    """Wiring half: the runtime path invokes the watchdog from both loops."""

    def test_wrapper_proc_defaults_none(self, comms: CommsLogger, tmp_log_dir: Path) -> None:
        w = LifecycleWrapper(comms, log_dir=tmp_log_dir)
        assert w._proc is None
        assert w._wd is None
        assert w._stdout_fh is None and w._stderr_fh is None

    def test_watchdog_disabled_when_config_off_or_no_memory_root(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        """No runner → the loops behave exactly as before (4 polls to confirm)."""
        for cfg, root in ((_wd_config(enabled=False), memory_root), (_wd_config(), None)):
            scenario = _TmuxScenario(alive_polls=0, text_for_poll=lambda k: IDLE_PANE)
            result, paste, _ = _run_tmux(wd_wrapper, clock, scenario, watchdog=cfg,
                                         memory_root=root)
            assert wd_wrapper._wd is None
            assert result.status == AgentStatus.COMPLETED
            assert scenario.polls == 4  # 2 grace + 2 confirm, unchanged
            assert not paste.called
        assert not (memory_root / "heartbeats").exists()

    def test_watchdog_tick_runs_on_suspected_dead_path(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        """Regression: the tick must fire on the post-grace single-negative
        ``continue`` path (which skips the rest of the iteration)."""
        # polls: grace, grace, dead(1)->continue, alive(reset), dead, dead->done.
        alive_seq = iter([True, True, False, True, False, False])
        with mock.patch.object(LifecycleWrapper, "_tmux_pane_alive",
                               side_effect=lambda pid: next(alive_seq)) as alive, \
             mock.patch.object(LifecycleWrapper, "_tmux_claude_running", return_value=True), \
             mock.patch.object(LifecycleWrapper, "_kill_tmux_window"), \
             mock.patch.object(LifecycleWrapper, "_capture_tmux_pane", return_value=IDLE_PANE), \
             mock.patch.object(wd_wrapper, "monitor_team",
                               return_value=TeamStatus(team_name="alpha")), \
             mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep):
            spy = _StatusSpy(wd_wrapper)
            with spy:
                result = wd_wrapper.wait_for_completion(
                    LeadProcess(tmux_pane_id="%5", team_name="alpha"), poll_interval=POLL,
                    on_status=lambda *_: None,
                    watchdog=_wd_config(), memory_root=memory_root,
                )
        assert result.status == AgentStatus.COMPLETED
        assert alive.call_count == 6
        assert spy.calls == 6  # one tick per poll, including the dead-path poll (#3)
        assert len(_tick_trace(memory_root)) == 6

    def test_single_pane_capture_per_poll(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        """ONE capture per poll, shared by the watchdog and on_status (last 5 lines)."""
        snapshots: list[str] = []
        scenario = _TmuxScenario(
            alive_polls=3, text_for_poll=lambda k: f"l1\nl2\nl3\nl4\nl5\nl6-{k}\n\u276f \n")
        result, _, capture = _run_tmux(
            wd_wrapper, clock, scenario, watchdog=_wd_config(), memory_root=memory_root,
            on_status=lambda _ts, snap: snapshots.append(snap),
        )
        assert result.status == AgentStatus.COMPLETED
        assert capture.call_count == scenario.polls == 5  # 3 alive + 2 confirm
        # 3 alive-path snapshots = last 5 lines of the shared capture; the
        # suspected-dead poll keeps its pre-existing "" snapshot.
        assert [len(snap.splitlines()) for snap in snapshots] == [5, 5, 5, 0]
        assert snapshots[0].splitlines()[-1] == "\u276f "
        assert snapshots[2].splitlines()[-2] == "l6-2"

    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_paste_and_submit_uses_named_buffer(
        self, mock_run: mock.MagicMock, mock_sleep: mock.MagicMock,
    ) -> None:
        LifecycleWrapper._paste_and_submit("%5", "hello there")
        cmds = [c.args[0] for c in mock_run.call_args_list]
        assert cmds[0][:5] == ["tmux", "load-buffer", "-b", "zo-nudge", "-"]
        assert mock_run.call_args_list[0].kwargs["input"] == "hello there"
        assert cmds[1] == ["tmux", "paste-buffer", "-b", "zo-nudge", "-d", "-t", "%5"]
        assert cmds[2] == ["tmux", "send-keys", "-t", "%5", "Enter"]
        # No temp file / default buffer involved.
        assert not any(c[1] == "load-buffer" and len(c) == 3 for c in cmds)

    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_launch_pastes_prompt_via_named_buffer(
        self, mock_run: mock.MagicMock, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper,
    ) -> None:
        """The launch path is refactored onto ``_paste_and_submit`` (behaviour-preserving)."""
        mock_run.return_value = mock.MagicMock(stdout="%5\n", returncode=0)
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}), \
             mock.patch.object(LifecycleWrapper, "_paste_and_submit") as paste:
            wrapper.launch_lead_session("the prompt", cwd="/target", team_name="a", use_tmux=True)
        assert paste.call_args_list[0] == mock.call("%5", "the prompt")

    @mock.patch("zo.wrapper.time.sleep")
    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_launch_records_pid_and_identity_best_effort(
        self, mock_run: mock.MagicMock, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper,
    ) -> None:
        """pane_pid → pgrep (newest child whose cmdline mentions claude) → pid + identity."""
        def fake_run(cmd, **kw):  # noqa: ANN001, ANN202
            out = "%5\n"
            if cmd[0] == "tmux" and cmd[1] == "display-message":
                out = "4242\n"
            elif cmd[0] == "pgrep":
                out = "4300\n4301\n"
            elif cmd[0] == "which":
                out = "/usr/local/bin/claude\n"
            return mock.MagicMock(stdout=out, returncode=0)
        mock_run.side_effect = fake_run
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux,1,0"}), \
             mock.patch("zo.wrapper.process_start_identity", return_value="darwin:1700000000:0"):
            result = wrapper.launch_lead_session("p", cwd="/target", team_name="a", use_tmux=True)
        assert result.pid == 4300
        assert result.pid_start_identity == "darwin:1700000000:0"
        # Filtered by command line so a shell's prompt helper / gitstatusd child
        # (which would later "die" and fake a dead lead) is never picked.
        assert ["pgrep", "-n", "-P", "4242", "-f", "claude"] in [
            c.args[0] for c in mock_run.call_args_list]

    @mock.patch("zo.wrapper.subprocess.run")
    def test_tmux_lead_identity_unresolvable_without_claude_child(
        self, mock_run: mock.MagicMock,
    ) -> None:
        """No claude child (only a prompt helper) → (None, None): unknown, never a wrong pid."""
        mock_run.return_value = mock.MagicMock(stdout="\n", returncode=1)
        assert LifecycleWrapper._resolve_tmux_lead_identity(4242) == (None, None)
        assert LifecycleWrapper._resolve_tmux_lead_identity(None) == (None, None)

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_headless_launch_records_identity(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper,
    ) -> None:
        mock_popen.return_value.pid = 4242
        with mock.patch("zo.wrapper.process_start_identity", return_value="linux:12345"):
            result = wrapper.launch_lead_session("p", cwd="/t", team_name="a", use_tmux=False)
        assert result.pid == 4242
        assert result.pid_start_identity == "linux:12345"

    def test_start_watchdog_gitignores_heartbeats_in_zo_dir_layout(
        self, wd_wrapper: LifecycleWrapper, tmp_path: Path,
    ) -> None:
        """Runtime files under ``<delivery>/.zo/memory/heartbeats/`` must never be
        committed with ``git add .zo/``: an existing ``.zo/.gitignore`` gains the
        entry once (idempotent); legacy layouts (no such file) are untouched."""
        zo_dir = tmp_path / "repo" / ".zo"
        (zo_dir / "memory").mkdir(parents=True)
        (zo_dir / ".gitignore").write_text("local.yaml\n")
        for _ in range(2):
            wd_wrapper._start_watchdog(_wd_config(), memory_root=zo_dir / "memory",
                                       zo_session_id="zo-s1", delivery_repo=None)
        text = (zo_dir / ".gitignore").read_text()
        assert text.split().count("memory/heartbeats/") == 1
        assert text.startswith("local.yaml\n")
        legacy = tmp_path / "zo" / "memory" / "proj"
        legacy.mkdir(parents=True)
        wd_wrapper._start_watchdog(_wd_config(), memory_root=legacy,
                                   zo_session_id="zo-s1", delivery_repo=None)
        assert not (legacy.parent / ".gitignore").exists()

    def test_wait_for_completion_builds_runner_and_persists_state(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        scenario = _TmuxScenario(alive_polls=1, text_for_poll=lambda k: IDLE_PANE)
        _run_tmux(wd_wrapper, clock, scenario, watchdog=_wd_config(), memory_root=memory_root)
        state = load_state(memory_root)
        assert state is not None
        assert state.zo_session_id == "zo-s1"
        assert state.ticks == scenario.polls == 4  # 1 alive + grace-absorbed + 2 confirm


# ---- seeded stall → nudge → escalate (oracle check 11) ----


class TestSeededStallTmux:
    """Seeded half (check 11): a 10-min stall is caught, nudged within budget,
    escalated exactly once, and surfaces as STALLED."""

    def test_seeded_10min_stall_detected_and_escalated_within_one_poll(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        scenario = _TmuxScenario(alive_polls=15, text_for_poll=lambda k: IDLE_PANE)

        result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                     watchdog=_wd_config(), memory_root=memory_root)

        cfg = _wd_config()
        assert 1 <= paste.call_count <= cfg.nudge_budget
        assert all(c.args == ("%5", cfg.nudge_message) for c in paste.call_args_list)
        errors = [e for e in _comms_events(tmp_path)
                  if e["event_type"] == "error" and e["error_type"] == "stall"]
        assert any(e["severity"] == "warning" for e in errors)  # first detection
        blocking = [e for e in errors if e["severity"] == "blocking"]
        assert len(blocking) == 1 and blocking[0]["escalated_to"] == "human"
        actions = [t["action"] for t in _tick_trace(memory_root)]
        # Stall lands on the first tick past the 600 s threshold (tick 10);
        # nudges 10..12; escalate on the very next tick after budget exhaustion.
        assert actions[:10] == ["none"] * 10
        assert actions[10:13] == ["nudge"] * 3
        assert actions[13] == "escalate"
        assert actions.count("escalate") == 1
        assert result.status == AgentStatus.STALLED
        assert result.stalled is True
        assert result.nudges_used == 3

    def test_seeded_rate_limited_session_is_never_nudged(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        """Banner with a reset still ahead (10:30) for the whole run: no keys, no
        stall nudge, no escalation; died while paused → RATE_LIMITED + resume_at."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        banner = BANNER_PANE.replace("10:05", "10:30")
        scenario = _TmuxScenario(alive_polls=14, text_for_poll=lambda k: banner)
        spy = _StatusSpy(wd_wrapper)
        with spy:
            result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                         watchdog=_wd_config(), memory_root=memory_root)
        assert not paste.called
        assert AgentStatus.PAUSED_RATE_LIMIT in spy.statuses
        checkpoints = [e for e in _comms_events(tmp_path)
                       if e["event_type"] == "checkpoint" and e["agent"] == "watchdog"]
        assert [c["subtask"] for c in checkpoints].count("rate-limit-pause") == 1
        actions = {t["action"] for t in _tick_trace(memory_root)}
        assert actions == {"pause"}
        assert all(t["never_block"] == "rate_limit" for t in _tick_trace(memory_root))
        # Died while paused → RATE_LIMITED (not COMPLETED) with the parsed reset time.
        assert result.status == AgentStatus.RATE_LIMITED
        assert result.resume_at == datetime(2026, 8, 17, 10, 30, 15, tzinfo=UTC)

    def test_seeded_static_banner_resumes_at_reset_without_rollover(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        """Regression: the real TUI never clears the usage-limit line. Past the
        parsed reset an UNCHANGED banner is stale → one resume nudge (not a
        day-rollover extension); heartbeat progress with the banner still on
        screen is a verified RESUME; the spent banner is then ignored."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))

        def text_for_poll(k: int) -> str:
            if k == 7:  # Claude worked after the resume nudge; banner still visible
                _plant_heartbeat(memory_root, tick_count=6, at=clock.now)
            return BANNER_PANE  # never changes

        scenario = _TmuxScenario(alive_polls=9, text_for_poll=text_for_poll)
        spy = _StatusSpy(wd_wrapper)
        with spy:
            result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                         watchdog=_wd_config(), memory_root=memory_root)
        cfg = _wd_config()
        assert paste.call_count == 1
        assert paste.call_args == mock.call("%5", cfg.nudge_message)
        trace = _tick_trace(memory_root)
        actions = [t["action"] for t in trace]
        assert actions[:6] == ["pause"] * 6  # 10:00..10:05 < 10:05:15
        assert actions[6] == "resume_nudge"  # 10:06: banner unchanged → stale, not extended
        assert actions[7] == "resume"  # verified by heartbeat delta, banner still on screen
        assert trace[8]["never_block"] is None and actions[8] == "none"  # spent banner ignored
        assert "escalate" not in actions
        assert spy.statuses[7] == AgentStatus.RUNNING
        state = load_state(memory_root)
        assert state is not None and state.paused_at is None and state.paused_until is None
        assert state.total_paused_sec == 420.0 and state.pause_attempts == 1
        assert result.status == AgentStatus.COMPLETED  # pause resolved → not RATE_LIMITED
        assert result.pause_total_sec == 420.0

    def test_permission_dialog_is_never_nudged(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        scenario = _TmuxScenario(alive_polls=14, text_for_poll=lambda k: DIALOG_PANE)
        result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                     watchdog=_wd_config(), memory_root=memory_root)
        assert not paste.called
        trace = _tick_trace(memory_root)
        assert len(trace) >= 14  # the watchdog actually ticked (not vacuous)
        assert all(t["never_block"] == "awaiting_input" for t in trace)
        assert "nudge" not in {t["action"] for t in trace}
        assert result.status == AgentStatus.COMPLETED

    def test_prose_rate_limit_mention_does_not_misclassify_finished_session(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
    ) -> None:
        """Regression: a lead that finishes with a summary *mentioning* a rate
        limit (prose, no reset time, no banner) and sits idle at the prompt is
        COMPLETED when the pane closes — not RATE_LIMITED for the driver to
        relaunch. An ML 'patience limit reached' line is not even a pause."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        prose = ("Done. Note: the API hit a rate limit earlier and retried; "
                 "all tests pass.\n\n❯ \n")
        scenario = _TmuxScenario(alive_polls=2, text_for_poll=lambda k: prose)
        result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                     watchdog=_wd_config(rate_limit_backoff_base_sec=600),
                                     memory_root=memory_root)
        trace = _tick_trace(memory_root)
        assert trace[0]["never_block"] == "rate_limit" and trace[0]["action"] == "pause"
        assert not paste.called  # closed within the backoff: no probe was due
        assert result.status == AgentStatus.COMPLETED and result.resume_at is None
        ml = "Training finished. early stopping: patience limit reached at epoch 30\n\n❯ \n"
        scenario = _TmuxScenario(alive_polls=3, text_for_poll=lambda k: ml)
        result, _, _ = _run_tmux(wd_wrapper, clock, scenario,
                                 watchdog=_wd_config(), memory_root=memory_root)
        assert result.status == AgentStatus.COMPLETED
        assert all(t["never_block"] is None for t in _tick_trace(memory_root)[len(trace):])

    def test_busy_pane_never_sends_keys_and_escalates_after_grace(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        """Regression: a persistently busy pane (spinner / 'esc to interrupt')
        cannot be nudged, so a stall there must ESCALATE once after
        ``escalate_grace_sec`` — not return NUDGE forever with nothing sent."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        scenario = _TmuxScenario(alive_polls=14, text_for_poll=lambda k: BUSY_PANE)
        result, paste, _ = _run_tmux(wd_wrapper, clock, scenario,
                                     watchdog=_wd_config(escalate_grace_sec=60),
                                     memory_root=memory_root)
        assert not paste.called
        actions = [t["action"] for t in _tick_trace(memory_root)]
        assert "nudge" not in actions
        assert actions[:10] == ["none"] * 10  # 600 s threshold → stall at tick 10
        assert actions[11] == "escalate" and actions.count("escalate") == 1  # +60 s grace
        blocking = [e for e in _comms_events(tmp_path)
                    if e["event_type"] == "error" and e["error_type"] == "stall"
                    and e["severity"] == "blocking"]
        assert len(blocking) == 1 and "busy" in blocking[0]["description"]
        assert result.status == AgentStatus.STALLED  # died with no progress since escalation

    def test_nudge_guard_skips_when_pane_turns_busy_before_paste(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        """The paste-time pane-ready guard still holds (race: verdict on an idle
        capture, pane busy by paste time) → nothing sent, one 'nudge-skipped'."""
        wd_wrapper._start_watchdog(_wd_config(), memory_root=memory_root,
                                   zo_session_id="zo-s1", delivery_repo=None)
        assert wd_wrapper._wd is not None
        lead = LeadProcess(tmux_pane_id="%5", team_name="alpha")
        verdict = StallVerdict(action=StallAction.NUDGE, stalled=True, reason="r",
                               evaluated_at=clock.now)
        with mock.patch.object(LifecycleWrapper, "_paste_and_submit") as paste:
            wd_wrapper._wd_nudge(lead, verdict, text=BUSY_PANE)
            wd_wrapper._wd_nudge(lead, verdict, text=BUSY_PANE)  # same episode: logged once
        assert not paste.called
        assert wd_wrapper._wd.state.nudges_used == 0
        subtasks = [e["subtask"] for e in _comms_events(tmp_path)
                    if e["event_type"] == "checkpoint" and e["agent"] == "watchdog"]
        assert subtasks == ["nudge-skipped"]


# ---- rate-limit pause auto-resumes on reset (oracle check 12) ----


class TestSeededRateLimitResumeTmux:
    """Seeded half (check 12): banner with 'resets at' → pause; past reset with
    banner gone → one resume nudge; heartbeat delta → verified resume."""

    def test_seeded_rate_limit_pause_auto_resumes_on_reset(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path, tmp_path: Path,
    ) -> None:
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))

        def text_for_poll(k: int) -> str:
            if k == 7:  # heartbeat delta lands right after the resume nudge
                _plant_heartbeat(memory_root, tick_count=6, at=clock.now)
            return BANNER_PANE if k < 3 else IDLE_PANE

        scenario = _TmuxScenario(alive_polls=8, text_for_poll=text_for_poll)
        spy = _StatusSpy(wd_wrapper)
        with spy:
            # timeout=400 < 420 s of wall time spent paused: must NOT time out.
            result, paste, _ = _run_tmux(wd_wrapper, clock, scenario, watchdog=_wd_config(),
                                         memory_root=memory_root, timeout=400,
                                         patch_monotonic=True)

        cfg = _wd_config()
        assert paste.call_count == 1
        assert paste.call_args == mock.call("%5", cfg.nudge_message)
        actions = [t["action"] for t in _tick_trace(memory_root)]
        assert actions[0] == "pause"
        assert actions[6] == "resume_nudge"
        assert actions[7] == "resume"
        assert spy.statuses[0] == AgentStatus.PAUSED_RATE_LIMIT
        assert spy.statuses[7] == AgentStatus.RUNNING
        subtasks = [e["subtask"] for e in _comms_events(tmp_path)
                    if e["event_type"] == "checkpoint" and e["agent"] == "watchdog"]
        assert subtasks.count("rate-limit-pause") == 1
        assert subtasks.count("rate-limit-resume") == 1
        # paused_until parsed from "resets at 10:05" (+15 s slack).
        state = load_state(memory_root)
        assert state is not None and state.total_paused_sec == 420.0
        assert result.pause_total_sec == 420.0
        assert result.status == AgentStatus.COMPLETED  # not TIMED_OUT, not STALLED
        assert result.paused_until is None


# ---- headless harness: same three mechanisms (checks 11-12) ----


class TestSeededHeadless:
    """Headless: no input channel (never a paste); stall → kill → STALLED;
    running + banner → PAUSED; exited + banner → RATE_LIMITED with resume_at."""

    NEUTRAL = "Working on task 1\nWorking on task 2\n"
    BANNER = "You've hit your usage limit \u00b7 resets at 10:05\n"

    @mock.patch("zo.wrapper.os.kill")
    def test_seeded_10min_stall_kills_headless_session_and_returns_stalled(
        self, mock_kill: mock.MagicMock, wd_wrapper: LifecycleWrapper, clock: FakeClock,
        memory_root: Path, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        # Hard bound: the process "finishes" on its own after 20 polls, so a
        # regression that drops the escalation/kill FAILS (COMPLETED) instead
        # of hanging the suite forever.
        polls = iter([None] * 20 + [0])
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=lambda: next(polls),
                               stdout_text=self.NEUTRAL)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep), \
             mock.patch.object(wd_wrapper, "kill_session", wraps=wd_wrapper.kill_session) as kill, \
             mock.patch.object(LifecycleWrapper, "_paste_and_submit") as paste, \
             mock.patch("zo._wrapper_watchdog.process_tree_cpu_seconds", return_value=0.0):
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert not paste.called
        assert kill.call_count == 1
        assert mock_kill.call_args_list[0] == mock.call(99, signal.SIGTERM)
        assert result.status == AgentStatus.STALLED
        assert result.stalled is True and result.exit_code == -9
        actions = [t["action"] for t in _tick_trace(memory_root)]
        assert actions[:10] == ["none"] * 10 and actions[10] == "escalate"
        assert actions.count("escalate") == 1 and len(actions) == 11  # killed on that tick
        blocking = [e for e in _comms_events(tmp_path)
                    if e["event_type"] == "error" and e["error_type"] == "stall"
                    and e["severity"] == "blocking"]
        assert len(blocking) == 1

    @mock.patch("zo.wrapper.os.kill")
    def test_seeded_silent_training_with_busy_cpu_is_not_killed(
        self, mock_kill: mock.MagicMock, wd_wrapper: LifecycleWrapper, clock: FakeClock,
        memory_root: Path, tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        """Regression (40-minute training question): a headless lead that prints
        nothing and ticks no heartbeat but whose process tree burns CPU is
        WORKING, not stalled — no escalation, no SIGTERM, COMPLETED."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        polls = iter([None] * 40 + [0])  # 40 min of silence, then a clean exit
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=lambda: next(polls),
                               stdout_text=self.NEUTRAL)
        # Process-tree CPU time == wall time (one core saturated by train.py).
        cpu = mock.MagicMock(side_effect=lambda pid: clock.mono)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep), \
             mock.patch.object(wd_wrapper, "kill_session") as kill, \
             mock.patch("zo._wrapper_watchdog.process_tree_cpu_seconds", cpu):
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert cpu.call_args_list and cpu.call_args_list[0] == mock.call(99)
        assert not kill.called and not mock_kill.called
        assert result.status == AgentStatus.COMPLETED and result.stalled is False
        trace = _tick_trace(memory_root)
        assert len(trace) == 40 and {t["action"] for t in trace} == {"none"}
        assert all(t["progress"] for t in trace[1:])  # first sample only baselines
        assert not [e for e in _comms_events(tmp_path)
                    if e["event_type"] == "error" and e["error_type"] == "stall"]

    def test_seeded_rate_limited_headless_session_is_paused_never_nudged(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
        tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=[None] * 5 + [0],
                               stdout_text=self.BANNER)
        spy = _StatusSpy(wd_wrapper)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep), \
             mock.patch.object(LifecycleWrapper, "_paste_and_submit") as paste, spy:
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert not paste.called
        assert spy.statuses[0] == AgentStatus.PAUSED_RATE_LIMIT
        assert "nudge" not in {t["action"] for t in _tick_trace(memory_root)}
        subtasks = [e["subtask"] for e in _comms_events(tmp_path)
                    if e["event_type"] == "checkpoint" and e["agent"] == "watchdog"]
        assert subtasks.count("rate-limit-pause") == 1
        # Exited while paused → RATE_LIMITED with the parsed reset time.
        assert result.status == AgentStatus.RATE_LIMITED
        assert result.resume_at == datetime(2026, 8, 17, 10, 5, 15, tzinfo=UTC)

    def test_seeded_headless_pause_resumes_on_heartbeat_progress(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
        tmp_log_dir: Path, tmp_path: Path,
    ) -> None:
        """check 12 headless: resume requires progress (no nudge channel)."""
        _plant_heartbeat(memory_root, tick_count=5, at=T0 - timedelta(hours=1))
        polls = {"n": 0}

        def poll() -> int | None:
            polls["n"] += 1
            if polls["n"] == 8:  # heartbeat delta after the pause window
                _plant_heartbeat(memory_root, tick_count=6, at=clock.now)
            return 0 if polls["n"] > 9 else None

        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=poll, stdout_text=self.BANNER)
        spy = _StatusSpy(wd_wrapper)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep), \
             mock.patch.object(LifecycleWrapper, "_paste_and_submit") as paste, spy:
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert not paste.called
        actions = [t["action"] for t in _tick_trace(memory_root)]
        assert actions[0] == "pause" and "resume" in actions
        assert "resume_nudge" not in actions and "nudge" not in actions
        assert spy.statuses[0] == AgentStatus.PAUSED_RATE_LIMIT
        assert spy.statuses[-1] == AgentStatus.RUNNING
        assert result.status == AgentStatus.COMPLETED
        assert result.pause_total_sec > 0
        subtasks = [e["subtask"] for e in _comms_events(tmp_path)
                    if e["event_type"] == "checkpoint" and e["agent"] == "watchdog"]
        assert "rate-limit-resume" in subtasks

    def test_headless_clean_exit_mentioning_rate_limit_stays_completed(
        self, wd_wrapper: LifecycleWrapper, clock: FakeClock, memory_root: Path,
        tmp_log_dir: Path,
    ) -> None:
        """rc == 0 + prose 'rate limit' in the JSON result → COMPLETED (the
        pause was prose-only: no reset, no banner, no non-zero rc)."""
        text = '{"result": "Done. The API hit a rate limit once and retried."}\n'
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=[None, None, 0], stdout_text=text)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep):
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert _tick_trace(memory_root)[0]["action"] == "pause"  # conservative while running
        assert result.status == AgentStatus.COMPLETED and result.resume_at is None
        # Same text but a non-zero exit is corroboration → RATE_LIMITED.
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=[None, 1], stdout_text=text)
        with mock.patch("zo.wrapper.time.sleep", side_effect=clock.sleep):
            result = wd_wrapper.wait_for_completion(
                lead, poll_interval=POLL, watchdog=_wd_config(), memory_root=memory_root)
        assert result.status == AgentStatus.RATE_LIMITED

    def test_read_new_output_uses_byte_cursor_over_both_logs(
        self, wd_wrapper: LifecycleWrapper, tmp_log_dir: Path,
    ) -> None:
        lead = _headless_setup(wd_wrapper, tmp_log_dir, poll=None, stdout_text="a\n")
        assert lead.stderr_log is not None
        lead.stderr_log.write_text("e1\n")
        assert wd_wrapper._read_new_output(lead) == "a\ne1\n"
        assert wd_wrapper._read_new_output(lead) == ""  # nothing new
        with open(lead.stdout_log, "a") as fh:  # type: ignore[arg-type]
            fh.write("b\n")
        assert wd_wrapper._read_new_output(lead) == "b\n"
        assert wd_wrapper._wd_text_window == "a\ne1\nb\n"


# ---- WatchdogRunner unit behaviour ----


class TestWatchdogRunner:
    def test_start_baselines_existing_heartbeats_and_ticks_write_trace(
        self, memory_root: Path, clock: FakeClock,
    ) -> None:
        _plant_heartbeat(memory_root, tick_count=7, at=T0 - timedelta(minutes=5))
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root,
                                zo_session_id="zo-s1", clock=clock)
        runner.start()
        assert runner.state.baseline_ticks == {"lead-s1": 7}
        proc = LeadProcess(tmux_pane_id="%1")
        v = runner.tick(process=proc, text=IDLE_PANE, can_nudge=True)
        assert v.progress is False  # pre-existing file does not count
        _plant_heartbeat(memory_root, tick_count=8, at=clock.now)
        v = runner.tick(process=proc, text=IDLE_PANE, can_nudge=True)
        assert v.progress is True
        trace = _tick_trace(memory_root)
        assert len(trace) == 2 and set(trace[0]) == {
            "ts", "action", "stalled", "reason", "never_block", "progress"}
        assert (memory_root / "heartbeats" / "_watchdog.json").exists()

    def test_nudge_budget_survives_runner_restart_same_session(
        self, memory_root: Path, clock: FakeClock,
    ) -> None:
        r1 = WatchdogRunner(config=_wd_config(), memory_root=memory_root,
                            zo_session_id="zo-s1", clock=clock)
        r1.start()
        r1.record_nudge()
        r1.record_nudge()
        r2 = WatchdogRunner(config=_wd_config(), memory_root=memory_root,
                            zo_session_id="zo-s1", clock=clock)
        r2.start()
        assert r2.state.nudges_used == 2
        r3 = WatchdogRunner(config=_wd_config(), memory_root=memory_root,
                            zo_session_id="zo-other", clock=clock)
        r3.start()
        assert r3.state.nudges_used == 0

    def test_paused_seconds_includes_open_pause(self, memory_root: Path, clock: FakeClock) -> None:
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock)
        runner.start()
        proc = LeadProcess(tmux_pane_id="%1")
        v = runner.tick(process=proc, text=BANNER_PANE, can_nudge=True)
        assert v.action.value == "pause"
        clock.advance(120)
        assert runner.paused_seconds() == 120.0
        assert runner.is_rate_limited is True

    def test_paused_seconds_stops_accruing_at_escalation(
        self, memory_root: Path, clock: FakeClock,
    ) -> None:
        """Regression: banner gone + no progress → 'resume unverified' escalation;
        the open pause must NOT keep suspending the wall-clock timeout forever."""
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock, tz=UTC)
        runner.start()
        proc = LeadProcess(tmux_pane_id="%1")
        plain = "Rate limit reached. Try again later.\n\n❯ \n"
        assert runner.tick(process=proc, text=plain, can_nudge=False).action.value == "pause"
        clock.advance(61)  # backoff (60 s) elapsed, banner gone, headless-style (no nudge)
        assert runner.tick(process=proc, text=IDLE_PANE, can_nudge=False).action.value == "none"
        clock.advance(60)
        v = runner.tick(process=proc, text=IDLE_PANE, can_nudge=False)
        assert v.action.value == "escalate" and "unverified" in v.reason
        assert runner.paused_seconds() == 121.0
        clock.advance(3600)
        runner.tick(process=proc, text=IDLE_PANE, can_nudge=False)
        assert runner.paused_seconds() == 121.0  # capped at the escalation
        assert runner.state.paused_at is not None  # a late verified resume still wins

    def test_tz_threads_into_banner_parse(self, memory_root: Path, clock: FakeClock) -> None:
        """Regression: 'resets at 3pm' is the operator's LOCAL 3pm, not 15:00 UTC."""
        tz = timezone(timedelta(hours=-7))  # e.g. US/Pacific in summer
        clock.now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)  # 13:00 local
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock, tz=tz)
        runner.start()
        v = runner.tick(process=LeadProcess(tmux_pane_id="%1"),
                        text="You've hit your usage limit · resets at 3pm\n❯ \n",
                        can_nudge=True)
        assert v.action.value == "pause"
        assert runner.state.paused_until == datetime(2026, 8, 17, 22, 0, 15, tzinfo=UTC)
        assert runner.parsed_resume_at() == runner.state.paused_until
        default = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock)
        assert default.tz == datetime.now().astimezone().tzinfo  # local by default

    def test_cpu_busy_process_tree_counts_as_progress(
        self, memory_root: Path, clock: FakeClock,
    ) -> None:
        cpu = {"secs": 0.0}
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock,
                                cpu_probe=lambda pid: cpu["secs"])
        runner.start()
        proc = LeadProcess(pid=4242)
        assert runner.tick(process=proc, text="", can_nudge=False,
                           process_dead=False).progress is False  # baseline sample
        clock.advance(60)
        cpu["secs"] += 3.0  # 5 % of wall: an idle TUI redrawing, not work
        assert runner.tick(process=proc, text="", can_nudge=False,
                           process_dead=False).progress is False
        clock.advance(60)
        cpu["secs"] += 30.0  # 50 % of wall: a training job is running
        assert runner.tick(process=proc, text="", can_nudge=False,
                           process_dead=False).progress is True
        # No pid → no CPU evidence (never invents progress).
        assert runner.tick(process=LeadProcess(tmux_pane_id="%1"), text="",
                           can_nudge=True).progress is False

    def test_tick_never_probes_death_without_pid(self, memory_root: Path, clock: FakeClock) -> None:
        probe = mock.MagicMock(return_value=True)
        runner = WatchdogRunner(config=_wd_config(), memory_root=memory_root, clock=clock,
                                dead_probe=probe)
        runner.start()
        v = runner.tick(process=LeadProcess(tmux_pane_id="%1"), text=IDLE_PANE, can_nudge=True)
        assert v.process_dead is None and not probe.called
        v = runner.tick(process=LeadProcess(pid=4242, pid_start_identity="linux:1"),
                        text=IDLE_PANE, can_nudge=False)
        assert v.process_dead is True
        probe.assert_called_once_with(4242, "linux:1")

    def test_advisory_paths_fail_open(self, tmp_path: Path, clock: FakeClock) -> None:
        """Unwritable memory root: ticks still return verdicts, nothing raises."""
        blocked = tmp_path / "blocked.txt"
        blocked.write_text("not a dir")
        runner = WatchdogRunner(config=_wd_config(), memory_root=blocked, clock=clock)
        runner.start()
        v = runner.tick(process=LeadProcess(tmux_pane_id="%1"), text=IDLE_PANE, can_nudge=True)
        assert v.action.value == "none"
        runner.stop()
