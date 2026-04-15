"""Unit tests for zo.memory — the ZO memory layer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from zo.memory import (
    Confidence,
    DecisionEntry,
    MemoryManager,
    OperatingMode,
    PriorEntry,
    SessionState,
    SessionSummary,
    _parse_decisions,
    _parse_priors,
    _parse_state,
    _render_decision,
    _render_prior,
    _render_state,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Return a temporary directory acting as a project root."""
    return tmp_path


@pytest.fixture()
def mm(tmp_project: Path) -> MemoryManager:
    """Return a MemoryManager wired to a temp directory."""
    return MemoryManager(project_dir=tmp_project, project_name="test-proj")


# ---------------------------------------------------------------------------
# STATE.md round-trip
# ---------------------------------------------------------------------------


class TestStateRoundTrip:
    """STATE.md write-then-read produces identical data."""

    def test_default_state_round_trip(self, mm: MemoryManager) -> None:
        state = SessionState(
            timestamp=datetime(2026, 4, 9, 14, 32, 0, tzinfo=UTC),
            mode=OperatingMode.BUILD,
            phase="data-prep",
            last_completed_subtask="download raw data",
            active_blockers=["missing API key"],
            next_steps=["clean data", "validate schema"],
            active_agents=["data-eng", "orchestrator"],
            git_head="abc1234",
        )
        mm.write_state(state)
        loaded = mm.read_state()

        assert loaded.mode == "build"
        assert loaded.phase == "data-prep"
        assert loaded.last_completed_subtask == "download raw data"
        assert loaded.active_blockers == ["missing API key"]
        assert loaded.next_steps == ["clean data", "validate schema"]
        assert loaded.active_agents == ["data-eng", "orchestrator"]
        assert loaded.git_head == "abc1234"

    def test_empty_lists_round_trip(self, mm: MemoryManager) -> None:
        state = SessionState(
            timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
            active_blockers=[],
            next_steps=[],
            active_agents=[],
        )
        mm.write_state(state)
        loaded = mm.read_state()

        assert loaded.active_blockers == []
        assert loaded.next_steps == []
        assert loaded.active_agents == []

    def test_null_subtask_round_trip(self, mm: MemoryManager) -> None:
        state = SessionState(last_completed_subtask=None, git_head=None)
        mm.write_state(state)
        loaded = mm.read_state()

        assert loaded.last_completed_subtask is None
        assert loaded.git_head is None

    def test_phase_states_round_trip(self, mm: MemoryManager) -> None:
        state = SessionState(
            timestamp=datetime(2026, 4, 12, 10, 0, 0, tzinfo=UTC),
            phase="phase_3",
            phase_states={
                "phase_1": "completed",
                "phase_2": "completed",
                "phase_3": "active",
                "phase_4": "pending",
            },
            completed_subtasks_by_phase={
                "phase_1": ["Data audit", "Data hygiene", "EDA"],
                "phase_2": ["Feature selection", "Domain validation"],
                "phase_3": ["Architecture selection"],
                "phase_4": [],
            },
        )
        mm.write_state(state)
        loaded = mm.read_state()

        assert loaded.phase == "phase_3"
        assert loaded.phase_states == {
            "phase_1": "completed",
            "phase_2": "completed",
            "phase_3": "active",
            "phase_4": "pending",
        }
        assert loaded.completed_subtasks_by_phase["phase_1"] == [
            "Data audit", "Data hygiene", "EDA",
        ]
        assert loaded.completed_subtasks_by_phase["phase_2"] == [
            "Feature selection", "Domain validation",
        ]
        assert loaded.completed_subtasks_by_phase["phase_3"] == ["Architecture selection"]
        assert loaded.completed_subtasks_by_phase["phase_4"] == []

    def test_empty_phase_states_round_trip(self, mm: MemoryManager) -> None:
        """Backward compat: STATE.md without ## Phases section still parses."""
        state = SessionState(phase="phase_1")
        mm.write_state(state)
        loaded = mm.read_state()

        assert loaded.phase_states == {}
        assert loaded.completed_subtasks_by_phase == {}


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    """Atomic write via temp file + os.replace."""

    def test_temp_file_cleaned_up(self, mm: MemoryManager) -> None:
        state = SessionState()
        mm.write_state(state)

        tmp_path = mm.memory_root / ".STATE.md.tmp"
        assert not tmp_path.exists(), "Temp file should be removed after atomic rename"
        assert (mm.memory_root / "STATE.md").exists()

    def test_overwrite_preserves_atomicity(self, mm: MemoryManager) -> None:
        """Writing twice should leave no temp file and update content."""
        mm.write_state(SessionState(phase="phase-1"))
        mm.write_state(SessionState(phase="phase-2"))

        loaded = mm.read_state()
        assert loaded.phase == "phase-2"
        assert not (mm.memory_root / ".STATE.md.tmp").exists()


