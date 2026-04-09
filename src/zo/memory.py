"""Memory layer for Zero Operators.

Manages persistent state across agent sessions via four markdown files
and a session recovery mechanism.  Every component is designed for fault
tolerance — interrupted sessions can be resumed from the last checkpoint.

Files managed (all under ``memory/{project-name}/``):

- **STATE.md** — lightweight checkpoint (atomic read/write)
- **DECISION_LOG.md** — append-only decision audit trail
- **PRIORS.md** — domain knowledge accumulated across iterations
- **sessions/session-{ts}.md** — one-file-per-session narrative

Typical usage::

    from zo.memory import MemoryManager
    mm = MemoryManager(project_dir=Path("my-repo"), project_name="alpha")
    mm.initialize_project()
    state = mm.read_state()
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

# Re-export models so callers can ``from zo.memory import SessionState`` etc.
from zo._memory_formats import (
    parse_decisions,
    parse_priors,
    parse_session_summary,
    parse_state,
    render_decision,
    render_prior,
    render_session_summary,
    render_state,
)
from zo._memory_models import (
    Confidence,
    DecisionEntry,
    OperatingMode,
    PriorEntry,
    SessionState,
    SessionSummary,
)

__all__ = [
    "Confidence",
    "DecisionEntry",
    "MemoryManager",
    "OperatingMode",
    "PriorEntry",
    "SessionState",
    "SessionSummary",
]

# Keep underscore-prefixed aliases for backward compat with tests
_parse_state = parse_state
_render_state = render_state
_parse_decisions = parse_decisions
_render_decision = render_decision
_parse_priors = parse_priors
_render_prior = render_prior
_render_session_summary = render_session_summary


class MemoryManager:
    """Manages ZO memory files for a single project.

    Args:
        project_dir: Root directory of the target repository (used for
            git operations).
        project_name: Human-readable project identifier used as the
            subdirectory name under ``memory/``.
    """

    def __init__(self, project_dir: Path, project_name: str) -> None:
        self._project_dir = Path(project_dir)
        self._project_name = project_name
        self._memory_root = self._project_dir / "memory" / project_name

    @property
    def memory_root(self) -> Path:
        """Root directory for this project's memory files."""
        return self._memory_root

    # -- STATE.md -----------------------------------------------------------

    def read_state(self) -> SessionState:
        """Read and parse STATE.md, returning defaults if missing/corrupt."""
        path = self._memory_root / "STATE.md"
        if not path.exists():
            return SessionState()
        try:
            text = path.read_text(encoding="utf-8")
            return parse_state(text)
        except (ValueError, KeyError):
            return SessionState()

    def write_state(self, state: SessionState) -> None:
        """Atomically write STATE.md (temp file + rename).

        This prevents corruption if the process is killed mid-write.
        """
        self._memory_root.mkdir(parents=True, exist_ok=True)
        target = self._memory_root / "STATE.md"
        tmp = self._memory_root / ".STATE.md.tmp"
        content = render_state(state)
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)

    # -- DECISION_LOG.md ----------------------------------------------------

    def read_decisions(self) -> list[DecisionEntry]:
        """Read and parse all entries from DECISION_LOG.md."""
        path = self._memory_root / "DECISION_LOG.md"
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return parse_decisions(text)

    def append_decision(self, entry: DecisionEntry) -> None:
        """Append a single decision entry to DECISION_LOG.md."""
        self._memory_root.mkdir(parents=True, exist_ok=True)
        path = self._memory_root / "DECISION_LOG.md"
        rendered = render_decision(entry)
        with open(path, "a", encoding="utf-8") as fh:
            if path.stat().st_size > 0:
                fh.write("\n")
            fh.write(rendered)

    # -- PRIORS.md ----------------------------------------------------------

    def read_priors(self) -> list[PriorEntry]:
        """Read and parse all entries from PRIORS.md."""
        path = self._memory_root / "PRIORS.md"
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return parse_priors(text)

    def append_prior(self, entry: PriorEntry) -> None:
        """Append a single prior entry to PRIORS.md."""
        self._memory_root.mkdir(parents=True, exist_ok=True)
        path = self._memory_root / "PRIORS.md"
        rendered = render_prior(entry)
        with open(path, "a", encoding="utf-8") as fh:
            if path.stat().st_size > 0:
                fh.write("\n")
            fh.write(rendered)

    def seed_priors(self, plan_priors: str) -> None:
        """Seed PRIORS.md from a plan.md domain priors section.

        Args:
            plan_priors: Raw text from the plan's domain priors section.
        """
        self._memory_root.mkdir(parents=True, exist_ok=True)
        path = self._memory_root / "PRIORS.md"

        # If the text already contains structured ## Prior: blocks, write as-is
        if "## Prior:" in plan_priors:
            path.write_text(plan_priors.rstrip() + "\n", encoding="utf-8")
            return

        # Otherwise treat each non-empty line as a simple prior statement
        lines = [ln.strip().lstrip("- ") for ln in plan_priors.splitlines()]
        lines = [ln for ln in lines if ln]
        entries = [
            render_prior(PriorEntry(
                category="domain",
                statement=line,
                evidence="seeded from plan.md",
                confidence=Confidence.MEDIUM,
            ))
            for line in lines
        ]
        path.write_text("\n".join(entries), encoding="utf-8")

    def supersede_prior(self, category: str, superseded_by: str) -> int:
        """Mark all priors in a category as superseded.

        Returns:
            Number of priors updated.
        """
        priors = self.read_priors()
        updated = 0
        for p in priors:
            if p.category == category and p.superseded_by is None:
                p.superseded_by = superseded_by
                updated += 1
        if updated > 0:
            path = self._memory_root / "PRIORS.md"
            rendered = "\n".join(render_prior(p) for p in priors)
            path.write_text(rendered, encoding="utf-8")
        return updated

    # -- Session summaries --------------------------------------------------

    def write_session_summary(self, summary: SessionSummary) -> Path:
        """Write a session summary file.

        Returns:
            Path to the written file.
        """
        sessions_dir = self._memory_root / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        path = sessions_dir / f"session-{ts}.md"
        path.write_text(render_session_summary(summary), encoding="utf-8")
        return path

    def read_recent_summaries(self, count: int = 3) -> list[SessionSummary]:
        """Read the most recent session summaries (newest first).

        Args:
            count: Maximum number of summaries to return.
        """
        sessions_dir = self._memory_root / "sessions"
        if not sessions_dir.exists():
            return []
        files = sorted(sessions_dir.glob("session-*.md"), reverse=True)
        summaries: list[SessionSummary] = []
        for path in files[:count]:
            try:
                text = path.read_text(encoding="utf-8")
                summaries.append(parse_session_summary(text))
            except (ValueError, KeyError):
                continue
        return summaries

    # -- Recovery -----------------------------------------------------------

    def recover_session(self) -> SessionState:
        """Recover session state, falling back to git history if needed.

        Reads STATE.md first.  If missing or corrupt, constructs a minimal
        state from git history.  Checks git_head against the actual repo
        HEAD and logs a discrepancy if they differ.
        """
        state = self.read_state()
        actual_head = self._get_git_head()

        state_path = self._memory_root / "STATE.md"
        if not state_path.exists():
            state.git_head = actual_head
            state.mode = OperatingMode.BUILD
            return state

        if actual_head and state.git_head and actual_head != state.git_head:
            state.active_blockers = [
                f"git_head mismatch: state={state.git_head}, actual={actual_head}",
                *[b for b in state.active_blockers if "git_head mismatch" not in b],
            ]
            state.git_head = actual_head
        return state

    def _get_git_head(self) -> str | None:
        """Return the current git HEAD commit hash, or None."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self._project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    # -- Project initialization ---------------------------------------------

    def initialize_project(self) -> None:
        """Create the directory structure and empty files for a new project.

        Idempotent — safe to call on an already-initialized project.
        """
        self._memory_root.mkdir(parents=True, exist_ok=True)
        (self._memory_root / "sessions").mkdir(exist_ok=True)
        for name in ("STATE.md", "DECISION_LOG.md", "PRIORS.md"):
            path = self._memory_root / name
            if not path.exists():
                path.touch()
