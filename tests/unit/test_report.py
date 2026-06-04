"""Unit tests for the report-mode prompt builder (zo.report)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zo.memory import MemoryManager, PriorEntry
from zo.report import DEFAULT_REPORT_OBJECTIVE, build_report_prompt, report_add_dirs
from zo.surrogate import SurrogateLayout

if TYPE_CHECKING:
    from pathlib import Path


def _surrogate(tmp_path: Path) -> SurrogateLayout:
    return SurrogateLayout(
        surrogate_id="report-x",
        role="report",
        delivery_repo=tmp_path / "prod",
        worktree=tmp_path / "prod-report-x",
        branch="report/report-x",
        memory_root=tmp_path / "prod" / ".zo" / "surrogates" / "report-x",
    )


def _canonical(tmp_path: Path) -> MemoryManager:
    mem = tmp_path / "prod" / ".zo" / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    cm = MemoryManager(project_dir=tmp_path / "prod", project_name="prod", memory_root=mem)
    cm.append_prior(PriorEntry(category="domain", statement="Bearing defect frequencies matter"))
    return cm


def _build(tmp_path: Path, **kw: object) -> str:
    return build_report_prompt(
        project_name="prod",
        surrogate=_surrogate(tmp_path),
        canonical_memory=_canonical(tmp_path),
        main_delivery=tmp_path / "prod",
        **kw,
    )


def test_report_add_dirs(tmp_path: Path) -> None:
    s = _surrogate(tmp_path)
    assert report_add_dirs(s, tmp_path / "prod") == [str(s.worktree), str(tmp_path / "prod")]


def test_prompt_has_paths_and_team(tmp_path: Path) -> None:
    s = _surrogate(tmp_path)
    p = _build(tmp_path)
    assert "prod" in p
    assert str(s.worktree) in p
    assert s.branch in p
    assert str(s.memory_root) in p
    assert "experiments" in p
    assert "oracle-qa" in p
    assert "data-engineer" in p


def test_prompt_requires_opus_never_haiku(tmp_path: Path) -> None:
    p = _build(tmp_path)
    assert 'model="opus"' in p
    assert "Never" in p
    assert "Haiku" in p


def test_prompt_has_hard_boundaries(tmp_path: Path) -> None:
    p = _build(tmp_path)
    assert "NOT" in p
    assert "STATE.md" in p  # forbids writing canonical memory
    assert "experiment" in p.lower()  # forbids mutating experiments


def test_prompt_snapshot_includes_priors(tmp_path: Path) -> None:
    assert "Bearing defect frequencies matter" in _build(tmp_path)


def test_default_and_custom_objective(tmp_path: Path) -> None:
    assert DEFAULT_REPORT_OBJECTIVE in _build(tmp_path)
    assert "Write only the results section" in _build(
        tmp_path, objective="Write only the results section",
    )
