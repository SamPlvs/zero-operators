"""CLI entry point for Zero Operators.

Provides the ``zo`` command group with subcommands for building,
continuing, initializing, and inspecting ZO projects.

Usage::

    zo build plans/my-project.md --gate-mode auto
    zo continue my-project
    zo init my-project
    zo status my-project
    zo draft ~/docs/req.md ~/data/ --project my-project
"""

from __future__ import annotations

import uuid
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from zo._orchestrator_models import GateMode

console = Console()

# ZO brand amber for highlights
_AMBER = "bold #F0C040"
_DIM = "#8a6020"
_VOID = "#080808"
_VERSION = "1.0.1"


def _zo_root() -> Path:
    """Derive the ZO repository root from the CLI package location."""
    return Path(__file__).resolve().parent.parent.parent


def _gate_mode_from_str(value: str) -> GateMode:
    """Map CLI gate-mode string to GateMode enum."""
    mapping = {
        "supervised": GateMode.SUPERVISED,
        "auto": GateMode.AUTO,
        "full-auto": GateMode.FULL_AUTO,
    }
    return mapping[value]


def _show_banner(
    project: str = "",
    mode: str = "",
    phase: str = "",
    gate_mode: str = "",
) -> None:
    """Display the ZO brand panel at startup."""
    from rich.panel import Panel
    from rich.text import Text

    logo = Text()
    logo.append("  ◎ ", style="#F0C040 bold")
    logo.append("Zero Operators", style="#F0C040 bold")
    logo.append(f"  v{_VERSION}\n", style=_DIM)
    logo.append("     Autonomous AI Research & Engineering Teams\n", style=_DIM)
    if project:
        logo.append("\n  Project:   ", style=_DIM)
        logo.append(project, style="#F0C040")
    if mode:
        logo.append("\n  Mode:      ", style=_DIM)
        logo.append(mode, style="#F0C040")
    if phase:
        logo.append("\n  Phase:     ", style=_DIM)
        logo.append(phase, style="#F0C040")
    if gate_mode:
        logo.append("\n  Gates:     ", style=_DIM)
        logo.append(gate_mode, style="#F0C040")

    console.print(Panel(
        logo,
        border_style="#F0C040",
        padding=(0, 1),
    ))


@click.group()
@click.version_option(version=_VERSION, package_name="zero-operators")
def cli() -> None:
    """Zero Operators -- Autonomous AI research and engineering team system."""


def _show_phase_review(phase, decomp, plan, gate_mode: str) -> None:  # noqa: ANN001
    """Display phase overview for human review before launch."""
    from rich.rule import Rule

    console.print()
    console.print(Rule(f"[{_AMBER}] Phase Review ", style=_AMBER))
    console.print()

    # Phase header
    console.print(f"  [{_AMBER}]Phase:[/]  {phase.phase_id} — {phase.name}")
    console.print(f"  [{_AMBER}]Goal:[/]   {phase.description}")
    console.print(f"  [{_AMBER}]Gate:[/]   {phase.gate_type} ({gate_mode} mode)")
    console.print()

    # Subtasks
    console.print(f"  [{_AMBER}]Subtasks:[/]")
    for i, st in enumerate(phase.subtasks, 1):
        console.print(f"    {i}. {st}")
    console.print()

    # Agents
    console.print(f"  [{_AMBER}]Agents:[/]  {', '.join(phase.assigned_agents)}")
    console.print()

    # Contracts summary
    phase_contracts = [
        c for c in decomp.agent_contracts if c.phase_id == phase.phase_id
    ]
    if phase_contracts:
        console.print(f"  [{_AMBER}]Contracts:[/]")
        for c in phase_contracts:
            owns = ", ".join(c.ownership) if c.ownership else "n/a"
            console.print(f"    [{_DIM}]{c.agent_name}[/] → owns: {owns}")
        console.print()

    # Oracle / gate criteria
    if plan.oracle:
        console.print(f"  [{_AMBER}]Gate Criteria (Oracle):[/]")
        if plan.oracle.primary_metric:
            console.print(f"    Metric: {plan.oracle.primary_metric}")
        if plan.oracle.target_threshold:
            console.print(f"    Target: {plan.oracle.target_threshold}")
        if plan.oracle.evaluation_method:
            console.print(f"    Method: {plan.oracle.evaluation_method}")
        console.print()

    # Dependencies
    if phase.depends_on:
        console.print(
            f"  [{_AMBER}]Depends on:[/]  {', '.join(phase.depends_on)}"
        )
        console.print()

    console.print(Rule(style=_DIM))


