"""Tests for zo.watchdog — the WS-C execution substrate (plan oracle checks 11-12).

Covers the never-block taxonomy, rate-limit reset parsing, heartbeat
freshness, evidence observers, process identity (positive proof only),
persistence and config. The ``evaluate()`` scenario table (seeded 10-min
stall, rate-limited-never-nudged, check-12 resume, …) lives in
``test_watchdog_policy.py``.
"""

from __future__ import annotations

import errno
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from pydantic import ValidationError

from zo import _proc, watchdog
from zo.watchdog import (
    HEARTBEATS_DIRNAME,
    WATCHDOG_STATE_FILENAME,
    Freshness,
    HeartbeatRecord,
    HeartbeatStatus,
    NeverBlockReason,
    WatchdogConfig,
    classify_freshness,
    classify_never_block,
    identities_may_match,
    is_process_dead,
    is_valid_process_start_identity,
    load_all_heartbeats,
    load_heartbeat,
    load_state,
    new_state,
    normalize_terminal_text,
    observe_files,
    observe_heartbeats,
    observe_text,
    pane_ready_for_nudge,
    parse_rate_limit_reset,
    pid_alive,
    process_start_identity,
    process_tree_cpu_seconds,
    progress_digest,
    rate_limit_banner_key,
    rate_limit_match,
    resolve_watchdog_config,
    save_state,
    sweep_stale_heartbeats,
    write_heartbeat,
)

if TYPE_CHECKING:
    from pathlib import Path

T0 = datetime(2026, 8, 17, 14, 0, tzinfo=UTC)
BANNER = "You've hit your usage limit · resets at 3pm"
DIALOG = "Do you want to proceed?\n❯ 1. Yes\n  2. Yes, and don't ask again\n  3. No (esc)"


def _hb(key: str = "lead-s1", ticks: int = 1, at: datetime = T0,
        status: HeartbeatStatus = HeartbeatStatus.EXECUTING) -> HeartbeatRecord:
    return HeartbeatRecord(agent_key=key, session_id="s1", last_tick_at=at,
                           status=status, tick_count=ticks)


# ---- never-block taxonomy (oracle check 11) ----

@pytest.mark.parametrize(("text", "reason"), [
    (BANNER, NeverBlockReason.RATE_LIMIT),
    ("Rate limit reached. Try again later.", NeverBlockReason.RATE_LIMIT),
    ("API Error: 429 too_many_requests", NeverBlockReason.RATE_LIMIT),
    ("weekly usage limit exhausted", NeverBlockReason.RATE_LIMIT),
    ("prompt is too long", NeverBlockReason.CONTEXT_LIMIT),
    ("Context window is full", NeverBlockReason.CONTEXT_LIMIT),
    ("stop_reason: context_exceeded", NeverBlockReason.CONTEXT_LIMIT),
    ("please run /login", NeverBlockReason.AUTH_ERROR),
    ("authentication_error: invalid api key", NeverBlockReason.AUTH_ERROR),
    ("HTTP 401 Unauthorized", NeverBlockReason.AUTH_ERROR),
    ("Not logged in", NeverBlockReason.AUTH_ERROR),
    (DIALOG, NeverBlockReason.AWAITING_INPUT),
    ("Waiting for your approval", NeverBlockReason.AWAITING_INPUT),
    ("Do you trust this folder?", NeverBlockReason.AWAITING_INPUT),
    ("Press Enter to continue", NeverBlockReason.AWAITING_INPUT),
    ("Interrupted by user", NeverBlockReason.USER_ABORT),
    # The real TUI renders the interrupt behind a ⎿ connector, old and new wording.
    ("⎿  Interrupted by user\n› ", NeverBlockReason.USER_ABORT),
    ("⎿  Interrupted · What should Claude do instead?\n› ", NeverBlockReason.USER_ABORT),
    ("stop_reason=user_cancel", NeverBlockReason.USER_ABORT),
    ("Request aborted", NeverBlockReason.USER_ABORT),
    ("manual_stop", NeverBlockReason.USER_ABORT),
    # Loose rate-limit phrases DO count with rate/usage/quota vocabulary on the line.
    ("Too many requests, try again later", NeverBlockReason.RATE_LIMIT),
    ("API usage limit reached for this 5-hour window", NeverBlockReason.RATE_LIMIT),
    ("Your usage resets in 2 hours at 5pm", NeverBlockReason.RATE_LIMIT),
    ("hit the rate limit; backing off", NeverBlockReason.RATE_LIMIT),
])
def test_taxonomy_positive(text: str, reason: NeverBlockReason) -> None:
    assert classify_never_block(text) is reason


