"""Machine-readable agent deliverable contracts (v2 WS-A1).

Compiles the prose ``AgentContract`` objects produced by
``Orchestrator.decompose_plan()`` into a per-project ``contracts.json``
under the project memory root, and validates produced artifacts against
it when a subagent stops (consumed by ``zo.hookkit`` from the
``SubagentStop`` hook).

Design notes:
    - ``contracts.json`` follows the ``gate_mode`` control-file precedent:
      machine-readable state lives in ``memory_root``, gitignored, written
      atomically.
    - Deliverable paths are derived from ``PhaseDefinition.required_artifacts``
      scoped by each agent's ownership prefixes; agents whose ownership
      matches no phase artifact keep an ownership-directory expectation
      instead, so validation never degenerates to always-pass prose.
    - Validation is fail-open on infrastructure problems (missing file,
      malformed JSON) but strict on declared deliverables — the hook layer
      must never brick a session, only catch contract violations.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pathlib import Path

    from zo._orchestrator_models import WorkflowDecomposition

__all__ = [
    "AgentDeliverables",
    "ContractsFile",
    "DeliverableSpec",
    "Violation",
    "emit_contracts",
    "load_contracts",
    "set_active_phase",
    "validate_agent_stop",
]

CONTRACTS_FILENAME = "contracts.json"


class DeliverableSpec(BaseModel):
    """One machine-checkable deliverable an agent must produce."""

    path: str
    kind: str = "file"  # "file" | "directory"
    min_bytes: int = 1
    required_patterns: list[str] = Field(default_factory=list)
    description: str = ""


class AgentDeliverables(BaseModel):
    """Deliverable set for one (agent, phase) pair."""

    agent_name: str
    phase_id: str
    deliverables: list[DeliverableSpec] = Field(default_factory=list)
    off_limits: list[str] = Field(default_factory=list)
    ownership: list[str] = Field(default_factory=list)


class ContractsFile(BaseModel):
    """Top-level schema of ``contracts.json``."""

    version: int = 1
    project: str = ""
    active_phase: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agents: list[AgentDeliverables] = Field(default_factory=list)


class Violation(BaseModel):
    """A single contract violation found at subagent stop."""

    agent_name: str
    phase_id: str
    path: str
    problem: str


def _derive_deliverables(
    ownership: list[str], required_artifacts: list[str],
) -> list[DeliverableSpec]:
    """Map phase artifacts to an agent via its ownership prefixes."""
    specs: list[DeliverableSpec] = []
    for artifact in required_artifacts:
        if any(artifact.startswith(prefix) for prefix in ownership):
            specs.append(
                DeliverableSpec(
                    path=artifact,
                    description="Phase required artifact within agent ownership",
                )
            )
    if not specs and ownership:
        # No named artifact matched: the agent still owes non-empty output
        # inside its primary ownership directory.
        specs.append(
            DeliverableSpec(
                path=ownership[0],
                kind="directory",
                description="Ownership directory must exist and be non-empty",
            )
        )
    return specs


def emit_contracts(
    workflow: WorkflowDecomposition,
    memory_root: Path,
    project: str,
    active_phase: str,
) -> Path:
    """Serialize workflow contracts to ``memory_root/contracts.json``.

    Written atomically (temp file + ``os.replace``) so a concurrently
    running hook never reads a torn file.

    Returns:
        The path written.
    """
    agents = [
        AgentDeliverables(
            agent_name=c.agent_name,
            phase_id=c.phase_id,
            deliverables=_derive_deliverables(
                c.ownership,
                next(
                    (
                        p.required_artifacts
                        for p in workflow.phases
                        if p.phase_id == c.phase_id
                    ),
                    [],
                ),
            ),
            off_limits=list(c.off_limits),
            ownership=list(c.ownership),
        )
        for c in workflow.agent_contracts
    ]
    doc = ContractsFile(project=project, active_phase=active_phase, agents=agents)
    memory_root.mkdir(parents=True, exist_ok=True)
    path = memory_root / CONTRACTS_FILENAME
    fd, tmp = tempfile.mkstemp(dir=str(memory_root), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(doc.model_dump_json(indent=2))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def load_contracts(path: Path) -> ContractsFile | None:
    """Load and parse ``contracts.json``; ``None`` on any problem (fail-open)."""
    try:
        return ContractsFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def set_active_phase(memory_root: Path, phase_id: str) -> None:
    """Update ``active_phase`` in an existing contracts file, if present.

    Atomic (temp + ``os.replace``) — a torn read in the fail-open hook
    layer would silently disable contract enforcement.
    """
    path = memory_root / CONTRACTS_FILENAME
    doc = load_contracts(path)
    if doc is None:
        return
    doc.active_phase = phase_id
    fd, tmp = tempfile.mkstemp(dir=str(memory_root), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(doc.model_dump_json(indent=2))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _check_spec(repo_root: Path, spec: DeliverableSpec) -> str | None:
    """Return a problem description for a deliverable, or ``None`` if met."""
    target = repo_root / spec.path
    if spec.kind == "directory":
        if not target.is_dir():
            return "required ownership directory missing"
        if not any(target.iterdir()):
            return "required ownership directory is empty"
        return None
    if not target.is_file():
        return "required deliverable file missing"
    size = target.stat().st_size
    if size < spec.min_bytes:
        return f"deliverable too small ({size} bytes < {spec.min_bytes})"
    if spec.required_patterns:
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "deliverable unreadable"
        for pattern in spec.required_patterns:
            if re.search(pattern, text) is None:
                return f"required pattern not found: {pattern!r}"
    return None


def validate_agent_stop(
    contracts_path: Path, agent_name: str, repo_root: Path,
) -> list[Violation]:
    """Validate one agent's deliverables for the active phase.

    Fail-open: unknown agent, missing contracts file, or no active-phase
    entry yields an empty violation list. Strict on declared deliverables.
    """
    doc = load_contracts(contracts_path)
    if doc is None:
        return []
    normalized = agent_name.strip().lower().replace(" ", "-")
    violations: list[Violation] = []
    for entry in doc.agents:
        if entry.agent_name != normalized or entry.phase_id != doc.active_phase:
            continue
        for spec in entry.deliverables:
            problem = _check_spec(repo_root, spec)
            if problem is not None:
                violations.append(
                    Violation(
                        agent_name=entry.agent_name,
                        phase_id=entry.phase_id,
                        path=spec.path,
                        problem=problem,
                    )
                )
    return violations
