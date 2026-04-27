"""Lifecycle wrapper for Claude Code agent team sessions.

Launches ONE Claude Code session (the Lead Orchestrator), then observes
team activity by monitoring file-system artefacts and tmux panes.

Two launch modes:

* **tmux** (default when inside a tmux session): spawns Claude Code
  in a visible tmux pane so the user can watch the interactive TUI.
  Agent teams with ``teammateMode: "tmux"`` naturally split into
  additional panes.
* **headless** (``--no-tmux`` or not inside tmux): runs Claude Code
  with ``--print --output-format json`` in a background subprocess
  with stdout/stderr piped to log files.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import re
import shlex
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from zo._wrapper_models import (
    AgentStatus,
    LeadProcess,
    TeamMember,
    TeamStatus,
)

if TYPE_CHECKING:
    from zo.comms import CommsLogger

__all__ = [
    "LifecycleWrapper",
    "AgentStatus",
    "LeadProcess",
    "TeamMember",
    "TeamStatus",
]

_RATE_LIMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"429", re.IGNORECASE),
    re.compile(r"rate.?limit", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
]


class LifecycleWrapper:
    """Manages the lifecycle of a Claude Code lead orchestrator session.

    Args:
        comms: CommsLogger instance for audit trail events.
        claude_bin: Path or name of the ``claude`` CLI binary.
        log_dir: Directory for stdout/stderr logs (default ``logs/wrapper``).
        max_retries: Max retries on rate-limit errors.
        base_backoff: Base backoff in seconds for rate-limit waits.
    """

    def __init__(
        self,
        comms: CommsLogger,
        *,
        claude_bin: str = "claude",
        log_dir: Path | None = None,
        max_retries: int = 3,
        base_backoff: float = 30.0,
    ) -> None:
        self._comms = comms
        self._claude_bin = claude_bin
        self._log_dir = Path(log_dir) if log_dir else Path("logs/wrapper")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._max_retries = max_retries
        self._base_backoff = base_backoff

    # --- Launch ---

    def launch_lead_session(
        self,
        prompt: str,
        *,
        cwd: str,
        team_name: str,
        model: str = "opus",
        max_turns: int = 200,
        use_tmux: bool = True,
        add_dirs: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> LeadProcess:
        """Launch one Claude Code session as the Lead Orchestrator.

        When inside tmux (and ``use_tmux`` is True), spawns Claude Code
        in a visible tmux pane so the user can watch the interactive TUI.
        Otherwise falls back to headless mode with ``--print``.

        Args:
            add_dirs: Extra directories to grant Claude Code access to
                via ``--add-dir``.  Use for delivery repos, data paths,
                and other directories agents need to read/write.
            extra_env: Extra environment variables to set for the
                Claude Code subprocess. For tmux launches, prepended
                inline to the shell command. For headless launches,
                merged into the subprocess ``env``. Used by the
                low-token preset to set
                ``CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60``.
        """
        extra = add_dirs or []
        env = extra_env or {}
        if use_tmux and self._is_in_tmux():
            return self._launch_tmux(prompt, cwd=cwd, team_name=team_name,
                                     model=model, max_turns=max_turns,
                                     add_dirs=extra, extra_env=env)
        return self._launch_headless(prompt, cwd=cwd, team_name=team_name,
                                     model=model, max_turns=max_turns,
                                     add_dirs=extra, extra_env=env)

    def _launch_tmux(
        self,
        prompt: str,
        *,
        cwd: str,
        team_name: str,
        model: str,
        max_turns: int,
        add_dirs: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> LeadProcess:
        """Launch Claude Code interactively in a visible tmux window.

        ``claude -p "..." --dangerously-skip-permissions`` runs
        non-interactively (no TUI).  To get the full interactive
        experience the user wants, we:

        1. Open a tmux window and start ``claude`` without ``-p``
        2. Wait for the TUI to render
        3. Paste the prompt into the TUI via tmux's paste buffer
        4. Send Enter — Claude processes it with the TUI visible
        """
        prompt_file = self._log_dir / f"{team_name}-prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        stdout_log = self._log_dir / f"{team_name}-stdout.log"
        stderr_log = self._log_dir / f"{team_name}-stderr.log"

        claude_abs = self._resolve_claude_bin()

        # 1. Create a new tmux window with a shell
        result = subprocess.run(
            ["tmux", "new-window", "-d", "-n", team_name,
             "-P", "-F", "#{pane_id}"],
            capture_output=True, text=True, timeout=10,
        )
        pane_id = result.stdout.strip()

        # 2. Start claude interactively (NO -p, NO --dangerously-skip-permissions)
        #    --dangerously-skip-permissions exits immediately in interactive mode.
        #    Permissions are handled via .claude/settings.json allow/deny rules.
        #    --add-dir grants access to the ZO root plus any delivery repos,
        #    data paths, or other directories agents need without prompting.
        add_dir_flags = f' --add-dir {shlex.quote(cwd)}'
        for d in (add_dirs or []):
            add_dir_flags += f' --add-dir {shlex.quote(d)}'
        env_prefix = ""
        for k, v in (extra_env or {}).items():
            env_prefix += f'{k}={shlex.quote(v)} '
        interactive_cmd = (
            f'{env_prefix}'
            f'{shlex.quote(claude_abs)}'
            f' --model {shlex.quote(model)}'
            f' --max-turns {max_turns}'
            f'{add_dir_flags}'
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, interactive_cmd, "Enter"],
            capture_output=True, text=True, timeout=10,
        )

        # 3. Wait for Claude Code TUI to become ready for input.
        #    Instead of a fixed sleep (fragile — differs per machine),
        #    poll the tmux pane content until the TUI has rendered.
        #    Claude Code shows its interface (box-drawing chars, model
        #    name, input area) once ready.  We detect this by checking
        #    that the pane has substantial content and has stabilised
        #    (same content for 2 consecutive polls).
        self._wait_for_tui_ready(pane_id, timeout_seconds=30)

        # 4. Load the prompt into tmux's paste buffer and paste it
        #    into the Claude TUI input field.
        subprocess.run(
            ["tmux", "load-buffer", str(prompt_file)],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["tmux", "paste-buffer", "-t", pane_id],
            capture_output=True, text=True, timeout=10,
        )

        # 5. Send Enter to submit the prompt.  Wait briefly for the
        #    paste to be ingested by the TUI before pressing Enter.
        time.sleep(1)
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "Enter"],
            capture_output=True, text=True, timeout=10,
        )

        # 6. Verify the prompt was submitted by checking that pane
        #    content changed after the paste (not still showing the
        #    empty input field).
        self._verify_prompt_submitted(pane_id, prompt_file)

        lead = LeadProcess(
            pid=None, status=AgentStatus.SPAWNING,
            started_at=datetime.now(UTC), team_name=team_name,
            stdout_log=stdout_log, stderr_log=stderr_log,
            tmux_pane_id=pane_id,
        )
        self._comms.log_checkpoint(
            agent="wrapper", phase="launch", subtask="lead-session",
            progress=f"Launched lead session in tmux pane={pane_id} team={team_name}",
        )
        self._proc = None
        self._stdout_fh = None
        self._stderr_fh = None
        return lead

    @staticmethod
    def _capture_pane(pane_id: str) -> str:
        """Capture the current visible content of a tmux pane."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", pane_id],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout
        except Exception:  # noqa: BLE001
            return ""

    def _wait_for_tui_ready(
        self, pane_id: str, *, timeout_seconds: int = 30,
    ) -> None:
        """Poll tmux pane until Claude Code TUI is ready for input.

        Replaces the fragile fixed ``time.sleep(8)``.  Checks:
        1. Pane has substantial content (TUI rendered, not just shell)
        2. Content has stabilised (same for 2 consecutive polls)

        Falls back to the full timeout if detection fails — never
        shorter than a safe minimum.
        """
        min_content_len = 100  # TUI frame + header = well over 100 chars
        poll_interval = 1.0
        stable_required = 2  # consecutive polls with same content
        min_wait = 3  # always wait at least 3s for process to start

        time.sleep(min_wait)

        prev_content = ""
        stable_count = 0
        elapsed = min_wait

        while elapsed < timeout_seconds:
            content = self._capture_pane(pane_id)
            content_stripped = content.strip()

            if len(content_stripped) > min_content_len:
                if content_stripped == prev_content:
                    stable_count += 1
                    if stable_count >= stable_required:
                        self._comms.log_checkpoint(
                            agent="wrapper",
                            phase="launch",
                            subtask="tui-ready",
                            progress=(
                                f"TUI ready after {elapsed:.0f}s "
                                f"({len(content_stripped)} chars)"
                            ),
                        )
                        return
                else:
                    stable_count = 0
                prev_content = content_stripped

            time.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout — log warning but proceed (paste may still work)
        self._comms.log_error(
            agent="wrapper",
            error_type="tui_timeout",
            severity="warning",
            description=(
                f"TUI readiness not detected after {timeout_seconds}s. "
                f"Proceeding with paste — prompt may need manual "
                f"resubmission from the saved prompt file."
            ),
        )

    def _verify_prompt_submitted(
        self, pane_id: str, prompt_file: Path,
    ) -> None:
        """Check that the paste was received by comparing pane content.

        If the pane still looks like an empty input field (no prompt
        text visible), attempt one retry.  If retry also fails, log
        a warning with the prompt file path for manual recovery.
        """
        time.sleep(2)  # give Claude a moment to process
        content = self._capture_pane(pane_id)

        # Check for signs that Claude is processing: content should be
        # longer than just the TUI frame, or contain thinking indicators
        if len(content.strip()) < 200:
            # Possible missed paste — retry once
            self._comms.log_checkpoint(
                agent="wrapper",
                phase="launch",
                subtask="paste-retry",
                progress="Paste may have missed — retrying once.",
            )
            subprocess.run(
                ["tmux", "load-buffer", str(prompt_file)],
                capture_output=True, text=True, timeout=10,
            )
            subprocess.run(
                ["tmux", "paste-buffer", "-t", pane_id],
                capture_output=True, text=True, timeout=10,
            )
            time.sleep(1)
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                capture_output=True, text=True, timeout=10,
            )

            # Final check
            time.sleep(2)
            content = self._capture_pane(pane_id)
            if len(content.strip()) < 200:
                self._comms.log_error(
                    agent="wrapper",
                    error_type="paste_failed",
                    severity="warning",
                    description=(
                        f"Prompt paste failed after retry. "
                        f"Manual recovery: open the Claude tmux "
                        f"window and paste from {prompt_file}"
                    ),
                )

    def _launch_headless(
        self,
        prompt: str,
        *,
        cwd: str,
        team_name: str,
        model: str,
        max_turns: int,
        add_dirs: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> LeadProcess:
        """Launch Claude Code as a headless subprocess (--print mode)."""
        cmd: list[str] = [
            self._claude_bin, "--print",
            "--output-format", "json",
            "--model", model,
            "--max-turns", str(max_turns),
            "--add-dir", cwd,
            "--dangerously-skip-permissions",
        ]
        for d in (add_dirs or []):
            cmd.extend(["--add-dir", d])
        cmd.extend(["-p", prompt])

        stdout_log = self._log_dir / f"{team_name}-stdout.log"
        stderr_log = self._log_dir / f"{team_name}-stderr.log"
        stdout_fh = open(stdout_log, "w", encoding="utf-8")  # noqa: SIM115
        stderr_fh = open(stderr_log, "w", encoding="utf-8")  # noqa: SIM115

        import os
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)

        proc = subprocess.Popen(
            cmd, stdout=stdout_fh, stderr=stderr_fh, text=True, env=env,
        )
        lead = LeadProcess(
            pid=proc.pid, status=AgentStatus.SPAWNING,
            started_at=datetime.now(UTC), team_name=team_name,
            stdout_log=stdout_log, stderr_log=stderr_log,
        )
        self._comms.log_checkpoint(
            agent="wrapper", phase="launch", subtask="lead-session",
            progress=f"Launched lead session pid={proc.pid} team={team_name}",
        )
        self._proc = proc
        self._stdout_fh = stdout_fh
        self._stderr_fh = stderr_fh
        return lead

    # --- Observe ---

    def monitor_team(self, team_name: str) -> TeamStatus:
        """Poll file-system artefacts for team member and task status.

        Reads ``~/.claude/teams/{team_name}/config.json`` and task files.
        Returns empty TeamStatus if the team directory doesn't exist yet.
        """
        members = self._read_team_config(team_name)
        tasks = self.read_task_list(team_name)
        completed = sum(1 for t in tasks if t.get("status") == "completed")
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        pending = sum(1 for t in tasks if t.get("status") == "pending")
        return TeamStatus(
            team_name=team_name, members=members, tasks_total=len(tasks),
            tasks_completed=completed, tasks_in_progress=in_progress,
            tasks_pending=pending,
            is_active=len(tasks) == 0 or in_progress > 0 or pending > 0,
        )

    def read_task_list(self, team_name: str) -> list[dict[str, Any]]:
        """Read all task JSON files from ``~/.claude/tasks/{team_name}/``."""
        tasks_dir = Path.home() / ".claude" / "tasks" / team_name
        if not tasks_dir.is_dir():
            return []
        tasks: list[dict[str, Any]] = []
        for path in sorted(tasks_dir.iterdir()):
            if path.suffix != ".json":
                continue
            try:
                tasks.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return tasks

    def monitor_session_logs(self, session_dir: Path) -> list[dict[str, Any]]:
        """Read JSONL session logs from a directory. Handles missing/empty gracefully."""
        if not session_dir.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(session_dir.glob("*.jsonl")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def observe_tmux_panes(self) -> dict[str, str]:
        """Capture output from all tmux panes. Returns empty dict if not in tmux."""
        if not self._is_in_tmux():
            return {}
        result: dict[str, str] = {}
        for pane in self._list_tmux_panes():
            pane_id = pane.get("id", "")
            if pane_id:
                result[pane_id] = self._capture_tmux_pane(pane_id)
        return result

    # --- Lifecycle ---

    def wait_for_completion(
        self,
        process: LeadProcess,
        *,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        on_status: Any | None = None,
        gate_mode_file: Path | None = None,
        project_name: str = "",
        delivery_repo: Path | None = None,
    ) -> LeadProcess:
        """Poll until the lead session completes.

        In tmux mode, monitors the pane existence. In headless mode,
        polls the subprocess. Calls ``on_status(team_status)`` each
        cycle if provided, so the CLI can print live progress.

        Args:
            gate_mode_file: Optional path to the ``gate_mode`` file.
                When provided, the wrapper re-reads the file each poll
                cycle and logs when the mode changes (set via
                ``zo gates set`` from another terminal).
            project_name: Project name for ``zo watch-training`` command.
            delivery_repo: Delivery repo path. When provided (with
                *project_name*), the wrapper auto-splits a training
                dashboard pane when training metrics appear.
        """
        self._gate_mode_file = gate_mode_file
        self._last_gate_mode: str | None = None
        self._training_pane_id: str | None = None
        self._project_name = project_name
        self._delivery_repo = delivery_repo
        try:
            if process.tmux_pane_id:
                return self._wait_tmux(process, poll_interval=poll_interval,
                                       timeout=timeout, on_status=on_status)
            return self._wait_headless(process, poll_interval=poll_interval,
                                       timeout=timeout, on_status=on_status)
        finally:
            self._close_training_pane()

    def _maybe_open_training_pane(self) -> None:
        """Open a training dashboard split-pane if metrics file appears.

        Only fires once.  Requires tmux and both *project_name* and
        *delivery_repo* to be set on the wrapper instance.

        Looks for ``training_status.json`` inside the active Phase 4
        experiment's artifacts dir (``.zo/experiments/<exp_id>/``),
        which is where ``ZOTrainingCallback.for_experiment()`` writes.
        """
        if self._training_pane_id is not None:
            return  # already open (or attempted)
        if not self._project_name or not self._delivery_repo:
            return
        if not self._is_in_tmux():
            return
        from zo.experiments import resolve_active_experiment_dir

        active_dir = resolve_active_experiment_dir(Path(self._delivery_repo))
        if active_dir is None:
            return
        metrics_file = active_dir / "training_status.json"
        if not metrics_file.exists():
            return

        # Split the current pane vertically — 40% for training dashboard
        try:
            result = subprocess.run(
                ["tmux", "split-window", "-v", "-p", "40", "-d",
                 "-P", "-F", "#{pane_id}",
                 "zo", "watch-training", "-p", self._project_name,
                 "--repo", str(self._delivery_repo)],
                capture_output=True, text=True, timeout=10,
            )
            pane_id = result.stdout.strip()
            if result.returncode == 0 and pane_id:
                self._training_pane_id = pane_id
                self._comms.log_checkpoint(
                    agent="wrapper", phase="training",
                    subtask="dashboard-open",
                    progress=f"Training dashboard opened in pane={pane_id}",
                )
            else:
                # Mark as attempted so we don't retry
                self._training_pane_id = ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._training_pane_id = ""

    def _close_training_pane(self) -> None:
        """Kill the training dashboard pane if it exists."""
        pane_id = getattr(self, "_training_pane_id", None)
        if not pane_id:
            return
        with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
            subprocess.run(
                ["tmux", "kill-pane", "-t", pane_id],
                capture_output=True, timeout=5,
            )
        self._training_pane_id = None

    def _check_gate_mode_change(self) -> None:
        """Re-read the gate_mode file and log if the mode changed."""
        gate_file = getattr(self, "_gate_mode_file", None)
        if gate_file is None or not gate_file.exists():
            return
        try:
            current = gate_file.read_text(encoding="utf-8").strip()
        except OSError:
            return
        last = getattr(self, "_last_gate_mode", None)
        if last is None:
            self._last_gate_mode = current
            return
        if current != last:
            self._comms.log_checkpoint(
                agent="wrapper", phase="lifecycle",
                subtask="gate-mode-change",
                progress=f"Gate mode changed: {last} -> {current}",
            )
            self._last_gate_mode = current

    def _wait_tmux(
        self,
        process: LeadProcess,
        *,
        poll_interval: float,
        timeout: float | None,
        on_status: Any | None,
    ) -> LeadProcess:
        """Wait for Claude to exit in the tmux pane, then clean up.

        Checks two conditions each poll cycle:
        1. Pane disappeared entirely (user killed the window) → done.
        2. Pane alive but Claude is no longer the foreground process
           (user typed /exit, Claude exited) → kill the window → done.
        """
        start_time = time.monotonic()
        process = process.model_copy(update={"status": AgentStatus.RUNNING})
        pane_id = process.tmux_pane_id or ""

        while True:
            self._check_gate_mode_change()
            self._maybe_open_training_pane()

            pane_exists = self._tmux_pane_alive(pane_id)
            claude_running = pane_exists and self._tmux_claude_running(pane_id)

            if not pane_exists or not claude_running:
                # Claude exited — clean up the leftover shell window.
                if pane_exists:
                    self._kill_tmux_window(pane_id)
                process = process.model_copy(update={
                    "exit_code": 0, "completed_at": datetime.now(UTC),
                    "status": AgentStatus.COMPLETED,
                })
                self._comms.log_checkpoint(
                    agent="wrapper", phase="lifecycle", subtask="completion",
                    progress="Lead session completed, agent window closed",
                )
                return process

            if on_status:
                team_status = self.monitor_team(process.team_name)
                pane_snapshot = self._capture_tmux_pane(pane_id, lines=5)
                on_status(team_status, pane_snapshot)

            if timeout and (time.monotonic() - start_time) > timeout:
                process = process.model_copy(update={"status": AgentStatus.TIMED_OUT})
                self._comms.log_error(
                    agent="wrapper", error_type="timeout", severity="blocking",
                    description=f"Lead session timed out after {timeout}s",
                )
                return process
            time.sleep(poll_interval)

    def _wait_headless(
        self,
        process: LeadProcess,
        *,
        poll_interval: float,
        timeout: float | None,
        on_status: Any | None,
    ) -> LeadProcess:
        """Wait for the headless subprocess to exit."""
        start_time = time.monotonic()
        retries = 0
        process = process.model_copy(update={"status": AgentStatus.RUNNING})

        while True:
            self._check_gate_mode_change()

            rc = self._proc.poll() if self._proc else -1
            if rc is not None:
                self._close_log_handles()
                process = process.model_copy(update={
                    "exit_code": rc, "completed_at": datetime.now(UTC),
                    "status": AgentStatus.COMPLETED if rc == 0 else AgentStatus.ERRORED,
                })
                self._comms.log_checkpoint(
                    agent="wrapper", phase="lifecycle", subtask="completion",
                    progress=f"Lead session exited code={rc}",
                )
                return process

            output = self._read_tail(process.stdout_log)
            if self._detect_rate_limit(output):
                if retries >= self._max_retries:
                    process = process.model_copy(update={"status": AgentStatus.RATE_LIMITED})
                    self._comms.log_error(
                        agent="wrapper", error_type="rate_limit", severity="blocking",
                        description=f"Rate limited after {retries} retries",
                    )
                    return process
                wait_secs = self._backoff_wait(retries)
                self._comms.log_checkpoint(
                    agent="wrapper", phase="lifecycle", subtask="rate-limit-backoff",
                    progress=f"Rate limited, retry {retries + 1}/{self._max_retries}, "
                             f"waiting {wait_secs:.0f}s",
                )
                time.sleep(wait_secs)
                retries += 1
                continue

            if on_status:
                team_status = self.monitor_team(process.team_name)
                on_status(team_status, "")

            if timeout and (time.monotonic() - start_time) > timeout:
                process = process.model_copy(update={"status": AgentStatus.TIMED_OUT})
                self._comms.log_error(
                    agent="wrapper", error_type="timeout", severity="blocking",
                    description=f"Lead session timed out after {timeout}s",
                )
                return process
            time.sleep(poll_interval)

    def kill_session(self, process: LeadProcess) -> LeadProcess:
        """Terminate the lead session. SIGTERM, wait 5s, SIGKILL if needed."""
        if process.tmux_pane_id:
            # Kill the tmux pane (sends SIGHUP to the process inside)
            subprocess.run(
                ["tmux", "kill-pane", "-t", process.tmux_pane_id],
                capture_output=True, timeout=5,
            )
            self._comms.log_error(
                agent="wrapper", error_type="session_killed", severity="warning",
                description=f"Killed lead session tmux pane={process.tmux_pane_id}",
            )
            return process.model_copy(update={
                "status": AgentStatus.ERRORED,
                "completed_at": datetime.now(UTC),
                "exit_code": -9,
            })

        if process.pid is None:
            return process
        with contextlib.suppress(ProcessLookupError):
            os.kill(process.pid, signal.SIGTERM)
        try:
            if self._proc:
                self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.kill(process.pid, signal.SIGKILL)
        self._close_log_handles()
        self._comms.log_error(
            agent="wrapper", error_type="session_killed", severity="warning",
            description=f"Killed lead session pid={process.pid}",
        )
        return process.model_copy(update={
            "status": AgentStatus.ERRORED,
            "completed_at": datetime.now(UTC),
            "exit_code": -9,
        })

    # --- Output parsing ---

    def get_session_output(self, process: LeadProcess) -> str:
        """Read the full stdout log file for a completed session."""
        if process.stdout_log and process.stdout_log.exists():
            return process.stdout_log.read_text(encoding="utf-8")
        return ""

    def parse_session_result(self, process: LeadProcess) -> dict[str, str]:
        """Parse JSON output from --output-format json.

        Returns dict with result, cost_usd, model, num_turns.
        Falls back to {"result": raw_text} if JSON parsing fails.
        """
        raw = self.get_session_output(process)
        if not raw:
            return {"result": ""}
        try:
            data = json.loads(raw)
            return {
                "result": str(data.get("result", "")),
                "cost_usd": str(data.get("cost_usd", "")),
                "model": str(data.get("model", "")),
                "num_turns": str(data.get("num_turns", "")),
            }
        except (json.JSONDecodeError, ValueError):
            return {"result": raw}

    # --- Private: rate limit handling ---

    @staticmethod
    def _detect_rate_limit(output: str) -> bool:
        """Return True if output contains rate-limit / overload patterns."""
        return any(pat.search(output) for pat in _RATE_LIMIT_PATTERNS)

    def _backoff_wait(self, attempt: int) -> float:
        """Exponential backoff: base * 2^attempt + random(0, 5)."""
        return self._base_backoff * (2 ** attempt) + random.uniform(0, 5)

    # --- Private: resolve claude binary ---

    def _resolve_claude_bin(self) -> str:
        """Return absolute path to the claude binary."""
        try:
            result = subprocess.run(
                ["which", self._claude_bin],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return self._claude_bin

    # --- Private: tmux helpers ---

    @staticmethod
    def _tmux_pane_alive(pane_id: str) -> bool:
        """Check if a tmux pane still exists (process running in it)."""
        if not pane_id:
            return False
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id}"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return pane_id in result.stdout.splitlines()

    @staticmethod
    def _tmux_claude_running(pane_id: str) -> bool:
        """Check if Claude Code is the active process in a tmux pane.

        When the user types /exit in Claude Code, the process exits but
        the tmux pane's shell remains.  ``_tmux_pane_alive`` would still
        return True.  This method checks the *current command* running
        in the pane — if it's ``claude``, the session is active; if it
        has fallen back to the shell (``bash``, ``zsh``, ``fish``, etc.),
        Claude has exited.
        """
        if not pane_id:
            return False
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", pane_id,
                 "-p", "#{pane_current_command}"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False
        cmd = result.stdout.strip().lower()
        # Claude Code runs as "claude" or "node" (the underlying runtime).
        # When it exits, the pane falls back to the user's shell.
        shells = {"bash", "zsh", "fish", "sh", "dash", "tcsh", "csh"}
        return cmd not in shells and len(cmd) > 0

    @staticmethod
    def _kill_tmux_window(pane_id: str) -> None:
        """Kill the tmux window containing a pane (cleanup after exit)."""
        if not pane_id:
            return
        with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
            subprocess.run(
                ["tmux", "kill-window", "-t", pane_id],
                capture_output=True, timeout=5,
            )

    @staticmethod
    def _is_in_tmux() -> bool:
        """Check if the current process is inside a tmux session."""
        return "TMUX" in os.environ

    @staticmethod
    def _list_tmux_panes() -> list[dict[str, str]]:
        """List all tmux panes with their IDs and titles."""
        try:
            result = subprocess.run(
                ["tmux", "list-panes", "-a", "-F", "#{pane_id}|#{pane_title}"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        panes: list[dict[str, str]] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 1)
            if len(parts) == 2:
                panes.append({"id": parts[0], "title": parts[1]})
        return panes

    @staticmethod
    def _capture_tmux_pane(pane_id: str, lines: int = 50) -> str:
        """Capture last N lines from a tmux pane."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", pane_id, "-S", f"-{lines}"],
                capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
        return result.stdout if result.returncode == 0 else ""

    # --- Private: helpers ---

    def _read_team_config(self, team_name: str) -> list[TeamMember]:
        """Read team config.json and return a list of TeamMember."""
        config_path = Path.home() / ".claude" / "teams" / team_name / "config.json"
        if not config_path.exists():
            return []
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return [
            TeamMember(
                name=m.get("name", "unknown"), agent_type=m.get("agent_type", ""),
                status=m.get("status", "unknown"), current_task=m.get("current_task", ""),
            )
            for m in data.get("members", [])
        ]

    @staticmethod
    def _read_tail(path: Path | None, lines: int = 100) -> str:
        """Read the last N lines of a file."""
        if not path or not path.exists():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
            return "\n".join(text.splitlines()[-lines:])
        except OSError:
            return ""

    def _close_log_handles(self) -> None:
        """Close stdout/stderr file handles if open."""
        for fh in (getattr(self, "_stdout_fh", None), getattr(self, "_stderr_fh", None)):
            if fh and not fh.closed:
                fh.close()
