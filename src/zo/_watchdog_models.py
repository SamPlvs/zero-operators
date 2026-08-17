"""Pydantic models + config for the watchdog (WS-C, oracle checks 11-12).

Split out of ``zo.watchdog`` (which re-exports every name here) so the policy
module stays under the 500-line rule. Nothing in this module does I/O.
"""

from __future__ import annotations

import os
from datetime import datetime  # noqa: TC003 — pydantic resolves field annotations at runtime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from zo._watchdog_text import NeverBlockReason, _aware

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "SCHEMA_VERSION", "Freshness", "HeartbeatRecord", "HeartbeatStatus", "StallAction",
    "StallVerdict", "WatchdogConfig", "WatchdogState", "new_state", "resolve_watchdog_config",
]

SCHEMA_VERSION = 1


# ---------------------------------------------------------------- heartbeats

class HeartbeatStatus(StrEnum):
    """Hook-derived liveness status of one agent key."""

    READY = "ready"
    EXECUTING = "executing"
    COMPACTING = "compacting"
    SHUTDOWN = "shutdown"


class HeartbeatRecord(BaseModel):
    """One ``<memory_root>/heartbeats/<agent_key>.json`` file."""

    schema_version: int = SCHEMA_VERSION
    agent_key: str
    agent_id: str | None = None
    agent_type: str | None = None
    session_id: str
    zo_session_id: str | None = None
    pid: int | None = None
    process_start_identity: str | None = None
    last_tick_at: datetime
    status: HeartbeatStatus = HeartbeatStatus.EXECUTING
    last_event: str = ""
    tick_count: int = 0


class Freshness(StrEnum):
    """Three-state heartbeat freshness; UNKNOWN is never a stall verdict."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


# ------------------------------------------------------------ config + state

class WatchdogConfig(BaseModel):
    """Per-project watchdog policy (``ProjectConfig.watchdog``)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    stall_threshold_sec: int = 1200
    startup_grace_sec: int = 120
    nudge_enabled: bool = True
    nudge_delay_sec: int = 30
    nudge_budget: int = 3
    nudge_message: str = (
        "Continue working on your assigned task and report concrete progress (not ACK-only)."
    )
    resume_nudge_budget: int = 2
    escalate_grace_sec: int = 120
    kill_headless_on_escalate: bool = True
    rate_limit_backoff_base_sec: int = 60
    rate_limit_backoff_max_sec: int = 1800
    rate_limit_max_pause_sec: int = 6 * 3600
    hard_max_restarts: int = 3
    progress_paths: list[str] = Field(default_factory=list)


def resolve_watchdog_config(
    project: WatchdogConfig | None = None, *, env: Mapping[str, str] | None = None,
) -> WatchdogConfig:
    """Project config + env overrides (``ZO_WATCHDOG=0`` kill switch, ``ZO_WATCHDOG_STALL_SEC``)."""
    env = os.environ if env is None else env
    base = project if project is not None else WatchdogConfig()
    update: dict[str, object] = {}
    if env.get("ZO_WATCHDOG", "").strip().lower() in {"0", "false", "no", "off"}:
        update["enabled"] = False
    stall = env.get("ZO_WATCHDOG_STALL_SEC", "").strip()
    if stall.isdigit() and int(stall) > 0:
        update["stall_threshold_sec"] = int(stall)
    return base.model_copy(update=update)


class WatchdogState(BaseModel):
    """Per-run watchdog state, persisted at ``<memory_root>/heartbeats/_watchdog.json``.

    ``pause_banner_key`` identifies the banner text the current pause was
    entered on (unchanged at expiry → stale banner, not a fresh limit);
    ``spent_banner_key`` is the banner of a pause resolved by verified
    progress (still visible in the tail but no longer evidence);
    ``pause_evidence`` records the tier of evidence (``reset`` — a parsed
    reset time; ``banner`` / ``prose`` / ``loose``) for exit classification;
    ``dead_escalated_at`` makes the positive-proof-dead escalation fire once.
    """

    zo_session_id: str = ""
    started_at: datetime
    last_tick_at: datetime | None = None
    ticks: int = 0
    last_progress_at: datetime
    baseline_ticks: dict[str, int] = Field(default_factory=dict)
    seen_ticks: dict[str, int] = Field(default_factory=dict)
    last_digest: str | None = None
    last_file_mtimes: dict[str, float] = Field(default_factory=dict)
    stall_since: datetime | None = None
    nudges_used: int = 0
    last_nudge_at: datetime | None = None
    resume_nudges_used: int = 0
    escalated_at: datetime | None = None
    dead_escalated_at: datetime | None = None
    stall_events: int = 0
    paused_at: datetime | None = None
    paused_until: datetime | None = None
    paused_reason: str | None = None
    pause_attempts: int = 0
    pause_banner_key: str | None = None
    pause_evidence: str | None = None
    spent_banner_key: str | None = None
    total_paused_sec: float = 0.0
    last_never_block: str | None = None


def new_state(*, now: datetime, zo_session_id: str = "",
              heartbeats: Sequence[HeartbeatRecord] = ()) -> WatchdogState:
    """Fresh state; pre-existing heartbeat files are baselined and do not count as progress."""
    baseline = {hb.agent_key: hb.tick_count for hb in heartbeats}
    return WatchdogState(
        zo_session_id=zo_session_id, started_at=_aware(now), last_progress_at=_aware(now),
        baseline_ticks=dict(baseline), seen_ticks=dict(baseline),
    )


# ------------------------------------------------------------ stall policy

class StallAction(StrEnum):
    """What the caller should do this tick."""

    NONE = "none"
    NUDGE = "nudge"
    RESUME_NUDGE = "resume_nudge"
    PAUSE = "pause"
    RESUME = "resume"
    ESCALATE = "escalate"


class StallVerdict(BaseModel):
    """Outcome of one ``evaluate()`` tick."""

    action: StallAction
    stalled: bool
    reason: str
    never_block: NeverBlockReason | None = None
    freshness: Freshness = Freshness.UNKNOWN
    process_dead: bool | None = None
    progress: bool = False
    evaluated_at: datetime
