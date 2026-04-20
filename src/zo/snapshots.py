"""Phase completion snapshots for Zero Operators.

At every phase gate transition (automated or human), the orchestrator
writes a structured snapshot to ``{memory_root}/snapshots/`` capturing
what happened in the phase: subtasks completed, artifacts produced,
recent decisions, issues, and a handoff note for the next phase.

Snapshots are the scannable index into a phase's work — a single file
that answers *"what happened in Phase 2?"* without reading thousands
of comms events. They are also injected into the next phase's lead
prompt as ``# Previous Phase Context``.

Format: markdown with YAML frontmatter (same pattern as STATE.md).
This keeps snapshots machine-parseable (yaml frontmatter) and
human-readable (markdown body), and lets future code query them
without an additional schema.

Typical usage::

    from zo.snapshots import PhaseSnapshot, write_snapshot
    snap = PhaseSnapshot(
        phase_id="phase_2",
        phase_name="Feature Engineering",
        status="completed",
        gate_decision="automated",
        gate_outcome="proceed",
        ...
    )
    path = write_snapshot(memory_root=Path(".zo/memory"), snapshot=snap)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 -- used at runtime

import yaml
from pydantic import BaseModel, Field

__all__ = [
    "SCHEMA_VERSION",
    "PhaseSnapshot",
    "render_snapshot",
    "write_snapshot",
    "load_latest_snapshot",
    "list_snapshots",
]


# Bump when the snapshot schema changes in a non-backward-compatible way.
# Loaders should handle older versions or refuse with a clear error.
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class PhaseSnapshot(BaseModel):
    """Structured record of one phase's completion.

    Attributes:
        schema_version: Snapshot format version for future migrations.
        phase_id: Phase identifier (e.g. ``"phase_2"``).
        phase_name: Human-readable phase name.
        status: Terminal PhaseStatus value (completed / blocked / skipped).
        gate_decision: ``"automated"`` or ``"human"``.
        gate_outcome: GateDecision value (proceed / hold / iterate / escalate).
        completed_at: Snapshot write time (UTC).
        duration_seconds: Optional elapsed time from phase start. ``None`` if
            not tracked.
        iterations: How many times the phase ran to completion (≥1).
        subtasks_total: Total subtasks defined for the phase.
        subtasks_completed: Count of completed subtasks.
        completed_subtask_ids: Names of completed subtasks in order.
        remaining_subtask_ids: Names of subtasks not completed (usually empty
            when gate_outcome == "proceed").
        required_artifacts: Declared artifact paths from PhaseDefinition.
        artifacts_present: Subset of required_artifacts that exist.
        artifacts_missing: Subset of required_artifacts that do not exist.
        recent_decisions: Last N decision entries (title + timestamp only;
            body stays in DECISION_LOG to avoid duplication).
        issues: Error/warning comms events observed during the phase.
        handoff_to_next: Free-form narrative for the next phase's lead.
            Blank by default; orchestrator or a phase-closing agent may fill.
        notes: Optional extra context (e.g. oracle result summary).
    """

    schema_version: int = SCHEMA_VERSION
    phase_id: str
    phase_name: str
    status: str
    gate_decision: str
    gate_outcome: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_seconds: int | None = None
    iterations: int = 1

    subtasks_total: int = 0
    subtasks_completed: int = 0
    completed_subtask_ids: list[str] = Field(default_factory=list)
    remaining_subtask_ids: list[str] = Field(default_factory=list)

    required_artifacts: list[str] = Field(default_factory=list)
    artifacts_present: list[str] = Field(default_factory=list)
    artifacts_missing: list[str] = Field(default_factory=list)

    recent_decisions: list[dict[str, str]] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)

    handoff_to_next: str = ""
    notes: str = ""

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def _frontmatter(snap: PhaseSnapshot) -> str:
    """Serialize snapshot fields as YAML frontmatter."""
    data = {
        "schema_version": snap.schema_version,
        "phase_id": snap.phase_id,
        "phase_name": snap.phase_name,
        "status": snap.status,
        "gate_decision": snap.gate_decision,
        "gate_outcome": snap.gate_outcome,
        "completed_at": snap.completed_at.isoformat(),
        "duration_seconds": snap.duration_seconds,
        "iterations": snap.iterations,
        "subtasks_total": snap.subtasks_total,
        "subtasks_completed": snap.subtasks_completed,
        "required_artifacts": snap.required_artifacts,
        "artifacts_present": snap.artifacts_present,
        "artifacts_missing": snap.artifacts_missing,
    }
    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False).strip()


def _subtasks_block(snap: PhaseSnapshot) -> str:
    if not snap.completed_subtask_ids and not snap.remaining_subtask_ids:
        return "_No subtasks defined._"
    lines = [f"- [x] {s}" for s in snap.completed_subtask_ids]
    lines.extend(f"- [ ] {s}" for s in snap.remaining_subtask_ids)
    return "\n".join(lines)


def _artifacts_block(snap: PhaseSnapshot) -> str:
    if not snap.required_artifacts:
        return "_No artifacts required._"
    present = set(snap.artifacts_present)
    lines = ["| Artifact | Status |", "|---|---|"]
    for a in snap.required_artifacts:
        status = "present" if a in present else "missing"
        lines.append(f"| `{a}` | {status} |")
    return "\n".join(lines)


def _decisions_block(snap: PhaseSnapshot) -> str:
    if not snap.recent_decisions:
        return "_No decisions logged in this phase window._"
    lines = []
    for d in snap.recent_decisions:
        ts = d.get("timestamp", "")
        title = d.get("title", "(untitled)")
        lines.append(f"- {ts} — {title}")
    return "\n".join(lines)


def _issues_block(snap: PhaseSnapshot) -> str:
    if not snap.issues:
        return "_None._"
    lines = []
    for i in snap.issues:
        sev = i.get("severity", "info").upper()
        msg = i.get("message", "")
        lines.append(f"- **{sev}** — {msg}")
    return "\n".join(lines)


def render_snapshot(snap: PhaseSnapshot) -> str:
    """Render a PhaseSnapshot as markdown with YAML frontmatter."""
    duration = "n/a"
    if snap.duration_seconds is not None:
        h, rem = divmod(snap.duration_seconds, 3600)
        m, _ = divmod(rem, 60)
        duration = f"{h}h {m}m" if h else f"{m}m"

    body = f"""---
{_frontmatter(snap)}
---

