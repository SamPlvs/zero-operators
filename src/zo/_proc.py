"""Process identity helpers for the watchdog (WS-C, oracle checks 11-12).

A pid alone is not proof of anything: pids are recycled. We pair a pid with a
platform-tagged *start identity* (``linux:<starttime ticks>``,
``darwin:<epoch>:<usec>``) so a recycled pid is detected as death, while an
unknown/malformed identity is never treated as positive proof of death.

Ported from oh-my-claudecode ``src/team/team-owner-epoch.ts`` (MIT License,
Copyright (c) 2025 Yeachan Heo) with the ``ps -o lstart=`` darwin fallback
only (no ``sysctl kern.proc.pid`` binary parsing); stdlib only, no psutil.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "identities_may_match",
    "is_process_dead",
    "is_valid_process_start_identity",
    "parse_linux_stat_starttime",
    "parse_ps_time",
    "pid_alive",
    "process_start_identity",
    "process_tree_cpu_seconds",
]

_MAX_IDENTITY_LEN = 1024
_LINUX_ID = re.compile(r"^linux:[1-9]\d*$")
_DARWIN_ID = re.compile(r"^darwin:([1-9]\d*):(\d+)$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_PS_LSTART_FORMAT = "%a %b %d %H:%M:%S %Y"


def _platform(platform: str | None) -> str:
    return platform or sys.platform


def pid_alive(pid: int) -> bool:
    """Signal-0 liveness: ESRCH → False; EPERM → True (alive, not ours)."""
    if not isinstance(pid, int) or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def parse_linux_stat_starttime(stat_text: str) -> str | None:
    """Return field 22 (``starttime``) of a ``/proc/<pid>/stat`` line.

    The command name (field 2) is wrapped in parentheses and may itself
    contain spaces or ``)``, so parsing splits after the LAST ``)``.
    """
    close = stat_text.rfind(")")
    if close < 0:
        return None
    fields = stat_text[close + 1:].split()
    # fields[0] is state (field 3); starttime is field 22 → index 19.
    if len(fields) < 20 or not fields[19].isdigit():
        return None
    return fields[19]


def _read_proc_stat(pid: int) -> str:
    with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
        return fh.read()


def _ps_lstart(pid: int, run: Callable) -> str:
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    result = run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True, text=True, env=env, timeout=5,
    )
    stdout = getattr(result, "stdout", "") or ""
    return stdout.strip()


def process_start_identity(
    pid: int, *, platform: str | None = None, run: Callable = subprocess.run,
) -> str | None:
    """Platform-tagged process start identity, or ``None`` on any failure.

    linux: ``linux:<starttime>`` from ``/proc/<pid>/stat``;
    darwin: ``darwin:<epoch_seconds>:0`` from ``ps -o lstart=`` (LC_ALL=C);
    other: ``<platform>:<raw ps lstart>``.
    """
    if not isinstance(pid, int) or pid < 1:
        return None
    plat = _platform(platform)
    try:
        if plat.startswith("linux"):
            ticks = parse_linux_stat_starttime(_read_proc_stat(pid))
            return f"linux:{ticks}" if ticks else None
        started = _ps_lstart(pid, run)
        if not started:
            return None
        if plat == "darwin":
            epoch = int(datetime.strptime(started, _PS_LSTART_FORMAT).timestamp())
            return f"darwin:{epoch}:0"
        return f"{plat}:{started}"
    except Exception:  # identity is best-effort and never raises
        return None


def is_valid_process_start_identity(value: object, *, platform: str | None = None) -> bool:
    """Regex allowlist for identities (≤ 1024 chars, platform-tagged)."""
    if not isinstance(value, str) or not value or len(value) > _MAX_IDENTITY_LEN:
        return False
    plat = _platform(platform)
    if plat.startswith("linux"):
        return _LINUX_ID.match(value) is not None
    if plat == "darwin":
        match = _DARWIN_ID.match(value)
        return match is not None and int(match.group(2)) < 1_000_000
    sep = value.find(":")
    if sep <= 0 or value[:sep] != plat:
        return False
    rest = value[sep + 1:]
    return bool(rest) and _CONTROL_CHARS.search(rest) is None


def identities_may_match(recorded: str, observed: str) -> bool:
    """Equal, or darwin same-second where either usec component is the ``0`` wildcard."""
    if recorded == observed:
        return True
    rec = _DARWIN_ID.match(recorded or "")
    obs = _DARWIN_ID.match(observed or "")
    return (
        rec is not None and obs is not None
        and rec.group(1) == obs.group(1)
        and (rec.group(2) == "0" or obs.group(2) == "0")
    )


def parse_ps_time(value: str) -> float | None:
    """Seconds from a ``ps -o time=`` field: ``[[dd-]hh:]mm:ss[.cc]``; ``None`` if malformed."""
    text = (value or "").strip()
    if not text:
        return None
    days = 0
    if "-" in text:
        day_part, text = text.split("-", 1)
        if not day_part.isdigit():
            return None
        days = int(day_part)
    parts = text.split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        secs = float(parts[-1])
        for unit, part in zip((60, 3600), reversed(parts[:-1]), strict=False):
            secs += int(part) * unit
    except ValueError:
        return None
    return days * 86400 + secs


def _ps_table(run: Callable) -> str:
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    result = run(
        ["ps", "-A", "-o", "pid=,ppid=,time="],
        capture_output=True, text=True, env=env, timeout=5,
    )
    return getattr(result, "stdout", "") or ""


def process_tree_cpu_seconds(pid: int, *, run: Callable = subprocess.run) -> float | None:
    """Cumulative CPU seconds of ``pid`` and all its descendants (``ps -A``); ``None`` on failure.

    A positive-activity signal for the watchdog: a lead whose process tree
    keeps burning CPU (a long silent training run inside one tool call) is
    not stalled even when heartbeats and text are silent. Never raises.
    """
    if not isinstance(pid, int) or pid < 1:
        return None
    try:
        children: dict[int, list[int]] = {}
        cpu: dict[int, float] = {}
        for line in _ps_table(run).splitlines():
            fields = line.split()
            if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
                continue
            secs = parse_ps_time(fields[2])
            if secs is None:
                continue
            cpu[int(fields[0])] = secs
            children.setdefault(int(fields[1]), []).append(int(fields[0]))
        if pid not in cpu:
            return None
        total, stack, seen = 0.0, [pid], set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            total += cpu.get(current, 0.0)
            stack.extend(children.get(current, ()))
        return total
    except Exception:  # advisory evidence: never raises
        return None


def is_process_dead(
    pid: int | None, recorded_identity: str | None, *,
    platform: str | None = None, run: Callable = subprocess.run,
) -> bool:
    """POSITIVE PROOF ONLY: ``True`` iff the pid is gone or provably recycled.

    ``pid`` None → False; ESRCH → True; alive + valid recorded identity +
    valid observed identity that cannot match → True; anything unknown,
    malformed, or EPERM → False.
    """
    if pid is None or not isinstance(pid, int) or pid < 1:
        return False
    if not pid_alive(pid):
        return True
    if not is_valid_process_start_identity(recorded_identity, platform=platform):
        return False
    observed = process_start_identity(pid, platform=platform, run=run)
    if not is_valid_process_start_identity(observed, platform=platform):
        return False
    return not identities_may_match(str(recorded_identity), str(observed))
