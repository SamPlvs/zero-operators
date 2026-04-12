"""Agentic plan generation from source documents.

Indexes a directory of source documents using the SemanticIndex, then
generates a plan.md that follows the 8-section schema from specs/plan.md.

Typical usage::

    from zo.draft import PlanDrafter
    drafter = PlanDrafter(source_dir=Path("docs"), project_name="alpha", zo_root=Path("."))
    count = drafter.index_documents()
    plan_path = drafter.generate_plan()
    valid = drafter.validate_draft(plan_path)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from zo.plan import parse_plan, validate_plan
from zo.semantic import IndexEntry, SemanticIndex

_SUPPORTED_EXTENSIONS = {".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}


class PlanDrafter:
    """Generates a plan.md from indexed source documents.

    Args:
        source_paths: Files and/or directories to index.
        project_name: Name for the generated project plan.
        zo_root: Root directory of the ZO repository.
        source_dir: Deprecated — use ``source_paths`` instead.
    """

    def __init__(
        self,
        project_name: str,
        zo_root: Path,
        *,
        source_paths: list[Path] | None = None,
        source_dir: Path | None = None,
    ) -> None:
        # Backwards compat: source_dir → source_paths
        if source_paths is not None:
            self._source_paths = [Path(p) for p in source_paths]
        elif source_dir is not None:
            self._source_paths = [Path(source_dir)]
        else:
            self._source_paths = []
        self._project_name = project_name
        self._zo_root = Path(zo_root)
        self._db_path = zo_root / "memory" / project_name / "draft_index.db"
        self._index = SemanticIndex(db_path=self._db_path)

    def index_documents(self) -> int:
        """Index documents from all source paths.

        Each path can be a file (indexed directly) or a directory
        (recursed for supported file types).

        Returns:
            Count of indexed documents.
        """
        count = 0
        for src in self._source_paths:
            if src.is_file():
                count += self._index_file(src, count)
            elif src.is_dir():
                for path in sorted(src.rglob("*")):
                    if path.is_file():
                        count += self._index_file(path, count)
        return count

    def _index_file(self, path: Path, offset: int) -> int:
        """Index a single file. Returns 1 on success, 0 on skip."""
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            return 0
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return 0

        lines = text.strip().splitlines()
        summary = lines[0][:200] if lines else path.name

        entry = IndexEntry(
            entry_id=f"doc-{offset:04d}",
            summary=f"[{path.name}] {summary}",
            full_text=text[:5000],
            source="document",
        )
        self._index.index_entry(entry)
        return 1

    def generate_plan(self) -> Path:
        """Generate a plan.md from indexed documents.

        Searches the index for key sections and assembles a plan template
        populated with content extracted from the source documents.

        Returns:
            Path to generated plan file.
        """
        plans_dir = self._zo_root / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"{self._project_name}.md"

        # Query for relevant content per section
        objective_hits = self._index.query("objective goal purpose", top_k=3)
        data_hits = self._index.query("data source dataset", top_k=3)
        domain_hits = self._index.query("domain knowledge prior assumption", top_k=3)
        metric_hits = self._index.query("metric evaluation success criteria", top_k=3)
        constraint_hits = self._index.query("constraint requirement limitation", top_k=3)

        now = datetime.now(UTC).strftime("%Y-%m-%d")

        sections = [
            "---",
            f'project_name: {self._project_name}',
            'version: "0.1.0"',
            f'created: "{now}"',
            f'last_modified: "{now}"',
            'status: active',
            'owner: "TODO"',
            "---",
            "",
            "## Objective",
            "",
            self._format_hits(objective_hits, "Define the project objective."),
            "",
            "## Oracle Definition",
            "",
            self._format_oracle(metric_hits),
            "",
            "## Workflow Configuration",
            "",
            "**Mode:** classical_ml",
            "",
            "## Data Sources",
            "",
            self._format_data_sources(data_hits),
            "",
            "## Domain Context and Priors",
            "",
            self._format_hits(domain_hits, "List domain knowledge and assumptions."),
            "",
            "## Agent Configuration",
            "",
            "**Active agents:** data-engineer, model-builder, oracle-qa, test-engineer",
            "",
            "## Constraints",
            "",
            self._format_hits(constraint_hits, "Define constraints."),
            "",
            "## Milestones and Timeline",
            "",
            "TODO: Define milestones.",
            "",
        ]

        plan_path.write_text("\n".join(sections), encoding="utf-8")
        return plan_path

    def generate_plan_from_description(self, description: str) -> Path:
        """Generate a plan.md from a free-text project description.

        Produces a structurally valid skeleton with the description seeded
        into appropriate sections. Designed to be fleshed out by the
        interactive Claude session.

        Args:
            description: Free-text project description from the user.

        Returns:
            Path to generated plan file.
        """
        plans_dir = self._zo_root / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"{self._project_name}.md"

        now = datetime.now(UTC).strftime("%Y-%m-%d")
        desc_lower = description.lower()

        # Infer workflow mode from description keywords
        dl_keywords = ("cnn", "neural", "deep learning", "transformer",
                       "lstm", "resnet", "pytorch", "tensorflow", "vit",
                       "diffusion", "gan", "autoencoder", "bert", "gpt")
        research_keywords = ("research", "experiment", "explore", "survey",
                             "literature", "hypothesis")
        if any(kw in desc_lower for kw in dl_keywords):
            workflow_mode = "deep_learning"
        elif any(kw in desc_lower for kw in research_keywords):
            workflow_mode = "research"
        else:
            workflow_mode = "classical_ml"

        # Extract metric hint if mentioned
        metric_hint = "TODO"
        for kw in ("accuracy", "rmse", "mae", "f1", "auc", "loss",
                    "precision", "recall", "bleu", "rouge", "mse",
                    "r2", "perplexity", "iou"):
            if kw in desc_lower:
                metric_hint = kw.upper() if len(kw) <= 4 else kw.capitalize()
                break

        sections = [
            "---",
            f"project_name: {self._project_name}",
            'version: "0.1.0"',
            f'created: "{now}"',
            f'last_modified: "{now}"',
            "status: active",
            'owner: "TODO"',
            "---",
            "",
            "## Objective",
            "",
            description,
            "",
            "TODO: Expand into full objective with concrete deliverables.",
            "",
            "## Oracle Definition",
            "",
            f"**Primary metric:** {metric_hint}",
            "**Ground truth source:** TODO",
            "**Evaluation method:** TODO",
            "**Target threshold:** TODO",
            "**Evaluation frequency:** TODO",
            "",
            "## Workflow Configuration",
            "",
            f"**Mode:** {workflow_mode}",
            "",
            "## Data Sources",
            "",
            "### Primary",
            "",
            "TODO: Describe your primary data source.",
            "",
            "## Domain Context and Priors",
            "",
            f"- Project context: {description}",
            "",
            "TODO: Add domain knowledge and assumptions.",
            "",
            "## Agent Configuration",
            "",
            "**Active agents:** data-engineer, model-builder, oracle-qa, test-engineer",
            "",
            "## Constraints",
            "",
            "TODO: Define constraints (time, compute, data, regulatory).",
            "",
            "## Milestones and Timeline",
            "",
            "TODO: Define milestones.",
            "",
        ]

        plan_path.write_text("\n".join(sections), encoding="utf-8")
        return plan_path

    def get_document_summaries(self, max_entries: int = 10) -> str:
        """Return formatted summaries of indexed documents.

        Used to inject document context into the Claude session prompt.

        Args:
            max_entries: Maximum number of summaries to return.

        Returns:
            Formatted string of document summaries, or empty string.
        """
        hits = self._index.query("project objective data domain", top_k=max_entries)
        if not hits:
            return ""
        lines = ["Indexed document summaries:"]
        for hit in hits:
            summary = hit.entry.summary
            if summary.startswith("["):
                idx = summary.find("]")
                if idx != -1:
                    summary = summary[idx + 2:]
            lines.append(f"  - {summary}")
        return "\n".join(lines)

    def validate_draft(self, plan_path: Path) -> bool:
        """Validate the generated plan against the schema.

        Args:
            plan_path: Path to the plan file to validate.

        Returns:
            True if valid.
        """
        try:
            plan = parse_plan(plan_path)
            report = validate_plan(plan)
            return report.valid
        except (ValueError, FileNotFoundError):
            return False

    def close(self) -> None:
        """Close the semantic index."""
        self._index.close()

    @staticmethod
    def _format_hits(hits: list, fallback: str) -> str:
        """Format search results into markdown content."""
        if not hits:
            return f"TODO: {fallback}"
        lines = []
        for hit in hits:
            summary = hit.entry.summary
            # Strip the [path] prefix for cleaner output
            if summary.startswith("["):
                idx = summary.find("]")
                if idx != -1:
                    summary = summary[idx + 2:]
            lines.append(f"- {summary}")
        return "\n".join(lines)

    @staticmethod
    def _format_oracle(hits: list) -> str:
        """Format oracle section from search results."""
        if not hits:
            return (
                "**Primary metric:** TODO\n"
                "**Ground truth source:** TODO\n"
                "**Evaluation method:** TODO\n"
                "**Target threshold:** TODO\n"
                "**Evaluation frequency:** TODO"
            )
        # Use first hit as a hint but keep the required structure
        summary = hits[0].entry.summary
        if summary.startswith("["):
            idx = summary.find("]")
            if idx != -1:
                summary = summary[idx + 2:]
        return (
            f"**Primary metric:** {summary}\n"
            "**Ground truth source:** TODO\n"
            "**Evaluation method:** TODO\n"
            "**Target threshold:** TODO\n"
            "**Evaluation frequency:** TODO"
        )

    @staticmethod
    def _format_data_sources(hits: list) -> str:
        """Format data sources section from search results."""
        if not hits:
            return "### Primary\n\nTODO: Describe your primary data source."
        lines = ["### Primary", ""]
        for hit in hits:
            summary = hit.entry.summary
            if summary.startswith("["):
                idx = summary.find("]")
                if idx != -1:
                    summary = summary[idx + 2:]
            lines.append(f"- {summary}")
        return "\n".join(lines)