# {snap.phase_name} — Completion Snapshot

**Phase:** `{snap.phase_id}`
**Status:** `{snap.status}` (gate: {snap.gate_decision} → `{snap.gate_outcome}`)
**Duration:** {duration} | **Iterations:** {snap.iterations}

## Subtasks ({snap.subtasks_completed}/{snap.subtasks_total})

{_subtasks_block(snap)}

## Required Artifacts

{_artifacts_block(snap)}

## Recent Decisions

{_decisions_block(snap)}

## Issues & Deferrals

{_issues_block(snap)}

## Handoff to Next Phase

{snap.handoff_to_next or "_No narrative handoff recorded._"}
"""
    if snap.notes:
        body += f"\n## Notes\n\n{snap.notes}\n"
    return body


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _snapshot_filename(snap: PhaseSnapshot) -> str:
    """Build the snapshot filename: phase_{id}_{YYYY-MM-DDTHH-MM-SS}.md."""
    ts = snap.completed_at.strftime("%Y-%m-%dT%H-%M-%S")
    return f"{snap.phase_id}_{ts}.md"


def write_snapshot(memory_root: Path, snapshot: PhaseSnapshot) -> Path:
    """Write a snapshot to ``{memory_root}/snapshots/``.

    Returns the absolute path of the written file. Creates the snapshots
    directory if it doesn't exist.
    """
    snapshots_dir = memory_root / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / _snapshot_filename(snapshot)
    path.write_text(render_snapshot(snapshot), encoding="utf-8")
    return path


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict:
    """Extract and parse the YAML frontmatter from a snapshot file."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def list_snapshots(memory_root: Path, phase_id: str | None = None) -> list[Path]:
    """List snapshot paths in ``{memory_root}/snapshots/``, newest first.

    Args:
        memory_root: Memory directory containing a ``snapshots/`` subdir.
        phase_id: When given, filter to snapshots for this phase only.

    Returns:
        List of paths sorted by filename (lexicographically ~ newest first
        given the timestamp suffix in the filename).
    """
    snapshots_dir = memory_root / "snapshots"
    if not snapshots_dir.is_dir():
        return []
    prefix = f"{phase_id}_" if phase_id else ""
    paths = [p for p in snapshots_dir.glob(f"{prefix}*.md") if p.is_file()]
    return sorted(paths, reverse=True)


def load_latest_snapshot(
    memory_root: Path, phase_id: str,
) -> PhaseSnapshot | None:
    """Load the most recent snapshot for a phase, or None if none exist."""
    paths = list_snapshots(memory_root, phase_id)
    if not paths:
        return None
    fm = _parse_frontmatter(paths[0].read_text(encoding="utf-8"))
    if not fm:
        return None
    # Frontmatter contains the subset of fields needed to reconstruct.
    # Fill body-only fields with defaults — loaders that need narrative
    # content should read the raw markdown.
    return PhaseSnapshot(**fm)
