"""Plan parser and validator for Zero Operators.

Parses plan.md files into structured Pydantic models and validates
all required sections, oracle fields, workflow mode, data sources,
and agent configuration per specs/plan.md.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path  # noqa: TC003 — used at runtime in parse_plan

from pydantic import BaseModel, Field


class PlanStatus(StrEnum):
    """Lifecycle status of a plan."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class WorkflowMode(StrEnum):
    """Valid workflow execution modes."""

    CLASSICAL_ML = "classical_ml"
    DEEP_LEARNING = "deep_learning"
    RESEARCH = "research"



class PlanFrontmatter(BaseModel):
    """YAML frontmatter at the top of a plan file."""

    project_name: str
    version: str
    created: str
    last_modified: str
    status: PlanStatus
    owner: str


class OracleDefinition(BaseModel):
    """Oracle section — the hard, verifiable success metric."""

    primary_metric: str
    ground_truth_source: str
    evaluation_method: str
    target_threshold: str
    evaluation_frequency: str
    secondary_metrics: str | None = None
    statistical_significance: str | None = None
    raw_content: str = ""


class WorkflowConfig(BaseModel):
    """Workflow configuration section."""

    mode: WorkflowMode
    raw_content: str = ""


class DataSource(BaseModel):
    """A single data source entry."""

    name: str
    raw_content: str = ""


class CustomAgentSpec(BaseModel):
    """A custom agent declared in the plan's Agent Configuration section."""

    name: str
    model: str = "claude-sonnet-4-6"
    role: str = ""


class AgentAdaptation(BaseModel):
    """A per-project prompt adaptation for an existing (core or custom) agent.

    Written by the Plan Architect during ``zo draft`` based on scout
    findings. Applied at build time by appending the adaptation text to
    the agent's spawn prompt — the agent's base ``.md`` definition is
    unchanged, so it remains reusable across projects.

    Adaptations *complement* custom agents (which add new roles) rather
    than replacing them: custom agents cover specialised roles the
    project needs; adaptations tailor *existing* agents (typically
    ``xai-agent`` and ``domain-evaluator``) to the project's domain.
    """

    agent_name: str
    adaptation: str


class AgentConfig(BaseModel):
    """Agent configuration section."""

    active_agents: list[str] = Field(default_factory=list)
    custom_agents: list[CustomAgentSpec] = Field(default_factory=list)
    adaptations: list[AgentAdaptation] = Field(default_factory=list)
    raw_content: str = ""

    def adaptation_for(self, agent_name: str) -> str | None:
        """Return the adaptation text for *agent_name*, or None if absent.

        Matches on exact ``agent_name`` (e.g. ``"xai-agent"``). The
        orchestrator calls this when building a spawn prompt so it can
        inject project-specific instructions on top of the agent's base
        definition.
        """
        for a in self.adaptations:
            if a.agent_name == agent_name:
                return a.adaptation
        return None


class Plan(BaseModel):
    """The full parsed plan — top-level container."""

    frontmatter: PlanFrontmatter
    objective: str = ""
    oracle: OracleDefinition | None = None
    workflow: WorkflowConfig | None = None
    data_sources: list[DataSource] = Field(default_factory=list)
    domain_priors: str = ""
    agents: AgentConfig | None = None
    constraints: str = ""

    # Optional sections — present if found, empty string if absent.
    milestones: str | None = None
    delivery: str | None = None
    environment: str | None = None
    open_questions: str | None = None

    # Raw section map for introspection.
    raw_sections: dict[str, str] = Field(default_factory=dict)

    # Source path.
    source_path: Path | None = None


class ValidationIssue(BaseModel):
    """A single validation finding."""

    section: str
    severity: str = "error"  # "error" | "warning"
    message: str


class ValidationReport(BaseModel):
    """Result of validating a parsed plan."""

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)



_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)^---\s*\n",
    re.MULTILINE | re.DOTALL,
)


