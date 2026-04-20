"""Experiment capture layer for Zero Operators.

Every Phase 4 iteration is recorded as a structured experiment in
``.zo/experiments/`` so future runs, dashboards, and the eventual
autonomous-iteration loop have a grounded, queryable history to
design against.

Shape::

    .zo/experiments/
    ├── registry.json                   # flat list of all experiments
    ├── exp-001/
    │   ├── hypothesis.md               # Model Builder, pre-run
    │   ├── config.yaml                 # frozen config snapshot
    │   ├── metrics.jsonl               # ZOTrainingCallback output
    │   ├── training_status.json        # ZOTrainingCallback output
    │   ├── result.md                   # Oracle, post-eval
    │   ├── diagnosis.md                # XAI / Domain Eval (optional)
    │   └── next.md                     # Model Builder, post-result
    └── exp-002/ ...

Responsibilities split cleanly:

* **This module** owns: the pydantic models, registry JSON I/O,
  experiment scaffolding (``mint_experiment``), and markdown parsers
  that read what agents wrote.
* **Agents** own: writing ``hypothesis.md``, ``result.md``, ``next.md``,
  ``diagnosis.md`` per their contracts.
* **Orchestrator** (separate module) owns: calling ``mint_experiment``
  at Phase 4 entry and ``update_result`` at gate check.

Typical usage::

    from zo.experiments import (
        load_registry, mint_experiment, parse_result_md, update_result,
    )
    reg = load_registry(Path(".zo/experiments"))
    exp = mint_experiment(
        registry_dir=Path(".zo/experiments"),
        project="prod-001", phase="phase_4",
        hypothesis="TFT beats LSTM on long-horizon",
        rationale="LSTM degrades past horizon-3",
    )
    # ... agent writes result.md ...
    result = parse_result_md(exp.artifacts_dir / "result.md")
    update_result(registry_dir=Path(".zo/experiments"),
                  exp_id=exp.id, result=result)
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003 -- used at runtime
from typing import Literal

import yaml
from pydantic import BaseModel, Field

__all__ = [
    "SCHEMA_VERSION",
    "ExperimentStatus",
    "PrimaryMetric",
    "ExperimentResult",
    "Experiment",
    "ExperimentRegistry",
    "load_registry",
    "save_registry",
    "mint_experiment",
    "update_result",
    "update_status",
    "update_next_ideas",
    "parse_result_md",
    "parse_hypothesis_md",
    "parse_next_md",
    "render_hypothesis_md",
    "next_exp_id",
    "REGISTRY_FILENAME",
    "EXPERIMENTS_DIR_NAME",
]


# Bump when the registry schema changes in a non-backward-compatible way.
SCHEMA_VERSION = 1

REGISTRY_FILENAME = "registry.json"
"""Filename for the flat experiment registry inside ``.zo/experiments/``."""

EXPERIMENTS_DIR_NAME = "experiments"
"""Relative name of the experiments directory inside ``.zo/``."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExperimentStatus(StrEnum):
    """Lifecycle status of a single experiment."""

    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTED = "aborted"


class PrimaryMetric(BaseModel):
    """The single metric the experiment is optimizing against.

    Attributes:
        name: Metric identifier (e.g. ``"mae_t+3"``, ``"accuracy"``).
        value: Evaluated value on the test set.
        delta_vs_parent: Signed change vs parent experiment's primary
            metric. ``None`` for the root experiment (no parent) or when
            comparison is not meaningful.
    """

    name: str
    value: float
    delta_vs_parent: float | None = None


