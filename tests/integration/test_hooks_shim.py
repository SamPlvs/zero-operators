"""Integration tests for the .claude/hooks/zo-hookkit.sh shim (v2 WS-A).

Drives the real bash script with stdin JSON exactly as Claude Code does —
the first tests in the repo to execute a hook script end-to-end. The shim
must stay fail-open (exit 0 always) and emit blocking JSON on stdout only
for genuine violations.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from zo._orchestrator_models import (
    AgentContract,
    GateType,
    PhaseDefinition,
    WorkflowDecomposition,
)
from zo.contracts import emit_contracts

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / ".claude" / "hooks" / "zo-hookkit.sh"


def _run_shim(event: str, payload: dict, env_overrides: dict[str, str]) -> tuple[int, str]:
    import os

    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        ["bash", str(SHIM), event],
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=30, env=env, cwd=str(REPO_ROOT), check=False,
    )
    return result.returncode, result.stdout


@pytest.fixture()
def contracts_env(tmp_path: Path) -> dict[str, str]:
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
            ),
        ],
    )
    contracts = emit_contracts(wf, tmp_path / "mem", "demo", "phase_1")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    return {
        "ZO_CONTRACTS_PATH": str(contracts),
        "ZO_DELIVERY_ROOT": str(delivery),
        "ZO_REPO_ROOT": str(REPO_ROOT),
        # WS-C: every routed handler now stamps a heartbeat under the memory
        # root — keep that in tmp, never in the live platform repo.
        "ZO_MEMORY_ROOT": str(tmp_path / "mem"),
    }


class TestShimSubagentStop:
    def test_seeded_violation_emits_block_json(self, contracts_env) -> None:
        code, out = _run_shim(
            "subagent-stop", {"agent_name": "data-engineer"}, contracts_env,
        )
        assert code == 0  # fail-open exit contract even when blocking
        payload = json.loads(out)
        assert payload["decision"] == "block"
        assert "data_quality.md" in payload["reason"]

    def test_satisfied_contract_silent(self, contracts_env) -> None:
        delivery = Path(contracts_env["ZO_DELIVERY_ROOT"])
        (delivery / "data" / "reports").mkdir(parents=True)
        (delivery / "data" / "reports" / "data_quality.md").write_text("# ok")
        code, out = _run_shim(
            "subagent-stop", {"agent_name": "data-engineer"}, contracts_env,
        )
        assert code == 0
        assert out == ""


class TestShimRobustness:
    def test_no_event_exits_zero(self) -> None:
        result = subprocess.run(
            ["bash", str(SHIM)], input="{}", capture_output=True, text=True,
            timeout=30, cwd=str(REPO_ROOT), check=False,
        )
        assert result.returncode == 0

    def test_garbage_stdin_exits_zero_silent(self, contracts_env) -> None:
        import os

        env = {**os.environ, **contracts_env}
        result = subprocess.run(
            ["bash", str(SHIM), "subagent-stop"],
            input="this is not json", capture_output=True, text=True,
            timeout=30, env=env, cwd=str(REPO_ROOT), check=False,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_unknown_event_exits_zero_silent(self) -> None:
        code, out = _run_shim("no-such-event", {}, {})
        assert code == 0
        assert out == ""


class TestSettingsWiring:
    """The settings.json must actually reference every new hook (unwired
    mechanisms are the #1 anti-pattern from the v2 review)."""

    def test_all_ws_a_events_wired(self) -> None:
        settings = json.loads(
            (REPO_ROOT / ".claude" / "settings.json").read_text()
        )
        hooks = settings["hooks"]
        for event in ("SubagentStop", "PreCompact", "SessionEnd", "PostToolUseFailure"):
            commands = [
                h["command"]
                for entry in hooks[event]
                for h in entry["hooks"]
            ]
            assert any("zo-hookkit.sh" in c for c in commands), event

    def test_drift_guard_on_stop_and_sealed_paths_on_pretooluse(self) -> None:
        settings = json.loads(
            (REPO_ROOT / ".claude" / "settings.json").read_text()
        )
        stop_cmds = [
            h["command"]
            for entry in settings["hooks"]["Stop"]
            for h in entry["hooks"]
        ]
        assert any("drift-guard" in c for c in stop_cmds)
        ptu_cmds = [
            h["command"]
            for entry in settings["hooks"]["PreToolUse"]
            for h in entry["hooks"]
        ]
        assert any("sealed-paths" in c for c in ptu_cmds)

    def test_heartbeat_wired_on_post_tool_use(self) -> None:
        """WS-C (oracle check 11): the heartbeat writer runs on every tool
        call (matcher ``*``) as a SECOND PostToolUse entry; the existing
        Write|Edit cascade-reminder entry is untouched and no new hook
        events were introduced."""
        settings = json.loads(
            (REPO_ROOT / ".claude" / "settings.json").read_text()
        )
        post = settings["hooks"]["PostToolUse"]
        heartbeat_entries = [
            (entry["matcher"], h)
            for entry in post
            for h in entry["hooks"]
            if "zo-hookkit.sh heartbeat" in h["command"]
        ]
        assert len(heartbeat_entries) == 1
        matcher, hook = heartbeat_entries[0]
        assert matcher == "*"
        assert hook["timeout"] <= 5
        assert hook["command"].endswith("|| exit 0")
        cascade = [
            entry for entry in post
            if entry["matcher"] == "Write|Edit"
            and any("cascade-reminder.sh" in h["command"] for h in entry["hooks"])
        ]
        assert len(cascade) == 1
        assert set(settings["hooks"]) == {
            "SessionStart", "PreToolUse", "PostToolUse", "Stop", "SubagentStop",
            "PreCompact", "SessionEnd", "PostToolUseFailure",
        }

    def test_shim_exports_hook_event_ts(self) -> None:
        assert 'export ZO_HOOK_EVENT_TS="$(date -u +%s)"' in SHIM.read_text()


# ---- heartbeat end-to-end through the shim (oracle check 11) -----------------


@pytest.fixture()
def heartbeat_env(tmp_path: Path) -> dict[str, str]:
    """Sandbox both roots so the shim writes only into tmp."""
    repo = tmp_path / "repo"
    repo.mkdir()
    mem = tmp_path / "mem"
    mem.mkdir()
    return {"ZO_REPO_ROOT": str(repo), "ZO_MEMORY_ROOT": str(mem)}


class TestShimHeartbeat:
    def test_end_to_end_heartbeat_write(self, heartbeat_env, tmp_path: Path) -> None:
        from zo.watchdog import HeartbeatRecord, HeartbeatStatus

        payload = {
            "hook_event_name": "PostToolUse", "session_id": "shim-1",
            "tool_name": "Bash", "agent_id": "agent-shim", "agent_type": "data-engineer",
        }
        code, out = _run_shim("heartbeat", payload, heartbeat_env)
        assert code == 0
        assert out == ""
        path = tmp_path / "mem" / "heartbeats" / "agent-shim.json"
        rec = HeartbeatRecord.model_validate_json(path.read_text(encoding="utf-8"))
        assert rec.agent_key == "agent-shim"
        assert rec.status is HeartbeatStatus.EXECUTING
        assert rec.last_event == "Bash"
        assert rec.tick_count == 1
        # nothing leaked into the live platform memory root
        live = REPO_ROOT / "memory" / "zo-platform" / "heartbeats" / "agent-shim.json"
        assert not live.exists()

    def test_lead_key_when_no_identity(self, heartbeat_env, tmp_path: Path) -> None:
        code, out = _run_shim(
            "heartbeat", {"hook_event_name": "PostToolUse", "session_id": "shim-2"},
            heartbeat_env,
        )
        assert code == 0 and out == ""
        assert (tmp_path / "mem" / "heartbeats" / "lead-shim-2.json").exists()

    def test_malformed_stdin_exits_zero_silent(self, heartbeat_env) -> None:
        import os

        env = {**os.environ, **heartbeat_env}
        result = subprocess.run(
            ["bash", str(SHIM), "heartbeat"],
            input="{not json at all", capture_output=True, text=True,
            timeout=30, env=env, cwd=str(REPO_ROOT), check=False,
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_no_memory_root_is_silent_noop(self, tmp_path: Path) -> None:
        import os

        repo = tmp_path / "repo"
        repo.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "ZO_MEMORY_ROOT"}
        env["ZO_REPO_ROOT"] = str(repo)
        result = subprocess.run(
            ["bash", str(SHIM), "heartbeat"],
            input=json.dumps({"session_id": "x"}), capture_output=True, text=True,
            timeout=30, env=env, cwd=str(REPO_ROOT), check=False,
        )
        assert result.returncode == 0 and result.stdout == ""
        assert not list(tmp_path.rglob("heartbeats"))


# ---- .gitignore guard for control-plane runtime files ---------------------


class TestGitignoreControlPlane:
    """Runtime files under the platform memory root must never be tracked;
    the ``!memory/zo-platform/`` re-include makes ordering load-bearing."""

    @pytest.fixture(autouse=True)
    def _require_git_repo(self) -> None:
        probe = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, check=False,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            pytest.skip("not inside a git work tree")

    @pytest.mark.parametrize(
        "rel",
        [
            "memory/zo-platform/heartbeats/agent-1.json",
            "memory/zo-platform/heartbeats/_watchdog.json",
            "memory/zo-platform/plan-ledger.json",
            "memory/zo-platform/contracts.json",
        ],
    )
    def test_control_plane_paths_are_ignored(self, rel: str) -> None:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-v", rel],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, f"{rel} is NOT ignored"
        assert ".gitignore" in result.stdout

    def test_platform_memory_itself_stays_tracked(self) -> None:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q",
             "memory/zo-platform/STATE.md"],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 1  # 1 == not ignored