# ---------------------------------------------------------------------------
# STATE.md — missing / corrupt
# ---------------------------------------------------------------------------


class TestStateMissingCorrupt:
    """Graceful handling of missing or broken STATE.md."""

    def test_missing_state_returns_defaults(self, mm: MemoryManager) -> None:
        state = mm.read_state()
        assert state.mode == "build"
        assert state.phase == "init"

    def test_corrupt_state_returns_defaults(self, mm: MemoryManager) -> None:
        mm.memory_root.mkdir(parents=True, exist_ok=True)
        (mm.memory_root / "STATE.md").write_text("not valid state", encoding="utf-8")
        state = mm.read_state()
        # Should get defaults without crashing
        assert state.phase == "init"


# ---------------------------------------------------------------------------
# DECISION_LOG.md
# ---------------------------------------------------------------------------


class TestDecisionLog:
    """Append-only decision log tests."""

    def test_append_and_read_single(self, mm: MemoryManager) -> None:
        entry = DecisionEntry(
            title="Use PyTorch",
            timestamp=datetime(2026, 4, 9, 14, 0, 0, tzinfo=UTC),
            context="Need a deep learning framework",
            decision="Use PyTorch over TensorFlow",
            rationale="Team expertise and flexibility",
            alternatives_considered="TensorFlow, JAX",
            outcome="proceed",
            confidence=Confidence.HIGH,
        )
        mm.append_decision(entry)
        decisions = mm.read_decisions()

        assert len(decisions) == 1
        assert decisions[0].title == "Use PyTorch"
        assert decisions[0].confidence == "high"

    def test_append_preserves_order(self, mm: MemoryManager) -> None:
        for i in range(5):
            mm.append_decision(
                DecisionEntry(
                    title=f"Decision {i}",
                    timestamp=datetime(2026, 4, 9, i, 0, 0, tzinfo=UTC),
                )
            )
        decisions = mm.read_decisions()

        assert len(decisions) == 5
        assert [d.title for d in decisions] == [f"Decision {i}" for i in range(5)]

    def test_empty_log_returns_empty_list(self, mm: MemoryManager) -> None:
        assert mm.read_decisions() == []

    def test_parse_real_markdown(self) -> None:
        """Parse a realistic DECISION_LOG.md fragment."""
        text = (
            "## Decision: Use cosine similarity\n"
            "**Timestamp**: 2026-04-09T10:00:00Z\n"
            "**Context**: Need a distance metric\n"
            "**Decision**: Cosine similarity over L2\n"
            "**Rationale**: Better for text embeddings\n"
            "**Alternatives Considered**: L2, dot product\n"
            "**Outcome**: implemented\n"
            "**Confidence**: high\n"
            "---\n"
            "\n"
            "## Decision: Pin fastembed version\n"
            "**Timestamp**: 2026-04-09T11:00:00Z\n"
            "**Context**: Reproducibility concern\n"
            "**Decision**: Pin to 0.3.1\n"
            "**Rationale**: Avoid breaking changes\n"
            "**Alternatives Considered**: Use latest\n"
            "**Outcome**: pending\n"
            "**Confidence**: medium\n"
            "---\n"
        )
        entries = _parse_decisions(text)
        assert len(entries) == 2
        assert entries[0].title == "Use cosine similarity"
        assert entries[0].outcome == "implemented"
        assert entries[1].title == "Pin fastembed version"
        assert entries[1].confidence == "medium"


# ---------------------------------------------------------------------------
# PRIORS.md
# ---------------------------------------------------------------------------


class TestPriors:
    """PRIORS.md read / write / seed / supersede."""

    def test_append_and_read(self, mm: MemoryManager) -> None:
        prior = PriorEntry(
            category="deployment",
            statement="K8s pods need resource limits",
            evidence="OOM kill in staging",
            confidence=Confidence.HIGH,
        )
        mm.append_prior(prior)
        priors = mm.read_priors()

        assert len(priors) == 1
        assert priors[0].category == "deployment"
        assert priors[0].superseded_by is None

    def test_seed_from_plain_text(self, mm: MemoryManager) -> None:
        plan_text = "- Always validate input shapes\n- Use mixed precision training\n"
        mm.seed_priors(plan_text)
        priors = mm.read_priors()

        assert len(priors) == 2
        assert priors[0].statement == "Always validate input shapes"
        assert priors[0].evidence == "seeded from plan.md"

    def test_seed_from_structured_blocks(self, mm: MemoryManager) -> None:
        structured = (
            "## Prior: architecture\n"
            "**Statement**: Microservices over monolith\n"
            "**Evidence**: Team scaling needs\n"
            "**Confidence**: high\n"
            "**Superseded By**: null\n"
            "---\n"
        )
        mm.seed_priors(structured)
        priors = mm.read_priors()

        assert len(priors) == 1
        assert priors[0].category == "architecture"

    def test_supersede(self, mm: MemoryManager) -> None:
        mm.append_prior(
            PriorEntry(category="infra", statement="Use EC2", confidence=Confidence.MEDIUM)
        )
        mm.append_prior(
            PriorEntry(category="infra", statement="Use ECS", confidence=Confidence.HIGH)
        )
        updated = mm.supersede_prior("infra", "Prior: serverless migration")

        assert updated == 2
        priors = mm.read_priors()
        assert all(p.superseded_by == "Prior: serverless migration" for p in priors)

    def test_empty_priors(self, mm: MemoryManager) -> None:
        assert mm.read_priors() == []


