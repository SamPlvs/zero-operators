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

from zo._memory_models import DecisionEntry, OperatingMode, SessionState, SessionSummary
from zo._orchestrator_models import (
    AgentContract,
    GateDecision,
    GateEvaluation,
    GateType,
    PhaseDefinition,
    PhaseStatus,
    WorkflowDecomposition,
)
from zo.plan import Plan, WorkflowMode

if TYPE_CHECKING:
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
# Agent-to-phase mapping
# ---------------------------------------------------------------------------

_AGENT_PHASE_MAP: dict[str, list[str]] = {
    "data-engineer": ["phase_0", "phase_1", "phase_2"],
    "model-builder": ["phase_3", "phase_4", "phase_5"],
    "oracle-qa": ["phase_3", "phase_4", "phase_5"],
    "code-reviewer": [
        "phase_1", "phase_2", "phase_3", "phase_4", "phase_5", "phase_6",
    ],
    "test-engineer": [
        "phase_1", "phase_2", "phase_3", "phase_4", "phase_5", "phase_6",
    ],
    "xai-agent": ["phase_5"],
    "domain-evaluator": ["phase_5"],
    "ml-engineer": ["phase_4", "phase_5", "phase_6"],
    "infra-engineer": ["phase_1", "phase_6"],
    "lead-orchestrator": [],
}

# ---------------------------------------------------------------------------
# Phase templates per workflow mode
# ---------------------------------------------------------------------------


