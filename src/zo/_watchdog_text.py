"""Terminal-text classifiers for the watchdog (WS-C, oracle checks 11-12).

Pure functions over captured pane / stdout text: ANSI normalization,
progress digest, never-block taxonomy, rate-limit reset parsing and the
pane-ready guard. No I/O. Public names are re-exported by ``zo.watchdog``.

Pattern tables ported from oh-my-claudecode (MIT License, Copyright (c) 2025
Yeachan Heo): ``src/hooks/todo-continuation/index.ts`` (context #213, rate
#777, auth #1308, user-abort — bare ``interrupt`` excluded per #2478),
``src/features/rate-limit-wait/tmux-detector.ts`` (rate-limit screen text,
git-output stripping, saved-transcript reject), ``src/team/tmux-session.ts``
(``paneLooksReady`` / ``paneHasActiveTask``). Contract adjustments: no bare
``429`` / ``overloaded``; ``awaiting_input`` category added.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, time, timedelta, tzinfo
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from zo.watchdog import HeartbeatRecord

_TAIL_LINES = 60
_PANE_TAIL_LINES = 40


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _secs(later: datetime, earlier: datetime) -> float:
    return (_aware(later) - _aware(earlier)).total_seconds()


class NeverBlockReason(StrEnum):
    """Conditions under which the watchdog must never nudge."""

    USER_ABORT = "user_abort"
    CONTEXT_LIMIT = "context_limit"
    RATE_LIMIT = "rate_limit"
    AUTH_ERROR = "auth_error"
    AWAITING_INPUT = "awaiting_input"
    COMPACTING = "compacting"


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns)


_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
GIT_OUTPUT_LINE_PATTERNS = _rx(
    r"^(commit [0-9a-f]{7,}|Author:|Date:|Merge: [0-9a-f]{6,}|diff --git|index [0-9a-f]+\.\."
    r"|@@ |[-+]{3} [ab]/)",
)
_SAVED_TRANSCRIPT_CMD = re.compile(
    r"^\s*(?:[$#%]|❯)?\s*(?:cat|bat|less|more|tail|head|sed|awk)\b.*"
    r"(?:hud|transcript|terminal|output|copied|\.txt)\b", re.IGNORECASE,
)
_IDLE_PROMPT = re.compile(r"^\s*(?:[│┃║▌▐▏▕╎┆┊]\s*)?[›>❯]\s*")
_IDLE_PROMPT_LINE = re.compile(r"^\s*(?:[│┃║▌▐▏▕╎┆┊]\s*)?[›>❯]\s*$")
_VOLATILE = _rx(
    r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏·✻✽✶✳✢]", r"esc to interrupt", r"\(\d+[smh]\b.*?\)",
    r"\b\d+\s*tokens?\b", r"\b\d+[smh]\s+elapsed\b", r"\? for shortcuts",
)
_ACTIVE_TASK = _rx(
    r"esc to interrupt", r"background terminal running",
    r"^[·✻]\s+[A-Za-z][A-Za-z0-9''-]*(?:\s+[A-Za-z][A-Za-z0-9''-]*){0,3}(?:…|\.{3})$",
)

# Rate-limit vocabulary in three tiers (same table as the contract, split so
# that exit classification can demand corroboration and prose cannot pause):
#   banner — unambiguous platform/API banners; sufficient alone, and enough
#            to classify a session exit as RATE_LIMITED;
#   prose  — "rate limit" in running text; enough to pause (never nudge)
#            but not, on its own, to classify an exit;
#   loose  — generic phrases ("limit reached", "try again later", "hit … limit",
#            "resets … at", "5-hour") that only count when the SAME line also
#            carries rate/usage/quota vocabulary — "patience limit reached at
#            epoch 30" and "the 5-hour window in the plan" are not banners.
RATE_LIMIT_BANNER_PATTERNS = _rx(
    r"usage limit", r"quota exceeded", r"too many requests", r"hit your limit",
    r"\bweekly\s+(?:usage\s+)?(?:limit|quota|cap|allowance|allocation)\b",
    r"you(?:'|’)ve\s+(?:hit|reached)\s+(?:your\s+)?(?:session\s+|usage\s+)?limit",
    r"\blimit\s+resets?\b", r"stop\s+and\s+wait\s+for\s+limit\s+to\s+reset",
    r"\b429\b(?!\d)(?=.*(?:rate|limit|request))", r"rate_limit(?:ed|_error)?",
    r"too_many_requests", r"quota_(?:exceeded|limit|exhausted)",
)
RATE_LIMIT_PROSE_PATTERNS = _rx(r"rate limit")
RATE_LIMIT_LOOSE_PATTERNS = _rx(
    r"try again later", r"limit reached", r"hit .+ limit", r"resets? .+ at", r"5[- ]?hour",
)
_RATE_LIMIT_CONTEXT = re.compile(r"usage|rate|quota|requests?|session limit|\bapi\b", re.I)
RATE_LIMIT_TEXT_PATTERNS = (
    RATE_LIMIT_BANNER_PATTERNS + RATE_LIMIT_PROSE_PATTERNS + RATE_LIMIT_LOOSE_PATTERNS
)
CONTEXT_LIMIT_PATTERNS = _rx(
    r"\b(?:context_limit|context_window|context_exceeded|context_full|max_context|token_limit"
    r"|max_tokens|conversation_too_long|input_too_long)\b",
    r"context (?:window )?(?:is )?(?:full|low|exceeded)", r"prompt is too long",
    r"compact(?:ing)? (?:the )?conversation",
)
AUTH_ERROR_PATTERNS = _rx(
    r"\b(?:authentication_error|authentication_failed|auth_error|unauthorized|unauthorised"
    r"|forbidden|invalid_token|token_invalid|token_expired|expired_token|oauth_expired"
    r"|oauth_token_expired|invalid_grant|insufficient_scope)\b",
    r"\b40[13]\b(?=.*(?:unauthori[sz]ed|forbidden|auth))",
    r"\bplease (?:run )?/login\b", r"\bnot logged in\b", r"\binvalid api key\b",
)
# "Interrupted by user" / "Interrupted · What should Claude do instead?" are
# rendered by the Claude Code TUI behind a ``⎿`` connector, so the anchor
# tolerates any leading non-word prefix; bare "interrupt" stays excluded.
USER_ABORT_PATTERNS = _rx(
    r"(?<!esc to )\b(?:aborted|abort|cancel)\b", r"user_cancel", r"user_interrupt", r"ctrl_c",
    r"manual_stop",
    r"^\W*interrupted(?:\s+by\s+user\b|\W+what\s+should\s+claude\s+do\s+instead)",
)
# Menu items are anchored to a selection cursor / line start so that ordinary
# numbered lists ("1. Read the file") and indexing ("arr[0]") in Claude's
# output do not read as a dialog (that would silently disable nudging).
AWAITING_INPUT_PATTERNS = _rx(
    r"do you want to (?:proceed|allow|continue)", r"^\s*❯\s*\d+\.\s", r"^\s*\[\d+\]\s",
    r"esc to cancel", r"yes,? (?:and )?(?:don't|do not) ask again", r"allow (?:once|always)",
    r"press enter", r"enter to confirm", r"select an option", r"choice:",
    r"waiting for (?:your )?(?:input|response|approval)",
    r"trust (?:this|the) (?:folder|workspace)",
)


def _any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def rate_limit_match(text: str) -> str | None:
    """Tier of the strongest rate-limit evidence in ``text``: ``"banner"`` |
    ``"prose"`` | ``"loose"`` | ``None`` (loose needs same-line context)."""
    if _any(RATE_LIMIT_BANNER_PATTERNS, text):
        return "banner"
    if _any(RATE_LIMIT_PROSE_PATTERNS, text):
        return "prose"
    for line in text.split("\n"):
        if _any(RATE_LIMIT_LOOSE_PATTERNS, line) and _RATE_LIMIT_CONTEXT.search(line):
            return "loose"
    return None


def rate_limit_banner_key(text: str) -> str:
    """The rate-limit evidence lines of the tail, joined — identifies *which*
    banner is on screen so an unchanged (stale) banner is told apart from a
    freshly printed one and from one that has already been resolved."""
    lines = _tail_lines(text, _TAIL_LINES)
    hits = [ln for ln in lines if rate_limit_match(ln) is not None]
    return "\n".join(hits)


_TEXT_TAXONOMY: tuple[tuple[NeverBlockReason, Callable[[str], bool]], ...] = (
    (NeverBlockReason.USER_ABORT, lambda t: _any(USER_ABORT_PATTERNS, t)),
    (NeverBlockReason.CONTEXT_LIMIT, lambda t: _any(CONTEXT_LIMIT_PATTERNS, t)),
    (NeverBlockReason.RATE_LIMIT, lambda t: rate_limit_match(t) is not None),
    (NeverBlockReason.AUTH_ERROR, lambda t: _any(AUTH_ERROR_PATTERNS, t)),
    (NeverBlockReason.AWAITING_INPUT, lambda t: _any(AWAITING_INPUT_PATTERNS, t)),
)


def normalize_terminal_text(text: str) -> str:
    """Strip ANSI/CR; drop git-output lines and saved-transcript command lines."""
    clean = _ANSI.sub("", text or "").replace("\r", "")
    kept = [
        line for line in clean.split("\n")
        if not any(p.match(line.lstrip()) for p in GIT_OUTPUT_LINE_PATTERNS)
        and not _SAVED_TRANSCRIPT_CMD.match(line)
    ]
    return "\n".join(kept)


def _tail_lines(text: str, count: int) -> list[str]:
    lines = [ln.rstrip() for ln in normalize_terminal_text(text).split("\n") if ln.strip()]
    return lines[-count:]


def progress_digest(text: str) -> str:
    """sha1 of the normalized text with volatile UI churn (spinners, counters) removed."""
    stable: list[str] = []
    for line in normalize_terminal_text(text).split("\n"):
        for pattern in _VOLATILE:
            line = pattern.sub("", line)
        if line.strip() and not _IDLE_PROMPT_LINE.match(line):
            stable.append(line.strip())
    return hashlib.sha1("\n".join(stable).encode("utf-8")).hexdigest()


def _any_compacting(heartbeats: Sequence[HeartbeatRecord], now: datetime, window: float) -> bool:
    return any(
        str(hb.status) == "compacting" and 0 <= _secs(now, hb.last_tick_at) <= window
        for hb in heartbeats
    )


def classify_never_block(
    text: str, *, is_interrupt: bool | None = None,
    heartbeats: Sequence[HeartbeatRecord] = (), now: datetime | None = None,
    compacting_window_sec: float = 300.0,
) -> NeverBlockReason | None:
    """Precedence: interrupt → USER_ABORT; then text (last 60 lines) USER_ABORT >
    CONTEXT_LIMIT > RATE_LIMIT > AUTH_ERROR > AWAITING_INPUT; then COMPACTING."""
    if is_interrupt:
        return NeverBlockReason.USER_ABORT
    tail = "\n".join(_tail_lines(text, _TAIL_LINES))
    for reason, matches in _TEXT_TAXONOMY:
        if matches(tail):
            return reason
    if heartbeats and _any_compacting(heartbeats, now or datetime.now(UTC), compacting_window_sec):
        return NeverBlockReason.COMPACTING
    return None


# --------------------------------------------------- rate-limit reset parsing

_RESET_IN = re.compile(
    r"(?:resets?|try again|retry)\s+in\s+(\d+)\s*(second|sec|s|minute|min|m|hour|hr|h)s?\b", re.I)
_RETRY_AFTER = re.compile(r"retry[- ]after[: ]+(\d+)", re.I)
_RESET_AT = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
_ISO_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?")
_RESET_VOCAB = re.compile(r"reset|retry|limit|again", re.I)
_UNIT_SEC = {"s": 1, "sec": 1, "second": 1, "m": 60, "min": 60, "minute": 60,
             "h": 3600, "hr": 3600, "hour": 3600}


def _clock_time(match: re.Match[str], now: datetime, local: tzinfo) -> datetime | None:
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    ampm = (match.group(3) or "").lower()
    if not ampm and match.group(2) is None:
        return None  # "resets 3" is not a clock time
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    local_now = _aware(now).astimezone(local)
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=local)
    return candidate if candidate > local_now else candidate + timedelta(days=1)


def _iso_reset(text: str, now: datetime, local: tzinfo) -> datetime | None:
    for line in text.split("\n"):
        if not _RESET_VOCAB.search(line):
            continue
        for match in _ISO_TS.finditer(line):
            try:
                stamp = datetime.fromisoformat(match.group(0).replace("Z", "+00:00"))
            except ValueError:
                continue
            stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=local)
            if stamp > _aware(now):
                return stamp
    return None


def parse_rate_limit_reset(
    text: str, *, now: datetime, tz: tzinfo | None = None,
) -> datetime | None:
    """Reset time from banner text ("resets at 3pm", "try again in 5 minutes",
    "retry-after: 90", ISO-8601 on a reset/limit line); ``None`` if absent.

    Clock times are interpreted in ``tz`` (else ``now.tzinfo``) — Claude Code
    prints the reset in the operator's LOCAL time, so runtime callers must
    pass the local zone. Within a tier the LAST occurrence wins: transcripts
    grow downward, so the newest banner is the authoritative one.
    """
    local = tz or _aware(now).tzinfo or UTC
    clean = normalize_terminal_text(text)
    if hits := list(_RESET_IN.finditer(clean)):
        m = hits[-1]
        return _aware(now) + timedelta(seconds=int(m.group(1)) * _UNIT_SEC[m.group(2).lower()])
    if hits := list(_RETRY_AFTER.finditer(clean)):
        return _aware(now) + timedelta(seconds=int(hits[-1].group(1)))
    stamps = [_clock_time(m, now, local) for m in _RESET_AT.finditer(clean)]
    if any(stamps):
        return [s for s in stamps if s is not None][-1]
    return _iso_reset(clean, now, local)


def pane_ready_for_nudge(text: str) -> bool:
    """Idle prompt visible AND no active task AND no awaiting-input dialog (last 40 lines)."""
    lines = _tail_lines(text, _PANE_TAIL_LINES)
    if not lines:
        return False
    ready = any(_IDLE_PROMPT.match(ln) for ln in lines[-5:])
    tail = "\n".join(lines)
    active = any(p.search(tail) for p in _ACTIVE_TASK)
    awaiting = any(p.search(tail) for p in AWAITING_INPUT_PATTERNS)
    return ready and not active and not awaiting

