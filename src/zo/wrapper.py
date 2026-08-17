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

Both poll loops tick the WS-C watchdog (``zo._wrapper_watchdog.WatchdogRunner``,
plan oracle checks 11-12) once per iteration when ``wait_for_completion`` is
given a ``WatchdogConfig`` and a memory root: stalls are nudged (tmux, bounded,
pane-ready guarded) then escalated; rate limits pause the session and resume
on verified progress; headless stalls are killed and returned as ``STALLED``.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
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
from zo._wrapper_watchdog import WatchdogRunner, local_tz
from zo.watchdog import (
    StallAction,
    StallVerdict,
    WatchdogConfig,
    pane_ready_for_nudge,
    parse_rate_limit_reset,
    process_start_identity,
    rate_limit_match,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import tzinfo

    from zo.comms import CommsLogger

__all__ = [
    "LifecycleWrapper",
    "AgentStatus",
    "LeadProcess",
    "TeamMember",
    "TeamStatus",
]

# Rolling window of recent headless output fed to the watchdog each poll.
_HEADLESS_TEXT_WINDOW_CHARS = 16 * 1024
# tmux pane capture depth per poll (shared by the watchdog and on_status).
_PANE_CAPTURE_LINES = 200
# Named tmux buffer for wrapper pastes so the operator's buffer is untouched.
_TMUX_BUFFER_NAME = "zo-nudge"
# Watchdog runtime files must never land in a delivery repo's history.
_HEARTBEATS_GITIGNORE_ENTRY = "memory/heartbeats/"


def _ensure_heartbeats_gitignored(memory_root: Path) -> None:
    """Idempotently ignore ``memory/heartbeats/`` in a zo-dir ``.zo/.gitignore``.

    Only touches an EXISTING ``<memory_root>/../.gitignore`` (the ``.zo/``
    scaffold writes one); legacy layouts keep memory outside the delivery
    repo and need nothing. Same pattern as ``surrogate._ensure_surrogates_gitignored``.
    """
    gitignore = Path(memory_root).parent / ".gitignore"
    if not gitignore.is_file():
        return
    existing = gitignore.read_text(encoding="utf-8")
    if _HEARTBEATS_GITIGNORE_ENTRY in existing.split():
        return
    with open(gitignore, "a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(f"\n# Watchdog runtime files (heartbeats, state, tick trace)\n"
                 f"{_HEARTBEATS_GITIGNORE_ENTRY}\n")


class LifecycleWrapper:
    """Manages the lifecycle of a Claude Code lead orchestrator session.

    Args:
        comms: CommsLogger instance for audit trail events.
        claude_bin: Path or name of the ``claude`` CLI binary.
        log_dir: Directory for stdout/stderr logs (default ``logs/wrapper``).
        max_retries: Retained for API compatibility; the in-loop rate-limit
            retry was replaced by the watchdog pause/resume (WS-C).
        base_backoff: Retained for API compatibility (see ``max_retries``).
        clock: Injectable wall clock (tz-aware ``datetime``) used by the
            watchdog runner; defaults to ``datetime.now(UTC)``.
        tz: Zone in which rate-limit banner clock times ("resets at 3pm")
            are interpreted; defaults to the operator's local zone (Claude
            Code renders the reset in local time).
    """

    # tmux liveness-detection guards (see ``_wait_tmux``).
    # Number of initial polls during which negative liveness readings are
    # ignored — covers Claude's TUI startup and any one-time workspace-trust
    # dialog. With the default 10s poll interval this is ~20s of grace.
    _STARTUP_GRACE_POLLS = 2
    # Consecutive negative readings required (after grace) to conclude the
    # session ended — debounces transient tmux query failures / foreground
    # flips so a single blip can't tear down a healthy session.
    _DEAD_CONFIRM_POLLS = 2
    # Shorter sleep used while confirming a suspected exit, so a genuine exit
    # is still detected promptly instead of after a full poll interval.
    _DEAD_RECHECK_INTERVAL = 2.0

    def __init__(
        self,
        comms: CommsLogger,
        *,
        claude_bin: str = "claude",
        log_dir: Path | None = None,
        max_retries: int = 3,
        base_backoff: float = 30.0,
        clock: Callable[[], datetime] | None = None,
        tz: tzinfo | None = None,
    ) -> None:
        self._comms = comms
        self._claude_bin = claude_bin
        self._log_dir = Path(log_dir) if log_dir else Path("logs/wrapper")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._tz: tzinfo = tz or local_tz()
        # Restore callable for the settings.local.json overlay (set in _launch_tmux).
        self._bypass_restore_fn: object | None = None
        # Headless subprocess handle + log handles (set in _launch_headless).
        self._proc: subprocess.Popen | None = None
        self._stdout_fh: Any | None = None
        self._stderr_fh: Any | None = None
        # WS-C watchdog runner (built in wait_for_completion when configured).
        self._wd: WatchdogRunner | None = None
        self._wd_text_window: str = ""
        self._wd_last_skip: tuple[str, datetime | None] | None = None
        self._out_cursors: dict[str, int] = {}

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
        bypass_permissions: bool = False,
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
            bypass_permissions: When True, Claude Code's tool-call
                permission prompts are suppressed.  In headless mode
                this is achieved via ``--dangerously-skip-permissions``;
                in tmux mode (where that flag exits Claude Code
                immediately) it's achieved by overlaying
                ``permissions.defaultMode: "bypassPermissions"`` onto
                the project's ``.claude/settings.local.json`` for the
                duration of the run.  See :mod:`zo.permissions_overlay`
                for the safe-overlay mechanism.  Default False.
        """
        extra = add_dirs or []
        env = extra_env or {}
        if use_tmux and self._is_in_tmux():
            return self._launch_tmux(prompt, cwd=cwd, team_name=team_name,
                                     model=model, max_turns=max_turns,
                                     add_dirs=extra, extra_env=env,
                                     bypass_permissions=bypass_permissions)
        return self._launch_headless(prompt, cwd=cwd, team_name=team_name,
                                     model=model, max_turns=max_turns,
                                     add_dirs=extra, extra_env=env,
                                     bypass_permissions=bypass_permissions)

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
        bypass_permissions: bool = False,
    ) -> LeadProcess:
        """Launch Claude Code interactively in a visible tmux window.

        ``claude -p "..." --dangerously-skip-permissions`` runs
        non-interactively (no TUI).  To get the full interactive
        experience the user wants, we:

        1. Open a tmux window and start ``claude`` without ``-p``
        2. Wait for the TUI to render
        3. Paste the prompt into the TUI via tmux's paste buffer
        4. Send Enter — Claude processes it with the TUI visible

        If ``bypass_permissions`` is True, a settings-file overlay is
        applied to ``<cwd>/.claude/settings.local.json`` before launch
        and restored via an atexit handler.  This is the only way to
        suppress permission prompts in interactive mode (the CLI flag
        is rejected by Claude Code in TUI mode).
        """
        # Apply bypass overlay (if requested) BEFORE Claude reads settings.
        if bypass_permissions:
            from zo.permissions_overlay import (
                apply_bypass_overlay,
                ensure_bypass_disclaimer_accepted,
            )
            # Persist the user's --bypass-permissions consent so Claude's
            # startup consent dialog never appears. Without this, the dialog
            # renders, _wait_for_tui_ready mistakes it for the ready TUI, and
            # the pasted lead prompt + Enter selects its default ("No, exit")
            # — Claude quits on startup and the session dies before any work.
            if ensure_bypass_disclaimer_accepted():
                self._comms.log_checkpoint(
                    agent="wrapper", phase="launch",
                    subtask="bypass-disclaimer",
                    progress="Recorded bypass-permissions consent in "
                             "~/.claude.json (suppresses startup dialog)",
                )
            restore_fn = apply_bypass_overlay(Path(cwd) / ".claude")
            atexit.register(restore_fn)
            self._bypass_restore_fn = restore_fn

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
        # Best-effort: the pane's shell pid, so the claude child can be
        # resolved after startup (WS-C process identity; unknown ≠ dead).
        shell_pid = self._tmux_pane_pid(pane_id)

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
        lead_pid, lead_identity = self._resolve_tmux_lead_identity(shell_pid)

        # 4./5. Paste the prompt into the Claude TUI input field via a
        #    named tmux buffer and submit it with Enter.
        self._paste_and_submit(pane_id, prompt)

        # 6. Verify the prompt was submitted by checking that pane
        #    content changed after the paste (not still showing the
        #    empty input field).
        self._verify_prompt_submitted(pane_id, prompt_file)

        lead = LeadProcess(
            pid=lead_pid, pid_start_identity=lead_identity,
            status=AgentStatus.SPAWNING,
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

    @staticmethod
    def _paste_and_submit(pane_id: str, text: str) -> None:
        """Paste ``text`` into a tmux pane via a NAMED buffer, then press Enter.

        Uses ``load-buffer -b zo-nudge -`` (stdin) + ``paste-buffer -b
        zo-nudge -d`` so the operator's default paste buffer is never
        clobbered and no temp file is needed. Shared by the launch path
        (lead prompt) and the watchdog nudge path.
        """
        subprocess.run(
            ["tmux", "load-buffer", "-b", _TMUX_BUFFER_NAME, "-"],
            input=text, capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["tmux", "paste-buffer", "-b", _TMUX_BUFFER_NAME, "-d", "-t", pane_id],
            capture_output=True, text=True, timeout=10,
        )
        # Wait briefly for the paste to be ingested by the TUI before Enter.
        time.sleep(1)
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "Enter"],
            capture_output=True, text=True, timeout=10,
        )

    @staticmethod
    def _tmux_pane_pid(pane_id: str) -> int | None:
        """``#{pane_pid}`` (the pane's shell pid) or ``None`` (best-effort)."""
        if not pane_id:
            return None
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-t", pane_id, "-p", "#{pane_pid}"],
                capture_output=True, text=True, timeout=5,
            )
            return int(result.stdout.strip())
        except Exception:  # noqa: BLE001 — identity is advisory
            return None

    @staticmethod
    def _resolve_tmux_lead_identity(shell_pid: int | None) -> tuple[int | None, str | None]:
        """Resolve the claude child of the pane shell (``pgrep``) + its start identity.

        Only children whose command line mentions ``claude`` qualify (an
        interactive shell also has prompt helpers, gitstatusd, …), newest
        first (``-n``). Returns ``(None, None)`` when unresolvable — unknown
        is never dead, and a wrong pid would be worse than none.
        """
        if shell_pid is None:
            return None, None
        try:
            result = subprocess.run(
                ["pgrep", "-n", "-P", str(shell_pid), "-f", "claude"],
                capture_output=True, text=True, timeout=5,
            )
            first = result.stdout.strip().splitlines()[0].strip()
            pid = int(first)
        except Exception:  # noqa: BLE001 — identity is advisory
            return None, None
        return pid, process_start_identity(pid)

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
            try:
                retry_text = prompt_file.read_text(encoding="utf-8")
            except OSError:
                retry_text = ""
            self._paste_and_submit(pane_id, retry_text)

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
        bypass_permissions: bool = False,
    ) -> LeadProcess:
        """Launch Claude Code as a headless subprocess (--print mode).

        When ``bypass_permissions`` is True, ``--dangerously-skip-permissions``
        is appended to the Claude CLI invocation so tool-call prompts
        are auto-approved.  When False (default), prompts fire as
        normal — useful for ``--gate-mode supervised`` runs where the
        user wants to review each tool call.
        """
        cmd: list[str] = [
            self._claude_bin, "--print",
            "--output-format", "json",
            "--model", model,
            "--max-turns", str(max_turns),
            "--add-dir", cwd,
        ]
        if bypass_permissions:
            from zo.permissions_overlay import ensure_bypass_disclaimer_accepted
            # --dangerously-skip-permissions / bypass mode refuses to start
            # until the disclaimer is accepted; persist the user's consent.
            ensure_bypass_disclaimer_accepted()
            cmd.append("--dangerously-skip-permissions")
        for d in (add_dirs or []):
            cmd.extend(["--add-dir", d])
        cmd.extend(["-p", prompt])

        stdout_log = self._log_dir / f"{team_name}-stdout.log"
        stderr_log = self._log_dir / f"{team_name}-stderr.log"
        stdout_fh = open(stdout_log, "w", encoding="utf-8")  # noqa: SIM115
        stderr_fh = open(stderr_log, "w", encoding="utf-8")  # noqa: SIM115

        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)

        proc = subprocess.Popen(
            cmd, stdout=stdout_fh, stderr=stderr_fh, text=True, env=env,
        )
        lead = LeadProcess(
            pid=proc.pid, status=AgentStatus.SPAWNING,
            pid_start_identity=self._safe_start_identity(proc.pid),
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
        watchdog: WatchdogConfig | None = None,
        memory_root: Path | None = None,
        zo_session_id: str = "",
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
            watchdog: WS-C watchdog policy. The external checker runs
                once per poll when this is enabled AND *memory_root* is
                given; otherwise the loops behave exactly as before.
            memory_root: Per-project memory root holding
                ``heartbeats/`` (heartbeat files, watchdog state, tick trace).
            zo_session_id: Comms session id for heartbeat/state correlation.
        """
        self._gate_mode_file = gate_mode_file
        self._last_gate_mode: str | None = None
        self._training_pane_id: str | None = None
        self._project_name = project_name
        self._delivery_repo = delivery_repo
        self._start_watchdog(watchdog, memory_root=memory_root,
                             zo_session_id=zo_session_id, delivery_repo=delivery_repo)
        try:
            if process.tmux_pane_id:
                return self._wait_tmux(process, poll_interval=poll_interval,
                                       timeout=timeout, on_status=on_status)
            return self._wait_headless(process, poll_interval=poll_interval,
                                       timeout=timeout, on_status=on_status)
        finally:
            self._close_training_pane()
            if self._wd is not None:
                self._wd.stop()

    # --- Watchdog (WS-C, oracle checks 11-12) ---

    def _start_watchdog(
        self, watchdog: WatchdogConfig | None, *, memory_root: Path | None,
        zo_session_id: str, delivery_repo: Path | None,
    ) -> None:
        """Build the runner when configured; fail-open (no runner) on any error."""
        self._wd = None
        if watchdog is None or not watchdog.enabled or memory_root is None:
            return
        root = Path(memory_root)
        paths: list[Path] = [root / "plan-ledger.json"]
        comms_dir = getattr(self._comms, "_log_dir", None)
        if comms_dir:
            paths.append(Path(comms_dir))
        if delivery_repo is not None:
            experiments = Path(delivery_repo) / ".zo" / "experiments"
            if experiments.exists():
                paths.append(experiments)
        paths.extend(Path(p) for p in watchdog.progress_paths)
        try:
            runner = WatchdogRunner(
                config=watchdog, memory_root=root, zo_session_id=zo_session_id,
                clock=self._clock, tz=self._tz, progress_paths=paths,
            )
            runner.start(runner.clock())
        except Exception as exc:  # noqa: BLE001 — advisory: never break the session
            self._wd_log_error("watchdog_init", "warning",
                               f"Watchdog disabled for this run: {exc!r}")
            return
        self._wd = runner
        with contextlib.suppress(Exception):  # advisory: never break the session
            _ensure_heartbeats_gitignored(root)

    def _wd_checkpoint(self, subtask: str, progress: str, *,
                       blockers: list[str] | None = None) -> None:
        """Advisory comms checkpoint from the watchdog (never raises)."""
        with contextlib.suppress(Exception):
            self._comms.log_checkpoint(agent="watchdog", phase="lifecycle",
                                       subtask=subtask, progress=progress,
                                       blockers=blockers)

    def _wd_log_error(self, error_type: str, severity: str, description: str, *,
                      escalated_to: str = "") -> None:
        """Advisory comms error from the watchdog (never raises)."""
        with contextlib.suppress(Exception):
            self._comms.log_error(agent="watchdog", error_type=error_type,
                                  severity=severity, description=description,
                                  escalated_to=escalated_to)

    def _watchdog_tick(
        self, process: LeadProcess, *, text: str, can_nudge: bool,
        process_dead: bool | None = None,
    ) -> StallVerdict | None:
        """One external-checker tick; applies side effects to ``process`` in place.

        Returns the verdict, or ``None`` when no runner is configured or the
        tick itself failed (fail-open: no decision fires on unknown evidence).
        """
        wd = self._wd
        if wd is None:
            return None
        try:
            verdict = wd.tick(process=process, text=text, can_nudge=can_nudge,
                              now=wd.clock(), process_dead=process_dead)
        except Exception as exc:  # noqa: BLE001 — evidence gathering is advisory
            self._wd_log_error("watchdog_tick", "warning", f"Watchdog tick failed: {exc!r}")
            return None
        if wd.last_new_stall:
            self._wd_log_error("stall", "warning", f"Stall detected: {verdict.reason}")
        if verdict.action in (StallAction.NUDGE, StallAction.RESUME_NUDGE):
            self._wd_nudge(process, verdict, text=text)
        elif verdict.action == StallAction.PAUSE:
            self._wd_pause(process, verdict)
        elif verdict.action == StallAction.RESUME:
            self._wd_resume(process, verdict)
        elif verdict.action == StallAction.ESCALATE:
            self._wd_escalate(process, verdict)
        wd.settle()
        return verdict

    def _wd_nudge(self, process: LeadProcess, verdict: StallVerdict, *, text: str) -> None:
        """Deliver a nudge into the tmux pane, guarded by ``pane_ready_for_nudge``."""
        wd = self._wd
        if wd is None:
            return
        resume = verdict.action == StallAction.RESUME_NUDGE
        budget = wd.config.resume_nudge_budget if resume else wd.config.nudge_budget
        used = wd.state.resume_nudges_used if resume else wd.state.nudges_used
        label = "resume nudge" if resume else "nudge"
        if not process.tmux_pane_id or not pane_ready_for_nudge(text):
            # Log once per stall/pause episode, not every poll.
            episode = (label, wd.state.stall_since or wd.state.paused_at)
            if episode != self._wd_last_skip:
                self._wd_last_skip = episode
                self._wd_checkpoint(
                    "nudge-skipped",
                    f"{label} {used + 1}/{budget} skipped: pane busy or awaiting input",
                    blockers=[verdict.reason])
            return
        try:
            self._paste_and_submit(process.tmux_pane_id, wd.config.nudge_message)
        except Exception as exc:  # noqa: BLE001 — tmux hiccup; do not consume budget
            self._wd_log_error("nudge_failed", "warning", f"Nudge paste failed: {exc!r}")
            return
        wd.record_nudge(wd.clock(), resume=resume)
        process.nudges_used = wd.state.nudges_used
        self._wd_checkpoint("nudge", f"{label} {used + 1}/{budget}: {verdict.reason}")

    def _wd_pause(self, process: LeadProcess, verdict: StallVerdict) -> None:
        """Enter the paused state on FIRST detection only (extensions are silent)."""
        wd = self._wd
        if wd is None:
            return
        state = wd.state
        process.paused_until = state.paused_until
        if state.paused_at != verdict.evaluated_at:
            return
        process.status = AgentStatus.PAUSED_RATE_LIMIT
        self._wd_checkpoint(
            "rate-limit-pause",
            f"Rate limit detected; paused until {state.paused_until}: {verdict.reason}",
            blockers=["rate_limit"])

    def _wd_resume(self, process: LeadProcess, verdict: StallVerdict) -> None:
        """Verified resume: progress observed after a rate-limit pause."""
        wd = self._wd
        if wd is None:
            return
        process.status = AgentStatus.RUNNING
        process.paused_until = None
        process.pause_total_sec = wd.state.total_paused_sec
        self._wd_checkpoint(
            "rate-limit-resume",
            f"Resumed after rate-limit pause (verified={verdict.progress}; "
            f"paused {process.pause_total_sec:.0f}s total): {verdict.reason}")

    def _wd_escalate(self, process: LeadProcess, verdict: StallVerdict) -> None:
        """Escalate to the human; headless additionally kills the session."""
        wd = self._wd
        if wd is None:
            return
        self._wd_log_error("stall", "blocking", verdict.reason, escalated_to="human")
        process.stalled = True
        if process.tmux_pane_id or not wd.config.kill_headless_on_escalate:
            return  # tmux: human-facing pane is never killed; keep waiting
        killed = self.kill_session(process)
        process.exit_code = killed.exit_code
        process.completed_at = killed.completed_at
        process.status = AgentStatus.STALLED

    def _read_new_output(self, process: LeadProcess) -> str:
        """Byte-cursor read of NEW stdout/stderr bytes; maintains the rolling window."""
        new_chunks: list[str] = []
        for path in (process.stdout_log, process.stderr_log):
            if path is None:
                continue
            key = str(path)
            try:
                with open(path, "rb") as fh:
                    fh.seek(self._out_cursors.get(key, 0))
                    data = fh.read()
                    self._out_cursors[key] = fh.tell()
            except OSError:
                continue
            if data:
                new_chunks.append(data.decode("utf-8", errors="replace"))
        new_text = "".join(new_chunks)
        if new_text:
            window = self._wd_text_window + new_text
            self._wd_text_window = window[-_HEADLESS_TEXT_WINDOW_CHARS:]
        return new_text

    def _elapsed(self, start_time: float) -> float:
        """Wall-clock seconds since ``start_time`` minus any rate-limit pause."""
        elapsed = time.monotonic() - start_time
        if self._wd is not None:
            elapsed -= self._wd.paused_seconds()
        return elapsed

    def _timed_out(self, process: LeadProcess, timeout: float | None,
                   start_time: float) -> LeadProcess | None:
        """Return the TIMED_OUT process if the (pause-adjusted) budget is spent."""
        if not timeout or self._elapsed(start_time) <= timeout:
            return None
        process = process.model_copy(update={"status": AgentStatus.TIMED_OUT})
        self._comms.log_error(
            agent="wrapper", error_type="timeout", severity="blocking",
            description=f"Lead session timed out after {timeout}s",
        )
        return process

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

        Two guards prevent a transient reading from tearing down a
        healthy session (see ``_STARTUP_GRACE_POLLS`` /
        ``_DEAD_CONFIRM_POLLS``):

        * **Startup grace** — the first poll fires within milliseconds
          of launch, before Claude's TUI has fully claimed the pane and
          while a one-time workspace-trust dialog may still be up.  We
          ignore negative readings for the first few polls so startup
          races never look like an immediate exit.
        * **Confirmation debounce** — a single negative reading (a
          momentary tmux query hiccup, or a brief foreground flip) is
          not enough.  We require several *consecutive* negatives before
          concluding the session ended.

        Without these, an instantaneous first poll could log
        "Session completed" ~15ms after launch and kill a session that
        was in fact starting normally.
        """
        start_time = time.monotonic()
        process = process.model_copy(update={"status": AgentStatus.RUNNING})
        pane_id = process.tmux_pane_id or ""

        poll_count = 0
        consecutive_dead = 0

        while True:
            self._check_gate_mode_change()
            self._maybe_open_training_pane()
            # ONE pane capture per poll, shared by the watchdog and on_status.
            pane_text = self._capture_tmux_pane(pane_id, lines=_PANE_CAPTURE_LINES)
            # Watchdog tick BEFORE the liveness reads so it also runs on the
            # suspected-dead ``continue`` path below. A busy pane (spinner,
            # "esc to interrupt", dialog) cannot be nudged, so the policy
            # escalates a persistent stall there instead of nudging forever.
            self._watchdog_tick(process, text=pane_text,
                                can_nudge=pane_ready_for_nudge(pane_text))

            pane_exists = self._tmux_pane_alive(pane_id)
            claude_running = pane_exists and self._tmux_claude_running(pane_id)
            in_startup_grace = poll_count < self._STARTUP_GRACE_POLLS
            poll_count += 1

            if not pane_exists or not claude_running:
                # During startup grace, ignore negatives entirely — Claude
                # may still be claiming the pane or showing a trust dialog.
                if in_startup_grace:
                    consecutive_dead = 0
                else:
                    consecutive_dead += 1
                    if consecutive_dead >= self._DEAD_CONFIRM_POLLS:
                        # Confirmed: Claude exited — clean up the shell window.
                        if pane_exists:
                            self._kill_tmux_window(pane_id)
                        return self._tmux_final_status(process)
                    # Suspected exit but not yet confirmed — re-check soon
                    # rather than waiting a full poll interval.
                    if on_status:
                        team_status = self.monitor_team(process.team_name)
                        on_status(team_status, "")
                    time.sleep(min(poll_interval, self._DEAD_RECHECK_INTERVAL))
                    continue
            else:
                consecutive_dead = 0

            if on_status:
                team_status = self.monitor_team(process.team_name)
                pane_snapshot = "\n".join(pane_text.splitlines()[-5:])
                on_status(team_status, pane_snapshot)

            timed_out = self._timed_out(process, timeout, start_time)
            if timed_out is not None:
                return timed_out
            time.sleep(poll_interval)

    def _tmux_final_status(self, process: LeadProcess) -> LeadProcess:
        """Terminal status once the tmux pane/claude is confirmed gone.

        ``STALLED`` if the watchdog escalated and nothing progressed since;
        ``RATE_LIMITED`` (with ``resume_at``) if the session died while a
        *corroborated* rate-limit pause was in effect (parsed reset time or
        an unambiguous banner — prose in a final summary does not count);
        else the normal ``COMPLETED``.
        """
        wd = self._wd
        status = AgentStatus.COMPLETED
        update: dict[str, Any] = {"exit_code": 0, "completed_at": datetime.now(UTC)}
        if process.stalled and (wd is None or not wd.progress_since_escalation()):
            status = AgentStatus.STALLED
        elif wd is not None and wd.rate_limit_exit_evidence():
            status = AgentStatus.RATE_LIMITED
            update["resume_at"] = wd.parsed_resume_at()
        update["status"] = status
        process = process.model_copy(update=update)
        self._comms.log_checkpoint(
            agent="wrapper", phase="lifecycle", subtask="completion",
            progress=f"Lead session completed, agent window closed (status={status.value})",
        )
        return process

    def _wait_headless(
        self,
        process: LeadProcess,
        *,
        poll_interval: float,
        timeout: float | None,
        on_status: Any | None,
    ) -> LeadProcess:
        """Wait for the headless subprocess to exit.

        Rate limits are handled by the watchdog pause/resume state (evaluated
        every poll — never a blocking backoff sleep). When the process exits
        while rate-limited the status is ``RATE_LIMITED`` with a parsed
        ``resume_at``; the driver above the wrapper relaunches.
        """
        start_time = time.monotonic()
        process = process.model_copy(update={"status": AgentStatus.RUNNING})
        self._wd_text_window = ""
        self._out_cursors = {}

        while True:
            self._check_gate_mode_change()
            self._read_new_output(process)

            rc = self._proc.poll() if self._proc else -1
            if rc is None:
                # Alive: process_dead=False is authoritative here (Popen.poll).
                verdict = self._watchdog_tick(process, text=self._wd_text_window,
                                              can_nudge=False, process_dead=False)
                if process.status == AgentStatus.STALLED:
                    return process
                if verdict is not None and verdict.action == StallAction.PAUSE:
                    # The banner is consumed: unlike a live pane it never
                    # disappears from a log window, so only NEW output is
                    # classified from here on (new-lines-only cursor).
                    self._wd_text_window = ""
            if rc is not None:
                self._close_log_handles()
                return self._headless_exit_status(process, rc)

            if on_status:
                team_status = self.monitor_team(process.team_name)
                on_status(team_status, "")

            timed_out = self._timed_out(process, timeout, start_time)
            if timed_out is not None:
                return timed_out
            time.sleep(poll_interval)

    def _headless_exit_status(self, process: LeadProcess, rc: int) -> LeadProcess:
        """Classify a headless exit: RATE_LIMITED (+resume_at) / COMPLETED / ERRORED.

        RATE_LIMITED needs corroboration: the watchdog's pause was backed by a
        parsed reset time or an unambiguous banner, or the process exited
        non-zero with rate-limit text in its final output. A successful run
        whose JSON result merely *mentions* rate limits stays COMPLETED.
        """
        window = self._wd_text_window
        wd = self._wd
        rate_limited = (
            (wd is not None and wd.rate_limit_exit_evidence(rc=rc))
            or (rc != 0 and self._detect_rate_limit(window))
        )
        update: dict[str, Any] = {"exit_code": rc, "completed_at": datetime.now(UTC)}
        if process.stalled and (wd is None or not wd.progress_since_escalation()):
            update["status"] = AgentStatus.STALLED  # escalated, kill disabled, died stalled
        elif rate_limited:
            resume_at = wd.parsed_resume_at() if wd is not None else None
            if resume_at is None:
                resume_at = parse_rate_limit_reset(window, now=self._clock(), tz=self._tz)
            update.update({"status": AgentStatus.RATE_LIMITED, "resume_at": resume_at})
            self._comms.log_error(
                agent="wrapper", error_type="rate_limit", severity="blocking",
                description=(f"Lead session exited code={rc} while rate limited; "
                             f"resume_at={resume_at}"),
            )
        else:
            update["status"] = AgentStatus.COMPLETED if rc == 0 else AgentStatus.ERRORED
        process = process.model_copy(update=update)
        self._comms.log_checkpoint(
            agent="wrapper", phase="lifecycle", subtask="completion",
            progress=f"Lead session exited code={rc}",
        )
        return process

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
        """Exit-classification only: does the final output carry a rate-limit banner?

        Uses the watchdog's tiered table (no bare ``429`` / ``overloaded``;
        loose phrases need same-line rate/usage/quota vocabulary — ``val_loss
        0.4291``, ``GPU overloaded`` and ``patience limit reached`` are not
        rate limits).
        """
        return rate_limit_match(output) is not None

    @staticmethod
    def _safe_start_identity(pid: object) -> str | None:
        """Best-effort process start identity for a freshly spawned pid."""
        if not isinstance(pid, int) or isinstance(pid, bool):
            return None
        try:
            return process_start_identity(pid)
        except Exception:  # noqa: BLE001 — identity is advisory
            return None

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