@pytest.mark.parametrize("text", [
    "epoch 3 val_loss 0.4291", "step 4290 loss 0.12", "GPU overloaded, retrying batch",
    "commit 8466d29 fix weekly report", "$ cat transcript.txt ... rate limit",
    "turn interrupted", "x = arr[0]\n1. Read the file\n2. Edit it", "  › ",
    "\x1b[32mtests passed\x1b[0m 401 items collected",
    # ML / prose lines that carry a loose token WITHOUT rate-limit vocabulary.
    "early stopping: patience limit reached at epoch 30",
    "Service temporarily unavailable, try again later",
    "Analysis: the 5-hour window in the plan means two full epochs",
    "The nightly counter resets every day at midnight",
    "we hit the recursion limit in the parser",
])
def test_taxonomy_negative(text: str) -> None:
    assert classify_never_block(text) is None


def test_rate_limit_match_tiers_and_banner_key() -> None:
    assert rate_limit_match(BANNER) == "banner"
    assert rate_limit_match("Error 429 Too Many Requests") == "banner"
    assert rate_limit_match("the API hit a rate limit earlier and retried") == "prose"
    assert rate_limit_match("Too many requests, try again later") == "banner"
    assert rate_limit_match("quota: try again later") == "loose"
    assert rate_limit_match("patience limit reached at epoch 30") is None
    key = rate_limit_banner_key("work\n" + BANNER + "\n› ")
    assert key == BANNER
    assert rate_limit_banner_key("work\n› ") == ""
    two = rate_limit_banner_key(BANNER + "\n› continue\n" + BANNER.replace("3pm", "5pm"))
    assert two.count("resets at") == 2 and two != key


def test_taxonomy_precedence_and_interrupt() -> None:
    assert classify_never_block(BANNER + "\n" + DIALOG) is NeverBlockReason.RATE_LIMIT
    assert classify_never_block("prompt is too long\n" + BANNER) is NeverBlockReason.CONTEXT_LIMIT
    assert classify_never_block("aborted\n" + BANNER) is NeverBlockReason.USER_ABORT
    assert classify_never_block("healthy", is_interrupt=True) is NeverBlockReason.USER_ABORT
    old = "\n".join([BANNER] + ["line"] * 70)  # banner scrolled past the 60-line tail
    assert classify_never_block(old) is None


def test_taxonomy_compacting_heartbeat_window() -> None:
    inside = _hb(at=T0 - timedelta(seconds=60), status=HeartbeatStatus.COMPACTING)
    outside = _hb(at=T0 - timedelta(seconds=600), status=HeartbeatStatus.COMPACTING)
    assert classify_never_block("", heartbeats=[inside], now=T0) is NeverBlockReason.COMPACTING
    assert classify_never_block("", heartbeats=[outside], now=T0) is None
    assert classify_never_block(BANNER, heartbeats=[inside], now=T0) is NeverBlockReason.RATE_LIMIT


def test_normalize_and_digest_ignore_volatile_churn() -> None:
    assert "commit" not in normalize_terminal_text("commit abcdef1234 msg\nreal\r\n")
    a = progress_digest("✻ Thinking… (12s · ↓ 1.2k tokens · esc to interrupt)\nwork\n› ")
    b = progress_digest("✽ Thinking… (14s · ↓ 1.3k tokens · esc to interrupt)\nwork\n\n> ")
    assert a == b
    assert a != progress_digest("work\nmore work\n› ")


def test_pane_ready_for_nudge_guards() -> None:
    assert pane_ready_for_nudge("done.\n\n› ")
    assert pane_ready_for_nudge("done.\n│ > ")
    assert not pane_ready_for_nudge("· Thinking…\n› ")
    assert not pane_ready_for_nudge("working (esc to interrupt)\n> ")
    assert not pane_ready_for_nudge(DIALOG)
    assert not pane_ready_for_nudge("no prompt at all")
    assert not pane_ready_for_nudge("")


# ---- rate-limit reset parsing (oracle check 12) ----