class ExperimentResult(BaseModel):
    """Evaluation outcome for a single experiment.

    Written by the Oracle to ``result.md`` after test-set eval, parsed
    back into this model by ``parse_result_md``.

    Attributes:
        oracle_tier: Which tier in the plan's oracle did this experiment
            meet? ``"must_pass"`` / ``"should_pass"`` / ``"could_pass"``
            / ``"fail"``.
        primary_metric: The headline metric (see ``PrimaryMetric``).
        secondary_metrics: Supporting metrics keyed by name.
        shortfalls: Bulleted observations about where the experiment
            fell short. Seeds the next experiment's hypothesis.
        evaluated_at: Timestamp of the evaluation (UTC).
    """

    oracle_tier: Literal["must_pass", "should_pass", "could_pass", "fail"]
    primary_metric: PrimaryMetric
    secondary_metrics: dict[str, float] = Field(default_factory=dict)
    shortfalls: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Experiment(BaseModel):
    """One experiment record in the registry.

    Attributes:
        id: Sequential identifier, format ``"exp-NNN"``.
        phase: Phase in which the experiment was run (usually
            ``"phase_4"``).
        parent_id: Exp-id this one iterates on. ``None`` for the
            root experiment of a phase.
        created: Mint time (UTC).
        hypothesis: One-sentence testable claim.
        rationale: Why this next, grounded in parent diagnosis.
        status: Lifecycle status.
        result: Populated after Oracle writes ``result.md``. ``None``
            while the experiment is still running.
        next_ideas: Proposed follow-up experiments (written by Model
            Builder to ``next.md`` post-result, parsed back to seed
            serial iterations).
        artifacts_dir: Path (relative to delivery repo root) where the
            experiment's files live, e.g.
            ``".zo/experiments/exp-001"``.
    """

    id: str
    phase: str
    parent_id: str | None = None
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    hypothesis: str = ""
    rationale: str = ""
    status: ExperimentStatus = ExperimentStatus.RUNNING
    result: ExperimentResult | None = None
    next_ideas: list[str] = Field(default_factory=list)
    artifacts_dir: str = ""

    model_config = {"use_enum_values": True}


class ExperimentRegistry(BaseModel):
    """Flat list of all experiments for a project.

    Persisted as ``.zo/experiments/registry.json``.

    Attributes:
        schema_version: Registry format version.
        project: Project identifier (for cross-reference with STATE).
        created: Registry creation time.
        experiments: All experiments in mint order.
    """

    schema_version: int = SCHEMA_VERSION
    project: str
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    experiments: list[Experiment] = Field(default_factory=list)

    model_config = {"use_enum_values": True}

    # -- Query helpers ------------------------------------------------------

    def find(self, exp_id: str) -> Experiment | None:
        """Return the experiment with ``exp_id`` or ``None``."""
        for e in self.experiments:
            if e.id == exp_id:
                return e
        return None

    def children_of(self, exp_id: str) -> list[Experiment]:
        """Return all experiments whose ``parent_id`` is ``exp_id``."""
        return [e for e in self.experiments if e.parent_id == exp_id]

    def latest_in_phase(self, phase: str) -> Experiment | None:
        """Return the most recently minted experiment for a phase."""
        candidates = [e for e in self.experiments if e.phase == phase]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.created)

    def lineage(self, exp_id: str) -> list[Experiment]:
        """Return ancestor chain for ``exp_id``, root first, self last."""
        chain: list[Experiment] = []
        current = self.find(exp_id)
        while current is not None:
            chain.append(current)
            if current.parent_id is None:
                break
            current = self.find(current.parent_id)
        return list(reversed(chain))


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------


def _registry_path(registry_dir: Path) -> Path:
    return registry_dir / REGISTRY_FILENAME


def load_registry(registry_dir: Path, project: str = "") -> ExperimentRegistry:
    """Load the registry from ``{registry_dir}/registry.json``.

    When the file doesn't exist, returns a fresh empty registry (callers
    can then ``save_registry`` to persist it). ``project`` is only used
    for initialization — if a registry already exists, its ``project``
    field is preserved.
    """
    path = _registry_path(registry_dir)
    if not path.is_file():
        return ExperimentRegistry(project=project)
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ExperimentRegistry.model_validate(raw)


