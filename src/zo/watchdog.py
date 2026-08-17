"""Watchdog — WS-C execution substrate (plan oracle checks 11-12).

Pure logic: no I/O in the classifier and predicate paths; process identity
and file helpers are small, injectable, and fail-open.

Pattern tables live in ``zo._watchdog_text``, models/config in
``zo._watchdog_models`` and process identity in ``zo._proc``; all are
re-exported here. Ported from oh-my-claudecode (MIT License, Copyright (c)
2025 Yeachan Heo): ``todo-continuation/index.ts``,
``rate-limit-wait/tmux-detector.ts``, ``team/idle-nudge.ts`` (nudge defaults),
``team/tmux-session.ts``, ``team/team-owner-epoch.ts``. Contract adjustments:
no bare ``429``/``overloaded``, ``awaiting_input`` added, bare ``interrupt``
excluded (OMC #2478).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from zo._proc import (
    identities_may_match,
    is_process_dead,
    is_valid_process_start_identity,
    pid_alive,
    process_start_identity,
    process_tree_cpu_seconds,
)
from zo._watchdog_models import (
    SCHEMA_VERSION,
    Freshness,
    HeartbeatRecord,
    HeartbeatStatus,
    StallAction,
    StallVerdict,
    WatchdogConfig,
    WatchdogState,
    new_state,
    resolve_watchdog_config,
)
from zo._watchdog_text import (
    AUTH_ERROR_PATTERNS,
    AWAITING_INPUT_PATTERNS,
    CONTEXT_LIMIT_PATTERNS,
    GIT_OUTPUT_LINE_PATTERNS,
    RATE_LIMIT_TEXT_PATTERNS,
    USER_ABORT_PATTERNS,
    NeverBlockReason,
    _aware,
    _secs,
    classify_never_block,
    normalize_terminal_text,
    pane_ready_for_nudge,
    parse_rate_limit_reset,
    progress_digest,
    rate_limit_banner_key,
    rate_limit_match,
)
from zo.ledger import _atomic_write

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import tzinfo
    from pathlib import Path

__all__ = [
    "AUTH_ERROR_PATTERNS", "AWAITING_INPUT_PATTERNS", "CONTEXT_LIMIT_PATTERNS", "Freshness",
    "GIT_OUTPUT_LINE_PATTERNS", "HEARTBEATS_DIRNAME", "HEARTBEAT_STALE_SWEEP_SEC",
    "HeartbeatRecord", "HeartbeatStatus", "NeverBlockReason", "RATE_LIMIT_TEXT_PATTERNS",
    "SCHEMA_VERSION", "StallAction", "StallVerdict", "USER_ABORT_PATTERNS",
    "WATCHDOG_STATE_FILENAME", "WatchdogConfig", "WatchdogState", "classify_freshness",
    "classify_never_block", "compute_pause_until", "evaluate", "heartbeat_path",
    "identities_may_match", "is_process_dead", "is_valid_process_start_identity",
    "load_all_heartbeats", "load_heartbeat", "load_state", "new_state", "normalize_terminal_text",
    "observe_files", "observe_heartbeats", "observe_text", "pane_ready_for_nudge",
    "parse_rate_limit_reset", "pid_alive", "process_start_identity", "process_tree_cpu_seconds",
    "progress_digest", "rate_limit_banner_key", "rate_limit_match", "resolve_watchdog_config",
    "save_state", "sweep_stale_heartbeats", "write_heartbeat",
]

HEARTBEATS_DIRNAME = "heartbeats"
WATCHDOG_STATE_FILENAME = "_watchdog.json"
HEARTBEAT_STALE_SWEEP_SEC = 24 * 3600
_RESET_SLACK_SEC = 15


# ---------------------------------------------------------------- heartbeats

def heartbeat_path(memory_root: Path, agent_key: str) -> Path:
    """``<memory_root>/heartbeats/<agent_key>.json``."""
    return memory_root / HEARTBEATS_DIRNAME / f"{agent_key}.json"


def load_heartbeat(path: Path) -> HeartbeatRecord | None:
    """Parse one heartbeat file; ``None`` on any error (fail-open)."""
    try:
        return HeartbeatRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # unreadable/malformed heartbeats are unknown, not stale
        return None


def _heartbeat_files(memory_root: Path) -> list[Path]:
    hb_dir = memory_root / HEARTBEATS_DIRNAME
    try:
        return sorted(p for p in hb_dir.glob("*.json") if not p.name.startswith("_"))
    except OSError:
        return []


def load_all_heartbeats(memory_root: Path) -> list[HeartbeatRecord]:
    """All parsable heartbeats; ignores ``_watchdog.json`` and unparsable files."""
    records = (load_heartbeat(p) for p in _heartbeat_files(memory_root))
    return [r for r in records if r is not None]


def write_heartbeat(memory_root: Path, record: HeartbeatRecord) -> Path:
    """Atomically write ``record`` (tmp + ``os.replace``; ``mkdir -p``)."""
    path = heartbeat_path(memory_root, record.agent_key)
    _atomic_write(path, record.model_dump_json(indent=2))
    return path


def sweep_stale_heartbeats(
    memory_root: Path, *, now: datetime, older_than_sec: int = HEARTBEAT_STALE_SWEEP_SEC,
) -> int:
    """Delete heartbeat files older than ``older_than_sec``; returns the count removed."""
    removed = 0
    for path in _heartbeat_files(memory_root):
        record = load_heartbeat(path)
        try:
            stamp = record.last_tick_at if record else datetime.fromtimestamp(
                path.stat().st_mtime, tz=UTC)
            if _secs(now, stamp) > older_than_sec:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def classify_freshness(
    record: HeartbeatRecord | None, *, now: datetime, stale_after_sec: float,
) -> Freshness:
    """``None`` → UNKNOWN; naive datetimes are treated as UTC."""
    if record is None:
        return Freshness.UNKNOWN
    return Freshness.FRESH if _secs(now, record.last_tick_at) < stale_after_sec else Freshness.STALE


def compute_pause_until(
    now: datetime, reset_at: datetime | None, *, attempt: int, config: WatchdogConfig,
) -> datetime:
    """``reset_at`` + 15 s slack, else exponential backoff capped by config."""
    if reset_at is not None:
        return _aware(reset_at) + timedelta(seconds=_RESET_SLACK_SEC)
    backoff = config.rate_limit_backoff_base_sec * (2 ** max(0, min(attempt, 30)))
    return _aware(now) + timedelta(seconds=min(backoff, config.rate_limit_backoff_max_sec))


def load_state(memory_root: Path) -> WatchdogState | None:
    """Load persisted state; ``None`` on any error (fail-open)."""
    path = memory_root / HEARTBEATS_DIRNAME / WATCHDOG_STATE_FILENAME
    try:
        return WatchdogState.model_validate_json(path.read_text("utf-8"))
    except Exception:
        return None


def save_state(memory_root: Path, state: WatchdogState) -> Path:
    """Atomically persist ``state``; returns the path written."""
    path = memory_root / HEARTBEATS_DIRNAME / WATCHDOG_STATE_FILENAME
    _atomic_write(path, state.model_dump_json(indent=2))
    return path


# ------------------------------------------------------- evidence observers

def observe_heartbeats(state: WatchdogState, heartbeats: Sequence[HeartbeatRecord]) -> bool:
    """True iff any key's ``tick_count`` advanced past what was seen (and its baseline)."""
    progressed = False
    for hb in heartbeats:
        seen = max(state.seen_ticks.get(hb.agent_key, 0), state.baseline_ticks.get(hb.agent_key, 0))
        if hb.tick_count > seen:
            progressed = True
        state.seen_ticks[hb.agent_key] = max(seen, hb.tick_count)
    return progressed


