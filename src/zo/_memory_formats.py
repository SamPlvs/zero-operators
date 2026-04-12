"""Markdown serialization and parsing for ZO memory files.

Internal module — import from ``zo.memory`` instead.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from zo._memory_models import (
    DecisionEntry,
    PriorEntry,
    SessionState,
    SessionSummary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BOLD_FIELD_RE = re.compile(r"\*\*(.+?)\*\*:\s*(.*)")
_DECISION_SPLIT_RE = re.compile(r"(?=^## Decision: )", re.MULTILINE)
_PRIOR_SPLIT_RE = re.compile(r"(?=^## Prior: )", re.MULTILINE)


def _format_list(items: list[str]) -> str:
    """Format a Python list as ``[a, b, c]``."""
    if not items:
        return "[]"
    return "[" + ", ".join(items) + "]"


def _parse_bracket_list(raw: str) -> list[str]:
    """Parse ``[a, b, c]`` or ``[]`` into a Python list."""
    raw = raw.strip()
    if raw in ("[]", ""):
        return []
    inner = raw.strip("[]")
    return [item.strip() for item in inner.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# STATE.md
# ---------------------------------------------------------------------------


def render_state(state: SessionState) -> str:
    """Render a SessionState to STATE.md markdown format."""
    ts = state.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    last = state.last_completed_subtask or "null"
    lines = [
        "# STATE",
        f"timestamp: {ts}",
        f"mode: {state.mode}",
        f"phase: {state.phase}",
        f"last_completed_subtask: {last}",
        f"active_blockers: {_format_list(state.active_blockers)}",
        f"next_steps: {_format_list(state.next_steps)}",
        f"active_agents: {_format_list(state.active_agents)}",
        f"git_head: {state.git_head or 'null'}",
        f"context_window_usage: {state.context_window_usage}",
    ]
    if state.phase_states:
        lines.append("")
        lines.append("## Phases")
        for pid, status in state.phase_states.items():
            subtasks = state.completed_subtasks_by_phase.get(pid, [])
            lines.append(f"{pid}: {status} {_format_list(subtasks)}")
    return "\n".join(lines) + "\n"


_PHASE_LINE_RE = re.compile(r"^(phase_\d+):\s*(\w+)\s*(.*)")


def parse_state(text: str) -> SessionState:
    """Parse STATE.md text into a SessionState model.

    Raises:
        ValueError: If the text cannot be parsed.
    """
    kv: dict[str, str] = {}
    phase_states: dict[str, str] = {}
    completed_by_phase: dict[str, list[str]] = {}
    in_phases_section = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "## Phases":
            in_phases_section = True
            continue
        if stripped.startswith("## ") and in_phases_section:
            in_phases_section = False
        if in_phases_section:
            m = _PHASE_LINE_RE.match(stripped)
            if m:
                pid, status, rest = m.group(1), m.group(2), m.group(3)
                phase_states[pid] = status
                completed_by_phase[pid] = _parse_bracket_list(rest)
            continue
        if stripped.startswith("#") or not stripped:
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        kv[key.strip()] = value.strip()

    if not kv:
        raise ValueError("STATE.md contains no parseable key-value pairs")

    kwargs: dict[str, Any] = {}
    if "timestamp" in kv:
        kwargs["timestamp"] = datetime.fromisoformat(kv["timestamp"].replace("Z", "+00:00"))
    for simple in ("mode", "phase", "context_window_usage"):
        if simple in kv:
            kwargs[simple] = kv[simple]
    if "last_completed_subtask" in kv:
        val = kv["last_completed_subtask"]
        kwargs["last_completed_subtask"] = None if val == "null" else val
    for list_key in ("active_blockers", "next_steps", "active_agents"):
        if list_key in kv:
            kwargs[list_key] = _parse_bracket_list(kv[list_key])
    if "git_head" in kv:
        val = kv["git_head"]
        kwargs["git_head"] = None if val == "null" else val
    if phase_states:
        kwargs["phase_states"] = phase_states
        kwargs["completed_subtasks_by_phase"] = completed_by_phase
    return SessionState(**kwargs)


# ---------------------------------------------------------------------------
# DECISION_LOG.md
# ---------------------------------------------------------------------------


def render_decision(entry: DecisionEntry) -> str:
    """Render a single DecisionEntry to markdown."""
    ts = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"## Decision: {entry.title}\n"
        f"**Timestamp**: {ts}\n"
        f"**Context**: {entry.context}\n"
        f"**Decision**: {entry.decision}\n"
        f"**Rationale**: {entry.rationale}\n"
        f"**Alternatives Considered**: {entry.alternatives_considered}\n"
        f"**Outcome**: {entry.outcome}\n"
        f"**Confidence**: {entry.confidence}\n"
        "---\n"
    )


def parse_decisions(text: str) -> list[DecisionEntry]:
    """Parse DECISION_LOG.md text into a list of DecisionEntry models."""
    blocks = _DECISION_SPLIT_RE.split(text)
    return [
        _parse_single_decision(b.strip())
        for b in blocks
        if b.strip().startswith("## Decision:")
    ]


def _parse_single_decision(block: str) -> DecisionEntry:
    """Parse one decision block into a DecisionEntry."""
    lines = block.splitlines()
    title = lines[0].removeprefix("## Decision:").strip()
    fields = _extract_bold_fields(lines[1:])
    kwargs: dict[str, Any] = {"title": title}
    if "Timestamp" in fields:
        kwargs["timestamp"] = datetime.fromisoformat(fields["Timestamp"].replace("Z", "+00:00"))
    field_map = {
        "Context": "context", "Decision": "decision", "Rationale": "rationale",
        "Alternatives Considered": "alternatives_considered",
        "Outcome": "outcome", "Confidence": "confidence",
    }
    for md_key, py_key in field_map.items():
        if md_key in fields:
            kwargs[py_key] = fields[md_key]
    return DecisionEntry(**kwargs)


# ---------------------------------------------------------------------------
# PRIORS.md
# ---------------------------------------------------------------------------


def render_prior(entry: PriorEntry) -> str:
    """Render a single PriorEntry to markdown."""
    sup = entry.superseded_by or "null"
    return (
        f"## Prior: {entry.category}\n"
        f"**Statement**: {entry.statement}\n"
        f"**Evidence**: {entry.evidence}\n"
        f"**Confidence**: {entry.confidence}\n"
        f"**Superseded By**: {sup}\n"
        "---\n"
    )


def parse_priors(text: str) -> list[PriorEntry]:
    """Parse PRIORS.md text into a list of PriorEntry models."""
    blocks = _PRIOR_SPLIT_RE.split(text)
    return [_parse_single_prior(b.strip()) for b in blocks if b.strip().startswith("## Prior:")]


def _parse_single_prior(block: str) -> PriorEntry:
    """Parse one prior block into a PriorEntry."""
    lines = block.splitlines()
    category = lines[0].removeprefix("## Prior:").strip()
    fields = _extract_bold_fields(lines[1:])
    superseded = fields.get("Superseded By", "null")
    return PriorEntry(
        category=category,
        statement=fields.get("Statement", ""),
        evidence=fields.get("Evidence", ""),
        confidence=fields.get("Confidence", "medium"),
        superseded_by=None if superseded == "null" else superseded,
    )


# ---------------------------------------------------------------------------
# Session summaries
# ---------------------------------------------------------------------------


def render_session_summary(summary: SessionSummary) -> str:
    """Render a SessionSummary to markdown."""

    def _bl(items: list[str]) -> str:
        return "".join(f"- {i}\n" for i in items).rstrip() if items else "- (none)"

    return "\n".join([
        f"# Session Summary: {summary.date}",
        f"**Date**: {summary.date}",
        f"**Duration**: {summary.duration}",
        f"**Mode**: {summary.mode}",
        f"**Agent**: {summary.agent}",
        "", "## Accomplished", _bl(summary.accomplished),
        "", "## Decisions Made", _bl(summary.decisions_made),
        "", "## Blockers Hit", _bl(summary.blockers_hit),
        "", "## Next Steps", _bl(summary.next_steps),
        "", "## Files Changed", _bl(summary.files_changed),
        "", "## Context Handoff",
        f"- Estimated completion: {summary.estimated_completion or 'unknown'}",
        "- Open questions: " + (
            ", ".join(summary.open_questions) if summary.open_questions else "(none)"
        ),
        f"- Recommended next phase: {summary.recommended_next_phase or 'TBD'}",
    ]) + "\n"


def parse_session_summary(text: str) -> SessionSummary:
    """Parse a session summary markdown file."""
    kwargs: dict[str, Any] = {}
    current_section: str | None = None
    section_items: list[str] = []

    def _flush() -> None:
        if current_section and section_items:
            kwargs[current_section.lower().replace(" ", "_")] = section_items[:]

    for line in text.splitlines():
        s = line.strip()
        m = _BOLD_FIELD_RE.match(s)
        if m and current_section is None:
            key, val = m.group(1).strip(), m.group(2).strip()
            for md_k, py_k in (("Date", "date"), ("Duration", "duration"),
                                ("Mode", "mode"), ("Agent", "agent")):
                if key == md_k:
                    kwargs[py_k] = val
            continue
        if s.startswith("## "):
            _flush()
            section_items = []
            current_section = s.removeprefix("## ").strip()
            continue
        if s.startswith("- ") and current_section:
            item = s.removeprefix("- ").strip()
            if item and item != "(none)":
                if current_section == "Context Handoff":
                    _parse_handoff(item, kwargs)
                else:
                    section_items.append(item)
    _flush()
    return SessionSummary(**kwargs)


def _parse_handoff(item: str, kwargs: dict[str, Any]) -> None:
    """Parse a Context Handoff bullet into kwargs."""
    if item.startswith("Estimated completion:"):
        kwargs["estimated_completion"] = item.split(":", 1)[1].strip()
    elif item.startswith("Open questions:"):
        raw = item.split(":", 1)[1].strip()
        if raw and raw != "(none)":
            kwargs["open_questions"] = [q.strip() for q in raw.split(",") if q.strip()]
    elif item.startswith("Recommended next phase:"):
        kwargs["recommended_next_phase"] = item.split(":", 1)[1].strip()


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _extract_bold_fields(lines: list[str]) -> dict[str, str]:
    """Extract ``**Key**: value`` fields from a list of lines."""
    fields: dict[str, str] = {}
    for line in lines:
        m = _BOLD_FIELD_RE.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
    return fields
