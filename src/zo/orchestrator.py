"""Orchestrator for Zero Operators.

Reads a plan, decomposes it into phases, generates agent contracts,
manages gates, and builds the lead prompt injected into a Claude Code
agent team session.  The orchestrator does NOT spawn agents directly —
it prepares context for ``wrapper.py`` which launches the lead session.

Typical usage::

    from zo.orchestrator import Orchestrator
    orch = Orchestrator(plan=plan, target=target, memory=mm,
                        comms=logger, semantic=idx, zo_root=Path("."))
    orch.start_session()
    decomp = orch.decompose_plan()
    prompt = orch.build_lead_prompt(decomp.phases[0])
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from zo._memory_models import DecisionEntry, OperatingMode, SessionState
from zo._orchestrator_models import (
    AgentContract,
    GateDecision,
    GateEvaluation,
    GateType,
    PhaseDefinition,
    PhaseStatus,
    WorkflowDecomposition,
)
from zo._orchestrator_phases import AGENT_PHASE_MAP, MODE_PHASE_FACTORY
from zo.plan import Plan, WorkflowMode

if TYPE_CHECKING:
    from zo._memory_models import SessionSummary
    from zo.comms import CommsLogger
    from zo.memory import MemoryManager
    from zo.semantic import SemanticIndex
    from zo.target import TargetConfig

__all__ = [
    "AgentContract",
    "GateDecision",
    "GateEvaluation",
    "GateType",
    "Orchestrator",
    "PhaseDefinition",
    "PhaseStatus",
    "WorkflowDecomposition",
]

# ---------------------------------------------------------------------------
# Contract metadata lookups
# ---------------------------------------------------------------------------

_ROLE_MAP: dict[str, str] = {
    "lead-orchestrator": "Coordinate pipeline, gate decisions, manage state",
    "data-engineer": "Data pipeline, cleaning, profiling, loaders",
    "model-builder": "Architecture, training, iteration against oracle",
    "oracle-qa": "Hard metric evaluation, gating, drift detection",
    "code-reviewer": "Code quality review, PEP8, security",
    "test-engineer": "Unit, integration, regression tests",
    "xai-agent": "Explainability analysis, SHAP, attention",
    "domain-evaluator": "Domain validation, plausibility checks",
    "ml-engineer": "Inference optimisation, GPU, experiment tracking",
    "infra-engineer": "Environment setup, dependencies, deployment",
}

_OWNERSHIP_MAP: dict[str, list[str]] = {
    "data-engineer": ["data/raw/", "data/processed/", "data/reports/"],
    "model-builder": ["models/", "experiments/"],
    "oracle-qa": ["oracle/", "oracle/reports/"],
    "code-reviewer": [],
    "test-engineer": ["tests/"],
    "xai-agent": ["xai/"],
    "domain-evaluator": ["domain_validation/"],
    "ml-engineer": ["infra/gpu/", "infra/tracking/"],
    "infra-engineer": ["env/", "scripts/"],
}

_OFF_LIMITS_MAP: dict[str, list[str]] = {
    "data-engineer": ["models/", "oracle/"],
    "model-builder": ["data/raw/", "oracle/"],
    "oracle-qa": ["models/", "data/raw/"],
    "code-reviewer": ["data/raw/", "models/"],
    "test-engineer": ["data/raw/", "models/"],
    "xai-agent": ["models/", "data/raw/"],
    "domain-evaluator": ["models/", "data/raw/"],
    "ml-engineer": ["models/", "data/raw/"],
    "infra-engineer": ["models/", "oracle/"],
}


class Orchestrator:
    """Coordinates plan decomposition, gating, and lead prompt generation.

    Args:
        plan: Parsed project plan.
        target: Parsed target configuration.
        memory: Memory manager for the project.
        comms: Comms logger for audit events.
        semantic: Semantic index for decision retrieval.
        zo_root: Root directory of the ZO repository.
    """

    def __init__(
        self,
        plan: Plan,
        target: TargetConfig,
        memory: MemoryManager,
        comms: CommsLogger,
        semantic: SemanticIndex,
        zo_root: Path,
    ) -> None:
        self._plan = plan
        self._target = target
        self._memory = memory
        self._comms = comms
        self._semantic = semantic
        self._zo_root = Path(zo_root)
        self._workflow: WorkflowDecomposition | None = None
        self._session_state: SessionState | None = None
        self._plan_hash: str = self._compute_plan_hash()

    @property
    def workflow(self) -> WorkflowDecomposition | None:
        """Current workflow decomposition, or None if not yet decomposed."""
        return self._workflow

    @property
    def session_state(self) -> SessionState:
        """Current session state (reads from memory if not yet loaded)."""
        if self._session_state is None:
            self._session_state = self._memory.read_state()
        return self._session_state

    # -- Session lifecycle ----------------------------------------------------

    def start_session(self) -> SessionState:
        """Start or recover a session."""
        state = self._memory.recover_session()
        state_path = self._memory.memory_root / "STATE.md"
        if not state_path.exists() or state.phase == "init":
            state.mode = OperatingMode.BUILD
        elif state.phase != "init":
            state.mode = OperatingMode.CONTINUE

        self._session_state = state
        self._memory.write_state(state)
        self._comms.log_decision(
            agent="orchestrator",
            title=f"Session started in {state.mode} mode",
            rationale=f"Phase={state.phase}, blockers={len(state.active_blockers)}",
            outcome=state.mode,
            confidence="high",
        )
        return state

    def end_session(self, summary: SessionSummary | None = None) -> None:
        """End the current session."""
        if self._session_state is not None:
            self._session_state.timestamp = datetime.now(UTC)
            self._memory.write_state(self._session_state)
        if summary is not None:
            self._memory.write_session_summary(summary)
        self._comms.log_decision(
            agent="orchestrator", title="Session ended",
            rationale="Normal session termination.", outcome="ended",
        )

    # -- Workflow decomposition -----------------------------------------------

    def decompose_plan(self) -> WorkflowDecomposition:
        """Decompose the plan into phases and agent contracts."""
        mode = (
            self._plan.workflow.mode
            if self._plan.workflow
            else WorkflowMode.CLASSICAL_ML
        )
        from zo._orchestrator_phases import classical_ml_phases
        factory = MODE_PHASE_FACTORY.get(mode, classical_ml_phases)
        phases = factory()

        active = self._plan.agents.active_agents if self._plan.agents else []
        for phase in phases:
            phase.assigned_agents = self._agents_for_phase(phase.phase_id, active)

        contracts: list[AgentContract] = []
        for phase in phases:
            for name in phase.assigned_agents:
                contracts.append(self.generate_agent_contract(name, phase))

        self._workflow = WorkflowDecomposition(
            mode=mode, phases=phases, agent_contracts=contracts,
        )
        self._comms.log_decision(
            agent="orchestrator",
            title=f"Plan decomposed into {len(phases)} phases ({mode})",
            rationale=f"Agents: {active}", outcome="decomposed", confidence="high",
        )
        if self._session_state is not None:
            self._session_state.phase = phases[0].phase_id
        return self._workflow

    def generate_agent_contract(
        self, agent_name: str, phase: PhaseDefinition,
    ) -> AgentContract:
        """Generate a contract for an agent within a phase."""
        return AgentContract(
            agent_name=agent_name,
            phase_id=phase.phase_id,
            role_description=_ROLE_MAP.get(agent_name, f"{agent_name} agent"),
            ownership=_OWNERSHIP_MAP.get(agent_name, []),
            off_limits=_OFF_LIMITS_MAP.get(agent_name, []),
            contract_produced=[f"{phase.phase_id}/{agent_name} artifacts"],
            contract_consumed=[f"Inputs from prior phase for {agent_name}"],
            validation_checklist=[
                "All outputs exist at specified paths",
                "Output schema matches contract",
                "No off-limits files modified",
            ],
            coordination_rules=[
                "Message orchestrator on blockers",
                "Use SendMessage for peer-to-peer comms",
                f"Report status for phase {phase.phase_id}",
            ],
        )

    # -- Build lead prompt ----------------------------------------------------

    def build_lead_prompt(self, phase: PhaseDefinition) -> str:
        """Build the full prompt for the Claude Code lead session."""
        sections = [
            self._prompt_role(), self._prompt_plan_context(),
            self._prompt_phase(phase), self._prompt_contracts(phase),
            self._prompt_roster(), self._prompt_memory(),
            self._prompt_coordination(), self._prompt_gate_criteria(phase),
            self._prompt_constraints(),
        ]
        return "\n\n---\n\n".join(s for s in sections if s)

    # -- Phase management -----------------------------------------------------

    def get_current_phase(self) -> PhaseDefinition | None:
        """Return the first PENDING phase with all dependencies met."""
        if self._workflow is None:
            return None
        completed = {
            p.phase_id for p in self._workflow.phases
            if p.status == PhaseStatus.COMPLETED
        }
        for phase in self._workflow.phases:
            if phase.status != PhaseStatus.PENDING:
                continue
            if all(dep in completed for dep in phase.depends_on):
                return phase
        return None

    def advance_phase(self, phase_id: str) -> GateEvaluation:
        """Evaluate the gate for a phase and advance if criteria are met."""
        phase = self._find_phase(phase_id)
        all_done = set(phase.subtasks) == set(phase.completed_subtasks)

        if phase.gate_type == GateType.BLOCKING:
            ev = GateEvaluation(
                phase_id=phase_id, gate_type=GateType.BLOCKING,
                decision=GateDecision.HOLD,
                rationale=(
                    "Blocking gate requires human approval." if all_done
                    else "Subtasks incomplete; blocking gate."
                ),
                requires_human=True,
            )
            if all_done:
                phase.status = PhaseStatus.GATED
            self._log_gate(ev)
            return ev

        if all_done:
            phase.status = PhaseStatus.COMPLETED
            ev = GateEvaluation(
                phase_id=phase_id, gate_type=GateType.AUTOMATED,
                decision=GateDecision.PROCEED,
                rationale="All subtasks complete; automated gate passed.",
            )
        else:
            remaining = set(phase.subtasks) - set(phase.completed_subtasks)
            ev = GateEvaluation(
                phase_id=phase_id, gate_type=GateType.AUTOMATED,
                decision=GateDecision.ITERATE,
                rationale=f"Subtasks remaining: {', '.join(sorted(remaining))}",
            )
        self._log_gate(ev)
        return ev

    def mark_subtask_complete(self, phase_id: str, subtask: str) -> None:
        """Mark a subtask as complete within a phase."""
        phase = self._find_phase(phase_id)
        if subtask not in phase.subtasks:
            raise ValueError(
                f"Subtask '{subtask}' not found in phase '{phase_id}'. "
                f"Available: {phase.subtasks}"
            )
        if subtask not in phase.completed_subtasks:
            phase.completed_subtasks.append(subtask)
        if self._session_state is not None:
            self._session_state.last_completed_subtask = subtask
            self._memory.write_state(self._session_state)
        self._comms.log_checkpoint(
            agent="orchestrator", phase=phase_id, subtask=subtask,
            progress=f"{len(phase.completed_subtasks)}/{len(phase.subtasks)} subtasks complete",
        )

    # -- Plan edit detection --------------------------------------------------

    def check_plan_edited(self) -> bool:
        """Check if the plan file has been modified since decomposition."""
        return self._compute_plan_hash() != self._plan_hash

    def replan(self, new_plan: Plan) -> WorkflowDecomposition:
        """Re-decompose with an updated plan."""
        self._plan = new_plan
        self._plan_hash = self._compute_plan_hash()
        self._comms.log_decision(
            agent="orchestrator", title="Plan re-decomposed after edit",
            rationale="Plan file changed; regenerating workflow.",
            outcome="replanned",
        )
        return self.decompose_plan()

    # -- Human checkpoints ----------------------------------------------------

    def prepare_gate_review(self, phase_id: str) -> dict[str, str]:
        """Prepare a summary for human gate review."""
        phase = self._find_phase(phase_id)
        review: dict[str, str] = {
            "phase": f"{phase.name} ({phase.phase_id})",
            "status": phase.status,
            "completed_subtasks": ", ".join(phase.completed_subtasks) or "none",
            "remaining_subtasks": ", ".join(
                set(phase.subtasks) - set(phase.completed_subtasks),
            ) or "none",
            "gate_type": phase.gate_type,
            "description": phase.description,
        }
        if self._plan.oracle:
            review["oracle_metric"] = self._plan.oracle.primary_metric
            review["target_threshold"] = self._plan.oracle.target_threshold
        return review

    def apply_human_decision(
        self, phase_id: str, decision: GateDecision, notes: str = "",
    ) -> None:
        """Apply a human's gate decision to a phase."""
        phase = self._find_phase(phase_id)
        if decision == GateDecision.PROCEED:
            phase.status = PhaseStatus.COMPLETED
        elif decision == GateDecision.ITERATE:
            phase.status = PhaseStatus.ACTIVE
            phase.completed_subtasks.clear()
        elif decision == GateDecision.ESCALATE:
            phase.status = PhaseStatus.BLOCKED
        else:
            phase.status = PhaseStatus.GATED

        self._comms.log_decision(
            agent="orchestrator",
            title=f"Human decision on {phase_id}: {decision}",
            rationale=notes or "Human reviewer decision.", outcome=decision,
        )
        self._memory.append_decision(DecisionEntry(
            title=f"Human gate decision: {phase_id}",
            context=f"Phase: {phase.name}",
            decision=decision, rationale=notes, outcome=decision,
        ))

    def get_phase_status(self, phase_id: str) -> PhaseStatus:
        """Return the status of a specific phase."""
        return self._find_phase(phase_id).status

    # -- Internal helpers -----------------------------------------------------

    def _find_phase(self, phase_id: str) -> PhaseDefinition:
        if self._workflow is None:
            raise ValueError("Workflow not yet decomposed; call decompose_plan() first.")
        for phase in self._workflow.phases:
            if phase.phase_id == phase_id:
                return phase
        ids = [p.phase_id for p in self._workflow.phases]
        raise ValueError(f"Phase '{phase_id}' not found. Available: {ids}")

    @staticmethod
    def _agents_for_phase(phase_id: str, active_agents: list[str]) -> list[str]:
        return [a for a in active_agents if phase_id in AGENT_PHASE_MAP.get(a, [])]

    def _compute_plan_hash(self) -> str:
        if self._plan.source_path and self._plan.source_path.exists():
            content = self._plan.source_path.read_bytes()
        else:
            content = self._plan.objective.encode()
        return hashlib.sha256(content).hexdigest()

    def _log_gate(self, evaluation: GateEvaluation) -> None:
        self._comms.log_decision(
            agent="orchestrator",
            title=f"Gate evaluation: {evaluation.phase_id}",
            rationale=evaluation.rationale, outcome=evaluation.decision,
        )
        self._memory.append_decision(DecisionEntry(
            title=f"Gate: {evaluation.phase_id} -> {evaluation.decision}",
            context=f"Gate type: {evaluation.gate_type}",
            decision=evaluation.decision, rationale=evaluation.rationale,
            outcome=evaluation.decision,
        ))

    # -- Prompt section builders ----------------------------------------------

    def _prompt_role(self) -> str:
        name = self._plan.frontmatter.project_name
        return dedent(f"""\
            # Role

            You are the Lead Orchestrator for project **{name}**.
            Your job is to coordinate the agent team, enforce phase gates,
            and drive the project to completion against the oracle metric.
            You do NOT write code, train models, or compute metrics.""")

    def _prompt_plan_context(self) -> str:
        p = self._plan
        oracle_text = p.oracle.raw_content if p.oracle else "Not defined"
        return dedent(f"""\
            # Plan Context

            **Objective:** {p.objective}

            **Oracle:**
            {oracle_text}

            **Constraints:**
            {p.constraints}""")

    def _prompt_phase(self, phase: PhaseDefinition) -> str:
        subtasks = "\n".join(f"- {s}" for s in phase.subtasks)
        agents = ", ".join(phase.assigned_agents) or "none assigned"
        deps = ", ".join(phase.depends_on) or "none"
        return dedent(f"""\
            # Current Phase: {phase.name} ({phase.phase_id})

            {phase.description}

            **Subtasks:**
            {subtasks}

            **Assigned agents:** {agents}
            **Gate type:** {phase.gate_type}
            **Dependencies:** {deps}""")

    def _prompt_contracts(self, phase: PhaseDefinition) -> str:
        if not self._workflow:
            return ""
        lines: list[str] = []
        for c in self._workflow.agent_contracts:
            if c.phase_id == phase.phase_id:
                lines.append(
                    f"### {c.agent_name}\nRole: {c.role_description}\n"
                    f"Owns: {', '.join(c.ownership) or 'n/a'}\n"
                    f"Off-limits: {', '.join(c.off_limits) or 'n/a'}\n"
                    f"Produces: {', '.join(c.contract_produced)}\n"
                    f"Consumes: {', '.join(c.contract_consumed)}"
                )
        return ("# Agent Contracts\n\n" + "\n\n".join(lines)) if lines else ""

    def _prompt_roster(self) -> str:
        agents_dir = self._zo_root / ".claude" / "agents"
        files = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
        roster = [f"- {f.stem}" for f in files]
        return (
            "# Agent Roster\n\nAvailable agents in `.claude/agents/`:\n"
            + "\n".join(roster)
            + "\n\nCreate new agent definitions if project requires "
            "expertise not covered above."
        )

    def _prompt_memory(self) -> str:
        state = self.session_state
        lines = [
            f"Mode: {state.mode}", f"Phase: {state.phase}",
            f"Blockers: {state.active_blockers or 'none'}",
        ]
        relevant = self._semantic.query(self._plan.objective, top_k=3)
        if relevant:
            lines.append("\n**Relevant past decisions:**")
            for r in relevant:
                lines.append(f"- [{r.score:.2f}] {r.entry.summary}")
        return "# Memory Context\n\n" + "\n".join(lines)

    @staticmethod
    def _prompt_coordination() -> str:
        return dedent("""\
            # Coordination Instructions

            - Use **TeamCreate** to create a named team for this phase.
            - Spawn agents with **Agent(team_name=...)**.
            - Agents communicate peer-to-peer via **SendMessage**.
            - Define ALL integration contracts before parallel spawn.
            - Log every decision to DECISION_LOG.md.
            - Update STATE.md at every phase transition.
            - Escalate to human if blockers persist after one debate round.""")

    def _prompt_gate_criteria(self, phase: PhaseDefinition) -> str:
        if not self._plan.oracle:
            return ""
        o = self._plan.oracle
        return dedent(f"""\
            # Gate Criteria

            **Primary metric:** {o.primary_metric}
            **Target threshold:** {o.target_threshold}
            **Evaluation method:** {o.evaluation_method}
            **Evaluation frequency:** {o.evaluation_frequency}

            Phase gate type: **{phase.gate_type}**
            All subtasks must be complete and gate criteria met before
            advancing to the next phase.""")

    def _prompt_constraints(self) -> str:
        return f"# Constraints\n\n{self._plan.constraints}" if self._plan.constraints else ""
