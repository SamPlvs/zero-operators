"""Tests for zo.contracts — machine-readable deliverable contracts (WS-A1).

Seeded-failure pattern per plans/zo-v2-rearchitecture.md: every enforcement
mechanism must catch a deliberately planted violation (oracle check 1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from zo._orchestrator_models import (
    AgentContract,
    GateType,
    PhaseDefinition,
    WorkflowDecomposition,
)
from zo.contracts import (
    CONTRACTS_FILENAME,
    emit_contracts,
    load_contracts,
    set_active_phase,
    validate_agent_stop,
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
                required_artifacts=[
                    "data/reports/data_quality.md", "oracle/eval.py",
                ],
            ),
        ],
        agent_contracts=[
            AgentContract(
                agent_name="data-engineer", phase_id="phase_1",
                role_description="r",
                ownership=["data/raw/", "data/reports/"],
                off_limits=["models/", "oracle/"],
            ),
            AgentContract(
                agent_name="code-reviewer", phase_id="phase_1",
                role_description="r", ownership=[],
                off_limits=["data/raw/", "models/"],
            ),
        ],
    )


class TestEmission:
    def test_emits_contracts_json_with_derived_deliverables(self, tmp_path: Path):
        path = emit_contracts(_workflow(), tmp_path / "mem", "demo", "phase_1")
        doc = load_contracts(path)
        assert doc is not None
        assert doc.project == "demo"
        assert doc.active_phase == "phase_1"
        engineer = next(a for a in doc.agents if a.agent_name == "data-engineer")
        assert [d.path for d in engineer.deliverables] == [
            "data/reports/data_quality.md"
        ]
        assert "oracle/" in engineer.off_limits

    def test_agent_without_ownership_has_no_deliverables(self, tmp_path: Path):
        path = emit_contracts(_workflow(), tmp_path / "mem", "demo", "phase_1")
        doc = load_contracts(path)
        reviewer = next(a for a in doc.agents if a.agent_name == "code-reviewer")
        assert reviewer.deliverables == []

    def test_ownership_fallback_directory_expectation(self, tmp_path: Path):
        wf = _workflow()
        wf.phases[0].required_artifacts = []  # no named artifacts match
        path = emit_contracts(wf, tmp_path / "mem", "demo", "phase_1")
        doc = load_contracts(path)
        engineer = next(a for a in doc.agents if a.agent_name == "data-engineer")
        assert engineer.deliverables[0].kind == "directory"
        assert engineer.deliverables[0].path == "data/raw/"

    def test_set_active_phase_updates_document(self, tmp_path: Path):
        mem = tmp_path / "mem"
        emit_contracts(_workflow(), mem, "demo", "phase_1")
        set_active_phase(mem, "phase_2")
        assert load_contracts(mem / CONTRACTS_FILENAME).active_phase == "phase_2"


class TestValidation:
    """Seeded-violation checks — the heart of oracle check 1."""

    def test_missing_deliverable_is_caught(self, tmp_path: Path):
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        repo.mkdir()
        path = emit_contracts(_workflow(), mem, "demo", "phase_1")
        violations = validate_agent_stop(path, "data-engineer", repo)
        assert len(violations) == 1
        assert violations[0].problem == "required deliverable file missing"

    def test_satisfied_deliverable_passes(self, tmp_path: Path):
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        (repo / "data" / "reports").mkdir(parents=True)
        (repo / "data" / "reports" / "data_quality.md").write_text("# report")
        path = emit_contracts(_workflow(), mem, "demo", "phase_1")
        assert validate_agent_stop(path, "data-engineer", repo) == []

    def test_agent_name_display_form_normalized(self, tmp_path: Path):
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        repo.mkdir()
        path = emit_contracts(_workflow(), mem, "demo", "phase_1")
        assert validate_agent_stop(path, "Data Engineer", repo)

    def test_undersized_deliverable_is_caught(self, tmp_path: Path):
        wf = _workflow()
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        (repo / "data" / "reports").mkdir(parents=True)
        (repo / "data" / "reports" / "data_quality.md").write_text("")
        path = emit_contracts(wf, mem, "demo", "phase_1")
        violations = validate_agent_stop(path, "data-engineer", repo)
        assert "too small" in violations[0].problem

    def test_empty_ownership_directory_is_caught(self, tmp_path: Path):
        wf = _workflow()
        wf.phases[0].required_artifacts = []
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        (repo / "data" / "raw").mkdir(parents=True)  # exists but empty
        path = emit_contracts(wf, mem, "demo", "phase_1")
        violations = validate_agent_stop(path, "data-engineer", repo)
        assert "empty" in violations[0].problem

    def test_inactive_phase_contracts_not_enforced(self, tmp_path: Path):
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        repo.mkdir()
        path = emit_contracts(_workflow(), mem, "demo", "phase_2")
        assert validate_agent_stop(path, "data-engineer", repo) == []

    def test_unknown_agent_fails_open(self, tmp_path: Path):
        mem, repo = tmp_path / "mem", tmp_path / "repo"
        repo.mkdir()
        path = emit_contracts(_workflow(), mem, "demo", "phase_1")
        assert validate_agent_stop(path, "mystery-agent", repo) == []

    def test_malformed_contracts_file_fails_open(self, tmp_path: Path):
        bad = tmp_path / "contracts.json"
        bad.write_text("{not json")
        assert validate_agent_stop(bad, "data-engineer", tmp_path) == []

    def test_missing_contracts_file_fails_open(self, tmp_path: Path):
        missing = tmp_path / "contracts.json"
        assert validate_agent_stop(missing, "data-engineer", tmp_path) == []