@pytest.mark.parametrize(("text", "expected"), [
    ("resets at 3pm", datetime(2026, 8, 17, 15, 0, tzinfo=UTC)),
    ("resets at 1pm", datetime(2026, 8, 18, 13, 0, tzinfo=UTC)),  # already past → tomorrow
    ("resets at 14:30", datetime(2026, 8, 17, 14, 30, tzinfo=UTC)),
    ("try again in 5 minutes", T0 + timedelta(minutes=5)),
    ("resets in 2 hours", T0 + timedelta(hours=2)),
    ("retry-after: 90", T0 + timedelta(seconds=90)),
    ("limit resets 2026-08-17T16:00:00Z", datetime(2026, 8, 17, 16, 0, tzinfo=UTC)),
    ("no reset info here", None),
    ("resets 3", None),
])
def test_parse_rate_limit_reset(text: str, expected: datetime | None) -> None:
    assert parse_rate_limit_reset(text, now=T0) == expected


def test_parse_rate_limit_reset_uses_tz() -> None:
    tz = datetime.now().astimezone().tzinfo
    got = parse_rate_limit_reset("resets at 3pm", now=T0, tz=tz)
    assert got is not None and got.astimezone(tz).hour == 15
    pacific = timezone(timedelta(hours=-7))
    got = parse_rate_limit_reset("resets at 3pm", now=datetime(2026, 8, 17, 20, 0, tzinfo=UTC),
                                 tz=pacific)
    assert got == datetime(2026, 8, 17, 22, 0, tzinfo=UTC)  # 3pm PDT today, not tomorrow UTC


def test_parse_rate_limit_reset_newest_banner_wins() -> None:
    """Transcripts grow downward: the LAST reset in a tier is the current one."""
    text = BANNER + "\n› continue\nYou've hit your usage limit · resets at 5pm"
    assert parse_rate_limit_reset(text, now=T0) == datetime(2026, 8, 17, 17, 0, tzinfo=UTC)
    text = "try again in 5 minutes\n...\ntry again in 20 minutes"
    assert parse_rate_limit_reset(text, now=T0) == T0 + timedelta(minutes=20)


# ---- heartbeat freshness (oracle check 11) ----

def test_freshness_three_state() -> None:
    assert classify_freshness(None, now=T0, stale_after_sec=60) is Freshness.UNKNOWN
    fresh = _hb(at=T0 - timedelta(seconds=30))
    assert classify_freshness(fresh, now=T0, stale_after_sec=60) is Freshness.FRESH
    naive = _hb(at=(T0 - timedelta(seconds=90)).replace(tzinfo=None))
    assert classify_freshness(naive, now=T0, stale_after_sec=60) is Freshness.STALE


# ---- evidence observers (oracle check 11) ----

def test_observe_heartbeats_ignores_baseline_files() -> None:
    state = new_state(now=T0, heartbeats=[_hb("old", ticks=5)])
    assert observe_heartbeats(state, [_hb("old", ticks=5)]) is False
    assert observe_heartbeats(state, [_hb("old", ticks=6)]) is True
    assert observe_heartbeats(state, [_hb("old", ticks=6)]) is False
    assert observe_heartbeats(state, [_hb("new", ticks=1)]) is True
    assert state.seen_ticks == {"old": 6, "new": 1}


def test_observe_text_digest_change_ignoring_churn() -> None:
    state = new_state(now=T0)
    assert observe_text(state, "⠋ Working (12s · 100 tokens)\n› ") is False  # first observation
    assert observe_text(state, "⠙ Working (14s · 200 tokens)\n› ") is False  # spinner churn
    assert observe_text(state, "⠙ Working\nwrote file\n› ") is True
    state.paused_at = T0
    assert observe_text(state, "banner gone\n› ") is False  # paused: text is not verified resume


def test_observe_files_mtime_advance_and_new_file(tmp_path: Path) -> None:
    f, d = tmp_path / "ledger.json", tmp_path / "logs"
    f.write_text("{}"), d.mkdir()
    state = new_state(now=T0)
    assert observe_files(state, [f, d, tmp_path / "missing"]) is False
    os.utime(f, (2_000_000_000, 2_000_000_000))
    assert observe_files(state, [f, d]) is True
    assert observe_files(state, [f, d]) is False
    child = d / "x.jsonl"
    child.write_text("1"), os.utime(child, (2_100_000_000, 2_100_000_000))
    assert observe_files(state, [d]) is True
    (tmp_path / "missing").write_text("now here")
    assert observe_files(state, [tmp_path / "missing"]) is True


# ---- process identity: positive proof only (oracle check 11) ----

LINUX_STAT = ("4242 (weird proc) name) S 1 4242 4242 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 "
              "987654 1 2 3")


