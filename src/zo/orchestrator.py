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
    GateMode,
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
    "GateMode",
    "GateType",
    "Orchestrator",
    "PhaseDefinition",
    "PhaseStatus",
    "WorkflowDecomposition",
]

# ---------------------------------------------------------------------------
# Custom agent template
# ---------------------------------------------------------------------------


def _render_custom_agent(spec: object) -> str:
    """Render a custom agent definition from a ``CustomAgentSpec``."""
    name_display = getattr(spec, "name", "custom").replace("-", " ").title()
    model = getattr(spec, "model", "claude-sonnet-4-6")
    role = getattr(spec, "role", "Custom specialist agent.")
    return (
        f"---\n"
        f"name: {name_display}\n"
        f"model: {model}\n"
        f"role: {role}\n"
        f"tier: phase-in\n"
        f"team: project\n"
        f"---\n\n"
        f"You are **{name_display}**, a custom specialist agent.\n\n"
        f"{role}\n\n"
        f"## Coordination Rules\n\n"
        f"- You are spawned by the Lead Orchestrator when your "
        f"expertise is needed.\n"
        f"- Communicate findings via SendMessage to the orchestrator "
        f"and relevant peers.\n"
        f"- Log significant decisions via the orchestrator for "
        f"DECISION_LOG.md.\n"
        f"- Follow all coding conventions: PEP8, type hints, Google "
        f"docstrings, <500 line files, <50 line functions.\n"
        f"- Do not modify files outside your assigned scope (the "
        f"orchestrator defines your scope at spawn time).\n\n"
        f"## Validation Checklist\n\n"
        f"Before reporting done:\n\n"
        f"- [ ] All deliverables produced as specified in your spawn "
        f"contract\n"
        f"- [ ] Findings communicated to relevant peers\n"
        f"- [ ] No files modified outside assigned scope\n"
        f"- [ ] Code follows project conventions\n"
    )


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
        plan_path: Optional override for the plan file path used in
            the lead prompt. When provided, this path is referenced
            instead of the default ``zo_root / "plans" / "<project>.md"``.
    """

    def __init__(
        self,
        plan: Plan,
        target: TargetConfig,
        memory: MemoryManager,
        comms: CommsLogger,
        semantic: SemanticIndex,
        zo_root: Path,
        *,
        gate_mode: GateMode = GateMode.SUPERVISED,
        plan_path: Path | None = None,
        low_token: bool = False,
        max_iterations_override: int | None = None,
    ) -> None:
        self._plan = plan
        self._target = target
        self._memory = memory
        self._comms = comms
        self._semantic = semantic
        self._zo_root = Path(zo_root)
        self._gate_mode = gate_mode
        self._plan_path = plan_path
        self._low_token = low_token
        self._max_iterations_override = max_iterations_override
        self._workflow: WorkflowDecomposition | None = None
        self._session_state: SessionState | None = None
        self._plan_hash: str = self._compute_plan_hash()

    @property
    def workflow(self) -> WorkflowDecomposition | None:
        """Current workflow decomposition, or None if not yet decomposed."""
        return self._workflow

    @property
    def gate_mode(self) -> GateMode:
        """Current gate mode (supervised / auto / full_auto)."""
        return self._gate_mode

    @gate_mode.setter
    def gate_mode(self, value: GateMode) -> None:
        """Change gate mode at runtime."""
        self._gate_mode = value

    @property
    def low_token(self) -> bool:
        """Whether the low-token preset is active for this orchestrator."""
        return self._low_token

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
        """End the current session, persisting phase states."""
        if self._session_state is not None:
            self._session_state.timestamp = datetime.now(UTC)
            self._capture_phase_states()
            self._memory.write_state(self._session_state)
        if summary is not None:
            self._memory.write_session_summary(summary)
        self._comms.log_decision(
            agent="orchestrator", title="Session ended",
            rationale="Normal session termination.", outcome="ended",
        )

    def _capture_phase_states(self) -> None:
        """Capture current workflow phase states into session_state for persistence."""
        if self._workflow is None or self._session_state is None:
            return
        states: dict[str, str] = {}
        subtasks: dict[str, list[str]] = {}
        for phase in self._workflow.phases:
            states[phase.phase_id] = phase.status
            subtasks[phase.phase_id] = list(phase.completed_subtasks)
        self._session_state.phase_states = states
        self._session_state.completed_subtasks_by_phase = subtasks

    # -- Workflow decomposition -----------------------------------------------

    def decompose_plan(self) -> WorkflowDecomposition:
        """Decompose the plan into phases and agent contracts."""
        self._ensure_custom_agents()

        mode = (
            self._plan.workflow.mode
            if self._plan.workflow
            else WorkflowMode.CLASSICAL_ML
        )
        from zo._orchestrator_phases import classical_ml_phases
        factory = MODE_PHASE_FACTORY.get(mode, classical_ml_phases)
        phases = factory()

        active = self._plan.agents.active_agents if self._plan.agents else []
        # Include custom agents from the plan in the active list
        if self._plan.agents and self._plan.agents.custom_agents:
            for spec in self._plan.agents.custom_agents:
                if spec.name not in active:
                    active.append(spec.name)
        for phase in phases:
            phase.assigned_agents = self._agents_for_phase(
                phase.phase_id, active, low_token=self._low_token,
            )

        contracts: list[AgentContract] = []
        for phase in phases:
            for name in phase.assigned_agents:
                contracts.append(self.generate_agent_contract(name, phase))

        self._workflow = WorkflowDecomposition(
            mode=mode, phases=phases, agent_contracts=contracts,
        )
        self._restore_phase_states()
        self._comms.log_decision(
            agent="orchestrator",
            title=f"Plan decomposed into {len(phases)} phases ({mode})",
            rationale=f"Agents: {active}", outcome="decomposed", confidence="high",
        )
        if self._session_state is not None and not self._session_state.phase_states:
            self._session_state.phase = phases[0].phase_id
        return self._workflow

    def _restore_phase_states(self) -> None:
        """Restore persisted phase states from session_state into workflow phases."""
        if self._workflow is None or self._session_state is None:
            return
        saved_states = self._session_state.phase_states
        saved_subtasks = self._session_state.completed_subtasks_by_phase
        if not saved_states:
            return
        for phase in self._workflow.phases:
            if phase.phase_id in saved_states:
                phase.status = PhaseStatus(saved_states[phase.phase_id])
                phase.completed_subtasks = list(
                    saved_subtasks.get(phase.phase_id, [])
                )

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
        """Build the full prompt for the Claude Code lead session.

        In ``low_token`` mode, drops the dedicated adaptations section
        (still inline in ``_prompt_contracts`` for spawned agents) and
        the descriptive blurb in the roster section. Saves ~2-5 KB on
        a typical lead prompt without losing per-agent adaptation
        instructions for the agents actually running in this phase.

        Also injects a sub-agent model override section telling the
        Lead Orchestrator to pass ``model="claude-sonnet-4-6"`` to
        every ``Agent()`` spawn, since Claude Code's TeamCreate
        defaults sub-agents to Opus regardless of their ``.md``
        frontmatter — without this override the savings only apply
        to the lead's own session.
        """
        sections = [
            self._prompt_role(), self._prompt_plan_context(),
            self._prompt_autonomy(),
            self._prompt_phase(phase), self._prompt_contracts(phase),
        ]
        if not self._low_token:
            sections.append(self._prompt_adaptations())
        sections.extend([
            self._prompt_roster(),
            self._prompt_experiment_context(phase),
            self._prompt_memory(), self._prompt_coordination(),
            self._prompt_low_token_overrides(),
            self._prompt_gate_criteria(phase), self._prompt_constraints(),
        ])
        return "\n\n---\n\n".join(s for s in sections if s)

    def _prompt_low_token_overrides(self) -> str:
        """Sub-agent model override instructions for low-token mode.

        Returns empty string when low-token is off. When on, instructs
        the Lead Orchestrator to pass an explicit ``model`` parameter
        to every ``Agent()`` spawn — bypassing Claude Code's default
        of Opus for TeamCreate-spawned sub-agents.

        Empirical finding (bench 2026-04-26, Claude Code 2.1.92):
        sub-agents spawn with ``--model claude-opus-4-6`` even when
        the agent ``.md`` file declares ``model: claude-sonnet-4-6``.
        Without this override, low-token mode only reduces lead-side
        spend; the actual workhorses (data-engineer, model-builder,
        oracle-qa, code-reviewer, test-engineer) stay on Opus.
        """
        if not self._low_token:
            return ""
        return dedent("""\
            # Low-Token Sub-Agent Model Override

            **CRITICAL:** Low-token mode is active. The lead session (you)
            is running on Sonnet, but Claude Code's `TeamCreate` /
            `Agent()` tools default sub-agents to **Opus** regardless of
            what their `.md` file declares. To make low-token mode
            actually save tokens end-to-end, you MUST pass an explicit
            `model` parameter when spawning sub-agents.

            **Required for every Agent() call:**

                Agent(
                    name="data-engineer",
                    team_name="...",
                    model="claude-sonnet-4-6",   # <-- always include
                    ...
                )

            Use `claude-sonnet-4-6` for ALL active agents in this run,
            regardless of what their `.md` file declares. The agent's
            instructions, tools, and contract still come from the `.md`
            file — only the model is overridden.

            **Exception:** if a specific agent absolutely requires Opus
            for the work (e.g. the user explicitly enabled Opus via
            `--lead-model opus` AND a per-agent override is needed),
            you may use `claude-opus-4-6`. Log every such exception to
            `DECISION_LOG.md` with the reason.

            **Fallback:** if the `Agent()` tool in your runtime version
            does not accept a `model` parameter, log a `DECISION_LOG`
            entry noting this and proceed without the override —
            lead-side savings still apply, but sub-agent savings
            cannot be achieved without an SDK-level fix.""")

    def _prompt_autonomy(self) -> str:
        """Tell the agent how much autonomy it has based on gate mode."""
        if self._gate_mode == GateMode.FULL_AUTO:
            return dedent("""\
                # Autonomy Level: FULL AUTO

                You have FULL AUTONOMY. Do NOT ask the human for permission
                or confirmation. Execute all subtasks, make all decisions,
                and advance through gates without pausing. Log decisions to
                DECISION_LOG.md. Only stop if you hit an unrecoverable error.""")
        if self._gate_mode == GateMode.AUTO:
            return dedent("""\
                # Autonomy Level: AUTO

                You have HIGH AUTONOMY. Execute subtasks and make decisions
                WITHOUT asking the human for confirmation. Do not ask
                "should I proceed?" or "do you want me to continue?" — just
                do the work. The only time you pause is at BLOCKING gates
                (human review required). Automated gates advance on their own.
                Log all decisions to DECISION_LOG.md.""")
        return dedent("""\
            # Autonomy Level: SUPERVISED

            Ask the human before major decisions. Present your plan,
            get approval, then execute. All gates require human review.""")

    def _prompt_adaptations(self) -> str:
        """Render the plan's agent adaptations as a dedicated section.

        Emits nothing when the plan has no adaptations. When present,
        the Lead Orchestrator reads this section and appends each
        adaptation to the corresponding agent's base ``.md`` instructions
        when spawning that agent via the ``Agent`` tool.
        """
        if not self._plan.agents or not self._plan.agents.adaptations:
            return ""
        lines: list[str] = [
            "# Per-project Agent Adaptations",
            "",
            "The plan tailors these agents for the project's domain. "
            "When you spawn any of them via `Agent(name=..., ...)`, "
            "include the adaptation text below in the spawn prompt, "
            "AFTER the agent's base instructions. Do NOT modify the "
            "agent's `.md` file itself — the adaptation is project-"
            "scoped.",
        ]
        for a in self._plan.agents.adaptations:
            lines.extend(["", f"## {a.agent_name}", "", a.adaptation])
        return "\n".join(lines)

    # -- Phase management -----------------------------------------------------

    def get_current_phase(self) -> PhaseDefinition | None:
        """Return the first actionable phase (GATED or PENDING with deps met).

        GATED phases are returned first so the CLI can prompt for human
        approval before re-launching a session.
        """
        if self._workflow is None:
            return None
        # Return a GATED phase first — it needs human decision
        for phase in self._workflow.phases:
            if phase.status == PhaseStatus.GATED:
                return phase
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

    def _refresh_gate_mode(self) -> None:
        """Re-read the gate mode from the file system if it exists.

        This allows ``zo gates set`` to change the mode mid-session
        from a separate terminal.  Falls back to the configured mode
        if the file is missing or contains an invalid value.
        """
        raw = self._memory.read_gate_mode()
        if raw is None:
            return
        try:
            new_mode = GateMode(raw)
        except ValueError:
            return
        if new_mode != self._gate_mode:
            self._comms.log_decision(
                agent="orchestrator",
                title=f"Gate mode changed: {self._gate_mode} -> {new_mode}",
                rationale="Detected gate_mode file update (zo gates set).",
                outcome=new_mode,
            )
            self._gate_mode = new_mode

    def advance_phase(self, phase_id: str) -> GateEvaluation:
        """Evaluate the gate for a phase and advance if criteria are met.

        Behaviour depends on ``gate_mode``:

        * **supervised** — every phase transition requires human approval,
          regardless of the gate_type defined in the plan.
        * **auto** (default) — only gates marked BLOCKING in the plan
          require human approval; automated gates proceed if subtasks done.
        * **full_auto** — no human gates at all; all gates are treated as
          automated and ZO runs to completion autonomously.
        """
        self._refresh_gate_mode()
        phase = self._find_phase(phase_id)
        all_done = set(phase.subtasks) == set(phase.completed_subtasks)

        # Determine effective gate type based on gate_mode
        if self._gate_mode == GateMode.SUPERVISED:
            effective_gate = GateType.BLOCKING
        elif self._gate_mode == GateMode.FULL_AUTO:
            effective_gate = GateType.AUTOMATED
        else:  # GateMode.AUTO — use plan-defined gate type
            effective_gate = phase.gate_type

        if effective_gate == GateType.BLOCKING:
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
            missing = self._check_artifacts(phase)
            exp_missing = self._finalize_experiments(phase)
            all_missing = [*missing, *exp_missing]
            if all_missing:
                ev = GateEvaluation(
                    phase_id=phase_id, gate_type=GateType.AUTOMATED,
                    decision=GateDecision.ITERATE,
                    rationale=(
                        f"Subtasks done but artifacts missing: "
                        f"{', '.join(all_missing)}"
                    ),
                )
                self._log_gate(ev)
                return ev
            # For phase_4 (training/iteration), consult the autonomous
            # loop evaluator before accepting the PROCEED. If the loop
            # says CONTINUE, keep the phase ACTIVE and return ITERATE —
            # the Lead Orchestrator sees this and mints a child exp on
            # the next build_lead_prompt call.
            auto_iter = self._auto_iterate_if_needed(phase)
            if auto_iter is not None:
                self._log_gate(auto_iter)
                return auto_iter

            phase.status = PhaseStatus.COMPLETED
            self._generate_test_report(phase)
            self._generate_notebook(phase)
            self._generate_snapshot(phase, "automated", GateDecision.PROCEED)
            ev = GateEvaluation(
                phase_id=phase_id, gate_type=GateType.AUTOMATED,
                decision=GateDecision.PROCEED,
                rationale="All subtasks complete; artifacts verified; automated gate passed.",
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
            self._finalize_experiments(phase)
            self._generate_test_report(phase)
            self._generate_notebook(phase)
            self._generate_snapshot(phase, "human", decision)
        elif decision == GateDecision.ITERATE:
            phase.status = PhaseStatus.ACTIVE
            phase.completed_subtasks.clear()
            self._abort_running_experiments(phase_id)
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
    def _agents_for_phase(
        phase_id: str,
        active_agents: list[str],
        *,
        low_token: bool = False,
    ) -> list[str]:
        """Filter the plan's active agents to those running in this phase.

        When ``low_token`` is True, drops cross-cutting agents whose
        contribution is "nice to have" (currently ``research-scout``)
        to save spawn-cost. ``code-reviewer`` is kept because silent
        quality drift is a worse trade than the saved tokens.
        """
        result: list[str] = []
        for a in active_agents:
            if low_token and a == "research-scout":
                continue
            phases = AGENT_PHASE_MAP.get(a)
            # Custom agents (not in map) are available for all phases —
            # the lead orchestrator decides when to actually spawn them.
            if phases is None or phase_id in phases:
                result.append(a)
        return result

    def _compute_plan_hash(self) -> str:
        if self._plan.source_path and self._plan.source_path.exists():
            content = self._plan.source_path.read_bytes()
        else:
            content = self._plan.objective.encode()
        return hashlib.sha256(content).hexdigest()

    def _check_artifacts(self, phase: PhaseDefinition) -> list[str]:
        """Return list of required artifacts missing from the delivery repo."""
        if not phase.required_artifacts:
            return []
        target_repo = Path(self._target.target_repo)
        if not target_repo.is_dir():
            return []
        missing: list[str] = []
        for artifact in phase.required_artifacts:
            path = target_repo / artifact
            if artifact.endswith("/"):
                if not path.is_dir() or not any(path.iterdir()):
                    missing.append(artifact)
            elif not path.exists():
                missing.append(artifact)
        return missing

    def _generate_test_report(self, phase: PhaseDefinition) -> None:
        """Generate a test report for a completed phase."""
        target_repo = Path(self._target.target_repo)
        test_dir = target_repo / "tests"
        if not target_repo.is_dir():
            return
        try:
            from zo.test_report import generate_test_report
            report_path = generate_test_report(
                test_dir=test_dir,
                delivery_repo=target_repo,
                phase_id=phase.phase_id,
                phase_name=phase.name,
            )
            if report_path:
                self._comms.log_checkpoint(
                    agent="orchestrator", phase=phase.phase_id,
                    subtask="test_report_generation",
                    progress=f"Test report generated: {report_path.name}",
                )
        except Exception as exc:  # noqa: BLE001
            self._comms.log_error(
                agent="orchestrator",
                error_type="test_report_generation_failed",
                message=f"Failed to generate test report for {phase.phase_id}: {exc}",
                severity="warning",
            )

    def _generate_notebook(self, phase: PhaseDefinition) -> None:
        """Generate a Jupyter notebook for a completed phase."""
        target_repo = Path(self._target.target_repo)
        if not target_repo.is_dir():
            return
        try:
            from zo.notebooks import generate_phase_notebook
            phase_num = phase.phase_id.removeprefix("phase_")
            generate_phase_notebook(
                phase_id=phase_num,
                phase_name=phase.name,
                delivery_repo=target_repo,
                artifacts=phase.required_artifacts,
                phase_summary=f"Phase {phase_num} ({phase.name}) completed.",
            )
            self._comms.log_checkpoint(
                agent="orchestrator", phase=phase.phase_id,
                subtask="notebook_generation",
                progress=f"Generated notebook for {phase.name}",
            )
        except Exception as exc:  # noqa: BLE001
            self._comms.log_error(
                agent="orchestrator",
                error_type="notebook_generation_failed",
                message=f"Failed to generate notebook for {phase.phase_id}: {exc}",
                severity="warning",
            )

    # -- Experiment capture layer (Phase 4) ---------------------------------

    _EXPERIMENT_PHASE = "phase_4"

    def _experiments_dir(self) -> Path | None:
        """Return the ``.zo/experiments/`` dir under the delivery repo.

        Returns ``None`` if the delivery repo doesn't exist yet (e.g.
        during tests that skip scaffolding, or before ``zo init``).
        """
        target_repo = Path(self._target.target_repo)
        if not target_repo.is_dir():
            return None
        return target_repo / ".zo" / "experiments"

    def _ensure_experiment_for_phase(
        self, phase_id: str,
    ) -> object | None:
        """Ensure a running experiment exists for the phase; mint if not.

        Only mints for ``phase_4``. Idempotent: returns the existing
        running experiment when one is already active for the phase;
        otherwise mints a new experiment with ``parent_id`` set to the
        latest experiment in the phase (for lineage).

        Returns ``None`` when the delivery repo is absent.
        """
        if phase_id != self._EXPERIMENT_PHASE:
            return None
        exp_dir = self._experiments_dir()
        if exp_dir is None:
            return None
        from zo.experiments import (
            ExperimentStatus,
            load_registry,
            mint_experiment,
        )
        registry = load_registry(
            exp_dir, project=self._plan.frontmatter.project_name,
        )
        # Return existing running experiment for this phase, if any.
        for exp in registry.experiments:
            if exp.phase == phase_id and exp.status == ExperimentStatus.RUNNING:
                return exp
        # Otherwise mint a new one, linked to the latest in this phase.
        latest = registry.latest_in_phase(phase_id)
        parent_id = latest.id if latest is not None else None
        return mint_experiment(
            registry_dir=exp_dir,
            project=self._plan.frontmatter.project_name,
            phase=phase_id,
            parent_id=parent_id,
        )

    def _finalize_experiments(
        self, phase: PhaseDefinition,
    ) -> list[str]:
        """Parse ``result.md`` for running Phase 4 experiments.

        For each running experiment in the phase, read its ``result.md``
        (if present), call ``update_result`` to store the result and
        mark the experiment complete. Returns a list of missing
        artifacts (one entry per running experiment without a valid
        ``result.md``) — empty when everything finalized cleanly.

        Non-phase_4 phases return an empty list immediately.
        """
        if phase.phase_id != self._EXPERIMENT_PHASE:
            return []
        exp_dir = self._experiments_dir()
        if exp_dir is None or not exp_dir.is_dir():
            return [".zo/experiments/<exp-NNN>/result.md (no experiments minted)"]
        from zo.experiments import (
            ExperimentStatus,
            load_registry,
            parse_result_md,
            update_result,
        )
        registry = load_registry(exp_dir)
        running = [
            e for e in registry.experiments
            if e.phase == phase.phase_id and e.status == ExperimentStatus.RUNNING
        ]
        if not running:
            # No running experiments; accept if any experiments exist for
            # this phase (i.e. all complete), otherwise flag.
            has_any = any(
                e.phase == phase.phase_id for e in registry.experiments
            )
            return [] if has_any else [
                ".zo/experiments/<exp-NNN>/result.md (no experiments for phase_4)",
            ]
        missing: list[str] = []
        for exp in running:
            artifacts = Path(exp.artifacts_dir)
            # Require ZOTrainingCallback output. Without it,
            # zo watch-training, the autonomous loop, and Phase 4
            # notebooks all break — the agent silently bypassed the
            # capture layer with a vanilla training loop.
            metrics_path = artifacts / "metrics.jsonl"
            status_path = artifacts / "training_status.json"
            if not metrics_path.exists():
                missing.append(
                    f".zo/experiments/{exp.id}/metrics.jsonl "
                    "(ZOTrainingCallback not used)",
                )
            if not status_path.exists():
                missing.append(
                    f".zo/experiments/{exp.id}/training_status.json "
                    "(ZOTrainingCallback not used)",
                )
            result_path = artifacts / "result.md"
            if not result_path.exists():
                missing.append(f".zo/experiments/{exp.id}/result.md")
                continue
            try:
                result = parse_result_md(result_path)
                update_result(exp_dir, exp.id, result)
            except Exception as exc:  # noqa: BLE001
                self._comms.log_error(
                    agent="orchestrator",
                    error_type="experiment_result_parse_failed",
                    message=f"Failed to parse {exp.id}/result.md: {exc}",
                    severity="warning",
                )
                missing.append(
                    f".zo/experiments/{exp.id}/result.md (parse failed)",
                )
        return missing

    def _auto_iterate_if_needed(
        self, phase: PhaseDefinition,
    ) -> GateEvaluation | None:
        """Consult the autonomous loop evaluator for phase_4 PROCEED.

        Returns a GateEvaluation (decision=ITERATE, reason logged from
        the LoopDecision) when the loop says CONTINUE — the caller
        keeps the phase ACTIVE and clears completed_subtasks so the
        Lead can start a fresh iteration (which mints a child exp via
        _ensure_experiment_for_phase on the next prompt build).

        Returns ``None`` when the loop is not applicable (non-phase_4,
        supervised gate mode) OR when the loop says stop (TARGET_HIT,
        PLATEAU, BUDGET_EXHAUSTED, DEAD_END) — in which case the caller
        finalizes the phase normally (COMPLETED + snapshot + notebook).
        """
        if phase.phase_id != self._EXPERIMENT_PHASE:
            return None
        # Supervised mode disables auto-iteration — every gate pauses.
        if self._gate_mode == GateMode.SUPERVISED:
            return None
        exp_dir = self._experiments_dir()
        if exp_dir is None or not exp_dir.is_dir():
            return None
        from zo.experiment_loop import (
            LoopVerdict,
            evaluate_loop_state,
            resolve_policy,
        )
        from zo.experiments import load_registry

        registry = load_registry(exp_dir)
        policy = resolve_policy(
            self._plan.experiment_loop if self._plan else None,
            low_token=self._low_token,
            max_iterations_override=self._max_iterations_override,
        )
        decision = evaluate_loop_state(registry, phase.phase_id, policy)

        # Log the decision to DECISION_LOG regardless of verdict.
        self._memory.append_decision(DecisionEntry(
            title=f"Loop verdict for {phase.phase_id}: {decision.verdict}",
            context=(
                f"Completed experiments: {decision.completed_count}. "
                f"Last exp: {decision.last_exp_id or 'none'}."
            ),
            decision=str(decision.verdict),
            rationale=decision.reason,
            outcome=str(decision.verdict),
        ))

        if decision.verdict != LoopVerdict.CONTINUE:
            # Stop — caller proceeds with phase completion.
            return None

        # Continue — reset phase, next prompt mints child exp.
        phase.status = PhaseStatus.ACTIVE
        phase.completed_subtasks.clear()
        return GateEvaluation(
            phase_id=phase.phase_id,
            gate_type=GateType.AUTOMATED,
            decision=GateDecision.ITERATE,
            rationale=f"Autonomous iteration: {decision.reason}",
        )

    def _abort_running_experiments(self, phase_id: str) -> None:
        """Mark all running experiments in a phase as ABORTED.

        Used when a phase is iterated — the in-flight experiment didn't
        produce a result, so a fresh one will be minted on the next
        lead prompt build.
        """
        if phase_id != self._EXPERIMENT_PHASE:
            return
        exp_dir = self._experiments_dir()
        if exp_dir is None or not exp_dir.is_dir():
            return
        from zo.experiments import (
            ExperimentStatus,
            load_registry,
            update_status,
        )
        registry = load_registry(exp_dir)
        for exp in registry.experiments:
            if exp.phase == phase_id and exp.status == ExperimentStatus.RUNNING:
                update_status(exp_dir, exp.id, ExperimentStatus.ABORTED)

    def _prompt_experiment_context(self, phase: PhaseDefinition) -> str:
        """Lead prompt section describing the active experiment (Phase 4).

        Includes the autonomous-loop briefing when gate mode allows it —
        Model Builder must auto-propose from parent's shortfalls without
        asking the human. Supervised mode keeps the human-in-the-loop
        phrasing.
        """
        if phase.phase_id != self._EXPERIMENT_PHASE:
            return ""
        exp = self._ensure_experiment_for_phase(phase.phase_id)
        if exp is None:
            return ""
        parent_line = (
            f" Parent: `{exp.parent_id}`." if exp.parent_id else
            " This is the root experiment for the phase."
        )

        # Policy + autonomy framing.
        from zo.experiment_loop import resolve_policy

        policy = resolve_policy(
            self._plan.experiment_loop if self._plan else None,
            low_token=self._low_token,
            max_iterations_override=self._max_iterations_override,
        )
        autonomous = self._gate_mode != GateMode.SUPERVISED

        loop_section = self._render_loop_briefing(exp, policy, autonomous)

        return dedent(f"""\
            # Experiment Capture Layer

            This phase is running **{exp.id}**.{parent_line}
            Artifacts directory: `{exp.artifacts_dir}` — every file for
            this iteration lives here.

            **Files agents write:**
            - `{exp.id}/hypothesis.md` — Model Builder writes BEFORE training
              (YAML frontmatter + markdown body). States the testable claim.
            - `{exp.id}/config.yaml` — frozen config snapshot (architecture,
              hyperparameters, data hash).
            - `{exp.id}/metrics.jsonl` + `{exp.id}/training_status.json` — emitted
              automatically by `ZOTrainingCallback.for_experiment(
                  registry_dir='.zo/experiments', experiment_id='{exp.id}')`.
              Use this factory; it handles the paths.
            - `{exp.id}/result.md` — Oracle writes AFTER eval. YAML frontmatter
              with `oracle_tier`, `primary_metric` (`name`, `value`,
              optional `delta_vs_parent`), `secondary_metrics`; markdown
              body has `## Shortfalls` bullets.
            - `{exp.id}/next.md` — Model Builder writes AFTER result. One
              `## exp-NNN` section per proposed follow-up experiment.
            - `{exp.id}/diagnosis.md` (optional) — XAI or Domain Evaluator
              writes when a failure-mode breakdown is needed.

            **Gate requirement:** the phase advances only when `result.md`
            exists in the active experiment's directory. The orchestrator
            parses it, marks the experiment complete, and computes
            `delta_vs_parent` automatically if the parent used the same
            `primary_metric.name`.

            {loop_section}""")

    @staticmethod
    def _render_loop_briefing(
        exp: object,
        policy: object,
        autonomous: bool,
    ) -> str:
        """Build the autonomy + proposer briefing block of the experiment prompt."""
        parent_id = getattr(exp, "parent_id", None)
        exp_id = getattr(exp, "id", "exp-???")
        stop_tier = getattr(policy, "stop_on_tier", "must_pass")
        max_iter = getattr(policy, "max_iterations", 10)
        plateau_eps = getattr(policy, "plateau_epsilon", 0.01)
        plateau_runs = getattr(policy, "plateau_runs", 3)

        if not autonomous:
            # Supervised mode — human reviews every gate.
            return dedent(f"""\
                **Iteration:** if this phase is re-iterated, a fresh
                experiment is minted with `parent_id = {exp_id}`. In
                supervised mode the human decides whether to iterate
                or advance at every gate.""")

        proposer_section = ""
        if parent_id:
            proposer_section = dedent(f"""\

                **Auto-proposer (child experiment — DO NOT ask the human):**
                1. Read `{parent_id}/result.md` — every bullet under `## Shortfalls`
                   is a candidate target for this iteration.
                2. Read `{parent_id}/diagnosis.md` if present — it tells you
                   *why* the shortfalls occurred at the model-internals level.
                3. Read `{parent_id}/next.md` — Model Builder already proposed
                   follow-ups; pick the highest-leverage idea.
                4. Write `{exp_id}/hypothesis.md` addressing the most impactful
                   shortfall. Rationale MUST cite specific findings from the
                   parent (not generic statements). No "should I continue?"
                   prompts — the loop is autonomous.""")

        return dedent("""\
            # Autonomous Iteration Loop

            This phase runs through an autonomous loop — the orchestrator
            keeps iterating experiments until one of:
            - `TARGET_HIT` — latest exp hits `oracle_tier >= {stop_tier}`
            - `BUDGET_EXHAUSTED` — completed {max_iter} iterations
            - `PLATEAU` — last {plateau_runs} children all had
              `|delta_vs_parent| < {plateau_eps}`
            - `DEAD_END` — no novel hypothesis possible (all candidates
              near-duplicate past experiments)

            Subtask completion → Oracle result.md → gate check. If the
            loop verdict is CONTINUE, the orchestrator marks this
            experiment complete, mints a child with
            `parent_id = {exp_id}`, and the cycle repeats WITHOUT
            pausing for human input.{proposer_section}

            Stop conditions and the next hypothesis are decided
            automatically. Your job is to do one iteration cleanly, not
            to decide when to stop.""").format(
                stop_tier=stop_tier, max_iter=max_iter,
                plateau_runs=plateau_runs, plateau_eps=plateau_eps,
                exp_id=exp_id, proposer_section=proposer_section,
            )

    def _generate_snapshot(
        self,
        phase: PhaseDefinition,
        gate_decision: str,
        gate_outcome: str,
    ) -> None:
        """Write a phase completion snapshot to ``{memory_root}/snapshots/``.

        Called at every gate PROCEED (automated or human). Failures are
        logged as warnings but do not block the gate — the snapshot is a
        reporting artifact, not a correctness gate.
        """
        try:
            from zo.snapshots import PhaseSnapshot, write_snapshot

            artifacts_missing = self._check_artifacts(phase)
            artifacts_present = [
                a for a in phase.required_artifacts if a not in artifacts_missing
            ]

            decisions = self._recent_decisions_for_phase(phase.phase_id)
            issues = self._issues_for_phase(phase.phase_id)

            snap = PhaseSnapshot(
                phase_id=phase.phase_id,
                phase_name=phase.name,
                status=str(phase.status),
                gate_decision=gate_decision,
                gate_outcome=str(gate_outcome),
                subtasks_total=len(phase.subtasks),
                subtasks_completed=len(phase.completed_subtasks),
                completed_subtask_ids=list(phase.completed_subtasks),
                remaining_subtask_ids=[
                    s for s in phase.subtasks if s not in phase.completed_subtasks
                ],
                required_artifacts=list(phase.required_artifacts),
                artifacts_present=artifacts_present,
                artifacts_missing=artifacts_missing,
                recent_decisions=decisions,
                issues=issues,
            )
            path = write_snapshot(self._memory.memory_root, snap)
            self._comms.log_checkpoint(
                agent="orchestrator", phase=phase.phase_id,
                subtask="snapshot_generation",
                progress=f"Phase snapshot written: {path.name}",
            )
        except Exception as exc:  # noqa: BLE001
            self._comms.log_error(
                agent="orchestrator",
                error_type="snapshot_generation_failed",
                message=f"Failed to write snapshot for {phase.phase_id}: {exc}",
                severity="warning",
            )

    def _recent_decisions_for_phase(
        self, phase_id: str, limit: int = 10,
    ) -> list[dict[str, str]]:
        """Pull recent decision events mentioning the phase, newest last."""
        try:
            events = self._comms.query_logs(event_type="decision")
        except Exception:  # noqa: BLE001
            return []
        matches: list[dict[str, str]] = []
        for ev in events:
            title = getattr(ev, "title", "") or ""
            rationale = getattr(ev, "rationale", "") or ""
            if phase_id in title or phase_id in rationale:
                matches.append({
                    "timestamp": ev.timestamp.isoformat()
                    if hasattr(ev.timestamp, "isoformat") else str(ev.timestamp),
                    "title": title,
                })
        return matches[-limit:]

    def _issues_for_phase(
        self, phase_id: str, limit: int = 10,
    ) -> list[dict[str, str]]:
        """Pull error/warning events mentioning the phase, newest last."""
        try:
            events = self._comms.query_logs(event_type="error")
        except Exception:  # noqa: BLE001
            return []
        matches: list[dict[str, str]] = []
        for ev in events:
            message = getattr(ev, "description", "") or ""
            error_type = getattr(ev, "error_type", "") or ""
            severity = str(getattr(ev, "severity", "info"))
            # Phase association is best-effort: match on message content.
            if phase_id in message or phase_id in error_type:
                matches.append({
                    "severity": severity,
                    "message": f"{error_type}: {message}" if error_type else message,
                })
        return matches[-limit:]

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
        plan_path = self._plan_path if self._plan_path is not None else (
            self._zo_root / "plans"
            / f"{p.frontmatter.project_name}.md"
        )
        return dedent(f"""\
            # Plan Context

            **CRITICAL — Read the full plan first:**
            Before doing ANYTHING else, read the complete plan file at
            `{plan_path}`. It contains data source paths, domain priors,
            environment config, agent adaptations, and delivery structure
            that you MUST know before starting work. The summary below is
            not sufficient — read the file.

            **Objective:** {p.objective}

            **Oracle:**
            {oracle_text}

            **Constraints:**
            {p.constraints}""")

    def _prompt_phase(self, phase: PhaseDefinition) -> str:
        subtasks = "\n".join(f"- {s}" for s in phase.subtasks)
        agents = ", ".join(phase.assigned_agents) or "none assigned"
        deps = ", ".join(phase.depends_on) or "none"
        artifacts = (
            "\n".join(f"- {a}" for a in phase.required_artifacts)
            if phase.required_artifacts
            else "- (none specified)"
        )
        return dedent(f"""\
            # Current Phase: {phase.name} ({phase.phase_id})

            {phase.description}

            **Subtasks:**
            {subtasks}

            **Required artifacts (must exist before gate passes):**
            {artifacts}

            **Assigned agents:** {agents}
            **Gate type:** {phase.gate_type}
            **Dependencies:** {deps}""")

    def _prompt_contracts(self, phase: PhaseDefinition) -> str:
        if not self._workflow:
            return ""
        lines: list[str] = []
        for c in self._workflow.agent_contracts:
            if c.phase_id == phase.phase_id:
                block = (
                    f"### {c.agent_name}\nRole: {c.role_description}\n"
                    f"Owns: {', '.join(c.ownership) or 'n/a'}\n"
                    f"Off-limits: {', '.join(c.off_limits) or 'n/a'}\n"
                    f"Produces: {', '.join(c.contract_produced)}\n"
                    f"Consumes: {', '.join(c.contract_consumed)}"
                )
                adaptation = self._adaptation_for(c.agent_name)
                if adaptation:
                    block += (
                        "\n\n**Project-specific adaptation "
                        f"(append to {c.agent_name}'s base instructions "
                        "when spawning):**\n"
                        + adaptation
                    )
                lines.append(block)
        return ("# Agent Contracts\n\n" + "\n\n".join(lines)) if lines else ""

    def _adaptation_for(self, agent_name: str) -> str | None:
        """Return the plan's adaptation text for *agent_name*, or None.

        Wraps ``AgentConfig.adaptation_for`` so the orchestrator tolerates
        plans that lack an ``agents`` section entirely (older plans, or
        plans drafted before the adaptation feature existed).
        """
        if not self._plan.agents:
            return None
        return self._plan.agents.adaptation_for(agent_name)

    def _ensure_custom_agents(self) -> None:
        """Create agent definition files for plan-specified custom agents.

        Writes ``.md`` files to ``.claude/agents/custom/`` for any custom
        agents declared in the plan that don't already have definitions.
        Existing files are reused (from previous projects).
        """
        if not self._plan.agents or not self._plan.agents.custom_agents:
            return
        custom_dir = self._zo_root / ".claude" / "agents" / "custom"
        custom_dir.mkdir(parents=True, exist_ok=True)
        for spec in self._plan.agents.custom_agents:
            agent_path = custom_dir / f"{spec.name}.md"
            if agent_path.exists():
                self._comms.log_checkpoint(
                    agent="orchestrator", phase="setup",
                    subtask="custom-agent-reuse",
                    progress=f"Reusing custom agent: {spec.name}",
                )
                continue
            agent_md = _render_custom_agent(spec)
            agent_path.write_text(agent_md, encoding="utf-8")
            self._comms.log_decision(
                agent="orchestrator",
                title=f"Created custom agent: {spec.name}",
                rationale=f"Plan specifies specialist not in core library: {spec.role}",
                outcome="agent_created",
            )

    def _prompt_roster(self) -> str:
        agents_dir = self._zo_root / ".claude" / "agents"
        core = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
        custom_dir = agents_dir / "custom"
        custom = sorted(custom_dir.glob("*.md")) if custom_dir.is_dir() else []
        # Exclude README from custom agents list
        custom = [f for f in custom if f.stem.lower() != "readme"]

        if self._low_token:
            # Compact roster: comma-separated names, no descriptive blurb.
            names = [f.stem for f in core] + [f.stem for f in custom]
            return "# Agent Roster\n\nAvailable: " + ", ".join(names)

        lines = ["# Agent Roster\n", "## Core Agents\n"]
        lines.extend(f"- {f.stem}" for f in core)
        if custom:
            lines.append("\n## Custom Agents (from previous projects)\n")
            lines.extend(f"- {f.stem}" for f in custom)
        lines.append(
            "\nCreate new specialists in `.claude/agents/custom/` "
            "when the project needs expertise not covered above. "
            "Custom agents can be any role: domain experts, data "
            "scientists, researchers, testers, QA specialists, etc."
        )
        return "\n".join(lines)

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
            - Escalate to human if blockers persist after one debate round.

            # Delivery Repo

            - Read **STRUCTURE.md** in the delivery repo for directory layout.
            - Agents read ONLY their relevant section to stay context-efficient.
            - **configs/** — YAML configuration. Edit configs, not code, to change experiments.
            - **experiments/** — Context trail. Update experiments/README.md index after each run.
            - Each experiment gets: frozen config snapshot, results.json, notes.md.
            - **Required artifacts** must exist before gate advances (see phase section above).
            - A Jupyter notebook is auto-generated after each phase completes.

            # Docker

            - All compute (training, evaluation, benchmarks) runs inside Docker.
            - Build: `docker compose -f docker/docker-compose.yml build`
            - Run: `docker compose -f docker/docker-compose.yml run --rm gpu <command>`
            - Agents may modify docker/Dockerfile to add project-specific packages.
            - Never install dependencies outside Docker — use pyproject.toml + uv sync.""")

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
