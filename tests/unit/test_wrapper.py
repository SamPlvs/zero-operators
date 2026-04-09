"""Unit tests for zo.wrapper and zo._wrapper_models."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from zo._wrapper_models import (
    AgentStatus,
    LeadProcess,
    TeamMember,
    TeamStatus,
)
from zo.comms import CommsLogger
from zo.wrapper import LifecycleWrapper


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
    def test_builds_correct_command(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        mock_popen.return_value.pid = 42

        result = wrapper.launch_lead_session(
            "do the thing",
            cwd="/target",
            team_name="alpha",
            model="opus",
            max_turns=100,
            use_tmux=True,
        )

        args = mock_popen.call_args
        cmd = args[0][0]
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--max-turns" in cmd
        assert "100" in cmd
        assert "--cwd" in cmd
        assert "/target" in cmd
        assert "--teammate-mode" in cmd
        assert "tmux" in cmd
        assert "-p" in cmd
        assert "do the thing" in cmd

        assert result.pid == 42
        assert result.status == AgentStatus.SPAWNING
        assert result.team_name == "alpha"
        assert result.stdout_log is not None

    @mock.patch("zo.wrapper.subprocess.Popen")
    def test_no_tmux_flag_when_disabled(
        self, mock_popen: mock.MagicMock, wrapper: LifecycleWrapper
    ) -> None:
        mock_popen.return_value.pid = 10
        wrapper.launch_lead_session(
            "prompt", cwd="/cwd", team_name="t", use_tmux=False
        )

        cmd = mock_popen.call_args[0][0]
        assert "--teammate-mode" not in cmd
        assert "tmux" not in cmd


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
        with mock.patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,123,0"}):
            with mock.patch.object(
                LifecycleWrapper,
                "_list_tmux_panes",
                return_value=[{"id": "%0", "title": "main"}, {"id": "%1", "title": "agent"}],
            ):
                with mock.patch.object(
                    LifecycleWrapper,
                    "_capture_tmux_pane",
                    side_effect=["output-0", "output-1"],
                ):
                    result = wrapper.observe_tmux_panes()
                    assert result == {"%0": "output-0", "%1": "output-1"}


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
    def test_detects_rate_limit_and_backs_off(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        mock_proc = mock.MagicMock()
        # First poll: still running; second poll: done.
        mock_proc.poll.side_effect = [None, 0]
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        stdout_file = tmp_log_dir / "alpha-stdout.log"
        stdout_file.write_text("Error 429 Too Many Requests")

        lead = LeadProcess(pid=99, team_name="alpha", stdout_log=stdout_file)

        result = wrapper.wait_for_completion(lead, poll_interval=0.01)
        assert result.status == AgentStatus.COMPLETED
        # Should have called sleep for the backoff.
        assert mock_sleep.called

    @mock.patch("zo.wrapper.time.sleep")
    def test_rate_limit_exhausts_retries(
        self, mock_sleep: mock.MagicMock, wrapper: LifecycleWrapper, tmp_log_dir: Path
    ) -> None:
        wrapper._max_retries = 2
        mock_proc = mock.MagicMock()
        mock_proc.poll.return_value = None  # Never completes.
        wrapper._proc = mock_proc
        wrapper._stdout_fh = mock.MagicMock()
        wrapper._stderr_fh = mock.MagicMock()

        stdout_file = tmp_log_dir / "alpha-stdout.log"
        stdout_file.write_text("rate limit exceeded")

        lead = LeadProcess(pid=99, team_name="alpha", stdout_log=stdout_file)

        result = wrapper.wait_for_completion(lead, poll_interval=0.01)
        assert result.status == AgentStatus.RATE_LIMITED


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
    @pytest.mark.parametrize(
        "text",
        [
            "HTTP 429 response",
            "rate limit exceeded",
            "Rate-Limited by server",
            "API overloaded",
            "too many requests",
        ],
    )
    def test_catches_known_patterns(self, text: str) -> None:
        assert LifecycleWrapper._detect_rate_limit(text) is True

    def test_returns_false_for_normal_output(self) -> None:
        assert LifecycleWrapper._detect_rate_limit("All tasks completed successfully.") is False


# ------------------------------------------------------------------ #
# _backoff_wait
# ------------------------------------------------------------------ #


class TestBackoffWait:
    def test_returns_increasing_durations(
        self, wrapper: LifecycleWrapper
    ) -> None:
        d0 = wrapper._backoff_wait(0)
        d1 = wrapper._backoff_wait(1)
        d2 = wrapper._backoff_wait(2)
        # base=30. Without jitter: 30, 60, 120. With jitter (+0..5):
        assert 30 <= d0 <= 35
        assert 60 <= d1 <= 65
        assert 120 <= d2 <= 125


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
