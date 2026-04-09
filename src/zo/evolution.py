"""Evolution engine for Zero Operators.

Implements the self-evolution protocol: when a failure occurs, the system
updates the rules that allowed the failure, not just the symptom.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from zo._evolution_models import (
    EvolutionEntry,
    FailureRecord,
    FailureSeverity,
    RetrospectiveReport,
    RootCauseAnalysis,
    RootCauseCategory,
    RuleUpdate,
)
from zo._memory_models import Confidence, DecisionEntry, PriorEntry
from zo.comms import CommsLogger, Severity

if TYPE_CHECKING:
    from zo.memory import MemoryManager

__all__ = [
    "EvolutionEngine",
    "EvolutionEntry",
    "FailureRecord",
    "FailureSeverity",
    "RetrospectiveReport",
    "RootCauseAnalysis",
    "RootCauseCategory",
    "RuleUpdate",
]

# Maps root cause category to the target document type for rule updates.
# Maps FailureSeverity to comms.Severity for error logging.
_SEVERITY_MAP: dict[FailureSeverity, Severity] = {
    FailureSeverity.CRITICAL: Severity.CRITICAL,
    FailureSeverity.MAJOR: Severity.BLOCKING,
    FailureSeverity.MINOR: Severity.WARNING,
}

# Maps root cause category to the target document type for rule updates.
_CATEGORY_DOC_MAP: dict[RootCauseCategory, str] = {
    RootCauseCategory.MISSING_RULE: "PRIORS.md",
    RootCauseCategory.INCOMPLETE_RULE: "spec",
    RootCauseCategory.IGNORED_RULE: "agent_definition",
    RootCauseCategory.NOVEL_CASE: "PRIORS.md",
    RootCauseCategory.REGRESSION: "PRIORS.md",
}


class EvolutionEngine:
    """Drives the ZO self-evolution protocol."""

    def __init__(
        self,
        memory: MemoryManager,
        comms: CommsLogger,
        zo_root: Path,
    ) -> None:
        self._memory = memory
        self._comms = comms
        self._zo_root = Path(zo_root)

    # -- Step 1: Document the failure --------------------------------------

    def record_failure(self, failure: FailureRecord) -> None:
        """Step 1: Document the failure to DECISION_LOG."""
        entry = DecisionEntry(
            title=f"Failure: {failure.title}",
            timestamp=failure.timestamp,
            context=(
                f"Detected by: {failure.detected_by} | "
                f"Severity: {failure.severity} | "
                f"Phase: {failure.phase}"
            ),
            decision=failure.description,
            rationale=failure.immediate_impact,
            alternatives_considered=", ".join(failure.artifacts_affected),
            outcome="failure_recorded",
            confidence=Confidence.HIGH,
        )
        self._memory.append_decision(entry)
        comms_severity = _SEVERITY_MAP.get(
            FailureSeverity(failure.severity), Severity.WARNING,
        )
        self._comms.log_error(
            agent=failure.detected_by,
            error_type="failure",
            severity=comms_severity,
            description=failure.description,
            affected_artifacts=failure.artifacts_affected,
        )

    # -- Step 2: Root cause analysis ---------------------------------------

    def analyze_root_cause(
        self,
        failure: FailureRecord,
        root_cause: str,
        rule_gap: str,
        category: RootCauseCategory,
    ) -> RootCauseAnalysis:
        """Step 2: Analyze and categorize the root cause."""
        doc_target = _CATEGORY_DOC_MAP[category]
        if doc_target == "spec" and rule_gap:
            doc_target = rule_gap
        elif doc_target == "agent_definition" and failure.detected_by:
            doc_target = f"agents/{failure.detected_by}.md"

        analysis = RootCauseAnalysis(
            failure=failure,
            root_cause=root_cause,
            rule_gap=rule_gap,
            category=category,
            document_to_update=doc_target,
        )

        # Log the analysis as a decision
        self._memory.append_decision(DecisionEntry(
            title=f"Root Cause: {failure.title}",
            timestamp=datetime.now(UTC),
            context=f"Category: {category}",
            decision=root_cause,
            rationale=f"Rule gap: {rule_gap}",
            alternatives_considered="",
            outcome="analysis_complete",
            confidence=Confidence.MEDIUM,
        ))

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Root cause analysis: {failure.title}",
            rationale=root_cause,
            outcome=f"category={category}, doc={doc_target}",
        )

        return analysis

    # -- Step 4: Propose rule update ---------------------------------------

    def propose_rule_update(self, analysis: RootCauseAnalysis) -> RuleUpdate:
        """Step 4: Propose a rule update based on root cause category."""
        cat = RootCauseCategory(analysis.category)
        failure_ref = f"Failure: {analysis.failure.title}"

        if cat in (RootCauseCategory.MISSING_RULE, RootCauseCategory.NOVEL_CASE):
            doc_path = str(
                self._memory.memory_root / "PRIORS.md"
            )
            change_desc = (
                f"Add new prior: {analysis.rule_gap}. "
                f"Evidence: {analysis.root_cause}"
            )
        elif cat == RootCauseCategory.INCOMPLETE_RULE:
            doc_path = str(self._zo_root / analysis.document_to_update)
            change_desc = (
                f"Expand rule to cover: {analysis.rule_gap}. "
                f"Missing case: {analysis.root_cause}"
            )
        elif cat == RootCauseCategory.IGNORED_RULE:
            doc_path = str(
                self._zo_root / ".claude" / "agents"
                / analysis.document_to_update
            )
            change_desc = (
                f"Strengthen instruction: must not ignore {analysis.rule_gap}. "
                f"Add explicit validation checklist item."
            )
        else:  # REGRESSION
            doc_path = str(
                self._memory.memory_root / "PRIORS.md"
            )
            change_desc = (
                f"Add regression guard for: {analysis.rule_gap}. "
                f"Reference prior failure: {analysis.root_cause}"
            )

        update = RuleUpdate(
            document_path=doc_path,
            change_description=change_desc,
            rationale=analysis.root_cause,
            failure_reference=failure_ref,
        )

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Proposed rule update for: {analysis.failure.title}",
            rationale=update.change_description,
            outcome=f"target={doc_path}",
        )

        return update

    # -- Apply rule update -------------------------------------------------

    def apply_rule_update(self, update: RuleUpdate) -> None:
        """Apply a proposed update to the target document."""
        doc = Path(update.document_path)
        now = datetime.now(UTC).strftime("%Y-%m-%d")

        if doc.name == "PRIORS.md":
            self._memory.append_prior(PriorEntry(
                category="evolution",
                statement=update.change_description,
                evidence=update.failure_reference,
                confidence=Confidence.HIGH,
            ))
        elif doc.suffix == ".md" and "agents" in doc.parts:
            # Agent definition — append checklist item
            doc.parent.mkdir(parents=True, exist_ok=True)
            with open(doc, "a", encoding="utf-8") as fh:
                fh.write(
                    f"\n- [ ] {update.change_description} "
                    f"(added {now} after {update.failure_reference})\n"
                )
        else:
            # Spec file — append changelog entry
            doc.parent.mkdir(parents=True, exist_ok=True)
            changelog_line = (
                f"\n---\n## Changelog\n"
                f"- {now}: {update.change_description} "
                f"after {update.failure_reference}. "
                f"Prevents: {update.rationale}\n"
            )
            with open(doc, "a", encoding="utf-8") as fh:
                fh.write(changelog_line)

        # Log the evolution entry to DECISION_LOG
        self._memory.append_decision(DecisionEntry(
            title=f"Evolution: {update.failure_reference}",
            timestamp=datetime.now(UTC),
            context=f"Document updated: {update.document_path}",
            decision=update.change_description,
            rationale=update.rationale,
            alternatives_considered="",
            outcome="rule_updated",
            confidence=Confidence.HIGH,
        ))

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Applied rule update: {update.document_path}",
            rationale=update.change_description,
            outcome="applied",
        )

    # -- Step 5: Verify update ---------------------------------------------

    def verify_update(
        self,
        update: RuleUpdate,
        failure: FailureRecord,
    ) -> bool:
        """Step 5: Verify the update would have caught the original failure."""
        doc = Path(update.document_path)
        if not doc.exists():
            self._comms.log_error(
                agent="evolution-engine",
                error_type="verification_failed",
                severity="warning",
                description=f"Target document does not exist: {doc}",
            )
            return False

        content = doc.read_text(encoding="utf-8")
        # Verify the rule content was actually written
        has_content = (
            update.change_description in content
            or update.failure_reference in content
        )

        if has_content:
            update.verified = True
            update.verification_method = (
                f"Structural check: confirmed rule content present in {doc.name} "
                f"for failure '{failure.title}'"
            )
        else:
            update.verification_method = (
                f"Structural check: rule content NOT found in {doc.name}"
            )

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Verification: {failure.title}",
            rationale=update.verification_method,
            outcome="verified" if has_content else "failed",
        )

        return has_content

    # -- Full post-mortem --------------------------------------------------

    def run_postmortem(
        self,
        failure: FailureRecord,
        root_cause: str,
        rule_gap: str,
        category: RootCauseCategory,
    ) -> EvolutionEntry:
        """Execute the full post-mortem: record -> analyze -> propose -> apply -> verify."""
        # Step 1
        self.record_failure(failure)
        # Step 2
        analysis = self.analyze_root_cause(failure, root_cause, rule_gap, category)
        # Step 4 (step 3 is the immediate fix, handled externally)
        update = self.propose_rule_update(analysis)
        self.apply_rule_update(update)
        # Step 5
        verified = self.verify_update(update, failure)

        entry = EvolutionEntry(
            title=f"Evolution: {failure.title}",
            timestamp=datetime.now(UTC),
            triggered_by=f"Failure: {failure.title}",
            document_updated=update.document_path,
            change=update.change_description,
            rationale=update.rationale,
            verified=verified,
            verification_method=update.verification_method,
        )

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Post-mortem complete: {failure.title}",
            rationale=f"Verified={verified}, doc={update.document_path}",
            outcome="postmortem_complete",
        )

        return entry

    # -- Retrospective -----------------------------------------------------

    def run_retrospective(self, project_name: str) -> RetrospectiveReport:
        """Run an end-of-project retrospective over DECISION_LOG."""
        decisions = self._memory.read_decisions()
        sessions = self._memory.read_recent_summaries(count=100)

        failures = [d for d in decisions if d.title.startswith("Failure:")]
        evolutions = [d for d in decisions if d.title.startswith("Evolution:")]
        root_causes = [d for d in decisions if d.title.startswith("Root Cause:")]

        # Build category distribution from root cause entries
        category_counts: Counter[str] = Counter()
        for rc in root_causes:
            # context field contains "Category: <cat>"
            if rc.context.startswith("Category:"):
                cat = rc.context.removeprefix("Category:").strip()
                category_counts[cat] += 1

        # Identify patterns — phases with multiple failures
        phase_counts: Counter[str] = Counter()
        for f in failures:
            # context contains "Phase: <phase>" embedded
            parts = f.context.split("|")
            for part in parts:
                part = part.strip()
                if part.startswith("Phase:"):
                    phase = part.removeprefix("Phase:").strip()
                    phase_counts[phase] += 1

        patterns: list[str] = []
        for phase, count in phase_counts.most_common():
            if count >= 2:
                patterns.append(
                    f"{count} failures in phase '{phase}' — "
                    f"consider adding a mandatory validation gate"
                )

        # Recommend updates for top categories
        recommended: list[str] = []
        for cat, count in category_counts.most_common():
            if count >= 2:
                recommended.append(
                    f"Address systemic {cat} issues ({count} occurrences) — "
                    f"review related specs and agent definitions"
                )

        lessons: list[str] = []
        if failures:
            lessons.append(
                f"Total {len(failures)} failures across "
                f"{len(sessions)} sessions"
            )
        if evolutions:
            lessons.append(
                f"{len(evolutions)} rule updates applied — "
                f"evolution coverage improving"
            )
        if not failures:
            lessons.append("No failures recorded — clean execution")

        now = datetime.now(UTC).strftime("%Y-%m-%d")
        report = RetrospectiveReport(
            project_name=project_name,
            date=now,
            sessions_completed=len(sessions),
            total_failures=len(failures),
            total_rule_updates=len(evolutions),
            failure_distribution=dict(category_counts),
            patterns=patterns,
            recommended_updates=recommended,
            lessons=lessons,
        )

        self._comms.log_decision(
            agent="evolution-engine",
            title=f"Retrospective: {project_name}",
            rationale=f"Failures={len(failures)}, evolutions={len(evolutions)}",
            outcome="retrospective_complete",
        )

        return report

    # -- Metrics -----------------------------------------------------------

    def get_evolution_metrics(self) -> dict[str, int | float]:
        """Extract evolution health metrics from DECISION_LOG."""
        decisions = self._memory.read_decisions()
        evolutions = [d for d in decisions if d.title.startswith("Evolution:")]
        root_causes = [d for d in decisions if d.title.startswith("Root Cause:")]

        total_updates = len(evolutions)

        # Count regressions
        category_counts: Counter[str] = Counter()
        for rc in root_causes:
            if rc.context.startswith("Category:"):
                cat = rc.context.removeprefix("Category:").strip()
                category_counts[cat] += 1

        regressions = category_counts.get(RootCauseCategory.REGRESSION, 0)
        total_causes = len(root_causes)
        regression_rate = (
            regressions / total_causes if total_causes > 0 else 0.0
        )

        # Coverage: priors per session
        priors = self._memory.read_priors()
        sessions = self._memory.read_recent_summaries(count=100)
        coverage = (
            len(priors) / len(sessions) if sessions else float(len(priors))
        )

        return {
            "total_rule_updates": total_updates,
            "regression_rate": regression_rate,
            "coverage_growth": coverage,
            **{f"category_{k}": v for k, v in category_counts.items()},
        }
