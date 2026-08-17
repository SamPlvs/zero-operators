"""Tests for zo.hookkit — the WS-A enforcement-plane hook handlers.

Each handler gets: (a) a seeded-violation test proving the mechanism
catches a planted problem (plan oracle checks 1-4, 7), and (b) a
fail-open test proving infrastructure problems never block a session.
Handlers are driven through ``main()`` with stdin/stdout patched — the
same interface the bash shim uses.

WS-C (plan oracle checks 11-12) adds the ``heartbeat`` writer: the JSON it
stamps is validated against ``zo.watchdog.HeartbeatRecord`` here (tests may
import pydantic models; the handler itself must not).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zo import hookkit
from zo._orchestrator_models import (
    AgentContract,
    GateType,
    PhaseDefinition,
    WorkflowDecomposition,
)
from zo.contracts import emit_contracts
from zo.watchdog import HeartbeatRecord, HeartbeatStatus


@pytest.fixture(autouse=True)
def _sandbox_roots(tmp_path: Path, monkeypatch) -> None:
    """Never let a handler resolve the real repo/memory root from cwd.

    Handlers fall back to ``os.getcwd()`` (``_repo_root``) and then to
    ``<repo>/memory/zo-platform`` — under pytest that is the live platform
    repo. Individual tests override these when they need specific roots.
    """
    monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path / "_repo"))
    monkeypatch.setenv("ZO_MEMORY_ROOT", str(tmp_path / "_mem"))


def _run(event: str, payload: dict, monkeypatch, capsys) -> dict | None:
    """Invoke a handler as the shim would; return parsed stdout or None."""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert hookkit.main([event]) == 0
    out = capsys.readouterr().out
    return json.loads(out) if out else None


def _emit_demo_contracts(mem: Path) -> Path:
    wf = WorkflowDecomposition(
        mode="classical_ml",
        phases=[
            PhaseDefinition(
                phase_id="phase_1", name="Data Review", description="d",
                gate_type=GateType.BLOCKING,
                required_artifacts=["data/reports/data_quality.md"],
            ),
        ],
        agent_contracts=[
            AgentContract(
                agent_name="data-engineer", phase_id="phase_1",
                role_description="r", ownership=["data/reports/"],
                off_limits=["models/", "oracle/"],
            ),
        ],
    )
    return emit_contracts(wf, mem, "demo", "phase_1")


# ---- subagent-stop (oracle check 1) ----------------------------------------


class TestSubagentStop:
    def test_seeded_missing_deliverable_blocks(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        contracts = _emit_demo_contracts(tmp_path / "mem")
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setenv("ZO_CONTRACTS_PATH", str(contracts))
        monkeypatch.setenv("ZO_DELIVERY_ROOT", str(repo))
        out = _run(
            "subagent-stop", {"agent_name": "data-engineer"}, monkeypatch, capsys,
        )
        assert out is not None
        assert out["decision"] == "block"
        assert "data/reports/data_quality.md" in out["reason"]

    def test_satisfied_contract_is_silent(self, tmp_path: Path, monkeypatch, capsys):
        contracts = _emit_demo_contracts(tmp_path / "mem")
        repo = tmp_path / "repo"
        (repo / "data" / "reports").mkdir(parents=True)
        (repo / "data" / "reports" / "data_quality.md").write_text("# report")
        monkeypatch.setenv("ZO_CONTRACTS_PATH", str(contracts))
        monkeypatch.setenv("ZO_DELIVERY_ROOT", str(repo))
        out = _run(
            "subagent-stop", {"agent_name": "data-engineer"}, monkeypatch, capsys,
        )
        assert out is None

    def test_no_agent_identity_fails_open(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_CONTRACTS_PATH", str(tmp_path / "contracts.json"))
        assert _run("subagent-stop", {}, monkeypatch, capsys) is None

    def test_stop_hook_active_guard(self, tmp_path: Path, monkeypatch, capsys):
        contracts = _emit_demo_contracts(tmp_path / "mem")
        monkeypatch.setenv("ZO_CONTRACTS_PATH", str(contracts))
        monkeypatch.setenv("ZO_DELIVERY_ROOT", str(tmp_path))
        out = _run(
            "subagent-stop",
            {"agent_name": "data-engineer", "stop_hook_active": True},
            monkeypatch, capsys,
        )
        assert out is None


# ---- drift-guard (oracle check 2) -------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True,
    )


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@t")
    (repo / "mod.py").write_text("def f():\n    return 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    return repo


def _transcript(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "transcript.jsonl"
    entry = {"message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
    path.write_text(json.dumps(entry) + "\n")
    return path


class TestDriftGuard:
    def test_seeded_claim_plus_stub_blocks(
        self, git_repo: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        (git_repo / "mod.py").write_text(
            "def f():\n    # TODO: actually implement\n    return 1\n"
        )
        transcript = _transcript(tmp_path, "All tests pass and the task is complete.")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        out = _run(
            "drift-guard", {"transcript_path": str(transcript)}, monkeypatch, capsys,
        )
        assert out is not None
        assert out["decision"] == "block"
        assert "TODO" in out["reason"]

    def test_claim_without_stubs_is_silent(
        self, git_repo: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        transcript = _transcript(tmp_path, "All tests pass and the task is complete.")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        out = _run(
            "drift-guard", {"transcript_path": str(transcript)}, monkeypatch, capsys,
        )
        assert out is None

    def test_stubs_without_claim_is_silent(
        self, git_repo: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        (git_repo / "mod.py").write_text("def f():\n    # TODO: later\n    return 1\n")
        transcript = _transcript(tmp_path, "Progress update: still working on f().")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        out = _run(
            "drift-guard", {"transcript_path": str(transcript)}, monkeypatch, capsys,
        )
        assert out is None

    def test_env_kill_switch(self, git_repo: Path, tmp_path: Path, monkeypatch, capsys):
        (git_repo / "mod.py").write_text("def f():\n    # TODO\n    return 1\n")
        transcript = _transcript(tmp_path, "Everything is done.")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        monkeypatch.setenv("ZO_DRIFT_GUARD", "0")
        out = _run(
            "drift-guard", {"transcript_path": str(transcript)}, monkeypatch, capsys,
        )
        assert out is None


# ---- precompact / session-end (oracle check 3) -------------------------------


@pytest.fixture()
def memory_root(tmp_path: Path) -> Path:
    from zo._memory_models import SessionState
    from zo.memory import MemoryManager

    mem = tmp_path / "memory" / "demo"
    manager = MemoryManager(tmp_path, "demo", memory_root=mem)
    manager.initialize_project()
    manager.write_state(SessionState(phase="phase_1"))
    return mem


class TestPrecompact:
    def test_flushes_checkpoint_and_logs_decision(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        from zo.memory import MemoryManager

        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        before = MemoryManager(tmp_path, "demo", memory_root=memory_root).read_state()
        out = _run("precompact", {"session_id": "s-1"}, monkeypatch, capsys)
        assert out is None
        manager = MemoryManager(tmp_path, "demo", memory_root=memory_root)
        after = manager.read_state()
        assert after.timestamp >= before.timestamp
        decisions = manager.read_decisions()
        assert any("pre-compaction" in d.title.lower() for d in decisions)

    def test_missing_state_fails_open(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(tmp_path / "nowhere"))
        assert _run("precompact", {}, monkeypatch, capsys) is None


class TestSessionEnd:
    def test_backfills_missing_summary(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        _run("session-end", {"session_id": "s-2"}, monkeypatch, capsys)
        summaries = list((memory_root / "sessions").glob("*.md"))
        assert len(summaries) == 1
        assert "auto-generated" in summaries[0].read_text()

    def test_existing_summary_today_not_duplicated(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        _run("session-end", {}, monkeypatch, capsys)
        _run("session-end", {}, monkeypatch, capsys)
        assert len(list((memory_root / "sessions").glob("*.md"))) == 1


# ---- post-tool-failure (oracle check 4) --------------------------------------


class TestPostToolFailure:
    def test_appends_structured_jsonl(self, tmp_path: Path, monkeypatch, capsys):
        feed = tmp_path / "feed"
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(feed))
        payload = {
            "session_id": "s-3", "tool_name": "Bash",
            "tool_input": {"command": "pytest"}, "error": "exit 1: boom",
        }
        _run("post-tool-failure", payload, monkeypatch, capsys)
        files = list(feed.glob("failures-*.jsonl"))
        assert len(files) == 1
        record = json.loads(files[0].read_text().splitlines()[0])
        assert record["tool_name"] == "Bash"
        assert record["event_type"] == "error"
        assert record["event_id"]
        assert "boom" in record["error"]

    def test_two_failures_two_lines(self, tmp_path: Path, monkeypatch, capsys):
        feed = tmp_path / "feed"
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(feed))
        _run("post-tool-failure", {"tool_name": "A", "error": "x"}, monkeypatch, capsys)
        _run("post-tool-failure", {"tool_name": "B", "error": "y"}, monkeypatch, capsys)
        lines = list(feed.glob("failures-*.jsonl"))[0].read_text().splitlines()
        assert len(lines) == 2

    def test_record_carries_is_interrupt_and_identity(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        """WS-C: user-abort evidence (``is_interrupt``) + agent identity are
        kept on the failure record — the live payload carries all three."""
        feed = tmp_path / "feed"
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(feed))
        payload = {
            "session_id": "s-4", "tool_name": "Bash", "error": "interrupted",
            "is_interrupt": True, "agent_id": "agent-7", "agent_type": "model-builder",
        }
        _run("post-tool-failure", payload, monkeypatch, capsys)
        record = json.loads(next(feed.glob("failures-*.jsonl")).read_text().splitlines()[0])
        assert record["is_interrupt"] is True
        assert record["agent_id"] == "agent-7"
        assert record["agent_type"] == "model-builder"
        # existing fields untouched
        assert record["event_type"] == "error" and record["tool_name"] == "Bash"

    def test_record_identity_fields_default_none(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        feed = tmp_path / "feed"
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(feed))
        _run("post-tool-failure", {"tool_name": "A", "error": "x"}, monkeypatch, capsys)
        record = json.loads(next(feed.glob("failures-*.jsonl")).read_text().splitlines()[0])
        assert record["is_interrupt"] is None
        assert record["agent_id"] is None and record["agent_type"] is None


# ---- sealed-paths (oracle check 7) -------------------------------------------


class TestSealedPaths:
    def test_seeded_write_to_sealed_control_file_denied(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        out = _run(
            "sealed-paths",
            {"tool_input": {"file_path": str(memory_root / "gate_mode")}},
            monkeypatch, capsys,
        )
        assert out is not None
        decision = out["hookSpecificOutput"]["permissionDecision"]
        assert decision == "deny"

    def test_seeded_write_to_user_sealed_prefix_denied(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        (memory_root / "sealed_paths").write_text("oracle/\n")
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        out = _run(
            "sealed-paths",
            {"tool_input": {"file_path": "oracle/eval.py"}},
            monkeypatch, capsys,
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_off_limits_write_denied_for_contracted_agent(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        _emit_demo_contracts(memory_root)
        delivery = tmp_path / "delivery"
        delivery.mkdir()
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        monkeypatch.setenv("ZO_DELIVERY_ROOT", str(delivery))
        out = _run(
            "sealed-paths",
            {
                "agent_name": "data-engineer",
                "tool_input": {"file_path": str(delivery / "models" / "net.py")},
            },
            monkeypatch, capsys,
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "off-limits" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_seeded_write_into_heartbeats_denied(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        """WS-C: agents must not forge liveness — the whole heartbeats
        subtree is sealed (prefix match), not just a single file."""
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        for target in ("heartbeats/x.json", "heartbeats/nested/agent-1.json"):
            out = _run(
                "sealed-paths",
                {"tool_input": {"file_path": str(memory_root / target)}},
                monkeypatch, capsys,
            )
            assert out is not None, target
            assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert "Sealed path" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_ordinary_write_is_silent(
        self, tmp_path: Path, memory_root: Path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(memory_root))
        out = _run(
            "sealed-paths",
            {"tool_input": {"file_path": "src/anything.py"}},
            monkeypatch, capsys,
        )
        assert out is None

    def test_no_file_path_fails_open(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        assert _run("sealed-paths", {"tool_input": {}}, monkeypatch, capsys) is None


# ---- dispatcher ---------------------------------------------------------------


class TestDispatcher:
    def test_unknown_event_is_noop(self, monkeypatch, capsys):
        assert hookkit.main(["not-an-event"]) == 0
        assert capsys.readouterr().out == ""

    def test_no_args_is_noop(self):
        assert hookkit.main([]) == 0

    def test_handler_exception_fails_open(self, monkeypatch, capsys):
        monkeypatch.setitem(
            hookkit._HANDLERS, "explode",
            lambda data: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        assert hookkit.main(["explode"]) == 0


# ---- trace observability -------------------------------------------------


class TestTrace:
    def test_every_invocation_writes_a_trace_line(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(tmp_path / "feed"))
        _run("post-tool-failure", {"tool_name": "Bash", "error": "x"}, monkeypatch, capsys)
        traces = list((tmp_path / "logs").glob("hook-trace-*.jsonl"))
        assert len(traces) == 1
        record = json.loads(traces[0].read_text().splitlines()[0])
        assert record["event"] == "post-tool-failure"
        assert "tool_name" in record["stdin_keys"]

    def test_trace_records_agent_identity_and_block(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        contracts = _emit_demo_contracts(tmp_path / "mem")
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_CONTRACTS_PATH", str(contracts))
        monkeypatch.setenv("ZO_DELIVERY_ROOT", str(repo))
        _run("subagent-stop", {"agent_name": "data-engineer"}, monkeypatch, capsys)
        record = json.loads(
            next((tmp_path / "logs").glob("hook-trace-*.jsonl")).read_text().splitlines()[0]
        )
        assert record["agent_identity"] == "data-engineer"
        assert record["emitted_output"] is True

    def test_trace_disabled_by_env(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_HOOK_TRACE", "0")
        monkeypatch.setenv("ZO_FAILURE_FEED_DIR", str(tmp_path / "feed"))
        _run("post-tool-failure", {"tool_name": "Bash", "error": "x"}, monkeypatch, capsys)
        assert not (tmp_path / "logs").exists()


class TestDriftGuardLivePayload:
    """Live Stop payloads carry last_assistant_message directly (verified
    in the 2026-08-12 live-session trace) — no transcript parse needed."""

    def test_inline_last_message_used_over_transcript(
        self, git_repo: Path, monkeypatch, capsys,
    ):
        (git_repo / "mod.py").write_text("def f():\n    # TODO: later\n    return 1\n")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        out = _run(
            "drift-guard",
            {"last_assistant_message": "All tests pass, implementation complete."},
            monkeypatch, capsys,
        )
        assert out is not None
        assert out["decision"] == "block"


# ---- heartbeat writer (oracle check 11) --------------------------------------


@pytest.fixture()
def hb_root(tmp_path: Path, monkeypatch) -> Path:
    """Sandboxed memory root for heartbeat writes; strips lead-env correlation."""
    mem = tmp_path / "mem"
    mem.mkdir()
    monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("ZO_MEMORY_ROOT", str(mem))
    for name in ("ZO_SESSION_ID", "ZO_LEAD_PID", "ZO_LEAD_PID_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    return mem


def _hb_load(mem: Path, key: str) -> HeartbeatRecord:
    """Read a heartbeat file and validate it against the watchdog model."""
    return HeartbeatRecord.model_validate_json(
        (mem / "heartbeats" / f"{key}.json").read_text(encoding="utf-8")
    )


def _age_file(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


_SUBAGENT_PAYLOAD = {
    "hook_event_name": "PostToolUse", "session_id": "s-hb", "tool_name": "Bash",
    "agent_id": "agent-42", "agent_type": "data-engineer",
}


class TestHeartbeat:
    """(a) the writer produces exactly the ``HeartbeatRecord`` shape and
    (b) it is fail-open — never output, never a non-zero exit."""

    def test_subagent_payload_keyed_by_agent_id(self, hb_root: Path, monkeypatch, capsys):
        assert _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys) is None
        rec = _hb_load(hb_root, "agent-42")
        assert rec.agent_key == "agent-42"
        assert rec.agent_id == "agent-42" and rec.agent_type == "data-engineer"
        assert rec.session_id == "s-hb"
        assert rec.status is HeartbeatStatus.EXECUTING
        assert rec.last_event == "Bash"
        assert rec.tick_count == 1
        assert rec.schema_version == 1
        assert rec.last_tick_at.tzinfo is not None
        assert abs((datetime.now(UTC) - rec.last_tick_at).total_seconds()) < 30

    def test_exact_field_set_matches_heartbeat_record(self, hb_root: Path, monkeypatch, capsys):
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        raw = json.loads((hb_root / "heartbeats" / "agent-42.json").read_text())
        assert set(raw) == set(HeartbeatRecord.model_fields)
        assert raw["last_tick_at"].endswith("+00:00")

    def test_lead_payload_keyed_by_session_id(self, hb_root: Path, monkeypatch, capsys):
        payload = {"hook_event_name": "PostToolUse", "session_id": "s-lead", "tool_name": "Read"}
        _run("heartbeat", payload, monkeypatch, capsys)
        rec = _hb_load(hb_root, "lead-s-lead")
        assert rec.agent_key == "lead-s-lead"
        assert rec.agent_id is None and rec.agent_type is None
        assert rec.last_event == "Read"

    def test_tick_count_increments(self, hb_root: Path, monkeypatch, capsys):
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        _age_file(hb_root / "heartbeats" / "agent-42.json", 10)
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        assert _hb_load(hb_root, "agent-42").tick_count == 2

    def test_seeded_post_tool_use_burst_is_debounced(self, hb_root: Path, monkeypatch, capsys):
        """Two PostToolUse stamps inside 2 s collapse to one write; a Stop
        event immediately after still stamps (only PostToolUse debounces)."""
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        assert _hb_load(hb_root, "agent-42").tick_count == 1
        stop = {**_SUBAGENT_PAYLOAD, "hook_event_name": "Stop"}
        _run("heartbeat", stop, monkeypatch, capsys)
        rec = _hb_load(hb_root, "agent-42")
        assert rec.tick_count == 2 and rec.status is HeartbeatStatus.READY

    def test_corrupt_existing_file_restarts_count(self, hb_root: Path, monkeypatch, capsys):
        hb_dir = hb_root / "heartbeats"
        hb_dir.mkdir()
        (hb_dir / "agent-42.json").write_text("{not json")
        _age_file(hb_dir / "agent-42.json", 10)
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        assert _hb_load(hb_root, "agent-42").tick_count == 1

    @pytest.mark.parametrize(
        ("event", "hook_event", "status"),
        [
            ("heartbeat", "PostToolUse", HeartbeatStatus.EXECUTING),
            ("drift-guard", "Stop", HeartbeatStatus.READY),
            ("subagent-stop", "SubagentStop", HeartbeatStatus.SHUTDOWN),
            ("precompact", "PreCompact", HeartbeatStatus.COMPACTING),
            ("session-end", "SessionEnd", HeartbeatStatus.SHUTDOWN),
        ],
    )
    def test_status_mapping_per_event_via_wired_handlers(
        self, hb_root: Path, monkeypatch, capsys, event: str, hook_event: str, status,
    ):
        """Wiring: every routed handler stamps a heartbeat with the status
        the contract assigns to its hook event; ``last_event`` is the
        hook_event_name for non-PostToolUse events."""
        payload = {"hook_event_name": hook_event, "session_id": "s-map", "tool_name": "Bash"}
        assert _run(event, payload, monkeypatch, capsys) is None
        rec = _hb_load(hb_root, "lead-s-map")
        assert rec.status is status
        assert rec.last_event == ("Bash" if hook_event == "PostToolUse" else hook_event)

    @pytest.mark.parametrize(
        ("event", "status"),
        [
            ("drift-guard", HeartbeatStatus.READY),
            ("subagent-stop", HeartbeatStatus.SHUTDOWN),
            ("precompact", HeartbeatStatus.COMPACTING),
            ("session-end", HeartbeatStatus.SHUTDOWN),
        ],
    )
    def test_handlers_stamp_without_hook_event_name(
        self, hb_root: Path, monkeypatch, capsys, event: str, status,
    ):
        """Older payload shapes lack ``hook_event_name`` — the routed handler
        knows its own event and still maps the status correctly."""
        _run(event, {"session_id": "s-old"}, monkeypatch, capsys)
        assert _hb_load(hb_root, "lead-s-old").status is status

    def test_stamping_does_not_change_drift_guard_output(
        self, git_repo: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        """The Stop hook still blocks on claim+stub AND a heartbeat lands."""
        mem = tmp_path / "mem"
        mem.mkdir()
        (git_repo / "mod.py").write_text("def f():\n    # TODO: later\n    return 1\n")
        monkeypatch.setenv("ZO_REPO_ROOT", str(git_repo))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(mem))
        out = _run(
            "drift-guard",
            {"session_id": "s-dg", "last_assistant_message": "All tests pass, task complete."},
            monkeypatch, capsys,
        )
        assert out is not None and out["decision"] == "block"
        assert _hb_load(mem, "lead-s-dg").status is HeartbeatStatus.READY

    def test_env_correlation_fields(self, hb_root: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_SESSION_ID", "zo-abc")
        monkeypatch.setenv("ZO_LEAD_PID", "4242")
        monkeypatch.setenv("ZO_LEAD_PID_IDENTITY", "darwin:1700000000:0")
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        rec = _hb_load(hb_root, "agent-42")
        assert rec.zo_session_id == "zo-abc"
        assert rec.pid == 4242
        assert rec.process_start_identity == "darwin:1700000000:0"

    def test_env_correlation_fields_absent_are_none(self, hb_root: Path, monkeypatch, capsys):
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        rec = _hb_load(hb_root, "agent-42")
        assert rec.zo_session_id is None and rec.pid is None
        assert rec.process_start_identity is None

    def test_agent_key_is_sanitised_for_filesystem(self, hb_root: Path, monkeypatch, capsys):
        payload = {**_SUBAGENT_PAYLOAD, "agent_id": "../evil/agent"}
        _run("heartbeat", payload, monkeypatch, capsys)
        files = sorted(p.name for p in (hb_root / "heartbeats").glob("*.json"))
        assert files == [".._evil_agent.json"]
        assert not (hb_root / "evil").exists()

    def test_atomic_write_leaves_no_tmp_file(self, hb_root: Path, monkeypatch, capsys):
        _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys)
        names = [p.name for p in (hb_root / "heartbeats").iterdir()]
        assert names == ["agent-42.json"]

    def test_fail_open_without_memory_root(self, tmp_path: Path, monkeypatch, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setenv("ZO_REPO_ROOT", str(repo))
        monkeypatch.delenv("ZO_MEMORY_ROOT", raising=False)
        assert _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys) is None
        assert not list(tmp_path.rglob("heartbeats"))

    def test_fail_open_when_memory_root_missing_dir(self, tmp_path: Path, monkeypatch, capsys):
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(tmp_path / "nowhere"))
        assert _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys) is None
        assert not (tmp_path / "nowhere").exists()

    def test_fail_open_when_heartbeats_dir_unwritable(
        self, hb_root: Path, monkeypatch, capsys,
    ):
        (hb_root / "heartbeats").write_text("i am a file, not a directory")
        assert _run("heartbeat", _SUBAGENT_PAYLOAD, monkeypatch, capsys) is None

    def test_heartbeat_path_imports_no_pydantic(self, hb_root: Path):
        """Perf contract: the PostToolUse path must not pay the pydantic
        import — the whole handler is stdlib-only (contracts import lazy)."""
        code = (
            "import io, json, sys\n"
            f"sys.stdin = io.StringIO(json.dumps({_SUBAGENT_PAYLOAD!r}))\n"
            "import zo.hookkit as h\n"
            "assert h.main(['heartbeat']) == 0\n"
            "assert 'pydantic' not in sys.modules, 'pydantic imported'\n"
            "assert 'zo.watchdog' not in sys.modules, 'watchdog imported'\n"
        )
        src = Path(hookkit.__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": str(src)}
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env,
            timeout=60, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert (hb_root / "heartbeats" / "agent-42.json").exists()

    def test_agent_identity_helper(self):
        assert hookkit._agent_identity({}) == (None, None)
        assert hookkit._agent_identity(
            {"agent_type": " builder ", "agent_id": "a-1"}
        ) == ("builder", "a-1")
        assert hookkit._agent_identity({"subagent_type": "x", "agent_id": ""}) == ("x", None)
        # _agent_name is unchanged (contract lookup key)
        assert hookkit._agent_name({"agent_name": "data-engineer"}) == "data-engineer"
