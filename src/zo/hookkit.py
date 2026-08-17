"""Hook-event handlers for the v2 enforcement plane (WS-A).

Invoked by thin bash shims in ``.claude/hooks/`` as::

    python3 -m zo.hookkit <event> < hook-input.json

Events:
    subagent-stop      validate agent deliverables against contracts.json
    drift-guard        block Stop when completion claims meet stub markers
    precompact         flush a STATE.md checkpoint before compaction
    session-end        ensure a session summary exists for today
    post-tool-failure  append a structured failure record (JSONL feed)
    sealed-paths       deny Write/Edit into sealed or off-limits paths

Every handler is fail-open: infrastructure problems (missing files,
unparseable stdin, unknown agent) exit 0 with no output. Only genuine
violations produce blocking JSON on stdout. This mirrors the existing
``.claude/hooks/*.sh`` convention — the enforcement plane must never
brick a session.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from zo.contracts import CONTRACTS_FILENAME, load_contracts, validate_agent_stop

__all__ = ["main"]

_COMPLETION_CLAIM = re.compile(
    r"\b(all (?:tests|checks) pass(?:ing|ed)?|fully (?:implemented|working)"
    r"|implementation (?:is )?complete|task (?:is )?complete[d]?"
    r"|everything (?:is )?(?:done|working)|finished implementing)\b",
    re.IGNORECASE,
)
_STUB_MARKER = re.compile(
    r"^\+.*(\bTODO\b|\bFIXME\b|\bXXX\b|NotImplementedError|raise NotImplemented\b)"
)
_SEALED_DEFAULTS = (
    "gate_mode", "gate_nonce", "gate_decision", CONTRACTS_FILENAME,
    "plan-ledger.json", "sealed_paths",
)


def _read_stdin_json() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        return {}


def _repo_root() -> Path:
    return Path(os.environ.get("ZO_REPO_ROOT", os.getcwd()))


def _memory_root(repo_root: Path) -> Path | None:
    env = os.environ.get("ZO_MEMORY_ROOT")
    if env:
        return Path(env)
    default = repo_root / "memory" / "zo-platform"
    return default if default.is_dir() else None


_emitted = False


def _emit(payload: dict) -> None:
    global _emitted
    _emitted = True
    sys.stdout.write(json.dumps(payload))


def _trace(event: str, data: dict) -> None:
    """Append one observability line per hook invocation (fail-open).

    Written to ``logs/hook-trace-{date}.jsonl`` under the repo root
    (gitignored). This is how we verify the enforcement plane actually
    fires in live sessions — the handlers themselves are silent unless
    they block. Records which stdin keys the live payload carried
    (answers the agent-identity question) but never payload values.
    Disable with ``ZO_HOOK_TRACE=0``.
    """
    if os.environ.get("ZO_HOOK_TRACE", "1") == "0":
        return
    with contextlib.suppress(OSError):
        trace_dir = _repo_root() / "logs"
        trace_dir.mkdir(parents=True, exist_ok=True)
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        line = json.dumps({
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "stdin_keys": sorted(data.keys()),
            "agent_identity": _agent_name(data),
            "session_id": data.get("session_id", ""),
            "emitted_output": _emitted,
        })
        with (trace_dir / f"hook-trace-{date}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# -- subagent-stop ------------------------------------------------------------


def _agent_name(data: dict) -> str | None:
    for key in ("agent_name", "agent_type", "subagent_type", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _handle_subagent_stop(data: dict) -> None:
    if data.get("stop_hook_active"):
        return
    agent = _agent_name(data)
    if agent is None:
        return
    repo_root = _repo_root()
    contracts_env = os.environ.get("ZO_CONTRACTS_PATH")
    if contracts_env:
        contracts_path = Path(contracts_env)
    else:
        memory_root = _memory_root(repo_root)
        if memory_root is None:
            return
        contracts_path = memory_root / CONTRACTS_FILENAME
    delivery_root = Path(os.environ.get("ZO_DELIVERY_ROOT", str(repo_root)))
    violations = validate_agent_stop(contracts_path, agent, delivery_root)
    if not violations:
        return
    lines = [f"- {v.path}: {v.problem}" for v in violations]
    reason = (
        f"Contract violation — agent '{agent}' (phase "
        f"{violations[0].phase_id}) has unmet deliverables:\n"
        + "\n".join(lines)
        + "\nProduce the missing deliverables before stopping, or report a "
        "blocker to the orchestrator."
    )
    _emit({"decision": "block", "reason": reason, "stopReason": reason})


# -- drift-guard ----------------------------------------------------------


def _last_assistant_text(transcript_path: str) -> str:
    text_parts: list[str] = []
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") or {}
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            text_parts.extend(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        break
    return "\n".join(text_parts)


def _added_stub_lines(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "HEAD", "--unified=0"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    if result.returncode != 0:
        return []
    return [
        line for line in result.stdout.splitlines()
        if _STUB_MARKER.search(line) and not line.startswith("+++")
    ]


def _handle_drift_guard(data: dict) -> None:
    if os.environ.get("ZO_DRIFT_GUARD", "1") == "0" or data.get("stop_hook_active"):
        return
    # Live Stop payloads carry the last message directly (verified in the
    # 2026-08-12 live-session trace); fall back to transcript parsing for
    # older payload shapes.
    last_message = data.get("last_assistant_message")
    if not isinstance(last_message, str) or not last_message:
        transcript = data.get("transcript_path")
        if not isinstance(transcript, str):
            return
        last_message = _last_assistant_text(transcript)
    if not last_message or _COMPLETION_CLAIM.search(last_message) is None:
        return
    stubs = _added_stub_lines(_repo_root())
    if not stubs:
        return
    preview = "\n".join(stubs[:5])
    reason = (
        "Workflow drift guard: the last message claims completion, but the "
        f"working tree adds stub/TODO markers:\n{preview}\n"
        "Finish the stubbed work or revise the completion claim before stopping."
    )
    _emit({"decision": "block", "reason": reason, "stopReason": reason})


# -- precompact / session-end ----------------------------------------------


def _memory_manager(memory_root: Path):
    from zo.memory import MemoryManager

    return MemoryManager(
        memory_root.parent.parent, memory_root.name, memory_root=memory_root,
    )


def _handle_precompact(data: dict) -> None:
    repo_root = _repo_root()
    memory_root = _memory_root(repo_root)
    if memory_root is None or not (memory_root / "STATE.md").exists():
        return
    from zo._memory_models import DecisionEntry

    manager = _memory_manager(memory_root)
    try:
        state = manager.read_state()
        state.timestamp = datetime.now(UTC)
        manager.write_state(state)
        manager.append_decision(
            DecisionEntry(
                title="Checkpoint: pre-compaction state flush",
                context=f"session={data.get('session_id', 'unknown')}",
                decision="Flushed STATE.md before context compaction (WS-A3 hook).",
                outcome="checkpointed",
            )
        )
    except Exception:  # noqa: BLE001 — hooks are fail-open by contract
        return


def _handle_session_end(data: dict) -> None:
    repo_root = _repo_root()
    memory_root = _memory_root(repo_root)
    if memory_root is None or not (memory_root / "STATE.md").exists():
        return
    from zo._memory_models import SessionSummary

    manager = _memory_manager(memory_root)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        recent = manager.read_recent_summaries(1)
        if recent and recent[0].date == today:
            return
        manager.write_session_summary(
            SessionSummary(
                accomplished=["(auto-generated at SessionEnd — no summary was written)"],
                next_steps=["Review this session's DECISION_LOG entries"],
                open_questions=[
                    f"session={data.get('session_id', 'unknown')} ended without "
                    "a hand-written summary; hook backfilled this stub"
                ],
            )
        )
    except Exception:  # noqa: BLE001 — hooks are fail-open by contract
        return


# -- post-tool-failure -------------------------------------------------------


def _handle_post_tool_failure(data: dict) -> None:
    repo_root = _repo_root()
    feed_dir = Path(
        os.environ.get("ZO_FAILURE_FEED_DIR", str(repo_root / "logs" / "comms"))
    )
    try:
        feed_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "event_id": str(uuid.uuid4()),
            "event_type": "error",
            "timestamp": datetime.now(UTC).isoformat(),
            "session_id": data.get("session_id", "unknown"),
            "tool_name": data.get("tool_name", "unknown"),
            "error": str(data.get("error", data.get("tool_response", "")))[:2000],
            "input_preview": json.dumps(data.get("tool_input", {}))[:500],
        }
        date = datetime.now(UTC).strftime("%Y-%m-%d")
        path = feed_dir / f"failures-{date}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        return


# -- sealed-paths --------------------------------------------------------------


def _sealed_prefixes(memory_root: Path | None) -> list[str]:
    prefixes: list[str] = []
    if memory_root is not None:
        prefixes.extend(str(memory_root / name) for name in _SEALED_DEFAULTS)
        sealed_file = memory_root / "sealed_paths"
        with contextlib.suppress(OSError):
            prefixes.extend(
                line.strip()
                for line in sealed_file.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            )
    return prefixes


def _handle_sealed_paths(data: dict) -> None:
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(file_path, str) or not file_path:
        return
    repo_root = _repo_root()
    memory_root = _memory_root(repo_root)
    resolved = str((repo_root / file_path).resolve()) if not os.path.isabs(
        file_path
    ) else str(Path(file_path).resolve())

    deny_reason: str | None = None
    for prefix in _sealed_prefixes(memory_root):
        anchor = prefix if os.path.isabs(prefix) else str((repo_root / prefix).resolve())
        if resolved == anchor or resolved.startswith(anchor.rstrip("/") + "/"):
            deny_reason = (
                f"Sealed path: {file_path} is oracle/control state and may not "
                "be modified by agents (v2 anti-Goodhart rule). Ask the human "
                "operator to change it."
            )
            break

    if deny_reason is None:
        agent = _agent_name(data)
        if agent is not None and memory_root is not None:
            doc = load_contracts(memory_root / CONTRACTS_FILENAME)
            if doc is not None:
                normalized = agent.strip().lower().replace(" ", "-")
                for entry in doc.agents:
                    if entry.agent_name != normalized:
                        continue
                    delivery = Path(os.environ.get("ZO_DELIVERY_ROOT", str(repo_root)))
                    for off in entry.off_limits:
                        anchor = str((delivery / off).resolve())
                        if resolved.startswith(anchor.rstrip("/") + "/"):
                            deny_reason = (
                                f"Contract violation: {entry.agent_name} may not "
                                f"write inside off-limits path '{off}'."
                            )
                            break
                    break

    if deny_reason is not None:
        _emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": deny_reason,
                }
            }
        )


_HANDLERS = {
    "subagent-stop": _handle_subagent_stop,
    "drift-guard": _handle_drift_guard,
    "precompact": _handle_precompact,
    "session-end": _handle_session_end,
    "post-tool-failure": _handle_post_tool_failure,
    "sealed-paths": _handle_sealed_paths,
}


def main(argv: list[str] | None = None) -> int:
    """Dispatch a hook event; always returns 0 (fail-open)."""
    global _emitted
    _emitted = False
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] not in _HANDLERS:
        return 0
    data = _read_stdin_json()
    try:
        _HANDLERS[args[0]](data)
    except Exception:  # noqa: BLE001 — hooks are fail-open by contract
        _trace(args[0], data)
        return 0
    _trace(args[0], data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
