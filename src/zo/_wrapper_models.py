"""Data models for the lifecycle wrapper.

Separated from wrapper.py to keep both files under 500 lines.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — needed at runtime by pydantic
from enum import StrEnum
from pathlib import Path  # noqa: TC003 — needed at runtime by pydantic

from pydantic import BaseModel, ConfigDict


class AgentStatus(StrEnum):
    """Lifecycle states for the lead orchestrator process."""

    SPAWNING = "spawning"
    RUNNING = "running"
    COMPLETED = "completed"
    ERRORED = "errored"
    RATE_LIMITED = "rate_limited"
    TIMED_OUT = "timed_out"
    # WS-C watchdog states (plan oracle checks 11-12).
    PAUSED_RATE_LIMIT = "paused_rate_limit"
    STALLED = "stalled"


class LeadProcess(BaseModel):
    """Tracks the lead orchestrator Claude Code session.

    Watchdog fields (WS-C): ``pid_start_identity`` pairs the pid with a
    platform-tagged start time so a recycled pid is never mistaken for the
    live lead; ``nudges_used`` / ``stalled`` / ``paused_until`` /
    ``resume_at`` / ``pause_total_sec`` mirror the runner's decisions so
    the CLI can render them without reading the watchdog state file.
    """

    pid: int | None = None
    status: AgentStatus = AgentStatus.SPAWNING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    team_name: str = ""
    stdout_log: Path | None = None
    stderr_log: Path | None = None
    tmux_pane_id: str | None = None
    pid_start_identity: str | None = None
    nudges_used: int = 0
    stalled: bool = False
    paused_until: datetime | None = None
    resume_at: datetime | None = None
    pause_total_sec: float = 0.0

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TeamMember(BaseModel):
    """A team member discovered from task/team files."""

    name: str
    agent_type: str = ""
    status: str = "unknown"
    current_task: str = ""


class TeamStatus(BaseModel):
    """Snapshot of the team's current state."""

    team_name: str
    members: list[TeamMember] = []
    tasks_total: int = 0
    tasks_completed: int = 0
    tasks_in_progress: int = 0
    tasks_pending: int = 0
    is_active: bool = True
