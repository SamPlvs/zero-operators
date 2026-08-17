"""Machine-readable plan ledger with oracle-owned pass flags (v2 WS-B).

``plan-ledger.json`` lives in the project memory root beside ``gate_mode``
and ``contracts.json``: one entry per (phase, subtask) with acceptance
criteria, a synthesized verification descriptor, and a boolean ``passes``
that ONLY the orchestrator's oracle-verified code paths may flip —
builders' direct writes are denied by the sealed-paths hook (WS-A4).
"What is done" becomes a query over this file; STATE.md remains the
human-readable projection.

Design notes:
    - Regeneration merges: structure comes from the current workflow
      decomposition, but ``passes``/``attempts``/``last_failure`` and
      ``phase_status`` are preserved by ``subtask_id`` so a re-decompose
      (plan edit, fresh session) never erases verified progress.
    - Every write is atomic (temp file + ``os.replace``) — a torn ledger
      read by a fail-open hook would silently unblock builders.
    - Mutators are fail-open at the call site (the orchestrator wraps
      them); a ledger IO problem must never crash a build.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from zo._orchestrator_models import WorkflowDecomposition

__all__ = [
    "LEDGER_FILENAME",
    "LedgerEntry",
    "LedgerFile",
    "emit_ledger",
    "load_ledger",
    "mark_phase_passed",
    "record_attempt",
    "record_phase_failure",
    "reset_phase",
    "set_phase_status",
]

LEDGER_FILENAME = "plan-ledger.json"


class LedgerEntry(BaseModel):
    """One subtask's machine-checkable progress record."""

    subtask_id: str
    phase_id: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    verification: str = ""
    passes: bool = False
    attempts: int = 0
    last_failure: str | None = None


class LedgerFile(BaseModel):
    """Top-level schema of ``plan-ledger.json``."""

    version: int = 1
    project: str = ""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    phase_status: dict[str, str] = Field(default_factory=dict)
    entries: list[LedgerEntry] = Field(default_factory=list)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_ledger(path: Path) -> LedgerFile | None:
    """Load and parse the ledger; ``None`` on any problem (fail-open)."""
    try:
        return LedgerFile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _criteria_for_phase(
    phase_id: str,
    required_artifacts: list[str],
    oracle_threshold: str | None,
) -> tuple[list[str], str]:
    """Synthesize acceptance criteria + verification descriptor.

    Criteria come from what the platform can already mechanically check:
    phase required-artifact existence (all phases) and the oracle
    threshold (phase_4, where ``_finalize_experiments`` parses the
    oracle's ``result.md``). Phases 1-3/5-6 are artifact-verified only —
    stated explicitly rather than pretending otherwise.
    """
    criteria = [f"artifact exists: {a}" for a in required_artifacts]
    if phase_id == "phase_4" and oracle_threshold:
        criteria.append(f"oracle threshold met: {oracle_threshold}")
        verification = "oracle result.md tier evaluation (_finalize_experiments)"
    elif required_artifacts:
        verification = "artifact existence check (_check_artifacts)"
    else:
        verification = "phase gate evaluation"
    return criteria, verification


def emit_ledger(
    workflow: WorkflowDecomposition,
    memory_root: Path,
    project: str,
    oracle_threshold: str | None = None,
) -> Path:
    """Generate (or regenerate, merge-preserving) the plan ledger.

    Returns:
        The path written.
    """
    path = memory_root / LEDGER_FILENAME
    previous = load_ledger(path)
    prev_entries = (
        {e.subtask_id: e for e in previous.entries} if previous else {}
    )
    prev_status = dict(previous.phase_status) if previous else {}

    entries: list[LedgerEntry] = []
    phase_status: dict[str, str] = {}
    for phase in workflow.phases:
        phase_status[phase.phase_id] = prev_status.get(
            phase.phase_id, str(phase.status),
        )
        criteria, verification = _criteria_for_phase(
            phase.phase_id, phase.required_artifacts, oracle_threshold,
        )
        for subtask in phase.subtasks:
            subtask_id = f"{phase.phase_id}:{_slug(subtask)}"
            old = prev_entries.get(subtask_id)
            entries.append(
                LedgerEntry(
                    subtask_id=subtask_id,
                    phase_id=phase.phase_id,
                    description=subtask,
                    acceptance_criteria=criteria,
                    verification=verification,
                    passes=old.passes if old else False,
                    attempts=old.attempts if old else 0,
                    last_failure=old.last_failure if old else None,
                )
            )

    doc = LedgerFile(project=project, phase_status=phase_status, entries=entries)
    _atomic_write(path, doc.model_dump_json(indent=2))
    return path


def _mutate(memory_root: Path, fn: Callable[[LedgerFile], None]) -> bool:
    """Load-modify-write the ledger atomically; False if absent/corrupt."""
    path = memory_root / LEDGER_FILENAME
    doc = load_ledger(path)
    if doc is None:
        return False
    fn(doc)
    _atomic_write(path, doc.model_dump_json(indent=2))
    return True


def mark_phase_passed(memory_root: Path, phase_id: str) -> bool:
    """Flip all of a phase's entries to ``passes: true``.

    ORACLE-OWNED: call only from the orchestrator's verified-completion
    paths (automated gate with artifacts/oracle checks green, or a
    nonce-verified human PROCEED). Builders cannot reach this — direct
    ledger writes are sealed (WS-A4) and this module is not agent-facing.
    """

    def fn(doc: LedgerFile) -> None:
        for entry in doc.entries:
            if entry.phase_id == phase_id:
                entry.passes = True
                entry.last_failure = None
        doc.phase_status[phase_id] = "completed"

    return _mutate(memory_root, fn)


def reset_phase(memory_root: Path, phase_id: str, reason: str) -> bool:
    """Reset a phase's entries for rework (ITERATE / loop CONTINUE)."""

    def fn(doc: LedgerFile) -> None:
        for entry in doc.entries:
            if entry.phase_id == phase_id:
                entry.passes = False
                entry.last_failure = reason[:500]
        doc.phase_status[phase_id] = "active"

    return _mutate(memory_root, fn)


def record_phase_failure(memory_root: Path, phase_id: str, reason: str) -> bool:
    """Record a failed gate evaluation without resetting progress."""

    def fn(doc: LedgerFile) -> None:
        for entry in doc.entries:
            if entry.phase_id == phase_id and not entry.passes:
                entry.last_failure = reason[:500]

    return _mutate(memory_root, fn)


def record_attempt(memory_root: Path, phase_id: str, subtask: str) -> bool:
    """Count a work attempt on a subtask (does NOT touch ``passes``)."""
    subtask_id = f"{phase_id}:{_slug(subtask)}"

    def fn(doc: LedgerFile) -> None:
        for entry in doc.entries:
            if entry.subtask_id == subtask_id:
                entry.attempts += 1

    return _mutate(memory_root, fn)


def set_phase_status(memory_root: Path, phase_id: str, status: str) -> bool:
    """Record a phase-status transition (active/gated/completed/blocked)."""

    def fn(doc: LedgerFile) -> None:
        doc.phase_status[phase_id] = status

    return _mutate(memory_root, fn)


def summarize(doc: LedgerFile) -> dict[str, tuple[int, int]]:
    """Per-phase (passed, total) counts for status rendering."""
    counts: dict[str, tuple[int, int]] = {}
    for entry in doc.entries:
        passed, total = counts.get(entry.phase_id, (0, 0))
        counts[entry.phase_id] = (passed + (1 if entry.passes else 0), total + 1)
    return counts
