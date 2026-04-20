"""Unit tests for phase completion snapshots (zo.snapshots)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 -- used at runtime in fixtures

import yaml

from zo.snapshots import (
    SCHEMA_VERSION,
    PhaseSnapshot,
    list_snapshots,
    load_latest_snapshot,
    render_snapshot,
    write_snapshot,
)


def _make_snapshot(**overrides) -> PhaseSnapshot:
    """Build a fully-populated snapshot for tests."""
    defaults = {
        "phase_id": "phase_2",
        "phase_name": "Feature Engineering",
        "status": "completed",
        "gate_decision": "automated",
        "gate_outcome": "proceed",
        "completed_at": datetime(2026, 4, 20, 14, 30, 0, tzinfo=UTC),
        "duration_seconds": 13320,
        "iterations": 1,
        "subtasks_total": 3,
        "subtasks_completed": 3,
        "completed_subtask_ids": ["2.1 Generation", "2.2 Filtering", "2.3 Docs"],
        "remaining_subtask_ids": [],
        "required_artifacts": ["data/features.parquet", "reports/feat.md"],
        "artifacts_present": ["data/features.parquet", "reports/feat.md"],
        "artifacts_missing": [],
        "recent_decisions": [
            {"timestamp": "2026-04-20T13:00:00+00:00", "title": "Dropped weak features"},
        ],
        "issues": [],
        "handoff_to_next": "Handoff note for Phase 3.",
    }
    defaults.update(overrides)
    return PhaseSnapshot(**defaults)


class TestPhaseSnapshotModel:
    def test_defaults_schema_version(self) -> None:
        snap = PhaseSnapshot(
            phase_id="phase_1", phase_name="Data", status="completed",
            gate_decision="automated", gate_outcome="proceed",
        )
        assert snap.schema_version == SCHEMA_VERSION
        assert snap.iterations == 1

    def test_completed_at_defaults_to_now(self) -> None:
        snap = PhaseSnapshot(
            phase_id="phase_1", phase_name="Data", status="completed",
            gate_decision="automated", gate_outcome="proceed",
        )
        # Should be a recent UTC timestamp.
        now = datetime.now(UTC)
        assert (now - snap.completed_at).total_seconds() < 5


class TestRenderSnapshot:
    def test_frontmatter_parses_as_yaml(self) -> None:
        text = render_snapshot(_make_snapshot())
        assert text.startswith("---\n")
        end = text.index("\n---\n", 4)
        fm = yaml.safe_load(text[4:end])
        assert fm["phase_id"] == "phase_2"
        assert fm["schema_version"] == SCHEMA_VERSION
        assert fm["subtasks_total"] == 3

    def test_body_contains_subtasks_block(self) -> None:
        text = render_snapshot(_make_snapshot())
        assert "- [x] 2.1 Generation" in text
        assert "- [x] 2.2 Filtering" in text

    def test_body_contains_artifacts_table(self) -> None:
        text = render_snapshot(_make_snapshot())
        assert "| `data/features.parquet` | present |" in text

    def test_missing_artifacts_shown(self) -> None:
        snap = _make_snapshot(
            artifacts_present=["data/features.parquet"],
            artifacts_missing=["reports/feat.md"],
        )
        text = render_snapshot(snap)
        assert "| `reports/feat.md` | missing |" in text

    def test_duration_formatted(self) -> None:
        text = render_snapshot(_make_snapshot(duration_seconds=13320))
        assert "3h 42m" in text

    def test_duration_short_no_hours(self) -> None:
        text = render_snapshot(_make_snapshot(duration_seconds=300))
        assert "5m" in text

    def test_duration_none(self) -> None:
        text = render_snapshot(_make_snapshot(duration_seconds=None))
        assert "n/a" in text

    def test_no_decisions_placeholder(self) -> None:
        text = render_snapshot(_make_snapshot(recent_decisions=[]))
        assert "_No decisions logged" in text

    def test_no_issues_placeholder(self) -> None:
        text = render_snapshot(_make_snapshot(issues=[]))
        assert "_None._" in text

    def test_issues_rendered_with_severity(self) -> None:
        snap = _make_snapshot(issues=[
            {"severity": "warning", "message": "something shaky"},
        ])
        text = render_snapshot(snap)
        assert "**WARNING**" in text
        assert "something shaky" in text

    def test_handoff_falls_back_to_placeholder(self) -> None:
        text = render_snapshot(_make_snapshot(handoff_to_next=""))
        assert "_No narrative handoff recorded._" in text

    def test_notes_only_shown_when_present(self) -> None:
        no_notes = render_snapshot(_make_snapshot(notes=""))
        assert "## Notes" not in no_notes
        with_notes = render_snapshot(_make_snapshot(notes="Oracle passed at tier 1."))
        assert "## Notes" in with_notes
        assert "Oracle passed at tier 1." in with_notes


class TestWriteSnapshot:
    def test_creates_snapshots_dir(self, tmp_path: Path) -> None:
        path = write_snapshot(tmp_path, _make_snapshot())
        assert path.exists()
        assert path.parent == tmp_path / "snapshots"

    def test_filename_includes_phase_and_timestamp(self, tmp_path: Path) -> None:
        path = write_snapshot(tmp_path, _make_snapshot())
        assert path.name.startswith("phase_2_")
        assert path.name.endswith(".md")
        assert "2026-04-20" in path.name

    def test_file_content_matches_render(self, tmp_path: Path) -> None:
        snap = _make_snapshot()
        path = write_snapshot(tmp_path, snap)
        assert path.read_text(encoding="utf-8") == render_snapshot(snap)

    def test_idempotent_with_different_timestamps(self, tmp_path: Path) -> None:
        a = _make_snapshot(completed_at=datetime(2026, 4, 20, 14, 30, 0, tzinfo=UTC))
        b = _make_snapshot(completed_at=datetime(2026, 4, 20, 15, 0, 0, tzinfo=UTC))
        write_snapshot(tmp_path, a)
        write_snapshot(tmp_path, b)
        files = list((tmp_path / "snapshots").glob("*.md"))
        assert len(files) == 2


class TestListAndLoad:
    def test_list_empty(self, tmp_path: Path) -> None:
        assert list_snapshots(tmp_path) == []

    def test_list_returns_newest_first(self, tmp_path: Path) -> None:
        older = _make_snapshot(completed_at=datetime(2026, 4, 20, 10, 0, 0, tzinfo=UTC))
        newer = _make_snapshot(completed_at=datetime(2026, 4, 20, 18, 0, 0, tzinfo=UTC))
        write_snapshot(tmp_path, older)
        write_snapshot(tmp_path, newer)
        paths = list_snapshots(tmp_path)
        assert len(paths) == 2
        assert "18-00-00" in paths[0].name
        assert "10-00-00" in paths[1].name

    def test_list_filters_by_phase_id(self, tmp_path: Path) -> None:
        write_snapshot(tmp_path, _make_snapshot(phase_id="phase_1"))
        write_snapshot(tmp_path, _make_snapshot(phase_id="phase_2"))
        only_phase_1 = list_snapshots(tmp_path, phase_id="phase_1")
        assert len(only_phase_1) == 1
        assert "phase_1" in only_phase_1[0].name

    def test_load_latest_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert load_latest_snapshot(tmp_path, "phase_1") is None

    def test_load_latest_roundtrips_frontmatter(self, tmp_path: Path) -> None:
        original = _make_snapshot()
        write_snapshot(tmp_path, original)
        loaded = load_latest_snapshot(tmp_path, "phase_2")
        assert loaded is not None
        assert loaded.phase_id == original.phase_id
        assert loaded.phase_name == original.phase_name
        assert loaded.status == original.status
        assert loaded.subtasks_total == original.subtasks_total
        assert loaded.schema_version == SCHEMA_VERSION
