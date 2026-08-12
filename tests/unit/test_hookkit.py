"""Tests for zo.hookkit — the WS-A enforcement-plane hook handlers.

Each handler gets: (a) a seeded-violation test proving the mechanism
catches a planted problem (plan oracle checks 1-4, 7), and (b) a
fail-open test proving infrastructure problems never block a session.
Handlers are driven through ``main()`` with stdin/stdout patched — the
same interface the bash shim uses.
"""

from __future__ import annotations

import io
import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from zo import hookkit
from zo._orchestrator_models import (
    AgentContract,
    GateType,
    PhaseDefinition,
    WorkflowDecomposition,
)
from zo.contracts import emit_contracts

if TYPE_CHECKING:
    from pathlib import Path


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
