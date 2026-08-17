"""Tests for zo.ledger — the WS-B control plane (plan oracle checks 8-9).

Seeded-failure pattern: builders' direct ledger writes are denied by the
sealed-paths hook; only the orchestrator's oracle-verified paths flip
``passes: true``.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from zo import hookkit
from zo._orchestrator_models import (
    GateType,
    PhaseDefinition,
    WorkflowDecomposition,
)
from zo.ledger import (
    LEDGER_FILENAME,
    emit_ledger,
    load_ledger,
    mark_phase_passed,
    record_attempt,
    record_phase_failure,
    reset_phase,
    set_phase_status,
    summarize,
)

if TYPE_CHECKING:
    from pathlib import Path


def _workflow() -> WorkflowDecomposition:
    return WorkflowDecomposition(
        mode="classical_ml",
        phases=[
            PhaseDefinition(
                phase_id="phase_1", name="Data Review", description="d",
                gate_type=GateType.BLOCKING,
                subtasks=["Raw data audit", "Schema check"],
                required_artifacts=["data/reports/data_quality.md"],
            ),
            PhaseDefinition(
                phase_id="phase_4", name="Training", description="t",
                gate_type=GateType.AUTOMATED,
                subtasks=["Train baseline"],
            ),
        ],
    )


class TestGeneration:
    def test_entries_per_subtask_with_synthesized_criteria(self, tmp_path: Path):
        path = emit_ledger(_workflow(), tmp_path, "demo", "RMSE <= 0.05")
        doc = load_ledger(path)
        assert doc is not None
        assert len(doc.entries) == 3
        audit = next(e for e in doc.entries if "raw-data-audit" in e.subtask_id)
        assert audit.passes is False
        assert audit.acceptance_criteria == [
            "artifact exists: data/reports/data_quality.md"
        ]
        train = next(e for e in doc.entries if e.phase_id == "phase_4")
        assert "oracle threshold met: RMSE <= 0.05" in train.acceptance_criteria
        assert "oracle" in train.verification

    def test_phase_status_initialized(self, tmp_path: Path):
        doc = load_ledger(emit_ledger(_workflow(), tmp_path, "demo"))
        assert set(doc.phase_status) == {"phase_1", "phase_4"}

    def test_regeneration_preserves_progress(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        mark_phase_passed(tmp_path, "phase_1")
        record_attempt(tmp_path, "phase_4", "Train baseline")
        # Re-decompose (plan edit / fresh session) regenerates structure...
        doc = load_ledger(emit_ledger(_workflow(), tmp_path, "demo"))
        # ...but verified progress and bookkeeping survive.
        assert all(e.passes for e in doc.entries if e.phase_id == "phase_1")
        train = next(e for e in doc.entries if e.phase_id == "phase_4")
        assert train.attempts == 1
        assert doc.phase_status["phase_1"] == "completed"


class TestMutators:
    def test_mark_phase_passed_scopes_to_phase(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        mark_phase_passed(tmp_path, "phase_1")
        doc = load_ledger(tmp_path / LEDGER_FILENAME)
        assert summarize(doc)["phase_1"] == (2, 2)
        assert summarize(doc)["phase_4"] == (0, 1)

    def test_reset_phase_clears_passes_and_records_reason(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        mark_phase_passed(tmp_path, "phase_1")
        reset_phase(tmp_path, "phase_1", "human ITERATE: rework features")
        doc = load_ledger(tmp_path / LEDGER_FILENAME)
        entry = next(e for e in doc.entries if e.phase_id == "phase_1")
        assert entry.passes is False
        assert "rework features" in entry.last_failure
        assert doc.phase_status["phase_1"] == "active"

    def test_record_phase_failure_keeps_passes(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        record_phase_failure(tmp_path, "phase_1", "artifacts missing: x.md")
        doc = load_ledger(tmp_path / LEDGER_FILENAME)
        entry = next(e for e in doc.entries if e.phase_id == "phase_1")
        assert entry.passes is False
        assert "artifacts missing" in entry.last_failure

    def test_attempts_do_not_touch_passes(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        record_attempt(tmp_path, "phase_1", "Raw data audit")
        record_attempt(tmp_path, "phase_1", "Raw data audit")
        doc = load_ledger(tmp_path / LEDGER_FILENAME)
        audit = next(e for e in doc.entries if "raw-data-audit" in e.subtask_id)
        assert audit.attempts == 2
        assert audit.passes is False

    def test_set_phase_status(self, tmp_path: Path):
        emit_ledger(_workflow(), tmp_path, "demo")
        set_phase_status(tmp_path, "phase_1", "gated")
        assert load_ledger(tmp_path / LEDGER_FILENAME).phase_status["phase_1"] == "gated"

    def test_mutators_fail_open_without_ledger(self, tmp_path: Path):
        assert mark_phase_passed(tmp_path, "phase_1") is False
        assert reset_phase(tmp_path, "phase_1", "x") is False

    def test_corrupt_ledger_fails_open(self, tmp_path: Path):
        (tmp_path / LEDGER_FILENAME).write_text("{broken")
        assert load_ledger(tmp_path / LEDGER_FILENAME) is None
        assert mark_phase_passed(tmp_path, "phase_1") is False


class TestOracleOwnership:
    """Plan oracle check 9: builder flip blocked, oracle flip lands."""

    def test_builder_direct_write_denied_by_sealed_paths(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        """A builder agent's Write to plan-ledger.json is denied (seeded)."""
        mem = tmp_path / "mem"
        emit_ledger(_workflow(), mem, "demo")
        monkeypatch.setenv("ZO_REPO_ROOT", str(tmp_path))
        monkeypatch.setenv("ZO_MEMORY_ROOT", str(mem))
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps({
                "agent_name": "model-builder",
                "tool_input": {"file_path": str(mem / LEDGER_FILENAME)},
            })),
        )
        assert hookkit.main(["sealed-paths"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_oracle_flip_lands_through_module_api(self, tmp_path: Path):
        """The orchestrator's verified path (mark_phase_passed) succeeds —
        it runs as platform code, outside the agent tool surface."""
        emit_ledger(_workflow(), tmp_path, "demo")
        assert mark_phase_passed(tmp_path, "phase_1") is True
        doc = load_ledger(tmp_path / LEDGER_FILENAME)
        assert summarize(doc)["phase_1"] == (2, 2)