def test_identity_linux_proc_parse_with_paren_in_comm() -> None:
    assert _proc.parse_linux_stat_starttime(LINUX_STAT) == "987654"
    with mock.patch.object(_proc, "_read_proc_stat", return_value=LINUX_STAT):
        assert process_start_identity(4242, platform="linux") == "linux:987654"
    with mock.patch.object(_proc, "_read_proc_stat", return_value="garbage"):
        assert process_start_identity(4242, platform="linux") is None
    with mock.patch.object(_proc, "_read_proc_stat", side_effect=FileNotFoundError):
        assert process_start_identity(4242, platform="linux") is None


def test_identity_darwin_ps_mocked() -> None:
    def run(cmd: list[str], **kw: object) -> SimpleNamespace:
        assert cmd[:3] == ["ps", "-o", "lstart="] and kw["env"]["LC_ALL"] == "C"
        return SimpleNamespace(stdout="Sun Aug 17 10:11:12 2026\n", returncode=0)

    got = process_start_identity(77, platform="darwin", run=run)
    assert got is not None and got.startswith("darwin:") and got.endswith(":0")
    assert is_valid_process_start_identity(got, platform="darwin")
    junk = lambda *a, **k: SimpleNamespace(stdout="?")  # noqa: E731
    assert process_start_identity(77, platform="darwin", run=junk) is None
    other = process_start_identity(77, platform="freebsd", run=run)
    assert other == "freebsd:Sun Aug 17 10:11:12 2026"


def test_identity_validator_and_matching() -> None:
    assert is_valid_process_start_identity("linux:12345", platform="linux")
    assert not is_valid_process_start_identity("linux:0", platform="linux")
    assert not is_valid_process_start_identity("darwin:1:0", platform="linux")
    assert not is_valid_process_start_identity("x" * 1025, platform="linux")
    assert not is_valid_process_start_identity(None, platform="darwin")
    assert identities_may_match("darwin:1700000000:0", "darwin:1700000000:4321")
    assert not identities_may_match("darwin:1700000000:1", "darwin:1700000000:2")
    assert not identities_may_match("linux:1", "linux:2")


def test_is_process_dead_positive_proof_only() -> None:
    assert is_process_dead(None, "linux:1") is False
    with mock.patch("os.kill", side_effect=ProcessLookupError):
        assert is_process_dead(4242, None) is True  # ESRCH is positive proof
        assert pid_alive(4242) is False
    with mock.patch("os.kill", side_effect=PermissionError(errno.EPERM, "eperm")):
        assert pid_alive(4242) is True
        assert is_process_dead(4242, "linux:1", platform="linux") is False  # unknown ≠ dead
    with mock.patch("os.kill", return_value=None), \
            mock.patch.object(_proc, "_read_proc_stat", return_value=LINUX_STAT):
        assert is_process_dead(4242, "linux:987654", platform="linux") is False
        assert is_process_dead(4242, "linux:111", platform="linux") is True  # recycled pid
        assert is_process_dead(4242, "malformed", platform="linux") is False
    with mock.patch("os.kill", return_value=None), \
            mock.patch.object(_proc, "_read_proc_stat", return_value="garbage"):
        assert is_process_dead(4242, "linux:111", platform="linux") is False  # observed unknown


@pytest.mark.parametrize(("value", "expected"), [
    ("0:00.05", 0.05), ("12:34.56", 754.56), ("1:02:03.04", 3723.04),  # darwin
    ("00:00:07", 7.0), ("01:02:03", 3723.0), ("1-02:03:04", 93784.0),  # linux (+days)
    ("", None), ("junk", None), ("1:2:3:4", None),
])
def test_parse_ps_time(value: str, expected: float | None) -> None:
    assert _proc.parse_ps_time(value) == expected


def test_process_tree_cpu_seconds_sums_descendants_and_fails_open() -> None:
    table = ("    1     0   0:10.00\n"
             " 4242     1   0:01.00\n"   # lead
             " 4300  4242   0:02.00\n"   # bash tool
             " 4301  4300  40:00.00\n"   # python train.py (busy)
             " 5000     1   9:99.99\n"   # unrelated
             "junk line\n")
    run = lambda *a, **k: SimpleNamespace(stdout=table)  # noqa: E731
    assert process_tree_cpu_seconds(4242, run=run) == 1.0 + 2.0 + 2400.0
    assert process_tree_cpu_seconds(4301, run=run) == 2400.0
    assert process_tree_cpu_seconds(7777, run=run) is None  # not in the table → unknown
    assert process_tree_cpu_seconds(0, run=run) is None
    boom = mock.MagicMock(side_effect=OSError("no ps"))
    assert process_tree_cpu_seconds(4242, run=boom) is None  # advisory: never raises