def observe_text(state: WatchdogState, text: str) -> bool:
    """True iff the progress digest changed (first observation → False).

    While a rate-limit pause is active a digest change is recorded but NOT
    reported as progress: the banner appearing/disappearing churns the text,
    and a resume must be verified by heartbeat or file evidence instead.
    """
    digest = progress_digest(text)
    changed = state.last_digest is not None and digest != state.last_digest
    state.last_digest = digest
    return changed and state.paused_at is None


def _newest_mtime(path: Path) -> float | None:
    try:
        stat = path.stat()
        if not path.is_dir():
            return stat.st_mtime
        return max([stat.st_mtime, *(p.stat().st_mtime for p in path.iterdir())])
    except OSError:
        return None


def observe_files(state: WatchdogState, paths: Sequence[Path]) -> bool:
    """True iff any path's mtime advanced or a previously-missing path appeared.

    Directories use the newest mtime among the dir and its direct entries.
    Missing paths are recorded as ``-1.0`` so their later appearance counts.
    """
    progressed = False
    for path in paths:
        key = str(path)
        mtime = _newest_mtime(path)
        prev = state.last_file_mtimes.get(key)
        current = -1.0 if mtime is None else mtime
        if prev is not None and current > prev:
            progressed = True
        state.last_file_mtimes[key] = max(prev if prev is not None else current, current)
    return progressed


