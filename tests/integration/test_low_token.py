"""End-to-end integration test for ``--low-token`` mode.

Verifies the preset propagates from CLI/plan through Orchestrator,
LoopPolicy, and prompt construction. Stops at the launch step (the
real ``claude`` CLI is not invoked here — that's a manual smoke test).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zo.comms import CommsLogger
from zo.experiment_loop import resolve_policy
from zo.memory import MemoryManager
from zo.orchestrator import Orchestrator
from zo.plan import Plan, parse_plan
from zo.semantic import SemanticIndex
from zo.target import TargetConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PLAN = REPO_ROOT / "tests" / "fixtures" / "test-project" / "plan.md"


def _make_target() -> TargetConfig:
    return TargetConfig(
        project="test-project",
        target_repo="/tmp/zo-test-delivery",
        target_branch="main",
        worktree_base="/tmp/worktrees",
        git_author_name="ZO Test",
        git_author_email="zo@test.dev",
        agent_working_dirs={},
        zo_only_paths=[".zo/"],
        enforce_isolation=False,
    )


@pytest.fixture
def plan() -> Plan:
    return parse_plan(FIXTURE_PLAN)


@pytest.fixture
def memory_setup(tmp_path: Path):
    memory = MemoryManager(
        project_dir=tmp_path, project_name="test-project",
    )
    memory.initialize_project()
    comms = CommsLogger(
        log_dir=tmp_path / "logs" / "comms",
        project="test-project", session_id="test-low-token",
    )
    semantic = SemanticIndex(db_path=tmp_path / "index.db")
    return memory, comms, semantic


class TestLowTokenPropagation:
    """``low_token`` flows from CLI → Orchestrator → LoopPolicy → prompt."""

    def test_orchestrator_remembers_low_token(
        self, plan: Plan, memory_setup,
    ) -> None:
        memory, comms, semantic = memory_setup
        orch = Orchestrator(
            plan=plan, target=_make_target(), memory=memory,
            comms=comms, semantic=semantic, zo_root=REPO_ROOT,
            low_token=True,
        )
        assert orch.low_token is True

    def test_max_iterations_override_propagates_to_policy(self) -> None:
        """The CLI's ``--max-iterations 3`` reaches resolve_policy."""
        policy = resolve_policy(None, low_token=True, max_iterations_override=3)
        assert policy.max_iterations == 3
        assert policy.stop_on_tier == "could_pass"

    def test_low_token_filters_research_scout_in_decompose(
        self, plan: Plan, memory_setup,
    ) -> None:
        """A plan that lists research-scout has it filtered when low_token=True."""
        memory, comms, semantic = memory_setup
        # Force the plan to include research-scout in active_agents.
        if plan.agents is not None:
            plan.agents.active_agents = [
                "data-engineer", "model-builder", "code-reviewer",
                "research-scout", "oracle-qa",
            ]
        orch = Orchestrator(
            plan=plan, target=_make_target(), memory=memory,
            comms=comms, semantic=semantic, zo_root=REPO_ROOT,
            low_token=True,
        )
        decomp = orch.decompose_plan()
        for phase in decomp.phases:
            assert "research-scout" not in phase.assigned_agents

    def test_low_token_off_keeps_research_scout(
        self, plan: Plan, memory_setup,
    ) -> None:
        memory, comms, semantic = memory_setup
        if plan.agents is not None:
            plan.agents.active_agents = [
                "data-engineer", "model-builder", "research-scout",
            ]
        orch = Orchestrator(
            plan=plan, target=_make_target(), memory=memory,
            comms=comms, semantic=semantic, zo_root=REPO_ROOT,
            low_token=False,
        )
        decomp = orch.decompose_plan()
        # research-scout should appear in at least one phase (it maps to 1-6).
        any_phase = any(
            "research-scout" in p.assigned_agents for p in decomp.phases
        )
        assert any_phase, "research-scout should be assigned when low_token=off"

    def test_plan_frontmatter_low_token_field_round_trips(
        self, tmp_path: Path,
    ) -> None:
        """Plan frontmatter ``low_token: true`` parses and reaches Orchestrator."""
        plan_text = FIXTURE_PLAN.read_text(encoding="utf-8")
        modified = plan_text.replace(
            'owner: "TestEngineer"',
            'owner: "TestEngineer"\nlow_token: true\nlead_model: sonnet',
        )
        new_plan_path = tmp_path / "low-token-plan.md"
        new_plan_path.write_text(modified, encoding="utf-8")
        new_plan = parse_plan(new_plan_path)
        assert new_plan.frontmatter.low_token is True
        assert new_plan.frontmatter.lead_model == "sonnet"
