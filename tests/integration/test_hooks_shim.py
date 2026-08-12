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