# ------------------------------------------------------------ stall policy

def _freshness(heartbeats: Sequence[HeartbeatRecord], now: datetime, stale: float) -> Freshness:
    verdicts = {classify_freshness(hb, now=now, stale_after_sec=stale) for hb in heartbeats}
    if not verdicts:
        return Freshness.UNKNOWN
    return Freshness.FRESH if Freshness.FRESH in verdicts else Freshness.STALE


def _already_escalated(state: WatchdogState, since: datetime | None) -> bool:
    return (state.escalated_at is not None and since is not None
            and _secs(state.escalated_at, since) >= 0)


def _escalate_once(state: WatchdogState, now: datetime, since: datetime | None,
                   reason: str) -> tuple[StallAction, str]:
    if _already_escalated(state, since):
        return StallAction.NONE, f"already escalated: {reason}"
    state.escalated_at = now
    return StallAction.ESCALATE, reason


def _mark_stall(state: WatchdogState, now: datetime) -> None:
    if state.stall_since is None:
        state.stall_since = now
        state.stall_events += 1


def _pause_end_for_accounting(state: WatchdogState, now: datetime) -> datetime:
    """Paused time stops accruing at an escalation raised during the pause."""
    esc = state.escalated_at
    if state.paused_at is not None and esc is not None and _secs(esc, state.paused_at) >= 0:
        return min(now, esc)
    return now


def _end_pause(state: WatchdogState, now: datetime, *, spent_banner: str | None) -> None:
    if state.paused_at is not None:
        end = _pause_end_for_accounting(state, now)
        state.total_paused_sec += max(0.0, _secs(end, state.paused_at))
    state.paused_at = state.paused_until = None
    state.paused_reason = state.pause_banner_key = state.pause_evidence = None
    state.spent_banner_key = spent_banner
    state.resume_nudges_used = 0


def _pause_target(state: WatchdogState, config: WatchdogConfig, now: datetime, text: str,
                  tz: tzinfo | None, *, attempt: int, previous: datetime | None) -> datetime:
    """``paused_until`` for a (re)entered pause; records the evidence tier.

    A parsed reset is honoured only if it lies in ``(now, now + max_pause]``:
    a stale clock time that rolled over to tomorrow ("resets at 3pm" re-read
    after 3pm) or a reset behind ``previous`` is not fresh information, so the
    exponential backoff applies instead.
    """
    reset = parse_rate_limit_reset(text, now=now, tz=tz)
    usable = (reset is not None and 0 < _secs(reset, now) <= config.rate_limit_max_pause_sec
              and (previous is None or _secs(reset, previous) > 0))
    state.pause_evidence = "reset" if usable else rate_limit_match(text)
    state.pause_banner_key = rate_limit_banner_key(text)
    return compute_pause_until(now, reset if usable else None, attempt=attempt, config=config)


def _rate_limited(state: WatchdogState, config: WatchdogConfig, now: datetime, text: str,
                  tz: tzinfo | None, can_nudge: bool) -> tuple[StallAction, str]:
    """Step 3: enter/extend a pause; escalate once past the max pause.

    A banner that is byte-for-byte the one the pause was entered on is STALE
    once ``paused_until`` has passed (a static transcript never clears the
    line): it is treated as gone → resume nudge / headless wait, never a
    day-rollover extension.
    """
    if state.paused_at is None:
        state.paused_at, state.paused_reason, state.pause_attempts = now, "rate_limit", 1
        state.paused_until = _pause_target(state, config, now, text, tz, attempt=0, previous=None)
        return StallAction.PAUSE, f"rate limit detected; paused until {state.paused_until:%H:%M:%S}"
    if _secs(now, state.paused_at) > config.rate_limit_max_pause_sec:
        return _escalate_once(state, now, state.paused_at, "rate-limit pause exceeded max")
    if state.paused_until is not None and _secs(now, state.paused_until) >= 0:
        if rate_limit_banner_key(text) == state.pause_banner_key:
            return _paused_banner_gone(state, config, now, can_nudge, stale=True)
        state.pause_attempts += 1
        state.paused_until = _pause_target(
            state, config, now, text, tz, attempt=state.pause_attempts - 1,
            previous=state.paused_until)
        return StallAction.PAUSE, f"rate limit persists; pause extended to {state.paused_until}"
    return StallAction.PAUSE, f"rate-limit pause in effect until {state.paused_until}"