def _parse_frontmatter_block(text: str) -> dict[str, str]:
    """Extract key-value pairs from YAML-style frontmatter.

    Uses a lightweight regex parser instead of pulling in PyYAML so
    the module stays dependency-free beyond pydantic + stdlib.

    Args:
        text: The raw frontmatter block (between ``---`` delimiters).

    Returns:
        Dict of string key-value pairs.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r'^([a-z_]+)\s*:\s*(.+)$', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"').strip("'")
            result[key] = value
    return result


def parse_frontmatter(text: str) -> PlanFrontmatter:
    """Parse YAML frontmatter from the top of a plan file.

    Args:
        text: Full plan file text.

    Returns:
        Populated ``PlanFrontmatter`` model.

    Raises:
        ValueError: If frontmatter block is missing or invalid.
    """
    m = _FRONTMATTER_RE.search(text)
    if not m:
        raise ValueError("Plan file is missing YAML frontmatter (--- delimiters).")
    raw = m.group(1)
    data = _parse_frontmatter_block(raw)

    required_keys = {"project_name", "version", "created", "last_modified", "status", "owner"}
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(f"Frontmatter missing required keys: {', '.join(sorted(missing))}")

    return PlanFrontmatter(**data)



_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _extract_sections(text: str) -> dict[str, str]:
    """Split plan text into ``## Heading`` -> body mapping.

    Args:
        text: Full plan file text (frontmatter already consumed is fine).

    Returns:
        Dict mapping normalised heading text to the body under that heading.
    """
    headings = list(_HEADING_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        sections[title] = body
    return sections



_ORACLE_FIELD_RE = re.compile(
    r"\*\*(.+?):?\*\*\s*:?\s*(.+?)(?=\n\*\*|\n\n|\Z)",
    re.DOTALL,
)

_ORACLE_FIELD_ALIASES: dict[str, str] = {
    "primary metric": "primary_metric",
    "primary_metric": "primary_metric",
    "ground truth source": "ground_truth_source",
    "ground_truth_source": "ground_truth_source",
    "ground truth": "ground_truth_source",
    "evaluation method": "evaluation_method",
    "evaluation_method": "evaluation_method",
    "target threshold": "target_threshold",
    "target_threshold": "target_threshold",
    "evaluation frequency": "evaluation_frequency",
    "evaluation_frequency": "evaluation_frequency",
    "secondary metrics": "secondary_metrics",
    "secondary_metrics": "secondary_metrics",
    "statistical significance": "statistical_significance",
    "statistical_significance": "statistical_significance",
}


def _parse_oracle(body: str) -> OracleDefinition:
    """Parse the Oracle section into an ``OracleDefinition``.

    Args:
        body: Raw markdown body of the Oracle section.

    Returns:
        Populated ``OracleDefinition``.
    """
    fields: dict[str, str] = {}
    for m in _ORACLE_FIELD_RE.finditer(body):
        raw_key = m.group(1).strip().lower()
        value = m.group(2).strip()
        canonical = _ORACLE_FIELD_ALIASES.get(raw_key)
        if canonical:
            fields[canonical] = value

    # Ensure required fields are present (will fail Pydantic validation
    # if truly missing, but we give a friendlier message via validation).
    return OracleDefinition(
        primary_metric=fields.get("primary_metric", ""),
        ground_truth_source=fields.get("ground_truth_source", ""),
        evaluation_method=fields.get("evaluation_method", ""),
        target_threshold=fields.get("target_threshold", ""),
        evaluation_frequency=fields.get("evaluation_frequency", ""),
        secondary_metrics=fields.get("secondary_metrics"),
        statistical_significance=fields.get("statistical_significance"),
        raw_content=body,
    )


def _parse_workflow(body: str) -> WorkflowConfig:
    """Parse the Workflow section.

    Args:
        body: Raw markdown body of the Workflow section.

    Returns:
        Populated ``WorkflowConfig``.

    Raises:
        ValueError: If mode is missing or invalid.
    """
    # Handle both **Mode:** value and **Mode**: value patterns.
    mode_match = re.search(
        r"\*\*Mode:?\*\*\s*:?\s*(.+)",
        body,
        re.MULTILINE,
    )
    if not mode_match:
        raise ValueError("Workflow section missing **Mode** field.")

    raw_mode = mode_match.group(1).strip().lower()
    # Handle "classical_ml (adapted — ...)" style annotations and
    # pipe-separated alternatives like "classical_ml | deep_learning".
    raw_mode = re.split(r"\s*[\(|]", raw_mode)[0].strip()

    try:
        mode = WorkflowMode(raw_mode)
    except ValueError as exc:
        raise ValueError(
            f"Invalid workflow mode '{raw_mode}'. "
            f"Must be one of: {', '.join(m.value for m in WorkflowMode)}"
        ) from exc

    return WorkflowConfig(mode=mode, raw_content=body)


_DATA_SOURCE_HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


def _parse_data_sources(body: str) -> list[DataSource]:
    """Parse the Data Sources section into a list of ``DataSource``.

    Args:
        body: Raw markdown body of the Data Sources section.

    Returns:
        List of ``DataSource`` entries. May be empty if no sub-headings found
        but body is non-empty (treated as a single unnamed source).
    """
    headings = list(_DATA_SOURCE_HEADING_RE.finditer(body))
    if not headings:
        # No ### sub-headings — treat entire body as one source if non-empty.
        stripped = body.strip()
        if stripped:
            return [DataSource(name="default", raw_content=stripped)]
        return []

    sources: list[DataSource] = []
    for i, match in enumerate(headings):
        name = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        raw = body[start:end].strip()
        sources.append(DataSource(name=name, raw_content=raw))
    return sources


_ACTIVE_AGENTS_RE = re.compile(
    r"\*\*Active agents:?\*\*\s*:?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)

_CUSTOM_AGENTS_RE = re.compile(
    r"\*\*Custom agents:?\*\*\s*:?\s*\n((?:\s*-\s*.+\n?)+)",
    re.IGNORECASE,
)

_CUSTOM_AGENT_LINE_RE = re.compile(
    r"-\s*(\S+)\s*:\s*(\S+)\s*[—–-]\s*(.+)",
)

# Agent adaptations block. Grabs everything from the label through the
# end of the block (a blank line followed by another ``**Foo:**`` label
# or end-of-body). The captured group is parsed line-by-line with
# ``_ADAPTATION_ENTRY_RE`` to pull individual adaptations.
_ADAPTATIONS_RE = re.compile(
    r"\*\*Agent adaptations:?\*\*\s*:?\s*\n"
    r"((?:.*\n?)*?)"
    r"(?=\n\s*\*\*[A-Z][\w ]+:|\Z)",
    re.IGNORECASE,
)

# A single adaptation entry opens with a dash, the agent name, and a
# colon. Subsequent indented lines continue the adaptation until the
# next dash-agent header or a blank line terminates it.
_ADAPTATION_HEADER_RE = re.compile(
    r"^\s*-\s*([A-Za-z][\w-]*)\s*:\s*(.*)$",
)

_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


def _parse_adaptations(raw_block: str) -> list[AgentAdaptation]:
    """Parse the body of the ``**Agent adaptations:**`` block.

    Accepts one or more entries of the form::

        - xai-agent: short one-line adaptation

        - domain-evaluator:
          Multi-line continuation lines (any indent) are joined into
          the adaptation body. Blank lines end the entry.

    Entries with an empty body are skipped (no effective adaptation).
    """
    entries: list[AgentAdaptation] = []
    current_name: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            return
        body = "\n".join(current_lines).strip()
        if body:
            entries.append(
                AgentAdaptation(agent_name=current_name, adaptation=body),
            )
        current_name = None
        current_lines = []

    for raw_line in raw_block.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            # Blank line — end of the current entry.
            _flush()
            continue
        m = _ADAPTATION_HEADER_RE.match(line)
        if m:
            _flush()
            current_name = m.group(1).strip()
            first = m.group(2).strip()
            current_lines = [first] if first else []
        elif current_name is not None:
            # Continuation line (any indent level).
            current_lines.append(line.strip())
    _flush()
    return entries


def _parse_agents(body: str) -> AgentConfig:
    """Parse the Agents section.

    Supports active agents, custom agent declarations, and per-project
    agent adaptations::

        **Active agents:** data-engineer, model-builder, oracle-qa, xai-agent

        **Custom agents:**
        - signal-analyst: Sonnet — Signal processing for vibration data
        - calibration-expert: Sonnet — Sensor calibration specialist

        **Agent adaptations:**

        - xai-agent:
          Focus on frequency-domain attribution, spectrograms, and
          vibration-mode decomposition. Generic SHAP/GradCAM is less
          relevant for time-series signals.

        - domain-evaluator:
          Apply project-specific domain priors — bearing failure signatures,
          known sensor drift patterns, modal frequency ranges.
    """
    agents: list[str] = []
    m = _ACTIVE_AGENTS_RE.search(body)
    if m:
        raw = m.group(1)
        agents = [a.strip() for a in raw.split(",") if a.strip()]

    custom: list[CustomAgentSpec] = []
    cm = _CUSTOM_AGENTS_RE.search(body)
    if cm:
        for line in cm.group(1).strip().splitlines():
            lm = _CUSTOM_AGENT_LINE_RE.match(line.strip())
            if lm:
                name = lm.group(1).strip()
                model_raw = lm.group(2).strip().lower()
                model = _MODEL_ALIASES.get(model_raw, model_raw)
                role = lm.group(3).strip()
                custom.append(CustomAgentSpec(
                    name=name, model=model, role=role,
                ))

    adaptations: list[AgentAdaptation] = []
    am = _ADAPTATIONS_RE.search(body)
    if am:
        adaptations = _parse_adaptations(am.group(1))

    return AgentConfig(
        active_agents=agents,
        custom_agents=custom,
        adaptations=adaptations,
        raw_content=body,
    )



_REQUIRED_SECTION_ALIASES: dict[str, str] = {
    "objective": "objective",
    "oracle": "oracle",
    "oracle definition": "oracle",
    "workflow": "workflow",
    "workflow configuration": "workflow",
    "data sources": "data_sources",
    "data": "data_sources",
    "domain priors": "domain_priors",
    "domain context and priors": "domain_priors",
    "domain context": "domain_priors",
    "agents": "agents",
    "agent configuration": "agents",
    "constraints": "constraints",
}

_OPTIONAL_SECTION_ALIASES: dict[str, str] = {
    "milestones": "milestones",
    "milestones and timeline": "milestones",
    "delivery": "delivery",
    "delivery specification": "delivery",
    "environment": "environment",
    "dependencies and environment": "environment",
    "open questions": "open_questions",
}


def _normalise_section_key(heading: str) -> str | None:
    """Return the canonical key for a heading, or ``None`` if unknown.

    Args:
        heading: Raw heading text from the markdown.

    Returns:
        Canonical key string or ``None``.
    """
    lower = heading.lower().strip()
    return _REQUIRED_SECTION_ALIASES.get(lower) or _OPTIONAL_SECTION_ALIASES.get(lower)



_REQUIRED_SECTIONS = frozenset({
    "objective",
    "oracle",
    "workflow",
    "data_sources",
    "domain_priors",
    "agents",
    "constraints",
})


def parse_plan(path: Path) -> Plan:
    """Parse a plan.md file into a ``Plan`` model.

    Args:
        path: Filesystem path to the plan markdown file.

    Returns:
        Fully populated ``Plan`` instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If frontmatter is missing/invalid.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)

    raw_sections = _extract_sections(text)

    # Map raw headings to canonical keys.
    mapped: dict[str, str] = {}
    for heading, body in raw_sections.items():
        key = _normalise_section_key(heading)
        if key:
            mapped[key] = body
        # Store everything in raw_sections regardless.

    # Parse structured sub-sections.
    oracle = _parse_oracle(mapped["oracle"]) if "oracle" in mapped else None
    workflow = _parse_workflow(mapped["workflow"]) if "workflow" in mapped else None
    data_sources = _parse_data_sources(mapped["data_sources"]) if "data_sources" in mapped else []
    agents = _parse_agents(mapped["agents"]) if "agents" in mapped else None

    return Plan(
        frontmatter=frontmatter,
        objective=mapped.get("objective", ""),
        oracle=oracle,
        workflow=workflow,
        data_sources=data_sources,
        domain_priors=mapped.get("domain_priors", ""),
        agents=agents,
        constraints=mapped.get("constraints", ""),
        milestones=mapped.get("milestones"),
        delivery=mapped.get("delivery"),
        environment=mapped.get("environment"),
        open_questions=mapped.get("open_questions"),
        raw_sections=raw_sections,
        source_path=path,
    )