def save_registry(registry_dir: Path, registry: ExperimentRegistry) -> Path:
    """Atomically write the registry to ``{registry_dir}/registry.json``."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    path = _registry_path(registry_dir)
    tmp = registry_dir / f".{REGISTRY_FILENAME}.tmp"
    tmp.write_text(
        registry.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------


def next_exp_id(registry: ExperimentRegistry) -> str:
    """Return the next sequential ``exp-NNN`` id for this registry."""
    if not registry.experiments:
        return "exp-001"
    # Parse existing ids; fall back to count+1 if any don't match pattern.
    numbers: list[int] = []
    for e in registry.experiments:
        match = re.match(r"^exp-(\d+)$", e.id)
        if match:
            numbers.append(int(match.group(1)))
    if not numbers:
        return f"exp-{len(registry.experiments) + 1:03d}"
    return f"exp-{max(numbers) + 1:03d}"


def mint_experiment(
    registry_dir: Path,
    project: str,
    phase: str,
    hypothesis: str = "",
    rationale: str = "",
    parent_id: str | None = None,
) -> Experiment:
    """Mint a new experiment.

    Creates ``{registry_dir}/{exp_id}/``, appends the entry to the
    registry, persists it, and returns the new Experiment. The caller
    (orchestrator) typically passes ``hypothesis`` and ``rationale``
    empty — Model Builder fills ``hypothesis.md`` itself, which is then
    read via ``parse_hypothesis_md`` to update the registry.
    """
    registry = load_registry(registry_dir, project=project)
    # Preserve registry-level project on first create.
    if not registry.project:
        registry.project = project

    exp_id = next_exp_id(registry)
    artifacts_dir = registry_dir / exp_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    exp = Experiment(
        id=exp_id,
        phase=phase,
        parent_id=parent_id,
        hypothesis=hypothesis,
        rationale=rationale,
        status=ExperimentStatus.RUNNING,
        artifacts_dir=str(artifacts_dir),
    )
    registry.experiments.append(exp)
    save_registry(registry_dir, registry)
    return exp


# ---------------------------------------------------------------------------
# Registry mutations
# ---------------------------------------------------------------------------


def update_result(
    registry_dir: Path, exp_id: str, result: ExperimentResult,
) -> Experiment:
    """Attach ``result`` to an experiment and mark it complete."""
    registry = load_registry(registry_dir)
    exp = registry.find(exp_id)
    if exp is None:
        raise ValueError(
            f"Experiment '{exp_id}' not found in registry at {registry_dir}",
        )
    # Compute delta_vs_parent if parent has a comparable primary metric.
    if exp.parent_id and result.primary_metric.delta_vs_parent is None:
        parent = registry.find(exp.parent_id)
        if (
            parent is not None
            and parent.result is not None
            and parent.result.primary_metric.name == result.primary_metric.name
        ):
            result.primary_metric.delta_vs_parent = (
                result.primary_metric.value
                - parent.result.primary_metric.value
            )
    exp.result = result
    exp.status = ExperimentStatus.COMPLETE
    save_registry(registry_dir, registry)
    return exp


def update_status(
    registry_dir: Path, exp_id: str, status: ExperimentStatus,
) -> Experiment:
    """Set the status of an experiment (e.g. to ``failed`` or ``aborted``)."""
    registry = load_registry(registry_dir)
    exp = registry.find(exp_id)
    if exp is None:
        raise ValueError(
            f"Experiment '{exp_id}' not found in registry at {registry_dir}",
        )
    exp.status = status
    save_registry(registry_dir, registry)
    return exp


def update_next_ideas(
    registry_dir: Path, exp_id: str, next_ideas: list[str],
) -> Experiment:
    """Attach proposed follow-up experiments to a completed experiment."""
    registry = load_registry(registry_dir)
    exp = registry.find(exp_id)
    if exp is None:
        raise ValueError(
            f"Experiment '{exp_id}' not found in registry at {registry_dir}",
        )
    exp.next_ideas = list(next_ideas)
    save_registry(registry_dir, registry)
    return exp


# ---------------------------------------------------------------------------
# Markdown parsers (read what agents wrote)
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return ``(frontmatter_dict, body_text)`` from a MD+YAML file.

    Returns ``({}, text)`` when no frontmatter is present.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    fm = yaml.safe_load(match.group(1)) or {}
    return fm, match.group(2)


def parse_result_md(path: Path) -> ExperimentResult:
    """Parse an Oracle-authored ``result.md`` into an ExperimentResult.

    Expected format: YAML frontmatter with ``oracle_tier``,
    ``primary_metric: {name, value, [delta_vs_parent]}``,
    ``secondary_metrics: {name: value, ...}``, ``evaluated_at``.
    Shortfalls are parsed from a ``## Shortfalls`` markdown section
    (each ``- `` bullet becomes one entry).

    Raises:
        ValueError: when required frontmatter fields are missing.
    """
    text = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    if not fm:
        raise ValueError(f"No YAML frontmatter in {path}")
    required = {"oracle_tier", "primary_metric"}
    missing = required - fm.keys()
    if missing:
        raise ValueError(
            f"Missing required frontmatter fields in {path}: {sorted(missing)}",
        )
    pm = fm["primary_metric"]
    primary = PrimaryMetric(
        name=pm["name"], value=float(pm["value"]),
        delta_vs_parent=(
            float(pm["delta_vs_parent"])
            if pm.get("delta_vs_parent") is not None else None
        ),
    )
    secondary: dict[str, float] = {
        k: float(v) for k, v in (fm.get("secondary_metrics") or {}).items()
    }
    shortfalls = _parse_bullets(body, "Shortfalls")

    evaluated_at = fm.get("evaluated_at")
    if isinstance(evaluated_at, str):
        evaluated_at_dt = datetime.fromisoformat(evaluated_at)
    elif isinstance(evaluated_at, datetime):
        evaluated_at_dt = evaluated_at
    else:
        evaluated_at_dt = datetime.now(UTC)

    return ExperimentResult(
        oracle_tier=fm["oracle_tier"],
        primary_metric=primary,
        secondary_metrics=secondary,
        shortfalls=shortfalls,
        evaluated_at=evaluated_at_dt,
    )


def parse_hypothesis_md(path: Path) -> tuple[str, str]:
    """Parse a ``hypothesis.md`` into ``(hypothesis, rationale)``.

    Hypothesis is the ``# Hypothesis`` section's first paragraph.
    Rationale is the ``## Rationale`` section's body (joined).
    Returns empty strings for missing sections.
    """
    text = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(text)
    hypothesis = _section_first_paragraph(body, level=1, heading="Hypothesis")
    rationale = _section_body(body, level=2, heading="Rationale")
    return hypothesis, rationale


def parse_next_md(path: Path) -> list[str]:
    """Parse a ``next.md`` into a list of proposed follow-up ideas.

    Each ``## exp-NNN`` section's first bullet (or first line) is one
    idea. Falls back to top-level bullets under a ``# Next experiments``
    heading when no per-exp subsections are present.
    """
    text = path.read_text(encoding="utf-8")
    ideas: list[str] = []
    sections = re.findall(
        r"^##\s+(exp-\d+)[^\n]*\n(.*?)(?=^##\s|\Z)",
        text, flags=re.MULTILINE | re.DOTALL,
    )
    for exp_name, body in sections:
        first_bullet = _first_bullet(body)
        label = first_bullet or body.strip().splitlines()[0] if body.strip() else ""
        if label:
            ideas.append(f"{exp_name}: {label}")
    if not ideas:
        ideas = _parse_bullets(text, "Next experiments")
    return ideas


# ---------------------------------------------------------------------------
# Markdown rendering (for module-internal writes when needed)
# ---------------------------------------------------------------------------


def render_hypothesis_md(exp: Experiment) -> str:
    """Render a hypothesis.md seed file from an Experiment.

    Useful for orchestrator-side scaffolding when the Model Builder
    hasn't authored its own hypothesis.md yet. Agents should normally
    overwrite this with their own content.
    """
    parent_line = exp.parent_id if exp.parent_id else "null"
    return f"""---