def _paused_banner_gone(state: WatchdogState, config: WatchdogConfig, now: datetime,
                        can_nudge: bool, *, stale: bool = False) -> tuple[StallAction, str]:
    """Step 4: banner gone (or stale), no progress yet — resume-nudge (tmux) or
    wait/escalate (headless / pane busy)."""
    what = "banner stale" if stale else "banner gone"
    until = state.paused_until or state.paused_at or now
    if _secs(now, until) < 0:
        return StallAction.NONE, f"paused ({what}) until {until}"
    if can_nudge and state.resume_nudges_used < config.resume_nudge_budget:
        return StallAction.RESUME_NUDGE, f"pause elapsed and {what}; resume nudge"
    dwell_ok = (state.last_nudge_at is None
                or _secs(now, state.last_nudge_at) >= config.nudge_delay_sec)
    if dwell_ok and _secs(now, until) >= config.rate_limit_backoff_base_sec:
        return _escalate_once(state, now, state.paused_at,
                              "no progress after rate-limit pause; resume unverified")
    return StallAction.NONE, "pause elapsed; waiting for verified resume progress"


def _other_never_block(state: WatchdogState, config: WatchdogConfig, now: datetime,
                       reason: NeverBlockReason) -> tuple[StallAction, str]:
    """Step 5: never nudge; compaction is progress; auth/context may escalate after threshold."""
    if reason == NeverBlockReason.COMPACTING:
        state.last_progress_at, state.stall_since = now, None
        return StallAction.NONE, "compacting: stall clock reset"
    stalled = _secs(now, state.last_progress_at) >= config.stall_threshold_sec
    if stalled and reason in (NeverBlockReason.AUTH_ERROR, NeverBlockReason.CONTEXT_LIMIT):
        _mark_stall(state, now)
        return _escalate_once(state, now, state.stall_since,
                              f"stalled under {reason.value}; nudging cannot help")
    return StallAction.NONE, f"never-block ({reason.value}): not nudging"


def _dead_action(state: WatchdogState, now: datetime) -> tuple[StallAction, str]:
    """Positive proof of death escalates ONCE per run (the pid cannot come back)."""
    _mark_stall(state, now)
    if state.dead_escalated_at is not None:
        return StallAction.NONE, "already escalated: lead process is dead"
    state.dead_escalated_at = state.escalated_at = now
    return StallAction.ESCALATE, "lead process is dead (positive proof)"


def _stalled_action(state: WatchdogState, config: WatchdogConfig, now: datetime, *,
                    can_nudge: bool) -> tuple[StallAction, str]:
    """Step 8: nudge with dwell/budget, else escalate once."""
    _mark_stall(state, now)
    since = state.stall_since or now
    dwell_ok = (state.last_nudge_at is None
                or _secs(now, state.last_nudge_at) >= config.nudge_delay_sec)
    first_ok = _secs(now, since) >= config.nudge_delay_sec or state.nudges_used > 0
    if can_nudge and state.nudges_used < config.nudge_budget and dwell_ok and first_ok:
        return StallAction.NUDGE, (
            f"no progress for {int(_secs(now, state.last_progress_at))}s; "
            f"nudge {state.nudges_used + 1}/{config.nudge_budget}")
    if can_nudge and state.nudges_used >= config.nudge_budget and dwell_ok:
        return _escalate_once(state, now, since, "nudge budget exhausted without progress")
    if not can_nudge and _secs(now, since) >= config.escalate_grace_sec:
        return _escalate_once(state, now, since,
                              "stalled and nudging impossible (headless or busy pane)")
    return StallAction.NONE, "stalled; waiting on nudge dwell"


