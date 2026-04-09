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
        source_dir: Directory containing source documents to index.
        project_name: Name for the generated project plan.
        zo_root: Root directory of the ZO repository.
    """

    def __init__(self, source_dir: Path, project_name: str, zo_root: Path) -> None:
        self._source_dir = Path(source_dir)
        self._project_name = project_name
        self._zo_root = Path(zo_root)
        self._db_path = zo_root / "memory" / project_name / "draft_index.db"
        self._index = SemanticIndex(db_path=self._db_path)

    def index_documents(self) -> int:
        """Index all documents in source_dir using SemanticIndex.

        Returns:
            Count of indexed documents.
        """
        count = 0
        for path in sorted(self._source_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Use first line as summary, full text for retrieval
            lines = text.strip().splitlines()
            summary = lines[0][:200] if lines else path.name
            rel_path = str(path.relative_to(self._source_dir))

            entry = IndexEntry(
                entry_id=f"doc-{count:04d}",
                summary=f"[{rel_path}] {summary}",
                full_text=text[:5000],  # Truncate very large files
                source="document",
            )
            self._index.index_entry(entry)
            count += 1

        return count

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
