"""Heartbeat writer for the hook plane (WS-C, plan oracle checks 11-12).

Stamps ``<memory_root>/heartbeats/<agent_key>.json`` on every routed hook
event so the wrapper-side watchdog (``zo.watchdog`` / ``zo._wrapper_watchdog``)
has per-agent liveness evidence.

Design constraints (see specs/watchdog.md):

* **stdlib-only** — this path runs on every ``PostToolUse``; it must never
  pay the pydantic import. The JSON body mirrors ``zo.watchdog.HeartbeatRecord``
  field-for-field (a test validates the shape; it is never imported here).
* **advisory / fail-open** — no error escapes to the session; a missing or
  unwritable memory root simply means no heartbeat.
* **never creates a memory root** — heartbeats are evidence, not scaffolding.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "HEARTBEATS_DIRNAME",
    "HEARTBEAT_STATUS_BY_EVENT",
    "agent_identity",
    "stamp_heartbeat",
]

HEARTBEATS_DIRNAME = "heartbeats"
HEARTBEAT_SCHEMA_VERSION = 1
HEARTBEAT_DEBOUNCE_SEC = 2.0
# hook_event_name → zo.watchdog.HeartbeatStatus value (kept as literals on
# purpose: the heartbeat path must not import zo.watchdog/pydantic).
HEARTBEAT_STATUS_BY_EVENT = {
    "PostToolUse": "executing",
    "Stop": "ready",
    "SubagentStop": "shutdown",
    "PreCompact": "compacting",
    "SessionEnd": "shutdown",
}
_AGENT_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def agent_identity(data: dict) -> tuple[str | None, str | None]:
    """Return ``(agent_type, agent_id)`` from a hook payload (None when absent).

    Live SubagentStop / PostToolUseFailure / PostToolUse payloads carry
    ``agent_id`` and ``agent_type``; PreToolUse payloads carry neither.
    Distinct from ``hookkit._agent_name`` (contract lookup key) on purpose.
    """
    def _pick(*keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    return _pick("agent_type", "subagent_type"), _pick("agent_id")


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() else None


def _read_json_dict(path: Path) -> dict:
    """Best-effort JSON object read; ``{}`` on any error (fail-open)."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _atomic_write_json(path: Path, record: dict) -> None:
    """Write ``record`` via tmp + ``os.replace`` (no partial file is ever visible)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _heartbeat_record(data: dict, *, agent_key: str, tick_count: int) -> dict:
    """Build the JSON body — field set mirrors ``zo.watchdog.HeartbeatRecord``."""
    agent_type, agent_id = agent_identity(data)
    event = str(data.get("hook_event_name") or "PostToolUse")
    last_event = data.get("tool_name") if event == "PostToolUse" else event
    return {
        "schema_version": HEARTBEAT_SCHEMA_VERSION,
        "agent_key": agent_key,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "session_id": str(data.get("session_id") or "unknown"),
        "zo_session_id": os.environ.get("ZO_SESSION_ID") or None,
        "pid": _env_int("ZO_LEAD_PID"),
        "process_start_identity": os.environ.get("ZO_LEAD_PID_IDENTITY") or None,
        "last_tick_at": datetime.now(UTC).isoformat(),
        "status": HEARTBEAT_STATUS_BY_EVENT.get(event, "executing"),
        "last_event": str(last_event or event),
        "tick_count": tick_count,
    }


def stamp_heartbeat(data: dict, *, memory_root: Path) -> None:
    """Stamp ``<memory_root>/heartbeats/<agent_key>.json`` (advisory, fail-open).

    ``agent_key`` is ``agent_id`` when present else ``lead-<session_id>``,
    sanitised for the filesystem (the record's ``agent_key`` field equals the
    filename stem). PostToolUse writes are debounced to one per
    ``HEARTBEAT_DEBOUNCE_SEC``; other events always stamp and ``tick_count``
    is monotonic across stamps.

    Args:
        data: The hook payload (already parsed JSON dict).
        memory_root: Existing per-project memory root; the caller resolves
            it and skips the stamp when it is unknown or not a directory.
    """
    session_id = str(data.get("session_id") or "unknown")
    _agent_type, agent_id = agent_identity(data)
    agent_key = _AGENT_KEY_UNSAFE.sub("_", agent_id or f"lead-{session_id}")
    path = memory_root / HEARTBEATS_DIRNAME / f"{agent_key}.json"
    event = str(data.get("hook_event_name") or "PostToolUse")
    try:
        with contextlib.suppress(OSError):
            age = datetime.now(UTC).timestamp() - path.stat().st_mtime
            if event == "PostToolUse" and 0 <= age < HEARTBEAT_DEBOUNCE_SEC:
                return
        previous = _read_json_dict(path).get("tick_count", 0)
        valid = isinstance(previous, int) and not isinstance(previous, bool) and previous >= 0
        tick_count = (previous if valid else 0) + 1
        record = _heartbeat_record(data, agent_key=agent_key, tick_count=tick_count)
        _atomic_write_json(path, record)
    except OSError:
        return