def _classify(state: WatchdogState, text: str, *, is_interrupt: bool | None,
              heartbeats: Sequence[HeartbeatRecord], now: datetime) -> NeverBlockReason | None:
    """Step 2, minus a banner already resolved by a verified resume (still on screen)."""
    reason = classify_never_block(text, is_interrupt=is_interrupt, heartbeats=heartbeats, now=now)
    if (reason == NeverBlockReason.RATE_LIMIT and state.paused_at is None
            and state.spent_banner_key and rate_limit_banner_key(text) == state.spent_banner_key):
        return None
    if reason != NeverBlockReason.RATE_LIMIT:
        state.spent_banner_key = None  # the resolved banner has scrolled away
    return reason


def _progress(state: WatchdogState, now: datetime, text: str,
              reason: NeverBlockReason | None) -> StallVerdict | None:
    """Step 1: progress resets the stall clock; verified resume once the pause elapsed."""
    state.last_progress_at, state.stall_since = now, None
    if state.paused_at is None:
        return None
    until = state.paused_until or state.paused_at
    if reason == NeverBlockReason.RATE_LIMIT and _secs(now, until) < 0:
        return None  # banner fresh and reset not reached: stay paused
    spent = rate_limit_banner_key(text) if reason == NeverBlockReason.RATE_LIMIT else None
    _end_pause(state, now, spent_banner=spent or None)
    return StallVerdict(action=StallAction.RESUME, stalled=False, evaluated_at=now,
                        reason="progress observed after rate-limit pause; resumed")


def evaluate(
    state: WatchdogState, config: WatchdogConfig, *, now: datetime, text: str,
    heartbeats: Sequence[HeartbeatRecord], progress: bool, process_dead: bool | None,
    is_interrupt: bool | None = None, can_nudge: bool, tz: tzinfo | None = None,
) -> StallVerdict:
    """The whole stall/nudge/pause decision policy for one tick (pure, clock-injected).

    ``tz`` is the operator's local zone for banner clock times ("resets at
    3pm"); ``None`` falls back to ``now.tzinfo``. ``can_nudge`` is False for
    headless AND for a tmux pane that is busy / showing a dialog, so a stall
    that cannot be nudged still escalates after ``escalate_grace_sec``.
    """
    now, can_nudge = _aware(now), can_nudge and config.nudge_enabled
    state.last_tick_at, state.ticks = now, state.ticks + 1
    reason = _classify(state, text, is_interrupt=is_interrupt, heartbeats=heartbeats, now=now)
    state.last_never_block = reason.value if reason else None
    base = {
        "never_block": reason, "process_dead": process_dead, "progress": progress,
        "freshness": _freshness(heartbeats, now, config.stall_threshold_sec),
    }
    if progress and (resumed := _progress(state, now, text, reason)) is not None:
        return resumed.model_copy(update=base)
    if reason == NeverBlockReason.RATE_LIMIT:
        action, why = _rate_limited(state, config, now, text, tz, can_nudge)
        return StallVerdict(action=action, stalled=False, reason=why, evaluated_at=now, **base)
    if state.paused_at is not None and reason is None:
        action, why = _paused_banner_gone(state, config, now, can_nudge)
        return StallVerdict(action=action, stalled=False, reason=why, evaluated_at=now, **base)
    if reason is not None:
        action, why = _other_never_block(state, config, now, reason)
        stalled = _secs(now, state.last_progress_at) >= config.stall_threshold_sec
        return StallVerdict(action=action, stalled=stalled, reason=why, evaluated_at=now, **base)
    if _secs(now, state.started_at) < config.startup_grace_sec:
        return StallVerdict(action=StallAction.NONE, stalled=False, reason="startup grace",
                            evaluated_at=now, **base)
    idle = _secs(now, state.last_progress_at)
    if process_dead is True and not progress:  # observed progress contradicts a dead verdict
        action, why = _dead_action(state, now)
        return StallVerdict(action=action, stalled=True, reason=why, evaluated_at=now, **base)
    if idle < config.stall_threshold_sec:
        state.stall_since = None
        return StallVerdict(action=StallAction.NONE, stalled=False, evaluated_at=now,
                            reason=f"healthy: last progress {int(idle)}s ago", **base)
    action, why = _stalled_action(state, config, now, can_nudge=can_nudge)
    return StallVerdict(action=action, stalled=True, reason=why, evaluated_at=now, **base)
