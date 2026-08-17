"""Watchdog runner for the lifecycle wrapper (WS-C, oracle checks 11-12).

``WatchdogRunner`` is the *external checker* that ``LifecycleWrapper`` ticks
once per poll iteration from both ``_wait_tmux`` and ``_wait_headless``. It
owns the persisted ``WatchdogState``, gathers evidence (heartbeat files, the
captured pane / stdout text, progress-path mtimes, process-tree CPU time,
positive-proof process death), calls the pure ``zo.watchdog.evaluate`` policy
and persists the state plus a one-line JSONL trace per tick. It performs NO
side effects on the session — nudging, pausing, escalating and killing are
the wrapper's job, so that comms, tmux and ``LeadProcess`` stay in one place.

Fail-open discipline: every advisory path (state persistence, trace writes,
file observation, CPU sampling) swallows errors; the decision path is pure
and never fires on unknown evidence (``process_dead=None`` is "unknown", not
"dead").
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from zo.watchdog import (
    HEARTBEATS_DIRNAME,
    NeverBlockReason,
    StallVerdict,
    WatchdogConfig,
    WatchdogState,
    evaluate,
    is_process_dead,
    load_all_heartbeats,
    load_state,
    new_state,
    observe_files,
    observe_heartbeats,
    observe_text,
    process_tree_cpu_seconds,
    save_state,
    sweep_stale_heartbeats,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import tzinfo
    from pathlib import Path

    from zo._wrapper_models import LeadProcess
    from zo.watchdog import HeartbeatRecord

__all__ = ["CPU_BUSY_FRACTION", "TICK_TRACE_FILENAME", "WatchdogRunner", "local_tz"]

TICK_TRACE_FILENAME = "_watchdog-ticks.jsonl"
# The lead's process tree must burn at least this fraction of the wall time
# between two samples for CPU time to count as progress: an idle TUI redraws
# at ~1 %, a training run inside a silent tool call sits at ≥ 100 %.
CPU_BUSY_FRACTION = 0.25
_CPU_MIN_INTERVAL_SEC = 1.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def local_tz() -> tzinfo:
    """The operator's local zone (Claude Code prints reset times in local time)."""
    return datetime.now().astimezone().tzinfo or UTC