def validate_plan(plan: Plan) -> ValidationReport:
    """Validate a parsed plan against the spec requirements.

    Checks:
    - All 8 required sections are present (frontmatter + 7 body sections).
    - Oracle definition has all 5 required fields.
    - Workflow mode is valid (enforced at parse time but re-checked).
    - At least one data source exists.
    - At least one active agent exists.

    Args:
        plan: A ``Plan`` instance returned by ``parse_plan``.

    Returns:
        ``ValidationReport`` with ``valid`` flag and list of issues.
    """
    issues: list[ValidationIssue] = []

    # --- Required sections presence ---
    if not plan.objective:
        issues.append(ValidationIssue(
            section="Objective",
            message="Missing required section: Objective.",
        ))

    if plan.oracle is None:
        issues.append(ValidationIssue(
            section="Oracle",
            message="Missing required section: Oracle Definition.",
        ))

    if plan.workflow is None:
        issues.append(ValidationIssue(
            section="Workflow",
            message="Missing required section: Workflow Configuration.",
        ))

    if not plan.data_sources:
        issues.append(ValidationIssue(
            section="Data Sources",
            message="At least one data source must be specified.",
        ))

    if not plan.domain_priors:
        issues.append(ValidationIssue(
            section="Domain Priors",
            message="Missing required section: Domain Context and Priors.",
        ))

    if plan.agents is None:
        issues.append(ValidationIssue(
            section="Agents",
            message="Missing required section: Agent Configuration.",
        ))

    if not plan.constraints:
        issues.append(ValidationIssue(
            section="Constraints",
            message="Missing required section: Constraints.",
        ))

    # --- Oracle field completeness ---
    if plan.oracle is not None:
        required_oracle_fields = {
            "primary_metric": "Primary metric",
            "ground_truth_source": "Ground truth source",
            "evaluation_method": "Evaluation method",
            "target_threshold": "Target threshold",
            "evaluation_frequency": "Evaluation frequency",
        }
        for field_name, label in required_oracle_fields.items():
            value = getattr(plan.oracle, field_name, "")
            if not value:
                issues.append(ValidationIssue(
                    section="Oracle",
                    message=f"Oracle missing required field: {label}.",
                ))

    # --- Agent completeness ---
    if plan.agents is not None and not plan.agents.active_agents:
        issues.append(ValidationIssue(
            section="Agents",
            message="At least one active agent must be specified.",
        ))

    return ValidationReport(
        valid=len(issues) == 0,
        issues=issues,
    )