def _ask_additional_instructions(gate_mode: str) -> str:
    """Prompt the user for additional instructions before launch.

    Skipped in full-auto mode (no human interaction).
    """
    if gate_mode == "full-auto":
        return ""
    console.print(
        f"  [{_AMBER}]Additional instructions?[/]"
        f" [{_DIM}](press Enter to skip, or type your request)[/]"
    )
    console.print()
    user_input = console.input(f"  [{_AMBER}]>[/] ").strip()
    if user_input:
        console.print(f"  [{_DIM}]Added to lead prompt.[/]")
    return user_input


def _launch_and_monitor(
    *,
    wrapper,  # noqa: ANN001
    prompt: str,
    team_name: str,
    zo_root: Path,
    orchestrator,  # noqa: ANN001
    semantic,  # noqa: ANN001
    no_tmux: bool,
) -> None:
    """Shared launch → monitor → end-session flow for all modes."""
    use_tmux = not no_tmux
    console.print(f"\n[{_AMBER}]Launching lead session:[/] team={team_name}")
    process = wrapper.launch_lead_session(
        prompt, cwd=str(zo_root), team_name=team_name, use_tmux=use_tmux,
    )

    if process.tmux_pane_id:
        console.print(f"[{_AMBER}]Agent session running in tmux.[/]")
        console.print(
            f"[{_DIM}]Ctrl-b n → agent window  |  Ctrl-b p → back here[/]"
        )
        console.print(
            f"[{_DIM}]Ctrl-b q N → jump to pane N  |  Ctrl-b z → zoom pane[/]"
        )
    else:
        console.print(f"[{_AMBER}]Monitoring session:[/] pid={process.pid}")
        console.print(
            f"[{_DIM}]Headless mode — logs at: logs/wrapper/{team_name}-stdout.log[/]"
        )
    console.print()

    _seen_events: set[str] = set()

    def _print_status(team_status, pane_snapshot=""):  # noqa: ANN001
        from datetime import UTC, datetime

        elapsed = ""
        if process.started_at:
            secs = int((datetime.now(UTC) - process.started_at).total_seconds())
            mins, sec = divmod(secs, 60)
            elapsed = f"{mins}m{sec:02d}s"

        header_parts = []
        if elapsed:
            header_parts.append(f"[{_DIM}][{elapsed}][/]")
        if team_status.members:
            names = ", ".join(m.name for m in team_status.members)
            header_parts.append(f"[{_AMBER}]Team:[/] {names}")
        if team_status.tasks_total > 0:
            header_parts.append(
                f"Tasks: [{_AMBER}]{team_status.tasks_completed}[/]"
                f"/{team_status.tasks_total} done, "
                f"{team_status.tasks_in_progress} active"
            )
        if header_parts:
            console.print("  " + "  ".join(header_parts))

        tasks = wrapper.read_task_list(process.team_name)
        for task in tasks:
            st = task.get("status", "")
            content = task.get("content", "")[:60]
            owner = task.get("owner", "")
            if st == "completed":
                icon = "[green]✓[/]"
            elif st == "in_progress":
                icon = f"[{_AMBER}]▶[/]"
            else:
                icon = f"[{_DIM}]○[/]"
            owner_str = f" [{_DIM}]({owner})[/]" if owner else ""
            console.print(f"    {icon} {content}{owner_str}")

        comms_dir = zo_root / "logs" / "comms"
        if comms_dir.is_dir():
            import json as _json
            for log_file in sorted(comms_dir.glob("*.jsonl"), reverse=True)[:1]:
                try:
                    lines = log_file.read_text(encoding="utf-8").splitlines()
                except OSError:
                    continue
                for line in lines[-10:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = _json.loads(line)
                    except ValueError:
                        continue
                    eid = evt.get("event_id", "")
                    if eid in _seen_events:
                        continue
                    _seen_events.add(eid)
                    etype = evt.get("event_type", "")
                    agent = evt.get("agent", "")
                    if etype == "decision":
                        title = evt.get("title", "")[:70]
                        console.print(
                            f"    [{_AMBER}]◆ DECISION[/] [{_DIM}]{agent}:[/] {title}"
                        )
                    elif etype == "gate":
                        result = evt.get("result", "")
                        gphase = evt.get("phase_id", "")
                        console.print(
                            f"    [{_AMBER}]⊘ GATE[/] {gphase}: {result}"
                        )
                    elif etype == "checkpoint":
                        progress = evt.get("progress", "")[:70]
                        console.print(f"    [{_DIM}]↳ {agent}: {progress}[/]")
                    elif etype == "error":
                        desc = evt.get("description", "")[:70]
                        console.print(
                            f"    [red]✗ ERROR[/] [{_DIM}]{agent}:[/] {desc}"
                        )

        if not tasks and not header_parts:
            console.print(f"  [{_DIM}][{elapsed}] Waiting for agents...[/]")
        console.print()

    process = wrapper.wait_for_completion(process, on_status=_print_status)

    if process.status == "completed":
        console.print("[green bold]Session completed successfully.[/]")
    else:
        console.print(f"[red bold]Session ended with status:[/] {process.status}")

    orchestrator.end_session()
    semantic.close()


@cli.command()
@click.argument("plan_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--gate-mode",
    type=click.Choice(["supervised", "auto", "full-auto"]),
    default="supervised",
    help="Gate evaluation mode (default: supervised)",
)
@click.option("--no-tmux", is_flag=True, help="Disable tmux agent visibility")
def build(plan_path: Path, gate_mode: str, no_tmux: bool) -> None:
    """Launch a project from a plan.md file.

    Smart mode detection:
    - Fresh project (no state) -> build from scratch
    - Existing state -> continue from current phase
    - Plan edited since last run -> re-decompose and continue
    """
    from zo.comms import CommsLogger
    from zo.memory import MemoryManager
    from zo.orchestrator import Orchestrator
    from zo.plan import parse_plan, validate_plan
    from zo.semantic import SemanticIndex
    from zo.target import parse_target
    from zo.wrapper import LifecycleWrapper

    zo_root = _zo_root()

    # 1. Parse and validate plan
    plan = parse_plan(plan_path)
    report = validate_plan(plan)
    if not report.valid:
        console.print("[red bold]Plan validation failed:[/]")
        for issue in report.issues:
            console.print(f"  [{_DIM}]{issue.section}:[/] {issue.message}")
        raise SystemExit(1)

    project_name = plan.frontmatter.project_name

    # 2. Parse target file
    target_path = zo_root / "targets" / f"{project_name}.target.md"
    if not target_path.exists():
        console.print(f"[red bold]Target file not found:[/] {target_path}")
        raise SystemExit(1)
    target = parse_target(target_path)

    # 3. Initialize memory and detect mode
    memory = MemoryManager(project_dir=zo_root, project_name=project_name)
    memory.initialize_project()
    state_check = memory.read_state()
    detected_mode = "build" if state_check.phase == "init" else "continue"

    # 4. Show brand banner
    _show_banner(
        project=project_name,
        mode=detected_mode,
        phase=state_check.phase if detected_mode == "continue" else "starting",
        gate_mode=gate_mode,
    )

    # 5. Create CommsLogger and SemanticIndex
    session_id = f"s-{uuid.uuid4().hex[:8]}"
    comms = CommsLogger(
        log_dir=zo_root / "logs" / "comms",
        project=project_name, session_id=session_id,
    )
    db_path = memory.memory_root / "index.db"
    semantic = SemanticIndex(db_path=db_path)

    decisions = memory.read_decisions()
    priors = memory.read_priors()
    if decisions:
        semantic.index_decisions(decisions)
    if priors:
        semantic.index_priors(priors)

    # 6. Create Orchestrator
    gm = _gate_mode_from_str(gate_mode)
    orchestrator = Orchestrator(
        plan=plan, target=target, memory=memory, comms=comms,
        semantic=semantic, zo_root=zo_root, gate_mode=gm,
    )
    orchestrator.start_session()

    # 7. Check for plan edits (continue mode)
    decomp = orchestrator.decompose_plan()
    if detected_mode == "continue" and orchestrator.check_plan_edited():
        console.print(f"[{_AMBER}]Plan changed since last run — re-decomposed.[/]")

    console.print(
        f"[{_DIM}]{len(decomp.phases)} phases, "
        f"{len(decomp.agent_contracts)} contracts[/]"
    )

    # 8. Get current phase
    phase = orchestrator.get_current_phase()
    if phase is None:
        console.print("[green bold]All phases complete. Nothing to do.[/]")
        raise SystemExit(0)

    # 9. Phase review + additional instructions
    _show_phase_review(phase, decomp, plan, gate_mode)
    extra = _ask_additional_instructions(gate_mode)

    prompt = orchestrator.build_lead_prompt(phase)
    if extra:
        prompt += f"\n\n---\n\n# Additional Human Instructions\n\n{extra}\n"

    # 10. Launch, monitor, end session
    wrapper = LifecycleWrapper(comms=comms, log_dir=zo_root / "logs" / "wrapper")
    _launch_and_monitor(
        wrapper=wrapper,
        prompt=prompt,
        team_name=f"zo-{project_name}",
        zo_root=zo_root,
        orchestrator=orchestrator,
        semantic=semantic,
        no_tmux=no_tmux,
    )


@cli.command("continue")
@click.argument("project_name")
@click.option(
    "--gate-mode",
    type=click.Choice(["supervised", "auto", "full-auto"]),
    default="supervised",
)
@click.option("--no-tmux", is_flag=True, help="Disable tmux agent visibility")
def continue_(project_name: str, gate_mode: str, no_tmux: bool) -> None:
    """Resume a paused project. Shorthand for zo build with the existing plan.

    Finds plans/{project_name}.md and runs zo build on it.
    """
    zo_root = _zo_root()
    plan_path = zo_root / "plans" / f"{project_name}.md"
    if not plan_path.exists():
        console.print(f"[red bold]Plan not found:[/] {plan_path}")
        console.print("Run [bold]zo build plans/your-plan.md[/] first.")
        raise SystemExit(1)

    # Delegate to build
    ctx = click.get_current_context()
    ctx.invoke(build, plan_path=plan_path, gate_mode=gate_mode, no_tmux=no_tmux)


@cli.command("init")
@click.argument("project_name")
@click.option(
    "--scaffold-delivery",
    type=click.Path(),
    default=None,
    help="Create standard ML project layout with Docker support at PATH.",
)
def init(project_name: str, scaffold_delivery: str | None) -> None:
    """Initialize a new project scaffold.

    Creates:
    - memory/{project_name}/STATE.md
    - memory/{project_name}/DECISION_LOG.md
    - memory/{project_name}/PRIORS.md
    - memory/{project_name}/sessions/
    - targets/{project_name}.target.md (template)
    - plans/{project_name}.md (template with all 8 required sections)

    With --scaffold-delivery PATH, also creates a delivery repo layout
    with data/, src/, Docker files, and a bare pyproject.toml.
    """
    zo_root = _zo_root()

    # Initialize memory
    from zo.memory import MemoryManager

    memory = MemoryManager(project_dir=zo_root, project_name=project_name)
    memory.initialize_project()
    console.print(f"[green]Memory initialized:[/] {memory.memory_root}")

    # Create target template
    targets_dir = zo_root / "targets"
    targets_dir.mkdir(parents=True, exist_ok=True)
    target_path = targets_dir / f"{project_name}.target.md"
    if not target_path.exists():
        target_path.write_text(
            _TARGET_TEMPLATE.format(project_name=project_name),
            encoding="utf-8",
        )
        console.print(f"[green]Target template created:[/] {target_path}")
    else:
        console.print(f"[{_DIM}]Target already exists:[/] {target_path}")

    # Create plan template
    plans_dir = zo_root / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f"{project_name}.md"
    if not plan_path.exists():
        plan_path.write_text(
            _PLAN_TEMPLATE.format(project_name=project_name),
            encoding="utf-8",
        )
        console.print(f"[green]Plan template created:[/] {plan_path}")
    else:
        console.print(f"[{_DIM}]Plan already exists:[/] {plan_path}")

    # Optional delivery repo scaffold
    if scaffold_delivery is not None:
        from zo.scaffold import scaffold_delivery as _scaffold

        _scaffold(Path(scaffold_delivery), project_name)

    console.print(f"\n[{_AMBER}]Project '{project_name}' scaffolded.[/]")
    console.print("Next steps:")
    console.print(f"  1. Edit [bold]{plan_path}[/]")
    console.print(f"  2. Edit [bold]{target_path}[/]")
    console.print(f"  3. Run [bold]zo build plans/{project_name}.md[/]")


@cli.command()
@click.argument("project_name")
def status(project_name: str) -> None:
    """Show current project status from STATE.md."""
    from zo.memory import MemoryManager

    zo_root = _zo_root()
    memory = MemoryManager(project_dir=zo_root, project_name=project_name)

    state_path = memory.memory_root / "STATE.md"
    if not state_path.exists():
        console.print(
            f"[red bold]No STATE.md found for '{project_name}'.[/] "
            "Run [bold]zo init[/] first."
        )
        raise SystemExit(1)

    state = memory.read_state()

    table = Table(title=f"Project: {project_name}", style=_AMBER)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Mode", state.mode)
    table.add_row("Phase", state.phase)
    table.add_row("Last Subtask", state.last_completed_subtask or "none")
    table.add_row("Blockers", ", ".join(state.active_blockers) or "none")
    table.add_row("Next Steps", ", ".join(state.next_steps) or "none")
    table.add_row("Active Agents", ", ".join(state.active_agents) or "none")
    table.add_row("Git HEAD", state.git_head or "unknown")
    table.add_row("Timestamp", str(state.timestamp))

    console.print(table)

    # Show recent sessions
    recent = memory.read_recent_summaries(count=3)
    if recent:
        console.print(f"\n[{_AMBER}]Recent sessions:[/]")
        for s in recent:
            accomplished = ", ".join(s.accomplished[:3]) or "no summary"
            console.print(f"  {s.date} ({s.mode}): {accomplished}")


@cli.command()
@click.argument("plan_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target-repo", "-t", type=click.Path(path_type=Path), default=None,
    help="Path to the delivery repository to validate.",
)
def preflight(plan_file: Path, target_repo: Path | None) -> None:
    """Validate a project is ready for zo build.

    Runs local-only checks: CLI availability, plan validation, agent
    definitions, memory round-trip, Docker, and GPU availability.
    """
    from zo.preflight import run_preflight

    zo_root = _zo_root()
    report = run_preflight(plan_file, zo_root, target_repo)

    for check in report.checks:
        if check.passed:
            icon = "[green bold]PASS[/]"
        elif check.warning:
            icon = "[yellow bold]WARN[/]"
        else:
            icon = "[red bold]FAIL[/]"
        console.print(f"  {icon}  {check.name}: {check.message}")

    console.print()
    total = len(report.checks)
    console.print(
        f"  [{_AMBER}]{report.passed}/{total} passed[/], "
        f"{report.warnings} warnings, {report.failed} failures"
    )

    if not report.all_passed:
        console.print(f"\n  [{_AMBER}]Fix failures before running zo build.[/]")
        raise SystemExit(1)
    console.print(f"\n  [{_AMBER}]Ready for zo build.[/]")


@cli.command()
@click.argument("source_paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--project", "-p", required=True, help="Project name for the generated plan")
@click.option("--no-tmux", is_flag=True, help="Skip interactive refinement session")
def draft(source_paths: tuple[Path, ...], project: str, no_tmux: bool) -> None:
    """Generate a plan.md from source documents.

    Accepts multiple file and/or directory paths. Indexes all documents,
    generates a compliant plan.md, then optionally launches an interactive
    Claude Code session to refine it with you.

    Usage::

        zo draft ~/docs/requirements.md ~/data/notes/ --project my-project
        zo draft ./specs --project alpha --no-tmux
    """
    from zo.draft import PlanDrafter

    if not source_paths:
        console.print("[red bold]No source paths provided.[/]")
        raise SystemExit(1)

    zo_root = _zo_root()
    drafter = PlanDrafter(
        source_paths=list(source_paths), project_name=project, zo_root=zo_root,
    )

    console.print(f"[{_AMBER}]Indexing documents from {len(source_paths)} path(s):[/]")
    for sp in source_paths:
        console.print(f"  [{_DIM}]{sp}[/]")
    count = drafter.index_documents()
    console.print(f"[green]Indexed {count} documents.[/]")

    console.print(f"[{_AMBER}]Generating plan...[/]")
    plan_path = drafter.generate_plan()
    console.print(f"[green]Plan generated:[/] {plan_path}")

    valid = drafter.validate_draft(plan_path)
    if valid:
        console.print("[green bold]Plan passes validation.[/]")
    else:
        console.print(
            f"[yellow bold]Plan has validation issues.[/] "
            f"Edit {plan_path} to fix them."
        )

    # Interactive refinement session
    if not no_tmux:
        from zo.wrapper import LifecycleWrapper

        console.print(
            f"\n[{_AMBER}]Opening interactive session to refine the plan...[/]"
        )
        from zo.comms import CommsLogger

        session_id = f"s-{uuid.uuid4().hex[:8]}"
        comms = CommsLogger(
            log_dir=zo_root / "logs" / "comms",
            project=project, session_id=session_id,
        )
        wrapper = LifecycleWrapper(comms=comms, log_dir=zo_root / "logs" / "wrapper")

        refine_prompt = (
            f"I've drafted a plan.md at {plan_path} for project '{project}'.\n\n"
            f"The plan was generated from {count} source documents.\n"
            f"Please review it, suggest improvements, and help me refine the "
            f"oracle definition, constraints, and agent configuration.\n\n"
            f"The plan schema is defined in specs/plan.md — ensure compliance."
        )

        prompt_file = zo_root / "logs" / "wrapper" / f"zo-draft-{project}-prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(refine_prompt, encoding="utf-8")

        # Launch interactive claude to refine the plan
        result = __import__("subprocess").run(
            ["tmux", "new-window", "-d", "-n", f"draft-{project}",
             "-P", "-F", "#{pane_id}"],
            capture_output=True, text=True, timeout=10,
        )
        pane_id = result.stdout.strip()

        import shlex
        claude_abs = wrapper._resolve_claude_bin()
        cmd = (
            f'{shlex.quote(claude_abs)}'
            f' --model sonnet'
            f' --add-dir {shlex.quote(str(zo_root))}'
        )
        __import__("subprocess").run(
            ["tmux", "send-keys", "-t", pane_id, cmd, "Enter"],
            capture_output=True, text=True, timeout=10,
        )

        import time
        time.sleep(3)
        __import__("subprocess").run(
            ["tmux", "load-buffer", str(prompt_file)],
            capture_output=True, text=True, timeout=10,
        )
        __import__("subprocess").run(
            ["tmux", "paste-buffer", "-t", pane_id],
            capture_output=True, text=True, timeout=10,
        )
        time.sleep(0.5)
        __import__("subprocess").run(
            ["tmux", "send-keys", "-t", pane_id, "Enter"],
            capture_output=True, text=True, timeout=10,
        )

        console.print(
            f"[{_AMBER}]Refinement session opened.[/] "
            f"[{_DIM}]Ctrl-b n to switch to it.[/]"
        )

    drafter.close()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TARGET_TEMPLATE = """\
---
project: {project_name}
target_repo: ../target-{project_name}
target_branch: main
worktree_base: .worktrees
git_author_name: ZO Agent
git_author_email: zo-agent@zero-operators.dev
agent_working_dirs:
  data-engineer: data/
  model-builder: models/
  oracle-qa: oracle/
  test-engineer: tests/
zo_only_paths:
  - memory/
  - logs/
  - .claude/
enforce_isolation: true
---

# Target: {project_name}

Configure the delivery repository path and isolation rules above.
"""

_PLAN_TEMPLATE = """\
---
project_name: {project_name}
version: "0.1.0"
created: "TODO"
last_modified: "TODO"
status: active
owner: "TODO"
---

## Objective

TODO: Define the project objective.

## Oracle Definition

**Primary metric:** TODO
**Ground truth source:** TODO
**Evaluation method:** TODO
**Target threshold:** TODO
**Evaluation frequency:** TODO

## Workflow Configuration

**Mode:** classical_ml

## Data Sources

### Primary

TODO: Describe your primary data source.

## Domain Context and Priors

TODO: List domain knowledge and assumptions.

## Agent Configuration

**Active agents:** data-engineer, model-builder, oracle-qa, test-engineer

## Constraints

TODO: Define constraints (compute, time, compliance).

## Milestones and Timeline

TODO: Define milestones.
"""