class WatchdogRunner:
    """Per-run watchdog: evidence gathering + policy call + persistence.

    Args:
        config: Resolved ``WatchdogConfig`` for this run.
        memory_root: Per-project memory root; heartbeats and the state file
            live under ``<memory_root>/heartbeats/``.
        zo_session_id: Comms session id (correlation only).
        clock: Injectable wall clock returning a tz-aware ``datetime``.
        tz: Zone used to interpret banner clock times ("resets at 3pm");
            defaults to the operator's local zone.
        progress_paths: Extra files/dirs whose mtime advance counts as
            progress (ledger, comms dir, experiments dir, config extras).
        dead_probe: Injectable positive-proof death check
            ``(pid, recorded_identity) -> bool``; defaults to
            :func:`zo.watchdog.is_process_dead`.
        cpu_probe: Injectable ``pid -> cumulative CPU seconds of the process
            tree`` (``None`` = unknown); defaults to
            :func:`zo.watchdog.process_tree_cpu_seconds`.
    """

    def __init__(
        self,
        *,
        config: WatchdogConfig,
        memory_root: Path,
        zo_session_id: str = "",
        clock: Callable[[], datetime] | None = None,
        tz: tzinfo | None = None,
        progress_paths: Sequence[Path] = (),
        dead_probe: Callable[[int | None, str | None], bool] | None = None,
        cpu_probe: Callable[[int], float | None] | None = None,
    ) -> None:
        self.config = config
        self.memory_root = memory_root
        self.zo_session_id = zo_session_id
        self._clock = clock or _utc_now
        self.tz: tzinfo = tz or local_tz()
        self.progress_paths: list[Path] = list(progress_paths)
        self._dead_probe = dead_probe or is_process_dead
        self._cpu_probe = cpu_probe or process_tree_cpu_seconds
        self._cpu_sample: tuple[float, datetime] | None = None
        self.state: WatchdogState = new_state(now=self._clock(), zo_session_id=zo_session_id)
        self.last_verdict: StallVerdict | None = None
        self.last_new_stall: bool = False

    # ------------------------------------------------------------ lifecycle

    def clock(self) -> datetime:
        """Current time from the injected clock (tz-aware)."""
        now = self._clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=UTC)

    def start(self, now: datetime | None = None) -> None:
        """Baseline pre-existing heartbeats, sweep stale files, carry a prior nudge budget.

        Pre-existing heartbeat files are baselined so they never count as
        progress; a persisted state for the SAME ``zo_session_id`` carries its
        ``nudges_used`` forward so a wrapper restart cannot refill the budget.
        """
        now = now or self.clock()
        with contextlib.suppress(Exception):
            sweep_stale_heartbeats(self.memory_root, now=now)
        heartbeats = self._load_heartbeats()
        self.state = new_state(now=now, zo_session_id=self.zo_session_id, heartbeats=heartbeats)
        prior = load_state(self.memory_root)
        if prior is not None and self.zo_session_id and prior.zo_session_id == self.zo_session_id:
            self.state.nudges_used = prior.nudges_used
            self.state.stall_events = prior.stall_events
        with contextlib.suppress(Exception):
            observe_files(self.state, self.progress_paths)  # baseline mtimes
        self.persist()

    def stop(self) -> None:
        """Persist final state (fail-open)."""
        self.persist()

    def persist(self) -> None:
        """Atomically save state; never raises."""
        with contextlib.suppress(Exception):
            save_state(self.memory_root, self.state)

    # ------------------------------------------------------------- evidence

    def _load_heartbeats(self) -> list[HeartbeatRecord]:
        try:
            return load_all_heartbeats(self.memory_root)
        except Exception:  # unreadable heartbeats are unknown, not stale
            return []

    def _observe_cpu(self, pid: int | None, now: datetime) -> bool:
        """True iff the lead's process tree burned ≥ ``CPU_BUSY_FRACTION`` of the
        wall time since the previous sample (a busy tree is not stalled)."""
        if pid is None:
            return False
        try:
            cpu = self._cpu_probe(pid)
        except Exception:
            cpu = None
        if cpu is None:
            self._cpu_sample = None
            return False
        prev, self._cpu_sample = self._cpu_sample, (cpu, now)
        if prev is None:
            return False
        wall = (now - prev[1]).total_seconds()
        return wall >= _CPU_MIN_INTERVAL_SEC and (cpu - prev[0]) >= CPU_BUSY_FRACTION * wall

    def _observe(self, text: str, heartbeats: Sequence[HeartbeatRecord], *,
                 pid: int | None, now: datetime) -> bool:
        """Run every observer (each updates state) and OR their verdicts."""
        progressed = False
        with contextlib.suppress(Exception):
            progressed = observe_heartbeats(self.state, heartbeats) or progressed
        if text.strip():  # an empty capture is unknown, not evidence
            with contextlib.suppress(Exception):
                progressed = observe_text(self.state, text) or progressed
        with contextlib.suppress(Exception):
            progressed = observe_files(self.state, self.progress_paths) or progressed
        cpu_busy = self._observe_cpu(pid, now)  # always sampled, even when already progressed
        return progressed or cpu_busy

    def _process_dead(self, process: LeadProcess, override: bool | None) -> bool | None:
        if override is not None:
            return override
        if process.pid is None:
            return None  # unknown identity is never proof of death
        try:
            return bool(self._dead_probe(process.pid, process.pid_start_identity))
        except Exception:
            return None

    # ----------------------------------------------------------------- tick

    def tick(
        self, *, process: LeadProcess, text: str, can_nudge: bool,
        now: datetime | None = None, process_dead: bool | None = None,
    ) -> StallVerdict:
        """Gather evidence, evaluate the policy, persist state + trace, return the verdict.

        Args:
            process: The lead process (pid/identity are read, never mutated).
            text: Captured pane text (tmux) or the rolling stdout/stderr window.
            can_nudge: True only for a tmux pane that is ready for input
                (headless and busy/dialog panes pass False).
            now: Injected clock value; defaults to ``self.clock()``.
            process_dead: Explicit liveness override (headless passes False
                while ``Popen.poll()`` is None); ``None`` → probe by pid.
        """
        now = now or self.clock()
        heartbeats = self._load_heartbeats()
        progress = self._observe(text, heartbeats, pid=process.pid, now=now)
        stall_events_before = self.state.stall_events
        verdict = evaluate(
            self.state, self.config, now=now, text=text, heartbeats=heartbeats,
            progress=progress, process_dead=self._process_dead(process, process_dead),
            can_nudge=can_nudge, tz=self.tz,
        )
        self.last_verdict = verdict
        self.last_new_stall = self.state.stall_events > stall_events_before
        self.persist()
        self._trace(verdict)
        return verdict

    def settle(self) -> None:
        """Re-baseline progress-path mtimes after the wrapper's own writes.

        The comms log dir is a progress path; the wrapper's nudge/escalate
        checkpoints land there and must not read back as agent progress on
        the next tick.
        """
        with contextlib.suppress(Exception):
            observe_files(self.state, self.progress_paths)

    def record_nudge(self, now: datetime | None = None, *, resume: bool = False) -> None:
        """Account for a nudge that was actually delivered (caller-side counters)."""
        now = now or self.clock()
        if resume:
            self.state.resume_nudges_used += 1
        else:
            self.state.nudges_used += 1
        self.state.last_nudge_at = now
        self.persist()

    # -------------------------------------------------------------- queries

    def paused_seconds(self, now: datetime | None = None) -> float:
        """Total paused seconds so far, including a pause still in effect.

        An open pause stops accruing at an escalation raised during it (resume
        unverified / max pause exceeded): the wall-clock timeout must not stay
        suspended forever once the watchdog has already handed off to a human.
        """
        total = self.state.total_paused_sec
        paused_at, esc = self.state.paused_at, self.state.escalated_at
        if paused_at is not None:
            end = now or self.clock()
            if esc is not None and esc >= paused_at:
                end = min(end, esc)
            total += max(0.0, (end - paused_at).total_seconds())
        return total

    @property
    def last_never_block(self) -> str | None:
        """Never-block reason recorded by the most recent tick (or ``None``)."""
        return self.state.last_never_block

    @property
    def is_rate_limited(self) -> bool:
        """True iff the most recent tick classified the text as a rate limit."""
        return self.state.last_never_block == NeverBlockReason.RATE_LIMIT.value

    def rate_limit_exit_evidence(self, *, rc: int | None = None) -> bool:
        """Should a session that just ended be classified ``RATE_LIMITED``?

        True iff a rate-limit pause is still open (never resumed) AND it is
        corroborated beyond "some tick matched": a parsed reset time, an
        unambiguous platform banner, or a non-zero exit code. Prose ("the API
        hit a rate limit earlier and retried") in a session that finished
        normally stays ``COMPLETED``.
        """
        if self.state.paused_at is None:
            return False
        if self.state.pause_evidence in ("reset", "banner"):
            return True
        return rc is not None and rc != 0

    def parsed_resume_at(self) -> datetime | None:
        """``paused_until`` when it came from a parsed reset time, else ``None``."""
        if self.state.pause_evidence == "reset":
            return self.state.paused_until
        return None

    def progress_since_escalation(self) -> bool:
        """True iff progress was observed after the last escalation."""
        esc = self.state.escalated_at
        return esc is None or self.state.last_progress_at > esc

    # ---------------------------------------------------------------- trace

    def _trace(self, verdict: StallVerdict) -> None:
        """Append one JSONL line per tick (advisory; never raises)."""
        line = {
            "ts": verdict.evaluated_at.isoformat(),
            "action": verdict.action.value,
            "stalled": verdict.stalled,
            "reason": verdict.reason,
            "never_block": verdict.never_block.value if verdict.never_block else None,
            "progress": verdict.progress,
        }
        path = self.memory_root / HEARTBEATS_DIRNAME / TICK_TRACE_FILENAME
        with contextlib.suppress(Exception):
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