# ---------------------------------------------------------------------------
# Session summaries
# ---------------------------------------------------------------------------


class TestSessionSummaries:
    """Session summary write + read_recent."""

    def test_write_and_read(self, mm: MemoryManager) -> None:
        summary = SessionSummary(
            date="2026-04-09",
            duration="45 minutes",
            mode=OperatingMode.BUILD,
            agent="orchestrator",
            accomplished=["Set up data pipeline", "Wrote tests"],
            decisions_made=["Use PyTorch"],
            blockers_hit=["Missing GPU access"],
            next_steps=["Request GPU quota"],
            files_changed=["src/model.py: initial model"],
            estimated_completion="2026-04-15",
            open_questions=["Which optimizer?"],
            recommended_next_phase="training",
        )
        path = mm.write_session_summary(summary)

        assert path.exists()
        assert "session-" in path.name

        summaries = mm.read_recent_summaries(count=5)
        assert len(summaries) == 1
        s = summaries[0]
        assert s.date == "2026-04-09"
        assert s.duration == "45 minutes"
        assert "Set up data pipeline" in s.accomplished
        assert s.estimated_completion == "2026-04-15"
        assert s.recommended_next_phase == "training"

    def test_read_recent_returns_most_recent_first(self, mm: MemoryManager) -> None:
        """Multiple summaries are returned newest-first."""
        from unittest.mock import patch as _patch

        for i in range(5):
            ts = f"2026-04-0{i + 1}-120000"
            fake_now = datetime(2026, 4, i + 1, 12, 0, 0, tzinfo=UTC)
            with _patch("zo.memory.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                # Directly write with a unique filename
                sessions_dir = mm.memory_root / "sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                from zo.memory import _render_session_summary

                summary = SessionSummary(
                    date=f"2026-04-0{i + 1}",
                    accomplished=[f"task-{i}"],
                )
                path = sessions_dir / f"session-{ts}.md"
                path.write_text(_render_session_summary(summary), encoding="utf-8")

        summaries = mm.read_recent_summaries(count=3)
        assert len(summaries) == 3
        # Most recent first (sorted by filename descending)
        assert summaries[0].date == "2026-04-05"
        assert summaries[1].date == "2026-04-04"
        assert summaries[2].date == "2026-04-03"

    def test_read_empty_sessions(self, mm: MemoryManager) -> None:
        assert mm.read_recent_summaries() == []


# ---------------------------------------------------------------------------
# Session recovery
# ---------------------------------------------------------------------------


class TestSessionRecovery:
    """Recovery from valid, missing, and corrupt STATE.md."""

    def test_recover_valid_state(self, mm: MemoryManager) -> None:
        state = SessionState(
            phase="training",
            mode=OperatingMode.CONTINUE,
            git_head="abc123",
        )
        mm.write_state(state)

        with patch.object(mm, "_get_git_head", return_value="abc123"):
            recovered = mm.recover_session()

        assert recovered.phase == "training"
        assert recovered.mode == "continue"

    def test_recover_missing_state(self, mm: MemoryManager) -> None:
        with patch.object(mm, "_get_git_head", return_value="def456"):
            recovered = mm.recover_session()

        assert recovered.mode == "build"
        assert recovered.git_head == "def456"

    def test_recover_corrupt_state(self, mm: MemoryManager) -> None:
        mm.memory_root.mkdir(parents=True, exist_ok=True)
        (mm.memory_root / "STATE.md").write_text("{{{{ garbage", encoding="utf-8")

        with patch.object(mm, "_get_git_head", return_value="ghi789"):
            recovered = mm.recover_session()

        # Falls back to defaults since STATE.md is corrupt
        assert recovered.mode == "build"

    def test_recover_detects_git_mismatch(self, mm: MemoryManager) -> None:
        state = SessionState(git_head="old_head", phase="building")
        mm.write_state(state)

        with patch.object(mm, "_get_git_head", return_value="new_head"):
            recovered = mm.recover_session()

        assert recovered.git_head == "new_head"
        assert any("git_head mismatch" in b for b in recovered.active_blockers)


# ---------------------------------------------------------------------------
# initialize_project
# ---------------------------------------------------------------------------


class TestInitializeProject:
    """Project initialization creates correct directory structure."""

    def test_creates_dirs_and_files(self, mm: MemoryManager) -> None:
        mm.initialize_project()

        assert mm.memory_root.exists()
        assert (mm.memory_root / "sessions").is_dir()
        assert (mm.memory_root / "STATE.md").exists()
        assert (mm.memory_root / "DECISION_LOG.md").exists()
        assert (mm.memory_root / "PRIORS.md").exists()

    def test_idempotent(self, mm: MemoryManager) -> None:
        mm.initialize_project()
        # Write some data
        mm.write_state(SessionState(phase="has-data"))
        # Re-init should not destroy existing files
        mm.initialize_project()
        state = mm.read_state()
        assert state.phase == "has-data"


# ---------------------------------------------------------------------------
# Auto-create directories
# ---------------------------------------------------------------------------


class TestAutoCreateDirs:
    """Operations on missing directories should create them."""

    def test_write_state_creates_dirs(self, mm: MemoryManager) -> None:
        assert not mm.memory_root.exists()
        mm.write_state(SessionState())
        assert mm.memory_root.exists()

    def test_append_decision_creates_dirs(self, mm: MemoryManager) -> None:
        assert not mm.memory_root.exists()
        mm.append_decision(DecisionEntry(title="test"))
        assert (mm.memory_root / "DECISION_LOG.md").exists()

    def test_append_prior_creates_dirs(self, mm: MemoryManager) -> None:
        assert not mm.memory_root.exists()
        mm.append_prior(PriorEntry(category="test", statement="test"))
        assert (mm.memory_root / "PRIORS.md").exists()

    def test_write_summary_creates_dirs(self, mm: MemoryManager) -> None:
        assert not mm.memory_root.exists()
        mm.write_session_summary(SessionSummary())
        assert (mm.memory_root / "sessions").is_dir()


# ---------------------------------------------------------------------------
# Render / parse unit tests
# ---------------------------------------------------------------------------


class TestRenderParse:
    """Low-level render and parse functions."""

    def test_state_render_parse_identity(self) -> None:
        state = SessionState(
            timestamp=datetime(2026, 4, 9, 14, 32, 0, tzinfo=UTC),
            mode=OperatingMode.MAINTAIN,
            phase="deployment",
            last_completed_subtask="run integration tests",
            active_blockers=["DNS not configured"],
            next_steps=["configure DNS", "deploy canary"],
            active_agents=["infra-eng"],
            git_head="deadbeef",
        )
        text = _render_state(state)
        parsed = _parse_state(text)

        assert parsed.mode == "maintain"
        assert parsed.phase == "deployment"
        assert parsed.active_blockers == ["DNS not configured"]

    def test_decision_render_parse(self) -> None:
        entry = DecisionEntry(
            title="Choose optimizer",
            timestamp=datetime(2026, 4, 9, 10, 0, 0, tzinfo=UTC),
            context="Training loop setup",
            decision="AdamW",
            rationale="Good default for transformers",
            alternatives_considered="SGD, Adam",
            outcome="implemented",
            confidence=Confidence.HIGH,
        )
        text = _render_decision(entry)
        parsed = _parse_decisions(text)

        assert len(parsed) == 1
        assert parsed[0].title == "Choose optimizer"
        assert parsed[0].outcome == "implemented"

    def test_prior_render_parse(self) -> None:
        entry = PriorEntry(
            category="ml",
            statement="Learning rate 3e-4 works for BERT fine-tuning",
            evidence="Experiment log #42",
            confidence=Confidence.HIGH,
            superseded_by=None,
        )
        text = _render_prior(entry)
        parsed = _parse_priors(text)

        assert len(parsed) == 1
        assert parsed[0].statement == "Learning rate 3e-4 works for BERT fine-tuning"
        assert parsed[0].superseded_by is None


# ---------------------------------------------------------------------------
# MemoryManager — memory_root override
# ---------------------------------------------------------------------------


class TestMemoryRootOverride:
    """MemoryManager respects the optional memory_root kwarg."""

    def test_custom_memory_root(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom" / "memory"
        mm = MemoryManager(
            project_dir=tmp_path, project_name="proj", memory_root=custom_root,
        )
        assert mm.memory_root == custom_root

    def test_default_memory_root(self, tmp_path: Path) -> None:
        mm = MemoryManager(project_dir=tmp_path, project_name="proj")
        assert mm.memory_root == tmp_path / "memory" / "proj"
