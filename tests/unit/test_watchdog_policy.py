"""``evaluate()`` scenario table for zo.watchdog (WS-C, plan oracle checks 11-12).

Every scenario drives the pure policy with an injected clock; ``seeded``
tests plant the failure condition (a 10-minute stall, a rate-limit banner,
a dead process) and assert the watchdog reacts exactly as the contract says.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from zo.watchdog import (
    HeartbeatRecord,
    HeartbeatStatus,
    NeverBlockReason,
    StallAction,
    StallVerdict,
    WatchdogConfig,
    WatchdogState,
    compute_pause_until,
    evaluate,
    new_state,
)

T0 = datetime(2026, 8, 17, 14, 0, tzinfo=UTC)
IDLE = "work done.\n\n› "
BANNER_RESET = "You've hit your usage limit · resets at 3pm\n› "
BANNER_PLAIN = "Rate limit reached. Try again later.\n› "
DIALOG = "Do you want to proceed?\n❯ 1. Yes\n  2. No (esc)"
CFG = WatchdogConfig(stall_threshold_sec=600, startup_grace_sec=120, nudge_delay_sec=30,
                     nudge_budget=3, escalate_grace_sec=120)


class Clock:
    """Injected clock: ``at(sec)`` returns T0 + sec."""

    @staticmethod
    def at(sec: float) -> datetime:
        return T0 + timedelta(seconds=sec)


def _tick(state: WatchdogState, sec: float, *, text: str = IDLE, progress: bool = False,
          can_nudge: bool = True, process_dead: bool | None = None,
          heartbeats: list[HeartbeatRecord] | None = None, cfg: WatchdogConfig = CFG,
          is_interrupt: bool | None = None) -> StallVerdict:
    return evaluate(state, cfg, now=Clock.at(sec), text=text, heartbeats=heartbeats or [],
                    progress=progress, process_dead=process_dead, is_interrupt=is_interrupt,
                    can_nudge=can_nudge)


def _deliver_nudge(state: WatchdogState, sec: float, *, resume: bool = False) -> None:
    """What the wrapper does after a nudge was actually delivered."""
    if resume:
        state.resume_nudges_used += 1
    else:
        state.nudges_used += 1
    state.last_nudge_at = Clock.at(sec)


# ---- (a) seeded 10-min stall → nudge ×3 → escalate once (oracle check 11) ----

def test_seeded_10min_stall_nudges_then_escalates_once() -> None:
    state = new_state(now=T0)
    minute_actions = [_tick(state, m * 60).action for m in range(12)]
    # t=0..1 grace, t=2..9 healthy, t=10 stalled but inside dwell, t=11 first nudge
    assert minute_actions[:11] == [StallAction.NONE] * 11
    assert minute_actions[11] == StallAction.NUDGE
    assert state.stall_since == Clock.at(600) and state.stall_events == 1
    _deliver_nudge(state, 660)
    assert _tick(state, 670).action == StallAction.NONE  # dwell between nudges
    assert _tick(state, 690).action == StallAction.NUDGE
    _deliver_nudge(state, 690)
    assert _tick(state, 720).action == StallAction.NUDGE
    _deliver_nudge(state, 720)
    assert _tick(state, 740).action == StallAction.NONE  # budget spent, dwell before escalating
    verdict = _tick(state, 750)
    assert verdict.action == StallAction.ESCALATE and verdict.stalled is True
    assert "budget" in verdict.reason and state.escalated_at == Clock.at(750)
    later = [_tick(state, 750 + 60 * i) for i in range(1, 4)]
    assert all(v.action == StallAction.NONE and v.stalled for v in later)  # escalate fires ONCE


def test_stall_clears_on_progress_and_can_recur() -> None:
    state = new_state(now=T0)
    _tick(state, 660)
    assert state.stall_since is not None
    verdict = _tick(state, 700, progress=True)
    assert verdict.action == StallAction.NONE and not verdict.stalled and state.stall_since is None
    assert _tick(state, 700 + 601).stalled is True
    assert state.stall_events == 2


# ---- (b) seeded rate-limited session is never nudged (oracle check 11) ----

def test_seeded_rate_limited_never_nudged() -> None:
    """A rate-limited session is never stall-NUDGED. Before ``paused_until`` the
    verdict is PAUSE; a static plain banner past its backoff is stale → the
    check-12 RESUME_NUDGE probe (not a stall nudge); a *fresh* banner (new
    text) extends the pause by backoff."""
    state = new_state(now=T0)
    actions = [_tick(state, sec, text=BANNER_PLAIN).action for sec in (0, 30, 59)]
    assert actions == [StallAction.PAUSE] * 3
    assert state.paused_at == T0 and state.paused_until == T0 + timedelta(seconds=60)
    # Static banner past its backoff: not a stall nudge, a resume probe.
    assert _tick(state, 60, text=BANNER_PLAIN).action == StallAction.RESUME_NUDGE
    # Fresh banner (Claude re-printed a limit line): extend by backoff, still PAUSE.
    fresh = BANNER_PLAIN + "\nRate limit reached again. Try again later.\n› "
    verdict = _tick(state, 61, text=fresh)
    assert verdict.action == StallAction.PAUSE and "extended" in verdict.reason
    assert state.pause_attempts == 2 and state.paused_until == T0 + timedelta(seconds=61 + 120)
    assert _tick(state, 100, text=fresh).action == StallAction.PAUSE
    assert state.nudges_used == 0 and state.last_never_block == "rate_limit"
    assert StallAction.NUDGE not in actions
    assert compute_pause_until(T0, None, attempt=0, config=CFG) == T0 + timedelta(seconds=60)
    assert compute_pause_until(T0, None, attempt=10, config=CFG) == T0 + timedelta(seconds=1800)


def test_rate_limit_pause_exceeding_max_escalates_once() -> None:
    cfg = CFG.model_copy(update={"rate_limit_max_pause_sec": 300})
    state = new_state(now=T0)
    _tick(state, 0, text=BANNER_PLAIN, cfg=cfg)
    verdict = _tick(state, 301, text=BANNER_PLAIN, cfg=cfg)
    assert verdict.action == StallAction.ESCALATE and "max" in verdict.reason
    assert _tick(state, 400, text=BANNER_PLAIN, cfg=cfg).action == StallAction.NONE


# ---- (c) check-12 resume: parsed reset → resume nudge → verified resume ----

def test_seeded_check12_resume_after_reset() -> None:
    state = new_state(now=T0)
    verdict = _tick(state, 0, text=BANNER_RESET)
    assert verdict.action == StallAction.PAUSE
    assert verdict.never_block is NeverBlockReason.RATE_LIMIT
    assert state.paused_until == datetime(2026, 8, 17, 15, 0, 15, tzinfo=UTC)
    assert _tick(state, 1800, text=BANNER_RESET).action == StallAction.PAUSE
    # banner gone but pause not yet elapsed → wait
    assert _tick(state, 1900).action == StallAction.NONE
    # banner gone, pause elapsed, no progress → resume nudge (bounded)
    verdict = _tick(state, 3700)
    assert verdict.action == StallAction.RESUME_NUDGE
    _deliver_nudge(state, 3700, resume=True)
    assert _tick(state, 3710).action == StallAction.RESUME_NUDGE
    _deliver_nudge(state, 3710, resume=True)
    assert _tick(state, 3720).action == StallAction.NONE  # resume budget (2) exhausted; dwell
    verdict = _tick(state, 3730, progress=True)
    assert verdict.action == StallAction.RESUME and not verdict.stalled
    assert state.paused_at is None and state.paused_until is None
    assert state.total_paused_sec == 3730.0 and state.resume_nudges_used == 0
    assert _tick(state, 3740).action == StallAction.NONE


def test_seeded_check12_banner_clock_time_is_local_tz() -> None:
    """Regression: 'resets at 3pm' is the operator's LOCAL 3pm. At 20:00Z in
    US/Pacific (13:00 local) the reset is 22:00Z today — not 15:00Z tomorrow."""
    pacific = timezone(timedelta(hours=-7))
    now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
    state = new_state(now=now)
    verdict = evaluate(state, CFG, now=now, text=BANNER_RESET, heartbeats=[], progress=False,
                       process_dead=None, can_nudge=True, tz=pacific)
    assert verdict.action == StallAction.PAUSE
    assert state.paused_until == datetime(2026, 8, 17, 22, 0, 15, tzinfo=UTC)
    assert state.pause_evidence == "reset"
    # tz=None keeps the pure default (now.tzinfo=UTC): "3pm" is already past →
    # tomorrow, which is beyond rate_limit_max_pause_sec and therefore NOT
    # honoured — exponential backoff (60 s) applies and the evidence tier is
    # the banner itself, not a parsed reset. The runner supplies the local tz.
    state = new_state(now=now)
    evaluate(state, CFG, now=now, text=BANNER_RESET, heartbeats=[], progress=False,
             process_dead=None, can_nudge=True)
    assert state.paused_until == now + timedelta(seconds=60)
    assert state.pause_evidence == "banner"


def test_seeded_static_banner_is_stale_at_reset_not_rolled_to_tomorrow() -> None:
    """Regression: the TUI never clears the usage-limit line. Past the reset an
    UNCHANGED banner → RESUME_NUDGE (never re-parsed into a +24 h extension);
    heartbeat progress with the banner still visible → verified RESUME; the
    spent banner is then ignored until it scrolls away."""
    state = new_state(now=T0)
    assert _tick(state, 0, text=BANNER_RESET).action == StallAction.PAUSE
    until = datetime(2026, 8, 17, 15, 0, 15, tzinfo=UTC)
    assert state.paused_until == until
    assert _tick(state, 3600, text=BANNER_RESET).action == StallAction.PAUSE  # 15:00:00 < until
    verdict = _tick(state, 3616, text=BANNER_RESET)  # 15:00:16 ≥ until, same banner
    assert verdict.action == StallAction.RESUME_NUDGE and "stale" in verdict.reason
    assert state.paused_until == until and state.pause_attempts == 1  # NOT tomorrow
    _deliver_nudge(state, 3616, resume=True)
    # Progress (heartbeat) while the banner is still in the tail → RESUME.
    verdict = _tick(state, 3640, text=BANNER_RESET, progress=True)
    assert verdict.action == StallAction.RESUME and state.paused_at is None
    assert state.total_paused_sec == 3640.0 and state.spent_banner_key
    # Same banner still on screen next tick: not a new pause; healthy tick.
    verdict = _tick(state, 3650, text=BANNER_RESET)
    assert verdict.action == StallAction.NONE and verdict.never_block is None
    assert state.paused_at is None
    # Banner scrolls away → the 'spent' memory is dropped; a NEW banner pauses again.
    _tick(state, 3660, text=IDLE)
    assert state.spent_banner_key is None
    assert _tick(state, 3670, text=BANNER_PLAIN).action == StallAction.PAUSE


def test_fresh_banner_past_reset_extends_by_backoff_not_day_rollover() -> None:
    """A re-printed 'resets at 3pm' read AFTER 3pm would parse as tomorrow; the
    extension rejects a reset beyond ``rate_limit_max_pause_sec`` and falls
    back to exponential backoff (a real later reset is honoured)."""
    state = new_state(now=T0)
    _tick(state, 0, text=BANNER_RESET)  # until 15:00:15
    fresh = BANNER_RESET + "\n› continue\nYou've hit your usage limit · resets at 3pm\n› "
    verdict = _tick(state, 3616, text=fresh)  # 15:00:16, banner text changed
    assert verdict.action == StallAction.PAUSE and "extended" in verdict.reason
    assert state.paused_until == Clock.at(3616 + 120)  # backoff attempt 1, not 15:00 tomorrow
    assert state.pause_evidence == "banner"
    later = fresh + "\nYou've hit your usage limit · resets at 5pm\n› "
    verdict = _tick(state, 3616 + 120, text=later)  # newest banner wins: 17:00 today
    assert state.paused_until == datetime(2026, 8, 17, 17, 0, 15, tzinfo=UTC)
    assert state.pause_evidence == "reset"


def test_progress_while_banner_fresh_before_reset_stays_paused() -> None:
    """A teammate heartbeat while the banner is fresh and the reset is ahead
    is not a verified resume (no PAUSE/RESUME flapping)."""
    state = new_state(now=T0)
    _tick(state, 0, text=BANNER_RESET)
    verdict = _tick(state, 30, text=BANNER_RESET, progress=True)
    assert verdict.action == StallAction.PAUSE and state.paused_at == T0
    verdict = _tick(state, 60, progress=True)  # banner gone → progress resumes at once
    assert verdict.action == StallAction.RESUME


def test_resume_nudges_exhausted_without_progress_escalates_once() -> None:
    state = new_state(now=T0)
    _tick(state, 0, text=BANNER_PLAIN)  # paused_until = +60 s
    for sec in (61, 71):
        assert _tick(state, sec).action == StallAction.RESUME_NUDGE
        _deliver_nudge(state, sec, resume=True)
    assert _tick(state, 90).action == StallAction.NONE  # dwell after the last resume nudge
    verdict = _tick(state, 125)
    assert verdict.action == StallAction.ESCALATE and "unverified" in verdict.reason
    assert _tick(state, 200).action == StallAction.NONE
    assert _tick(state, 300, progress=True).action == StallAction.RESUME  # late resume still wins


# ---- (d) headless resume requires progress ----

def test_headless_resume_requires_progress() -> None:
    state = new_state(now=T0)
    _tick(state, 0, text=BANNER_PLAIN, can_nudge=False)  # paused_until = +60 s
    assert _tick(state, 61, can_nudge=False).action == StallAction.NONE
    assert _tick(state, 100, can_nudge=False).action == StallAction.NONE
    verdict = _tick(state, 121, can_nudge=False)  # paused_until + backoff base → escalate
    assert verdict.action == StallAction.ESCALATE and "unverified" in verdict.reason
    assert _tick(state, 130, can_nudge=False).action == StallAction.NONE
    verdict = _tick(state, 140, can_nudge=False, progress=True)
    # Paused time stops accruing at the escalation (t=121): a late verified
    # resume does not retroactively suspend the run timeout past the hand-off.
    assert verdict.action == StallAction.RESUME and state.total_paused_sec == 121.0


def test_headless_stall_escalates_after_grace_without_nudging() -> None:
    state = new_state(now=T0)
    assert _tick(state, 660, can_nudge=False).action == StallAction.NONE
    verdict = _tick(state, 660 + 120, can_nudge=False)
    assert verdict.action == StallAction.ESCALATE and "headless" in verdict.reason
    assert _tick(state, 900, can_nudge=False).action == StallAction.NONE
    assert state.nudges_used == 0


# ---- (e) dead process → escalate right after grace (oracle check 11) ----

def test_seeded_dead_process_escalates_after_grace() -> None:
    state = new_state(now=T0)
    assert _tick(state, 60, process_dead=True).action == StallAction.NONE  # grace
    verdict = _tick(state, 121, process_dead=True)
    assert verdict.action == StallAction.ESCALATE and verdict.process_dead is True
    assert "dead" in verdict.reason and verdict.stalled
    assert _tick(state, 200, process_dead=True).action == StallAction.NONE
    assert _tick(state, 200, process_dead=None).action == StallAction.NONE  # unknown ≠ dead


def test_progress_contradicts_dead_verdict_and_dead_escalates_at_most_once() -> None:
    """Regression: a recycled/wrong pid with heartbeats still ticking must not
    escalate on EVERY tick — progress wins, and positive-proof death is
    escalated once per run even across stall resets."""
    state = new_state(now=T0)
    verdicts = [_tick(state, 200 + i * 10, process_dead=True, progress=True) for i in range(5)]
    assert {v.action for v in verdicts} == {StallAction.NONE}
    assert all(not v.stalled for v in verdicts) and state.stall_events == 0
    # No progress this tick → dead is escalated once …
    verdict = _tick(state, 300, process_dead=True)
    assert verdict.action == StallAction.ESCALATE and "dead" in verdict.reason
    # … progress clears the stall, dead again → NOT a second escalation.
    _tick(state, 310, process_dead=True, progress=True)
    actions = [_tick(state, 320 + i * 10, process_dead=True).action for i in range(5)]
    assert actions == [StallAction.NONE] * 5 and state.stall_events == 2
    assert state.dead_escalated_at == Clock.at(300)


def test_busy_tmux_pane_cannot_be_nudged_and_escalates_after_grace() -> None:
    """Regression: the wrapper passes ``can_nudge=False`` for a busy pane
    (spinner / 'esc to interrupt'); a stall there escalates after
    ``escalate_grace_sec`` instead of returning NUDGE forever."""
    state = new_state(now=T0)
    busy = "· Running… (25m 12s · esc to interrupt)\n"
    actions = [_tick(state, sec, text=busy, can_nudge=False).action for sec in (600, 660, 700)]
    assert actions == [StallAction.NONE, StallAction.NONE, StallAction.NONE]  # grace 120 s
    verdict = _tick(state, 720, text=busy, can_nudge=False)
    assert verdict.action == StallAction.ESCALATE and "busy" in verdict.reason
    assert _tick(state, 800, text=busy, can_nudge=False).action == StallAction.NONE
    assert state.nudges_used == 0


# ---- (f) startup grace ----

def test_startup_grace_suppresses() -> None:
    cfg = CFG.model_copy(update={"stall_threshold_sec": 10, "startup_grace_sec": 300})
    state = new_state(now=T0)
    assert all(_tick(state, s, cfg=cfg).action == StallAction.NONE for s in (0, 100, 299))
    assert _tick(state, 300, cfg=cfg).stalled is True


# ---- (g) awaiting_input / other never-block reasons are never nudged ----

def test_awaiting_input_never_nudged() -> None:
    state = new_state(now=T0)
    verdicts = [_tick(state, m * 60, text=DIALOG) for m in range(30)]
    assert {v.action for v in verdicts} == {StallAction.NONE}
    assert verdicts[-1].never_block is NeverBlockReason.AWAITING_INPUT
    assert verdicts[-1].stalled is True  # the clock ran, but no nudge and no escalation


def test_user_abort_and_interrupt_never_nudged() -> None:
    state = new_state(now=T0)
    assert _tick(state, 900, is_interrupt=True).action == StallAction.NONE
    assert state.last_never_block == "user_abort"
    assert _tick(state, 960, text="Interrupted by user\n› ").action == StallAction.NONE


def test_auth_error_escalates_after_threshold_but_never_nudges() -> None:
    state = new_state(now=T0)
    assert _tick(state, 300, text="please run /login\n› ").action == StallAction.NONE
    verdict = _tick(state, 601, text="please run /login\n› ")
    assert verdict.action == StallAction.ESCALATE and "auth_error" in verdict.reason
    assert _tick(state, 700, text="please run /login\n› ").action == StallAction.NONE
    assert state.nudges_used == 0


# ---- (h) compacting resets the stall clock ----

def test_compacting_resets_clock() -> None:
    state = new_state(now=T0)
    hb = HeartbeatRecord(agent_key="lead-s1", session_id="s1", tick_count=1,
                         last_tick_at=Clock.at(590), status=HeartbeatStatus.COMPACTING)
    verdict = _tick(state, 600, heartbeats=[hb])
    assert verdict.action == StallAction.NONE and verdict.never_block is NeverBlockReason.COMPACTING
    assert state.last_progress_at == Clock.at(600)
    assert _tick(state, 1100).stalled is False
    assert _tick(state, 1200).stalled is True


# ---- (i) progress via any observer feeds evaluate() ----

def test_progress_flag_resets_clock_and_disabled_nudges_do_not_fire() -> None:
    state = new_state(now=T0)
    _tick(state, 500, progress=True)
    assert state.last_progress_at == Clock.at(500)
    verdict = _tick(state, 1000)
    assert verdict.action == StallAction.NONE and verdict.progress is False
    off = CFG.model_copy(update={"nudge_enabled": False})
    state = new_state(now=T0)
    assert _tick(state, 700, cfg=off).action == StallAction.NONE
    verdict = _tick(state, 700 + 120, cfg=off)
    assert verdict.action == StallAction.ESCALATE and state.nudges_used == 0


def test_verdict_carries_freshness_and_tick_bookkeeping() -> None:
    state = new_state(now=T0)
    fresh = HeartbeatRecord(agent_key="a", session_id="s", last_tick_at=Clock.at(50), tick_count=1)
    verdict = _tick(state, 60, heartbeats=[fresh])
    assert verdict.freshness == "fresh" and verdict.evaluated_at == Clock.at(60)
    assert state.ticks == 1 and state.last_tick_at == Clock.at(60)
    stale = HeartbeatRecord(agent_key="a", session_id="s", last_tick_at=T0, tick_count=1)
    assert _tick(state, 700, heartbeats=[stale]).freshness == "stale"
    assert _tick(state, 700).freshness == "unknown"