# ---- persistence + config (oracle checks 11-12) ----

def test_heartbeat_round_trip_and_state_file_excluded(tmp_path: Path) -> None:
    write_heartbeat(tmp_path, _hb("agent-a", ticks=3))
    write_heartbeat(tmp_path, _hb("lead-s1", ticks=1))
    hb_dir = tmp_path / HEARTBEATS_DIRNAME
    (hb_dir / WATCHDOG_STATE_FILENAME).write_text('{"not": "a heartbeat"}')
    (hb_dir / "broken.json").write_text("{oops")
    records = load_all_heartbeats(tmp_path)
    assert [r.agent_key for r in records] == ["agent-a", "lead-s1"]
    assert records[0].tick_count == 3 and records[0].last_tick_at == T0
    assert load_heartbeat(hb_dir / "broken.json") is None
    assert not list(hb_dir.glob("*.tmp"))  # atomic: no partial files left behind


def test_write_heartbeat_atomic_no_partial_file(tmp_path: Path) -> None:
    with mock.patch("os.replace", side_effect=OSError("disk full")), pytest.raises(OSError):
        write_heartbeat(tmp_path, _hb("agent-a"))
    assert not (tmp_path / HEARTBEATS_DIRNAME / "agent-a.json").exists()
    assert not list((tmp_path / HEARTBEATS_DIRNAME).glob("*.tmp"))


def test_sweep_stale_heartbeats(tmp_path: Path) -> None:
    write_heartbeat(tmp_path, _hb("fresh", at=T0 - timedelta(hours=1)))
    write_heartbeat(tmp_path, _hb("stale", at=T0 - timedelta(hours=30)))
    assert sweep_stale_heartbeats(tmp_path, now=T0) == 1
    assert [r.agent_key for r in load_all_heartbeats(tmp_path)] == ["fresh"]


def test_state_round_trip_and_fail_open(tmp_path: Path) -> None:
    assert load_state(tmp_path) is None
    state = new_state(now=T0, zo_session_id="zo-1", heartbeats=[_hb("a", ticks=2)])
    state.paused_at, state.nudges_used = T0, 2
    path = save_state(tmp_path, state)
    assert path == tmp_path / HEARTBEATS_DIRNAME / WATCHDOG_STATE_FILENAME
    assert load_state(tmp_path) == state
    assert json.loads(path.read_text())["baseline_ticks"] == {"a": 2}
    path.write_text("{corrupt")
    assert load_state(tmp_path) is None
    assert load_all_heartbeats(tmp_path) == []  # state file never counts as a heartbeat


def test_watchdog_config_defaults_and_extra_forbid() -> None:
    cfg = WatchdogConfig()
    assert (cfg.enabled, cfg.stall_threshold_sec, cfg.nudge_budget, cfg.hard_max_restarts) == (
        True, 1200, 3, 3)
    with pytest.raises(ValidationError):
        WatchdogConfig(tick_cron="* * * * *")


def test_resolve_watchdog_config_env_kill_switch() -> None:
    assert resolve_watchdog_config(env={}).enabled is True
    assert resolve_watchdog_config(env={"ZO_WATCHDOG": "0"}).enabled is False
    project = WatchdogConfig(nudge_budget=5)
    got = resolve_watchdog_config(project, env={"ZO_WATCHDOG_STALL_SEC": "600"})
    assert (got.stall_threshold_sec, got.nudge_budget) == (600, 5)
    assert project.stall_threshold_sec == 1200  # input not mutated
    junk = resolve_watchdog_config(env={"ZO_WATCHDOG_STALL_SEC": "junk"})
    assert junk.stall_threshold_sec == 1200


def test_module_carries_mit_attribution() -> None:
    assert "MIT" in (watchdog.__doc__ or "") and "Yeachan Heo" in (watchdog.__doc__ or "")


def test_public_api_surface_resolves() -> None:
    for name in watchdog.__all__:
        assert getattr(watchdog, name) is not None, name
    assert {"evaluate", "classify_never_block", "is_process_dead", "WatchdogConfig"} <= set(
        watchdog.__all__)