def _classical_ml_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the classical_ml workflow."""
    return [
        PhaseDefinition(
            phase_id="phase_1",
            name="Data Review and Pipeline",
            description="Validate raw data, profile, clean, version, build loaders.",
            subtasks=[
                "Raw data audit", "Data hygiene", "Exclusion filters",
                "Data alignment", "EDA", "Data versioning", "Data loader",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=[],
        ),
        PhaseDefinition(
            phase_id="phase_2",
            name="Feature Engineering and Selection",
            description="Engineer features, filter, prune multicollinearity, rank.",
            subtasks=[
                "Feature engineering", "Section filter", "Statistical filter",
                "Multicollinearity pruning", "Domain validation", "Feature ranking",
            ],
            gate_type=GateType.BLOCKING,
            depends_on=["phase_1"],
        ),
        PhaseDefinition(
            phase_id="phase_3",
            name="Model Design",
            description=(
                "Select architecture, design loss, define training strategy, "
                "set up oracle and experiment tracking."
            ),
            subtasks=[
                "Architecture selection", "Loss function design",
                "Training strategy", "Regime segmentation",
                "Oracle setup", "Experiment tracking",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_2"],
        ),
        PhaseDefinition(
            phase_id="phase_4",
            name="Training and Iteration",
            description="Train, iterate, cross-validate, ensemble exploration.",
            subtasks=[
                "Baseline training", "Iteration protocol",
                "Cross-validation", "Ensemble exploration",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_3"],
        ),
        PhaseDefinition(
            phase_id="phase_5",
            name="Analysis and Validation",
            description=(
                "Explainability, domain consistency, error analysis, "
                "ablation, statistical significance."
            ),
            subtasks=[
                "Feature attribution", "Domain consistency",
                "Data corroboration", "Magnitude plausibility",
                "Error analysis", "Ablation study",
                "Significance testing", "Reproducibility",
                "Report assembly",
            ],
            gate_type=GateType.BLOCKING,
            depends_on=["phase_4"],
        ),
        PhaseDefinition(
            phase_id="phase_6",
            name="Packaging",
            description="Inference pipeline, model card, validation report, tests.",
            subtasks=[
                "Inference pipeline", "Model card",
                "Validation report", "Drift detection", "Test suite",
            ],
            gate_type=GateType.AUTOMATED,
            depends_on=["phase_5"],
        ),
    ]


def _deep_learning_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the deep_learning workflow."""
    phases = _classical_ml_phases()
    # Phase 2: input representation focus
    phases[1] = PhaseDefinition(
        phase_id="phase_2",
        name="Input Representation Design",
        description=(
            "Design input representations, transfer learning assessment, "
            "augmentation strategy."
        ),
        subtasks=[
            "Input representation design", "Transfer learning assessment",
            "Augmentation strategy",
        ],
        gate_type=GateType.BLOCKING,
        depends_on=["phase_1"],
    )
    # Phase 3: expanded architecture search
    phases[2] = PhaseDefinition(
        phase_id="phase_3",
        name="Model Design (Deep Learning)",
        description=(
            "Architecture search, loss design, training strategy with LR "
            "scheduling and gradient diagnostics, oracle and tracking setup."
        ),
        subtasks=[
            "Architecture selection", "Loss function design",
            "Training strategy", "Gradient diagnostics plan",
            "Regime segmentation", "Oracle setup", "Experiment tracking",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_2"],
    )
    # Phase 4: add training diagnostics subtask
    phases[3] = PhaseDefinition(
        phase_id="phase_4",
        name="Training and Iteration (Deep Learning)",
        description=(
            "Train with diagnostics, iterate, cross-validate, ensemble."
        ),
        subtasks=[
            "Baseline training", "Training diagnostics",
            "Iteration protocol", "Cross-validation", "Ensemble exploration",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_3"],
    )
    return phases


def _research_phases() -> list[PhaseDefinition]:
    """Return phase definitions for the research workflow."""
    phase_0 = PhaseDefinition(
        phase_id="phase_0",
        name="Literature Review and Prior Art",
        description="Survey prior art, define baselines and evaluation protocol.",
        subtasks=["Prior art survey", "Baseline definition"],
        gate_type=GateType.AUTOMATED,
        depends_on=[],
    )
    base = _deep_learning_phases()
    # Shift dependency: phase_1 now depends on phase_0
    base[0].depends_on = ["phase_0"]
    # Phase 5: expand with ablation and reproducibility
    base[4] = PhaseDefinition(
        phase_id="phase_5",
        name="Analysis and Validation (Research)",
        description=(
            "Full analysis with ablation studies, statistical significance, "
            "reproducibility verification."
        ),
        subtasks=[
            "Feature attribution", "Domain consistency",
            "Data corroboration", "Magnitude plausibility",
            "Error analysis", "Ablation study",
            "Significance testing", "Reproducibility",
            "Report assembly",
        ],
        gate_type=GateType.BLOCKING,
        depends_on=["phase_4"],
    )
    # Phase 6: add research artifacts
    base[5] = PhaseDefinition(
        phase_id="phase_6",
        name="Packaging (Research)",
        description=(
            "Inference pipeline, model card, validation report, tests, "
            "paper-ready figures and reproducibility bundle."
        ),
        subtasks=[
            "Inference pipeline", "Model card", "Validation report",
            "Drift detection", "Test suite", "Research artifacts",
        ],
        gate_type=GateType.AUTOMATED,
        depends_on=["phase_5"],
    )
    return [phase_0, *base]


_MODE_PHASE_FACTORY: dict[WorkflowMode, callable] = {
    WorkflowMode.CLASSICAL_ML: _classical_ml_phases,
    WorkflowMode.DEEP_LEARNING: _deep_learning_phases,
    WorkflowMode.RESEARCH: _research_phases,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


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

    # -- Properties -----------------------------------------------------------

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
        """Start or recover a session.

        Reads STATE.md, recovers if needed, determines operating mode,
        and logs the session start decision.

        Returns:
            The current session state.
        """
        state = self._memory.recover_session()
        # Determine mode based on existing state
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
            rationale=(
                f"Phase={state.phase}, "
                f"blockers={len(state.active_blockers)}"
            ),
            outcome=state.mode,
            confidence="high",
        )
        return state

    def end_session(self, summary: SessionSummary | None = None) -> None:
        """End the current session.

        Writes session state, optional summary, and logs the end event.

        Args:
            summary: Optional session summary to persist.
        """
        if self._session_state is not None:
            self._session_state.timestamp = datetime.now(UTC)
            self._memory.write_state(self._session_state)

        if summary is not None:
            self._memory.write_session_summary(summary)

        self._comms.log_decision(
            agent="orchestrator",
            title="Session ended",
            rationale="Normal session termination.",
            outcome="ended",
        )

    # -- Workflow decomposition -----------------------------------------------

    def decompose_plan(self) -> WorkflowDecomposition:
        """Decompose the plan into phases and agent contracts.

        Reads the workflow mode from the plan, generates phase templates,
        assigns agents, and produces contracts.

        Returns:
            The full workflow decomposition.
        """
        mode = (
            self._plan.workflow.mode
            if self._plan.workflow
            else WorkflowMode.CLASSICAL_ML
        )
        factory = _MODE_PHASE_FACTORY.get(mode, _classical_ml_phases)
        phases = factory()

        active_agents = (
            self._plan.agents.active_agents if self._plan.agents else []
        )
        # Assign agents to phases
        for phase in phases:
            phase.assigned_agents = self._agents_for_phase(
                phase.phase_id, active_agents,
            )

        # Generate contracts
        contracts: list[AgentContract] = []
        for phase in phases:
            for agent_name in phase.assigned_agents:
                contracts.append(
                    self.generate_agent_contract(agent_name, phase),
                )

        self._workflow = WorkflowDecomposition(
            mode=mode, phases=phases, agent_contracts=contracts,
        )

        self._comms.log_decision(
            agent="orchestrator",
            title=f"Plan decomposed into {len(phases)} phases ({mode})",
            rationale=f"Agents: {active_agents}",
            outcome="decomposed",
            confidence="high",
        )

        # Update session state
        if self._session_state is not None:
            self._session_state.phase = phases[0].phase_id

        return self._workflow

    def generate_agent_contract(
        self, agent_name: str, phase: PhaseDefinition,
    ) -> AgentContract:
        """Generate a contract for an agent within a phase.

        Args:
            agent_name: Agent identifier (e.g. ``"data-engineer"``).
            phase: The phase this contract belongs to.

        Returns:
            A populated ``AgentContract``.
        """
        role_map = {
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
        ownership_map = {
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
        off_limits_map = {
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

        return AgentContract(
            agent_name=agent_name,
            phase_id=phase.phase_id,
            role_description=role_map.get(agent_name, f"{agent_name} agent"),
            ownership=ownership_map.get(agent_name, []),
            off_limits=off_limits_map.get(agent_name, []),
            contract_produced=[
                f"{phase.phase_id}/{agent_name} artifacts",
            ],
            contract_consumed=[
                f"Inputs from prior phase for {agent_name}",
            ],
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
        """Build the full prompt for the Claude Code lead session.

        This is the critical method — it produces the context injection
        that turns a generic Claude session into a project-aware
        orchestrator.

        Args:
            phase: The current phase to execute.

        Returns:
            A multi-section prompt string.
        """
        plan = self._plan
        project_name = plan.frontmatter.project_name
        sections: list[str] = []

        # 1. Role
        sections.append(dedent(f"""\
            # Role

            You are the Lead Orchestrator for project **{project_name}**.
            Your job is to coordinate the agent team, enforce phase gates,
            and drive the project to completion against the oracle metric.
            You do NOT write code, train models, or compute metrics."""))

        # 2. Plan context
        oracle_text = plan.oracle.raw_content if plan.oracle else "Not defined"
        sections.append(dedent(f"""\
            # Plan Context

            **Objective:** {plan.objective}

            **Oracle:**
            {oracle_text}

            **Constraints:**
            {plan.constraints}"""))

        # 3. Current phase
        subtask_list = "\n".join(f"- {s}" for s in phase.subtasks)
        agent_list = ", ".join(phase.assigned_agents) or "none assigned"
        sections.append(dedent(f"""\
            # Current Phase: {phase.name} ({phase.phase_id})

            {phase.description}

            **Subtasks:**
            {subtask_list}

            **Assigned agents:** {agent_list}
            **Gate type:** {phase.gate_type}
            **Dependencies:** {', '.join(phase.depends_on) or 'none'}"""))

        # 4. Agent contracts
        if self._workflow:
            contract_lines: list[str] = []
            for c in self._workflow.agent_contracts:
                if c.phase_id == phase.phase_id:
                    contract_lines.append(
                        f"### {c.agent_name}\n"
                        f"Role: {c.role_description}\n"
                        f"Owns: {', '.join(c.ownership) or 'n/a'}\n"
                        f"Off-limits: {', '.join(c.off_limits) or 'n/a'}\n"
                        f"Produces: {', '.join(c.contract_produced)}\n"
                        f"Consumes: {', '.join(c.contract_consumed)}"
                    )
            if contract_lines:
                sections.append(
                    "# Agent Contracts\n\n" + "\n\n".join(contract_lines),
                )

        # 5. Agent roster
        agents_dir = self._zo_root / ".claude" / "agents"
        agent_files = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
        roster_lines = [f"- {f.stem}" for f in agent_files]
        sections.append(
            "# Agent Roster\n\n"
            "Available agents in `.claude/agents/`:\n"
            + "\n".join(roster_lines)
            + "\n\nCreate new agent definitions if project requires "
            "expertise not covered above."
        )

        # 6. Memory context
        state = self.session_state
        memory_lines = [
            f"Mode: {state.mode}",
            f"Phase: {state.phase}",
            f"Blockers: {state.active_blockers or 'none'}",
        ]
        # Query semantic index for relevant past decisions
        relevant = self._semantic.query(plan.objective, top_k=3)
        if relevant:
            memory_lines.append("\n**Relevant past decisions:**")
            for r in relevant:
                memory_lines.append(f"- [{r.score:.2f}] {r.entry.summary}")
        sections.append(
            "# Memory Context\n\n" + "\n".join(memory_lines),
        )

        # 7. Coordination instructions
        sections.append(dedent("""\
            # Coordination Instructions

            - Use **TeamCreate** to create a named team for this phase.
            - Spawn agents with **Agent(team_name=...)**.
            - Agents communicate peer-to-peer via **SendMessage**.
            - Define ALL integration contracts before parallel spawn.
            - Log every decision to DECISION_LOG.md.
            - Update STATE.md at every phase transition.
            - Escalate to human if blockers persist after one debate round."""))

        # 8. Gate criteria
        if plan.oracle:
            sections.append(dedent(f"""\
                # Gate Criteria

                **Primary metric:** {plan.oracle.primary_metric}
                **Target threshold:** {plan.oracle.target_threshold}
                **Evaluation method:** {plan.oracle.evaluation_method}
                **Evaluation frequency:** {plan.oracle.evaluation_frequency}

                Phase gate type: **{phase.gate_type}**
                All subtasks must be complete and gate criteria met before
                advancing to the next phase."""))

        # 9. Constraints
        if plan.constraints:
            sections.append(f"# Constraints\n\n{plan.constraints}")

        return "\n\n---\n\n".join(sections)

    # -- Phase management -----------------------------------------------------

    def get_current_phase(self) -> PhaseDefinition | None:
        """Return the first phase that is PENDING with all dependencies met.

        Returns:
            The next actionable phase, or None if all are done/blocked.
        """
        if self._workflow is None:
            return None

        completed = {
            p.phase_id
            for p in self._workflow.phases
            if p.status == PhaseStatus.COMPLETED
        }
        for phase in self._workflow.phases:
            if phase.status != PhaseStatus.PENDING:
                continue
            if all(dep in completed for dep in phase.depends_on):
                return phase
        return None

    def advance_phase(self, phase_id: str) -> GateEvaluation:
        """Evaluate the gate for a phase and advance if criteria are met.

        Args:
            phase_id: The phase to evaluate.

        Returns:
            Gate evaluation result.

        Raises:
            ValueError: If the phase is not found.
        """
        phase = self._find_phase(phase_id)

        # Check all subtasks are complete
        all_done = set(phase.subtasks) == set(phase.completed_subtasks)

        if phase.gate_type == GateType.BLOCKING:
            evaluation = GateEvaluation(
                phase_id=phase_id,
                gate_type=GateType.BLOCKING,
                decision=GateDecision.HOLD,
                rationale=(
                    "Blocking gate requires human approval."
                    if all_done
                    else "Subtasks incomplete; blocking gate."
                ),
                requires_human=True,
            )
            if all_done:
                phase.status = PhaseStatus.GATED
            self._log_gate(evaluation)
            return evaluation

        # Automated gate
        if all_done:
            phase.status = PhaseStatus.COMPLETED
            evaluation = GateEvaluation(
                phase_id=phase_id,
                gate_type=GateType.AUTOMATED,
                decision=GateDecision.PROCEED,
                rationale="All subtasks complete; automated gate passed.",
                requires_human=False,
            )
        else:
            remaining = set(phase.subtasks) - set(phase.completed_subtasks)
            evaluation = GateEvaluation(
                phase_id=phase_id,
                gate_type=GateType.AUTOMATED,
                decision=GateDecision.ITERATE,
                rationale=f"Subtasks remaining: {', '.join(sorted(remaining))}",
                requires_human=False,
            )

        self._log_gate(evaluation)
        return evaluation

    def mark_subtask_complete(
        self, phase_id: str, subtask: str,
    ) -> None:
        """Mark a subtask as complete within a phase.

        Args:
            phase_id: Phase containing the subtask.
            subtask: Name of the subtask to mark done.

        Raises:
            ValueError: If the phase or subtask is not found.
        """
        phase = self._find_phase(phase_id)
        if subtask not in phase.subtasks:
            raise ValueError(
                f"Subtask '{subtask}' not found in phase '{phase_id}'. "
                f"Available: {phase.subtasks}"
            )
        if subtask not in phase.completed_subtasks:
            phase.completed_subtasks.append(subtask)

        # Update session state
        if self._session_state is not None:
            self._session_state.last_completed_subtask = subtask
            self._memory.write_state(self._session_state)

        self._comms.log_checkpoint(
            agent="orchestrator",
            phase=phase_id,
            subtask=subtask,
            progress=(
                f"{len(phase.completed_subtasks)}/{len(phase.subtasks)} "
                "subtasks complete"
            ),
        )

    # -- Plan edit detection --------------------------------------------------

    def check_plan_edited(self) -> bool:
        """Check if the plan file has been modified since decomposition.

        Returns:
            True if the plan content hash differs from the stored hash.
        """
        current = self._compute_plan_hash()
        return current != self._plan_hash

    def replan(self, new_plan: Plan) -> WorkflowDecomposition:
        """Re-decompose with an updated plan.

        Args:
            new_plan: The updated plan.

        Returns:
            New workflow decomposition.
        """
        self._plan = new_plan
        self._plan_hash = self._compute_plan_hash()

        self._comms.log_decision(
            agent="orchestrator",
            title="Plan re-decomposed after edit",
            rationale="Plan file changed; regenerating workflow.",
            outcome="replanned",
        )

        return self.decompose_plan()

    # -- Human checkpoints ----------------------------------------------------

    def prepare_gate_review(self, phase_id: str) -> dict[str, str]:
        """Prepare a summary for human gate review.

        Args:
            phase_id: Phase to prepare review for.

        Returns:
            Dict with review sections (phase, subtasks, metrics, etc.).
        """
        phase = self._find_phase(phase_id)
        completed = ", ".join(phase.completed_subtasks) or "none"
        remaining = ", ".join(
            set(phase.subtasks) - set(phase.completed_subtasks),
        ) or "none"

        review: dict[str, str] = {
            "phase": f"{phase.name} ({phase.phase_id})",
            "status": phase.status,
            "completed_subtasks": completed,
            "remaining_subtasks": remaining,
            "gate_type": phase.gate_type,
            "description": phase.description,
        }

        if self._plan.oracle:
            review["oracle_metric"] = self._plan.oracle.primary_metric
            review["target_threshold"] = self._plan.oracle.target_threshold

        return review

    def apply_human_decision(
        self,
        phase_id: str,
        decision: GateDecision,
        notes: str = "",
    ) -> None:
        """Apply a human's gate decision to a phase.

        Args:
            phase_id: Phase the decision applies to.
            decision: The human's decision.
            notes: Optional notes from the reviewer.
        """
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
            rationale=notes or "Human reviewer decision.",
            outcome=decision,
        )

        self._memory.append_decision(DecisionEntry(
            title=f"Human gate decision: {phase_id}",
            context=f"Phase: {phase.name}",
            decision=decision,
            rationale=notes,
            outcome=decision,
        ))

    # -- Status queries -------------------------------------------------------

    def get_phase_status(self, phase_id: str) -> PhaseStatus:
        """Return the status of a specific phase.

        Args:
            phase_id: Phase to query.

        Returns:
            Current phase status.

        Raises:
            ValueError: If the phase is not found.
        """
        return self._find_phase(phase_id).status

    # -- Internal helpers -----------------------------------------------------

    def _find_phase(self, phase_id: str) -> PhaseDefinition:
        """Locate a phase by ID, raising ValueError if not found."""
        if self._workflow is None:
            raise ValueError("Workflow not yet decomposed; call decompose_plan() first.")
        for phase in self._workflow.phases:
            if phase.phase_id == phase_id:
                return phase
        ids = [p.phase_id for p in self._workflow.phases]
        raise ValueError(f"Phase '{phase_id}' not found. Available: {ids}")

    def _agents_for_phase(
        self, phase_id: str, active_agents: list[str],
    ) -> list[str]:
        """Return active agents relevant to a given phase."""
        return [
            a for a in active_agents
            if phase_id in _AGENT_PHASE_MAP.get(a, [])
        ]

    def _compute_plan_hash(self) -> str:
        """Hash the plan's source file content, or the objective as fallback."""
        if self._plan.source_path and self._plan.source_path.exists():
            content = self._plan.source_path.read_bytes()
        else:
            content = self._plan.objective.encode()
        return hashlib.sha256(content).hexdigest()

    def _log_gate(self, evaluation: GateEvaluation) -> None:
        """Log a gate evaluation to comms and memory."""
        self._comms.log_decision(
            agent="orchestrator",
            title=f"Gate evaluation: {evaluation.phase_id}",
            rationale=evaluation.rationale,
            outcome=evaluation.decision,
        )
        self._memory.append_decision(DecisionEntry(
            title=f"Gate: {evaluation.phase_id} -> {evaluation.decision}",
            context=f"Gate type: {evaluation.gate_type}",
            decision=evaluation.decision,
            rationale=evaluation.rationale,
            outcome=evaluation.decision,
        ))