exp_id: {exp.id}
parent_id: {parent_line}
created: {exp.created.isoformat()}
---

# Hypothesis

{exp.hypothesis or "_TODO: state the testable claim in one sentence._"}

## Rationale

{exp.rationale or "_TODO: explain why this next, grounded in parent diagnosis._"}
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_bullets(text: str, heading: str) -> list[str]:
    """Return bullets under a ``#``-or-``##`` ``{heading}`` section.

    Matches either single- or double-hash headings so callers can share
    one helper for top-level sections (``# Next experiments``) and
    subsections (``## Shortfalls``).
    """
    pattern = re.compile(
        rf"^#{{1,2}}\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,2}}\s|\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return []
    section = match.group(1)
    return [
        line.strip()[2:].strip()
        for line in section.splitlines()
        if line.strip().startswith("- ")
    ]


def _first_bullet(text: str) -> str:
    """Return the first ``- bullet`` in ``text`` or ``""``."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped[2:].strip()
    return ""


def _section_first_paragraph(text: str, level: int, heading: str) -> str:
    """Return first paragraph under ``{'#'*level} {heading}``."""
    pattern = re.compile(
        rf"^{'#' * level}\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,{level + 1}}}\s|\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    # First paragraph = text until a blank line.
    lines: list[str] = []
    for raw in match.group(1).splitlines():
        if not raw.strip():
            if lines:
                break
            continue
        lines.append(raw.strip())
    return " ".join(lines).strip()


def _section_body(text: str, level: int, heading: str) -> str:
    """Return the full body under ``{'#'*level} {heading}``."""
    pattern = re.compile(
        rf"^{'#' * level}\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,{level + 1}}}\s|\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(1).strip()
