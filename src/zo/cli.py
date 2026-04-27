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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.table import Table

from zo._orchestrator_models import GateMode

if TYPE_CHECKING:
    from zo.memory import MemoryManager
    from zo.target import TargetConfig

console = Console()

# ZO brand amber for highlights
_AMBER = "bold #F0C040"
_DIM = "#8a6020"
_VOID = "#080808"
_VERSION = "1.0.2"


def _zo_root() -> Path:
    """Derive the ZO repository root from the CLI package location."""
    return Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Project discovery — find project state in .zo/ (new) or legacy layout
# ---------------------------------------------------------------------------


@dataclass
class ProjectContext:
    """Resolved paths for a project, whether from .zo/ or legacy layout."""

    layout: str  # "zo-dir" or "legacy"
    delivery_repo: Path
    plan_path: Path
    project_name: str
    zo_root: Path

    def make_memory(self) -> MemoryManager:
        """Create a MemoryManager pointing at the right root."""
        from zo.memory import MemoryManager

        if self.layout == "zo-dir":
            return MemoryManager(
                project_dir=self.delivery_repo,
                project_name=self.project_name,
                memory_root=self.delivery_repo / ".zo" / "memory",
            )
        return MemoryManager(
            project_dir=self.zo_root, project_name=self.project_name,
        )

    def make_target(self) -> TargetConfig:
        """Load target config from .zo/config.yaml or legacy target file."""
        if self.layout == "zo-dir":
            from zo.project_config import load_project_config, to_target_config

            pc = load_project_config(self.delivery_repo)
            return to_target_config(pc, self.delivery_repo)

        from zo.target import parse_target

        target_path = self.zo_root / "targets" / f"{self.project_name}.target.md"
        return parse_target(target_path)


def _detect_delivery_repo(project_name: str | None = None) -> Path | None:
    """Check cwd for a .zo/config.yaml marker. Return cwd if found."""
    from zo.project_config import has_zo_dir, load_project_config

    cwd = Path.cwd()
    if not has_zo_dir(cwd):
        return None

    if project_name is not None:
        try:
            pc = load_project_config(cwd)
            if pc.project_name != project_name:
                return None
        except Exception:  # noqa: BLE001
            return None

    return cwd


def _load_project_context(
    project_name: str,
    delivery_repo: Path | None = None,
) -> ProjectContext:
    """Resolve project paths from .zo/ layout or legacy layout.

    Precedence:
    1. Explicit ``delivery_repo`` with .zo/config.yaml
    2. cwd with .zo/config.yaml matching ``project_name``
    3. Legacy layout (zo_root/targets/, zo_root/plans/, zo_root/memory/)
    """
    from zo.project_config import has_zo_dir, load_project_config

    zo_root = _zo_root()

    # Try explicit delivery repo
    if delivery_repo is not None:
        delivery_repo = Path(delivery_repo).resolve()
        if has_zo_dir(delivery_repo):
            pc = load_project_config(delivery_repo)
            plan_path = delivery_repo / ".zo" / "plans" / f"{pc.project_name}.md"
            return ProjectContext(
                layout="zo-dir",
                delivery_repo=delivery_repo,
                plan_path=plan_path,
                project_name=pc.project_name,
                zo_root=zo_root,
            )

    # Try cwd detection
    detected = _detect_delivery_repo(project_name)
    if detected is not None:
        pc = load_project_config(detected)
        plan_path = detected / ".zo" / "plans" / f"{pc.project_name}.md"
        return ProjectContext(
            layout="zo-dir",
            delivery_repo=detected,
            plan_path=plan_path,
            project_name=pc.project_name,
            zo_root=zo_root,
        )

    # Fall back to legacy layout
    main_root = _main_repo_root()
    plan_path = main_root / "plans" / f"{project_name}.md"
    target_path = main_root / "targets" / f"{project_name}.target.md"

    # Resolve delivery repo from legacy target file
    delivery_path = main_root.parent / f"{project_name}-delivery"
    if target_path.exists():
        from zo.target import parse_target

        target = parse_target(target_path)
        delivery_path = Path(target.target_repo).resolve()

    return ProjectContext(
        layout="legacy",
        delivery_repo=delivery_path,
        plan_path=plan_path,
        project_name=project_name,
        zo_root=zo_root,
    )


def _ensure_local_config(delivery_repo: Path) -> None:
    """Check for .zo/local.yaml; auto-detect environment if missing.

    On a new machine, local.yaml won't exist yet. This function detects
    the environment (GPU, CUDA, Docker) and prompts for any paths that
    can't be auto-detected (data_dir), then writes .zo/local.yaml.
    """
    from zo.project_config import LocalConfig, load_local_config, save_local_config

    existing = load_local_config(delivery_repo)
    if existing is not None:
        return  # Already set up on this machine

    from zo.environment import detect_environment

    console.print(f"\n[{_AMBER}]New machine detected — setting up local config.[/]")

    env = detect_environment()
    gpu_names: list[str] = []
    if env and env.gpu_names:
        gpu_names = list(env.gpu_names) if not isinstance(env.gpu_names, list) else env.gpu_names

    # Prompt for data directory (can't auto-detect)
    data_dir = click.prompt(
        "  Data directory (raw data path on this machine)",
        default="", show_default=False,
    )

    local = LocalConfig(
        data_dir=data_dir or None,
        gpu_count=env.gpu_count if env else 0,
        gpu_names=gpu_names,
        cuda_version=env.cuda_version if env else None,
        docker_available=env.docker_available if env else False,
        gate_mode="supervised",
        zo_repo_path=str(_zo_root()),
    )
    save_local_config(delivery_repo, local)

    console.print(f"[green]Local config written:[/] {delivery_repo / '.zo' / 'local.yaml'}")
    if env and env.gpu_count:
        console.print(f"  [{_DIM}]GPUs: {env.gpu_count}x {', '.join(gpu_names)}[/]")
    if env and env.cuda_version:
        console.print(f"  [{_DIM}]CUDA: {env.cuda_version}[/]")


def _main_repo_root() -> Path:
    """Return the main git repo root, even if running from a worktree.

    ZO artifacts (plans, memory, state) should always live in the main
    repo, not in worktrees. Worktrees are for ZO development.
    """
    import subprocess

    zo_root = _zo_root()
    try:
        # git worktree list --porcelain: first line is the main repo
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=str(zo_root),
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("worktree "):
                    # First worktree entry is always the main repo
                    return Path(line.split(" ", 1)[1])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return zo_root


def _gate_mode_from_str(value: str) -> GateMode:
    """Map CLI gate-mode string to GateMode enum."""
    mapping = {
        "supervised": GateMode.SUPERVISED,
        "auto": GateMode.AUTO,
        "full-auto": GateMode.FULL_AUTO,
    }
    return mapping[value]


# ---------------------------------------------------------------------------
# Low-token preset
# ---------------------------------------------------------------------------
# Single source of truth for the cost-saving profile activated by
# ``--low-token`` or plan field ``low_token: true``. Each entry below
# is documented in docs/concepts/low-token-mode.mdx — keep in sync.
#
# Precedence (highest first): CLI flag > plan field > preset > base default.
_LOW_TOKEN_PRESET: dict[str, object] = {
    "lead_model": "sonnet",         # was "opus" — ~5x cheaper
    "max_iterations": 2,             # cuts the dominant Phase-4 multiplier
    "stop_on_tier": "could_pass",    # earlier stop on weakest acceptable tier
    "drop_research_scout": True,     # skip cross-cutting literature review
    "headlines_disabled": True,      # disable Haiku ticker (~60 calls/hr)
    "gate_mode": "full-auto",        # no human-loop overhead
    "compact_threshold": "60",       # CLAUDE_AUTOCOMPACT_PCT_OVERRIDE
}


def _resolve_lead_model(
    *,
    cli_lead_model: str | None,
    plan_lead_model: str | None,
    low_token: bool,
) -> str:
    """Resolve effective lead model: CLI > plan > preset > base default."""
    if cli_lead_model is not None:
        return cli_lead_model
    if plan_lead_model is not None:
        return plan_lead_model
    if low_token:
        return str(_LOW_TOKEN_PRESET["lead_model"])
    return "opus"


def _resolve_gate_mode(
    *,
    cli_gate_mode: str | None,
    low_token: bool,
) -> str:
    """Resolve effective gate mode. None => preset default if low_token, else 'supervised'."""
    if cli_gate_mode is not None:
        return cli_gate_mode
    if low_token:
        return str(_LOW_TOKEN_PRESET["gate_mode"])
    return "supervised"


def _show_banner(
    project: str = "",
    mode: str = "",
    phase: str = "",
    gate_mode: str = "",
    low_token: bool = False,
) -> None:
    """Display the ZO brand panel at startup.

    When ``low_token`` is True, appends a "low-token" badge to the
    banner so the user has constant visual confirmation that the
    cost-saving preset is active.
    """
    from rich.panel import Panel
    from rich.text import Text

    logo = Text()
    logo.append("  ◎ ", style="#F0C040 bold")
    logo.append("Zero Operators", style="#F0C040 bold")
    logo.append(f"  v{_VERSION}", style=_DIM)
    if low_token:
        logo.append("  [low-token]", style="#F0C040 bold")
    logo.append("\n", style=_DIM)
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


# ---------------------------------------------------------------------------
# Branded help rendering
# ---------------------------------------------------------------------------


def _render_help(ctx: click.Context, command: click.Command) -> str:
    """Render a ZO-branded --help screen for a Command or Group.

    Replaces Click's default plain-text help with a Rich-formatted
    output: orbital-mark banner (amber on void), sectioned headers
    (USAGE / DESCRIPTION / ARGUMENTS / COMMANDS / OPTIONS) in the
    brand palette, and the version in the banner.

    Returns a string with ANSI codes; Click echoes it and strips
    codes automatically when stdout is not a TTY (tests, pipes).
    """
    import shutil
    import textwrap
    from io import StringIO

    from rich.console import Console as _RichConsole
    from rich.panel import Panel
    from rich.text import Text

    is_group = isinstance(command, click.Group)
    is_root = ctx.parent is None

    term_width = shutil.get_terminal_size((100, 24)).columns
    buf = StringIO()
    rc = _RichConsole(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        width=min(term_width, 100),
        highlight=False,
        emoji=False,
    )

    # --- Branded banner -----------------------------------------------------
    banner = Text()
    banner.append("◎  ", style=_AMBER)
    banner.append("ZERO OPERATORS", style=_AMBER)
    banner.append("   ")
    banner.append(f"v{_VERSION}", style=_DIM)
    if is_root:
        banner.append("\n\n")
        banner.append(
            "Autonomous research and engineering team system.\n", style=_DIM
        )
        banner.append(
            "You input a plan. Agents execute. The oracle verifies.",
            style=_DIM,
        )
    rc.print(Panel(banner, border_style=_AMBER, padding=(0, 2)))

    # --- USAGE --------------------------------------------------------------
    usage_pieces = command.collect_usage_pieces(ctx)
    rc.print()
    rc.print(f"[{_AMBER}]USAGE[/]")
    usage_line = Text("  ")
    usage_line.append(ctx.command_path, style="bold")
    usage_line.append(" ")
    usage_line.append(" ".join(usage_pieces))
    rc.print(usage_line)

    # --- QUICK START (root group only) -------------------------------------
    if is_group and is_root:
        rc.print()
        rc.print(f"[{_AMBER}]QUICK START[/]")
        quickstart = [
            ("zo init <project>",       "Scaffold memory, targets, and a plan skeleton"),
            ("zo draft -p <project>",   "Draft plans/<project>.md with a Plan Architect"),
            ("zo preflight <plan.md>",  "Verify plan, CLI, Docker, GPU — ready to build"),
            ("zo build <plan.md>",      "Launch the agent team to execute the plan"),
            ("zo continue <project>",   "Resume a paused project (shorthand for build)"),
        ]
        cmdw = max(len(c) for c, _ in quickstart) + 2
        for i, (cmd, desc) in enumerate(quickstart, 1):
            row = Text(f"  {i}. ")
            row.append(cmd.ljust(cmdw), style="bold")
            row.append("  ")
            row.append(desc, style=_DIM)
            rc.print(row)

    # --- DESCRIPTION (skip for root group — banner already says it) ---------
    # User-provided help text may contain literal "[...]" and "\" — print
    # with markup=False so Rich treats it as plain text.
    help_text = (command.help or "").strip()
    if help_text and not (is_root and is_group):
        rc.print()
        rc.print(f"[{_AMBER}]DESCRIPTION[/]")
        for line in help_text.splitlines():
            if line.strip():
                rc.print(f"  {line}", markup=False, highlight=False)
            else:
                rc.print()

    # Click adds --help lazily via get_params(ctx); params alone omits it.
    all_params = command.get_params(ctx)

    # --- ARGUMENTS ----------------------------------------------------------
    # User-content sections below build Rich ``Text`` objects directly
    # (rather than inline "[bold]..[/]" markup) so literal "[...]" and
    # backslashes from docstrings/metavars render verbatim.
    args = [p for p in all_params if isinstance(p, click.Argument)]
    if args:
        rc.print()
        rc.print(f"[{_AMBER}]ARGUMENTS[/]")
        for a in args:
            line = Text("  ")
            line.append(a.human_readable_name, style="bold")
            rc.print(line)

    # --- COMMANDS (groups only) --------------------------------------------
    if is_group:
        visible: list[tuple[str, str]] = []
        for name in sorted(command.commands.keys()):
            sub = command.commands[name]
            if sub.hidden:
                continue
            short = sub.get_short_help_str(limit=80) or ""
            visible.append((name, short.rstrip(".")))
        if visible:
            rc.print()
            rc.print(f"[{_AMBER}]COMMANDS[/]")
            namew = max(len(n) for n, _ in visible) + 2
            for name, desc in visible:
                line = Text("  ")
                line.append(name.ljust(namew), style="bold")
                line.append("  ")
                line.append(desc, style=_DIM)
                rc.print(line)

    # --- OPTIONS ------------------------------------------------------------
    opt_records: list[tuple[str, str]] = []
    for p in all_params:
        if not isinstance(p, click.Option) or p.hidden:
            continue
        record = p.get_help_record(ctx)
        if record is None:
            continue
        opt_records.append(record)
    if opt_records:
        rc.print()
        rc.print(f"[{_AMBER}]OPTIONS[/]")
        declw = min(max(len(d) for d, _ in opt_records), 38)
        wrap_w = max(rc.width - declw - 6, 20)
        for decl, help_msg in opt_records:
            help_msg = (help_msg or "").strip()
            if len(decl) <= declw:
                wrapped = textwrap.wrap(help_msg, width=wrap_w) or [""]
                first = Text("  ")
                first.append(decl.ljust(declw), style="bold")
                first.append("  ")
                first.append(wrapped[0], style=_DIM)
                rc.print(first)
                pad = " " * (declw + 4)
                for cont in wrapped[1:]:
                    cont_line = Text(pad)
                    cont_line.append(cont, style=_DIM)
                    rc.print(cont_line)
            else:
                long_decl = Text("  ")
                long_decl.append(decl, style="bold")
                rc.print(long_decl)
                if help_msg:
                    pad = " " * (declw + 4)
                    for cont in textwrap.wrap(help_msg, width=wrap_w):
                        cont_line = Text(pad)
                        cont_line.append(cont, style=_DIM)
                        rc.print(cont_line)

    # --- Footer hint for the root group ------------------------------------
    if is_group and is_root:
        rc.print()
        rc.print(
            f"[{_DIM}]Run[/] [bold]zo COMMAND --help[/] "
            f"[{_DIM}]for details on a specific command.[/]"
        )

    return buf.getvalue().rstrip("\n")


class ZoCommand(click.Command):
    """Click Command that renders --help with the ZO brand system."""

    def get_help(self, ctx: click.Context) -> str:  # noqa: D401
        return _render_help(ctx, self)


class ZoGroup(click.Group):
    """Click Group that renders --help with the ZO brand system.

    Propagates ``ZoCommand`` to all registered subcommands and
    ``ZoGroup`` itself to any nested groups, so the whole CLI tree
    picks up branded help automatically.
    """

    command_class = ZoCommand
    group_class = type  # sentinel: nested groups use the same class

    def get_help(self, ctx: click.Context) -> str:  # noqa: D401
        return _render_help(ctx, self)


@click.group(cls=ZoGroup)
@click.version_option(version=_VERSION, package_name="zero-operators")
def cli() -> None:
    """Autonomous AI research and engineering team system.

    You input a plan. Agents coordinate to build and deliver code.
    The oracle verifies the work.
    """


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


def _print_next_steps(team_name: str, zo_root: Path) -> None:
    """Print context-aware next steps after a session completes."""
    console.print(f"\n[{_AMBER}]Next steps:[/]")
    if team_name.startswith("init-"):
        project = team_name.removeprefix("init-")
        console.print(f"  1. Review targets/{project}.target.md and plans/{project}.md")
        console.print(f"  2. Run [bold]zo draft -p {project}[/] to refine the plan with scouts")
    elif team_name.startswith("draft-"):
        project = team_name.removeprefix("draft-")
        plan_path = zo_root / "plans" / f"{project}.md"
        if plan_path.exists():
            size_kb = plan_path.stat().st_size // 1024
            console.print(f"  Plan ready: plans/{project}.md ({size_kb}KB)")
        console.print(f"  1. Review [bold]plans/{project}.md[/] — edit if needed")
        console.print(f"  2. Run [bold]zo preflight plans/{project}.md[/] to validate")
        console.print(f"  3. Run [bold]zo build plans/{project}.md[/] to start the agent team")
    elif team_name.startswith("zo-"):
        project = team_name.removeprefix("zo-")
        console.print(f"  1. Check [bold]zo status {project}[/] for current phase")
        console.print(f"  2. Run [bold]zo build plans/{project}.md[/] to continue")
    console.print()


def _generate_session_summary(events: list[str], team_name: str) -> None:
    """Ask Haiku for a 2-3 line session summary and print next steps."""
    events_text = "\n".join(events[-30:])
    try:
        result = __import__("subprocess").run(
            ["claude", "-p", "--model", "haiku",
             f"Summarise this agent session in 2-3 short bullet points "
             f"(what was accomplished, what's ready). No preamble, just "
             f"bullets:\n\n{events_text}"],
            capture_output=True, text=True, timeout=20,
        )
        summary = result.stdout.strip()
        if summary:
            console.print(f"\n[{_AMBER}]Session summary:[/]")
            for line in summary.split("\n"):
                line = line.strip()
                if line:
                    console.print(f"  {line}")
    except Exception:
        pass  # Non-critical — skip if Haiku unavailable
    console.print()


def _launch_and_monitor(
    *,
    wrapper,  # noqa: ANN001
    prompt: str,
    team_name: str,
    zo_root: Path,
    orchestrator=None,  # noqa: ANN001
    semantic=None,  # noqa: ANN001
    no_tmux: bool = False,
    model: str = "opus",
    max_turns: int = 200,
    gate_mode_file: Path | None = None,
    project_name: str = "",
    delivery_repo: Path | None = None,
    add_dirs: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    headlines_disabled: bool = False,
) -> None:
    """Shared launch → monitor → end-session flow for build and draft.

    Args:
        extra_env: Extra environment variables passed to the Claude Code
            subprocess. The low-token preset uses this to set
            ``CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=60``.
        headlines_disabled: When True, skips the periodic Haiku headline
            summaries. Set by ``--low-token`` and ``--no-headlines``.
    """
    use_tmux = not no_tmux
    console.print(f"\n[{_AMBER}]Launching lead session:[/] team={team_name}")
    process = wrapper.launch_lead_session(
        prompt, cwd=str(zo_root), team_name=team_name,
        model=model, max_turns=max_turns, use_tmux=use_tmux,
        add_dirs=add_dirs or [],
        extra_env=extra_env or {},
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
    _headline_buffer: list[str] = []
    _last_headline_time: float = 0.0
    _headline_interval = 60  # seconds between Haiku summaries

    def _maybe_print_headline() -> None:
        """Send buffered events to Haiku for a 1-line summary."""
        import time as _time

        nonlocal _last_headline_time
        if headlines_disabled:
            return
        now = _time.monotonic()
        if not _headline_buffer:
            return
        if now - _last_headline_time < _headline_interval:
            return

        events_text = "\n".join(_headline_buffer[-15:])
        _headline_buffer.clear()
        _last_headline_time = now

        try:
            result = __import__("subprocess").run(
                ["claude", "-p", "--model", "haiku",
                 f"Summarise these agent events in ONE short "
                 f"headline (max 80 chars). No preamble, just "
                 f"the headline:\n\n{events_text}"],
                capture_output=True, text=True, timeout=15,
            )
            headline = result.stdout.strip().split("\n")[0][:80]
            if headline:
                console.print(
                    f"  [{_AMBER}]▸ {headline}[/]"
                )
        except Exception:
            pass  # Non-critical — skip if Haiku unavailable

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
                        _headline_buffer.append(f"{agent} decided: {title}")
                    elif etype == "gate":
                        result = evt.get("result", "")
                        gphase = evt.get("phase_id", "")
                        console.print(
                            f"    [{_AMBER}]⊘ GATE[/] {gphase}: {result}"
                        )
                        _headline_buffer.append(f"Gate {gphase}: {result}")
                    elif etype == "checkpoint":
                        progress = evt.get("progress", "")[:70]
                        console.print(f"    [{_DIM}]↳ {agent}: {progress}[/]")
                        _headline_buffer.append(f"{agent}: {progress}")
                    elif etype == "error":
                        desc = evt.get("description", "")[:70]
                        console.print(
                            f"    [red]✗ ERROR[/] [{_DIM}]{agent}:[/] {desc}"
                        )
                        _headline_buffer.append(f"ERROR {agent}: {desc}")

        if not tasks and not header_parts:
            console.print(f"  [{_DIM}][{elapsed}] Waiting for agents...[/]")

        _maybe_print_headline()
        console.print()

    process = wrapper.wait_for_completion(
        process, on_status=_print_status, gate_mode_file=gate_mode_file,
        project_name=project_name, delivery_repo=delivery_repo,
    )

    console.print()
    if process.status == "completed":
        console.print("[green bold]Session completed.[/]")
    else:
        console.print(f"[red bold]Session ended with status:[/] {process.status}")

    # Generate a Haiku summary of the session from buffered events.
    # Low-token / --no-headlines opts out of this auxiliary call too.
    if _headline_buffer and not headlines_disabled:
        _generate_session_summary(_headline_buffer, team_name)

    # Always print next steps based on what command just ran.
    _print_next_steps(team_name, zo_root)

    if orchestrator:
        orchestrator.end_session()
    if semantic:
        semantic.close()


@cli.command()
@click.argument("plan_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--gate-mode",
    type=click.Choice(["supervised", "auto", "full-auto"]),
    default=None,
    help="Gate evaluation mode. Default: 'supervised' (or 'full-auto' if --low-token).",
)
@click.option("--no-tmux", is_flag=True, help="Disable tmux agent visibility")
@click.option(
    "--low-token", is_flag=True,
    help="Activate the cost-saving preset: Sonnet lead, 2 max iterations, "
    "stop on could_pass tier, no headlines, full-auto gates, earlier "
    "auto-compaction. Plan-level 'low_token: true' achieves the same.",
)
@click.option(
    "--lead-model",
    type=click.Choice(["opus", "sonnet", "haiku"]),
    default=None,
    help="Override the lead orchestrator model. Composes with --low-token.",
)
@click.option(
    "--max-iterations", type=int, default=None,
    help="Hard cap on Phase-4 experiment iterations. Wins over plan and preset.",
)
@click.option(
    "--no-headlines", is_flag=True,
    help="Disable the Haiku headline ticker (saves ~60 small calls/hour).",
)
def build(
    plan_path: Path,
    gate_mode: str | None,
    no_tmux: bool,
    low_token: bool,
    lead_model: str | None,
    max_iterations: int | None,
    no_headlines: bool,
) -> None:
    """Launch a project from a plan.md file.

    Smart mode detection:
    - Fresh project (no state) -> build from scratch
    - Existing state -> continue from current phase
    - Plan edited since last run -> re-decompose and continue

    Supports both .zo/ layout (plan in delivery repo) and legacy layout
    (plan in ZO repo). When run from a delivery repo with .zo/, the
    plan_path is resolved from .zo/plans/.
    """
    from zo.comms import CommsLogger
    from zo.orchestrator import Orchestrator
    from zo.plan import parse_plan, validate_plan
    from zo.semantic import SemanticIndex
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

    # 1a. Resolve low-token + override settings.
    #     Precedence: CLI flag > plan field > preset default > base default.
    effective_low_token = low_token or plan.frontmatter.low_token
    effective_gate_mode = _resolve_gate_mode(
        cli_gate_mode=gate_mode, low_token=effective_low_token,
    )
    effective_lead_model = _resolve_lead_model(
        cli_lead_model=lead_model,
        plan_lead_model=plan.frontmatter.lead_model,
        low_token=effective_low_token,
    )
    effective_headlines_disabled = (
        no_headlines or effective_low_token
    )
    extra_env: dict[str, str] = {}
    if effective_low_token:
        extra_env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(
            _LOW_TOKEN_PRESET["compact_threshold"],
        )

    # 2. Resolve project context (.zo/ or legacy)
    # If the plan lives inside a .zo/plans/ directory, infer delivery repo
    # from the plan path so build inherits context from continue --repo.
    delivery_hint: Path | None = None
    if plan_path.resolve().parts[-3:-1] == (".zo", "plans"):
        delivery_hint = plan_path.resolve().parent.parent.parent
    ctx = _load_project_context(project_name, delivery_repo=delivery_hint)
    target = ctx.make_target()
    memory = ctx.make_memory()
    memory.initialize_project()

    # 3. Detect mode from state
    state_check = memory.read_state()
    detected_mode = "build" if state_check.phase == "init" else "continue"

    # 4. Show brand banner
    _show_banner(
        project=project_name,
        mode=detected_mode,
        phase=state_check.phase if detected_mode == "continue" else "starting",
        gate_mode=effective_gate_mode,
        low_token=effective_low_token,
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
    gm = _gate_mode_from_str(effective_gate_mode)
    memory.write_gate_mode(gm.value)
    orchestrator = Orchestrator(
        plan=plan, target=target, memory=memory, comms=comms,
        semantic=semantic, zo_root=zo_root, gate_mode=gm,
        plan_path=plan_path,
        low_token=effective_low_token,
        max_iterations_override=max_iterations,
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
    _show_phase_review(phase, decomp, plan, effective_gate_mode)
    extra = _ask_additional_instructions(effective_gate_mode)

    prompt = orchestrator.build_lead_prompt(phase)
    if extra:
        prompt += f"\n\n---\n\n# Additional Human Instructions\n\n{extra}\n"

    # 10. Launch, monitor, end session
    delivery_path = Path(target.target_repo).resolve()
    wrapper = LifecycleWrapper(comms=comms, log_dir=zo_root / "logs" / "wrapper")
    _launch_and_monitor(
        wrapper=wrapper,
        prompt=prompt,
        team_name=f"zo-{project_name}",
        zo_root=zo_root,
        orchestrator=orchestrator,
        semantic=semantic,
        no_tmux=no_tmux,
        model=effective_lead_model,
        gate_mode_file=memory.memory_root / "gate_mode",
        project_name=project_name,
        delivery_repo=delivery_path,
        add_dirs=[str(delivery_path)],
        extra_env=extra_env,
        headlines_disabled=effective_headlines_disabled,
    )


@cli.command("continue")
@click.argument("project_name", required=False, default=None)
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Path to delivery repo with .zo/ directory. "
    "Use when reconnecting to a project on a new machine.",
)
@click.option(
    "--gate-mode",
    type=click.Choice(["supervised", "auto", "full-auto"]),
    default=None,
)
@click.option("--no-tmux", is_flag=True, help="Disable tmux agent visibility")
@click.option(
    "--low-token", is_flag=True,
    help="Activate the cost-saving preset (see `zo build --help`).",
)
@click.option(
    "--lead-model",
    type=click.Choice(["opus", "sonnet", "haiku"]),
    default=None,
    help="Override the lead orchestrator model.",
)
@click.option(
    "--max-iterations", type=int, default=None,
    help="Hard cap on Phase-4 experiment iterations.",
)
@click.option(
    "--no-headlines", is_flag=True,
    help="Disable the Haiku headline ticker.",
)
def continue_(
    project_name: str | None,
    repo: str | None,
    gate_mode: str | None,
    no_tmux: bool,
    low_token: bool,
    lead_model: str | None,
    max_iterations: int | None,
    no_headlines: bool,
) -> None:
    """Resume a paused project or reconnect on a new machine.

    Finds the project plan and runs zo build on it. Supports both
    .zo/ layout (delivery repo) and legacy layout (ZO repo).

    On a new machine, use --repo to point at the delivery repo::

        zo continue --repo ~/my-project

    If .zo/local.yaml is missing, ZO will auto-detect the environment
    and prompt for any machine-specific paths before proceeding.

    From inside the delivery repo (cwd has .zo/), project_name is
    optional — it's read from .zo/config.yaml.
    """
    from zo.project_config import has_zo_dir, load_project_config

    # Resolve delivery repo from --repo flag or cwd
    delivery = Path(repo).resolve() if repo else None

    # If no project_name given, try to infer from .zo/config.yaml
    if project_name is None:
        detect_path = delivery or Path.cwd()
        if has_zo_dir(detect_path):
            pc = load_project_config(detect_path)
            project_name = pc.project_name
            if delivery is None:
                delivery = detect_path
        else:
            console.print(
                "[red bold]No project name given and no .zo/ found in cwd.[/]"
            )
            console.print(
                "Usage: [bold]zo continue PROJECT[/] or "
                "[bold]zo continue --repo /path/to/delivery[/]"
            )
            raise SystemExit(1)

    _show_banner(project=project_name, mode="continue")

    # Load project context
    pctx = _load_project_context(project_name, delivery_repo=delivery)

    # If .zo/ layout and local.yaml is missing, set it up
    if pctx.layout == "zo-dir":
        _ensure_local_config(pctx.delivery_repo)

    plan_path = pctx.plan_path
    if not plan_path.exists():
        console.print(f"[red bold]Plan not found:[/] {plan_path}")
        console.print("Run [bold]zo build plans/your-plan.md[/] first.")
        raise SystemExit(1)

    # Delegate to build
    click_ctx = click.get_current_context()
    click_ctx.invoke(
        build,
        plan_path=plan_path,
        gate_mode=gate_mode,
        no_tmux=no_tmux,
        low_token=low_token,
        lead_model=lead_model,
        max_iterations=max_iterations,
        no_headlines=no_headlines,
    )


@cli.command("init")
@click.argument("project_name")
@click.option(
    "--no-tmux", is_flag=True,
    help="Skip the conversational Init Architect; write files "
    "headlessly using the flags below.",
)
@click.option(
    "--branch", default="main", show_default=True,
    help="Target git branch on the delivery repo.",
)
@click.option(
    "--scaffold-delivery", type=click.Path(), default=None,
    help="Create a fresh delivery repo at PATH. Mutually exclusive "
    "with --existing-repo.",
)
@click.option(
    "--existing-repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Overlay ZO structure onto an existing local repo at PATH "
    "(adds configs/, experiments/, docker/, STRUCTURE.md if missing; "
    "never touches existing code).",
)
@click.option(
    "--base-image", default=None,
    help="Docker base image (if unset, suggested from host CUDA).",
)
@click.option(
    "--gpu-host", default=None,
    help="Remote GPU host where training runs (e.g. 'gpu-server-01'). "
    "Captured in plan.md Environment section.",
)
@click.option(
    "--data-path", default=None,
    help="Data location — local path or remote string like "
    "'host:/abs/path'. Captured in plan.md Environment section.",
)
@click.option(
    "--no-detect", is_flag=True,
    help="Skip host environment auto-detection; leave Environment "
    "placeholders as TODO.",
)
@click.option(
    "--layout-mode",
    type=click.Choice(["standard", "adaptive"], case_sensitive=False),
    default="standard", show_default=True,
    help="'standard' = full ZO layout (src/data, src/model, ...). "
    "'adaptive' = only ZO meta-dirs (configs/, experiments/, docker/); "
    "leaves src/ and data/ alone for repos with an existing code layout.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Preview the files and directories that WOULD be created, "
    "without writing anything. The Init Architect runs this first, "
    "shows you the preview, and only commits after you confirm.",
)
@click.option(
    "--reset", is_flag=True,
    help="DELETE the ZO init artifacts for this project — "
    "memory/{project}/, targets/{project}.target.md, and "
    "plans/{project}.md. The delivery repo is NEVER touched. "
    "Prompts for confirmation unless --yes is also passed.",
)
@click.option(
    "--yes", "-y", is_flag=True,
    help="Skip confirmation prompts (used with --reset).",
)
def init(
    project_name: str,
    no_tmux: bool,
    branch: str,
    scaffold_delivery: str | None,
    existing_repo: Path | None,
    base_image: str | None,
    gpu_host: str | None,
    data_path: str | None,
    no_detect: bool,
    layout_mode: str,
    dry_run: bool,
    reset: bool,
    yes: bool,
) -> None:
    """Initialize a new project — conversational by default.

    Without ``--no-tmux``, launches the **Init Architect** in a tmux
    pane. The agent inspects the environment, asks a short interview
    (new vs existing repo, branch, training host, data location), then
    invokes ``zo init ... --no-tmux ...`` to write the scaffold.

    With ``--no-tmux``, writes files directly from the flags. Use this
    in CI/scripts or when you know exactly what you want:

        zo init my-project --no-tmux \\
            --existing-repo ~/code/my-project \\
            --branch feature-branch \\
            --gpu-host gpu-server-01 \\
            --data-path /mnt/data/project/raw

    Either mode creates:
      - memory/{project}/ — STATE, DECISION_LOG, PRIORS, sessions/
      - targets/{project}.target.md — absolute repo path, branch
      - plans/{project}.md — with Environment section pre-populated
      - Delivery repo layout (fresh scaffold or overlay onto existing)
    """
    # Normalize layout_mode to lowercase — Click's Choice can pass through
    # whatever case the user typed.
    layout_mode = layout_mode.lower()

    # --reset is a short-circuit: delete init artifacts and exit. No other
    # flags are meaningful alongside it (except --yes for non-interactive).
    if reset:
        _show_banner(project=project_name, mode="init --reset")
        _init_reset(project_name=project_name, skip_confirm=yes)
        return

    # Guardrail: mutually exclusive flags
    if scaffold_delivery is not None and existing_repo is not None:
        raise click.UsageError(
            "--scaffold-delivery and --existing-repo are mutually exclusive. "
            "Use --existing-repo for overlay onto an existing codebase, or "
            "--scaffold-delivery to create a fresh repo at a custom path."
        )

    # Guardrail: layout_mode=adaptive only makes sense with an existing repo
    # (it skips creating src/ dirs, which would leave a fresh scaffold broken).
    if layout_mode == "adaptive" and existing_repo is None:
        raise click.UsageError(
            "--layout-mode=adaptive requires --existing-repo. "
            "Adaptive mode skips creating src/ and data/ dirs so your "
            "existing code layout is preserved — it doesn't make sense "
            "on a fresh scaffold. Use standard mode for new repos."
        )

    # Guardrail: existing_repo must actually look like a repo
    if existing_repo is not None:
        existing_repo = existing_repo.expanduser().resolve()
        if not existing_repo.exists():
            raise click.UsageError(
                f"--existing-repo path does not exist: {existing_repo}"
            )
        if not existing_repo.is_dir():
            raise click.UsageError(
                f"--existing-repo must be a directory: {existing_repo}"
            )
        git_dir = existing_repo / ".git"
        if not git_dir.exists():
            raise click.UsageError(
                f"--existing-repo is not a git repository (no .git/ found): "
                f"{existing_repo}. Run `git init` inside it first, or point "
                f"at a different path."
            )
        # Best-effort branch sanity check. A warning, not a hard error —
        # the user may be about to create this branch.
        _warn_if_branch_missing(existing_repo, branch)

    # Normalize scaffold_delivery path early (expanduser).
    if scaffold_delivery is not None:
        scaffold_delivery = str(Path(scaffold_delivery).expanduser())

    _show_banner(project=project_name, mode="init")

    if not no_tmux:
        # Conversational default — guardrail: ensure tmux is actually usable.
        # If not, give the user a helpful actionable error instead of
        # silently failing deep inside the wrapper.
        import shutil as _shutil

        if _shutil.which("tmux") is None:
            raise click.UsageError(
                "tmux is not installed, required for the conversational "
                "init flow. Install tmux, or re-run with --no-tmux and the "
                "flags listed in `zo init --help`."
            )
        if dry_run:
            raise click.UsageError(
                "--dry-run is only meaningful with --no-tmux. The Init "
                "Architect invokes `zo init --no-tmux --dry-run ...` "
                "itself before committing writes."
            )
        _launch_init_architect(
            project=project_name,
            hints={
                "branch": branch,
                "scaffold_delivery": scaffold_delivery,
                "existing_repo": str(existing_repo) if existing_repo else None,
                "base_image": base_image,
                "gpu_host": gpu_host,
                "data_path": data_path,
                "layout_mode": layout_mode,
            },
        )
        return

    _init_headless(
        project_name=project_name,
        branch=branch,
        scaffold_delivery=scaffold_delivery,
        existing_repo=existing_repo,
        base_image=base_image,
        gpu_host=gpu_host,
        data_path=data_path,
        detect=not no_detect,
        layout_mode=layout_mode,
        dry_run=dry_run,
    )


def _warn_if_branch_missing(repo_path: Path, branch: str) -> None:
    """Emit a warning if *branch* doesn't exist on the given git repo.

    Best-effort — silently no-ops if git is missing or the call fails.
    We warn rather than error because the agent/user may intend to
    create this branch before starting work.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--verify",
             f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            # Check remote branches too before warning.
            remote = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--verify",
                 f"refs/remotes/origin/{branch}"],
                capture_output=True, text=True, timeout=5,
            )
            if remote.returncode != 0:
                console.print(
                    f"[yellow]Warning:[/] branch '{branch}' does not exist "
                    f"on {repo_path}. You may need to create it "
                    f"(`git -C {repo_path} checkout -b {branch}`) before "
                    f"running `zo build`."
                )
    except Exception:  # noqa: BLE001
        pass  # Best-effort only.


def _init_headless(
    *,
    project_name: str,
    branch: str,
    scaffold_delivery: str | None,
    existing_repo: Path | None,
    base_image: str | None,
    gpu_host: str | None,
    data_path: str | None,
    detect: bool,
    layout_mode: str = "standard",
    dry_run: bool = False,
) -> None:
    """Write init artifacts directly from flags (no tmux, no agent).

    This is the single source of truth for file writes. The conversational
    Init Architect also routes here via ``zo init ... --no-tmux ...``.

    When ``dry_run=True``, no filesystem changes occur; a preview of what
    WOULD happen is printed to stdout instead. The Init Architect runs a
    dry-run first, shows output to the user, then commits.
    """
    from zo.environment import EnvironmentInfo, detect_environment, suggest_base_image

    zo_root = _main_repo_root()

    # Resolve the delivery repo path. Precedence:
    #   --existing-repo  → overlay mode, no new scaffold tree
    #   --scaffold-delivery PATH → new scaffold at absolute path
    #   neither → default to ../{project}-delivery and scaffold
    if existing_repo is not None:
        delivery_path = Path(existing_repo).resolve()
        overlay = True
    elif scaffold_delivery is not None:
        delivery_path = Path(scaffold_delivery).resolve()
        overlay = False
    else:
        delivery_path = (zo_root.parent / f"{project_name}-delivery").resolve()
        overlay = False

    # Environment detection — best-effort, user can edit the plan later.
    env: EnvironmentInfo | None = detect_environment() if detect else None
    resolved_base_image = base_image or (
        suggest_base_image(env) if env else "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime"
    )

    plan_content = _render_plan_template(
        project_name=project_name,
        env=env,
        base_image=resolved_base_image,
        gpu_host=gpu_host,
        data_path=data_path,
    )
    target_content = _TARGET_TEMPLATE.format(
        project_name=project_name,
        target_repo=str(delivery_path),
        target_branch=branch,
    )

    target_path = zo_root / "targets" / f"{project_name}.target.md"
    plan_path = zo_root / "plans" / f"{project_name}.md"

    if dry_run:
        _print_init_preview(
            project_name=project_name,
            zo_root=zo_root,
            delivery_path=delivery_path,
            branch=branch,
            target_path=target_path,
            plan_path=plan_path,
            target_content=target_content,
            plan_content=plan_content,
            overlay=overlay,
            layout_mode=layout_mode,
        )
        return

    _init_commit_writes(
        project_name=project_name,
        zo_root=zo_root,
        delivery_path=delivery_path,
        branch=branch,
        target_path=target_path,
        plan_path=plan_path,
        target_content=target_content,
        plan_content=plan_content,
        overlay=overlay,
        layout_mode=layout_mode,
    )


def _init_commit_writes(
    *,
    project_name: str,
    zo_root: Path,
    delivery_path: Path,
    branch: str,
    target_path: Path,
    plan_path: Path,
    target_content: str,
    plan_content: str,
    overlay: bool,
    layout_mode: str,
) -> None:
    """Actually write all init artifacts. Called after a successful
    dry-run or directly when the user chose not to preview.

    Writes to BOTH locations for backward compatibility:
    - .zo/ in delivery repo (new portable layout)
    - Legacy locations in ZO repo (so older commands still work)
    """
    from zo.memory import MemoryManager
    from zo.project_config import ProjectConfig, save_project_config
    from zo.scaffold import scaffold_delivery as _scaffold

    # Probe host GPU availability so the scaffolded docker-compose.yml
    # gets the right deploy block. None on detection failure → scaffold
    # falls back to the GPU template (safest default on a Linux server).
    try:
        from zo.environment import detect_environment
        _detected_gpu = detect_environment().gpu_count > 0
    except Exception:  # noqa: BLE001
        _detected_gpu = None

    # Delivery repo scaffold (fresh) or overlay (existing) — do this
    # first so .zo/ directories exist before we write into them.
    if overlay:
        _scaffold(
            delivery_path, project_name,
            overlay=True, layout_mode=layout_mode,
            gpu_enabled=_detected_gpu,
        )
    elif not delivery_path.exists():
        _scaffold(
            delivery_path, project_name,
            overlay=False, layout_mode=layout_mode,
            gpu_enabled=_detected_gpu,
        )
        console.print(f"[green]Delivery repo scaffolded:[/] {delivery_path}")
    else:
        # Path exists but user didn't pass --existing-repo — treat as overlay
        # rather than silently skipping, so structure is guaranteed.
        _scaffold(
            delivery_path, project_name,
            overlay=True, layout_mode=layout_mode,
            gpu_enabled=_detected_gpu,
        )

    # -- .zo/ layout (new, portable) --

    # .zo/config.yaml — portable project config
    zo_dir = delivery_path / ".zo"
    zo_dir.mkdir(parents=True, exist_ok=True)
    config_path = zo_dir / "config.yaml"
    if not config_path.exists():
        pc = ProjectConfig(
            project_name=project_name,
            branch=branch,
            agent_working_dirs={
                "data-engineer": "src/data/",
                "model-builder": "src/model/",
                "ml-engineer": "src/engineering/",
                "inference": "src/inference/",
                "oracle-qa": "reports/",
                "test-engineer": "tests/",
                "xai-agent": "reports/",
                "domain-evaluator": "reports/",
            },
        )
        save_project_config(delivery_path, pc)
        console.print(f"[green]Project config created:[/] {config_path}")
    else:
        console.print(f"[{_DIM}]Project config already exists:[/] {config_path}")

    # Memory in .zo/memory/ (portable)
    zo_memory = MemoryManager(
        project_dir=delivery_path,
        project_name=project_name,
        memory_root=zo_dir / "memory",
    )
    zo_memory.initialize_project()
    console.print(f"[green]Memory initialized:[/] {zo_memory.memory_root}")

    # Plan in .zo/plans/ (portable)
    zo_plan_path = zo_dir / "plans" / f"{project_name}.md"
    zo_plan_path.parent.mkdir(parents=True, exist_ok=True)
    if not zo_plan_path.exists():
        zo_plan_path.write_text(plan_content, encoding="utf-8")
        console.print(f"[green]Plan template created:[/] {zo_plan_path}")
    else:
        console.print(f"[{_DIM}]Plan already exists:[/] {zo_plan_path}")

    # -- Legacy layout (backward compat) --

    # Legacy memory in ZO repo
    legacy_memory = MemoryManager(
        project_dir=zo_root, project_name=project_name,
    )
    legacy_memory.initialize_project()

    # Legacy target file
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        target_path.write_text(target_content, encoding="utf-8")
        console.print(f"  [{_DIM}]Legacy target:[/] {target_path}")

    # Legacy plan
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    if not plan_path.exists():
        plan_path.write_text(plan_content, encoding="utf-8")
        console.print(f"  [{_DIM}]Legacy plan:[/] {plan_path}")

    console.print(f"\n[{_AMBER}]Project '{project_name}' ready.[/]")
    console.print("Next steps:")
    console.print(
        f"  1. Draft plan: [bold]zo draft --project {project_name}[/]"
    )
    console.print(
        f"  2. Build: [bold]zo build {zo_plan_path}[/]"
    )
    console.print(
        f"  3. Commit .zo/: [bold]cd {delivery_path} && "
        f"git add .zo/ && git commit -m 'feat: add ZO project state'[/]"
    )


def _print_init_preview(
    *,
    project_name: str,
    zo_root: Path,
    delivery_path: Path,
    branch: str,
    target_path: Path,
    plan_path: Path,
    target_content: str,
    plan_content: str,
    overlay: bool,
    layout_mode: str,
) -> None:
    """Render a preview of what ``_init_commit_writes`` WOULD do.

    No filesystem mutations happen. The Init Architect routes this
    output to the user before invoking the real writes.
    """
    from zo.scaffold import (
        _FILE_TEMPLATES,
        _META_DIRECTORIES,
        _STANDARD_DIRECTORIES,
    )

    console.print(f"\n[{_AMBER}]── DRY RUN — no files written ──[/]\n")
    console.print(f"[{_AMBER}]Project:[/] {project_name}")
    console.print(f"[{_AMBER}]Delivery repo:[/] {delivery_path}")
    console.print(f"[{_AMBER}]Branch:[/] {branch}")
    console.print(f"[{_AMBER}]Layout mode:[/] {layout_mode}")
    console.print(
        f"[{_AMBER}]Scaffold mode:[/] "
        f"{'overlay (existing)' if overlay else 'new scaffold'}"
    )
    console.print()

    # ZO artifacts (always written)
    console.print(f"[{_AMBER}]Would create in ZO repo ({zo_root}):[/]")
    memory_root = zo_root / "memory" / project_name
    _would_write(memory_root / "STATE.md", tag="(new)")
    _would_write(memory_root / "DECISION_LOG.md", tag="(new)")
    _would_write(memory_root / "PRIORS.md", tag="(new)")
    _would_write(memory_root / "sessions", tag="(dir)")
    _would_write(target_path, tag="(new)" if not target_path.exists() else "(exists — kept)")
    _would_write(plan_path, tag="(new)" if not plan_path.exists() else "(exists — kept)")
    console.print()

    # Delivery repo — directories and files
    if layout_mode == "adaptive":
        dirs = _META_DIRECTORIES
    else:
        dirs = _META_DIRECTORIES + _STANDARD_DIRECTORIES

    if layout_mode == "adaptive":
        skip = {"README.md", "pyproject.toml", ".gitignore"}
        templates = [p for p, _ in _FILE_TEMPLATES if p not in skip]
    else:
        templates = [p for p, _ in _FILE_TEMPLATES]

    console.print(
        f"[{_AMBER}]Would create in delivery repo ({delivery_path}):[/]"
    )
    for rel in dirs:
        full = delivery_path / rel
        if full.exists() and any(full.iterdir()):
            console.print(f"  [{_DIM}]preserved[/] {rel}/")
        else:
            console.print(f"  [green]+[/] {rel}/")
    for rel in templates:
        full = delivery_path / rel
        if full.exists():
            console.print(f"  [{_DIM}]preserved[/] {rel}")
        else:
            console.print(f"  [green]+[/] {rel}")

    console.print()
    console.print(f"[{_AMBER}]target.md preview ({len(target_content)} chars):[/]")
    # Show first 30 lines to keep output scannable
    preview = "\n".join(target_content.splitlines()[:30])
    console.print(f"[{_DIM}]{preview}[/]")
    console.print()
    console.print(f"[{_AMBER}]plan.md Environment section preview:[/]")
    env_lines: list[str] = []
    capture = False
    for line in plan_content.splitlines():
        if line.startswith("## Environment"):
            capture = True
        elif capture and line.startswith("## "):
            break
        if capture:
            env_lines.append(line)
    console.print(f"[{_DIM}]" + "\n".join(env_lines) + "[/]")
    console.print()
    console.print(
        f"[{_AMBER}]── END DRY RUN — re-run without --dry-run to commit ──[/]"
    )


def _would_write(path: Path, *, tag: str) -> None:
    """Helper: print a single 'would write' line for dry-run output."""
    console.print(f"  [green]+[/] {path}  [{_DIM}]{tag}[/]")


def _init_reset(*, project_name: str, skip_confirm: bool) -> None:
    """Delete ZO init artifacts for *project_name*.

    Removes ``memory/{project}/``, ``targets/{project}.target.md``, and
    ``plans/{project}.md`` from the main repo. The delivery repo is
    NEVER touched — we refuse to rm user code.

    Refuses if nothing exists (saves the user from thinking they ran
    reset on a fresh project and deleted something they shouldn't).
    """
    import shutil

    zo_root = _main_repo_root()
    memory_dir = zo_root / "memory" / project_name
    target_path = zo_root / "targets" / f"{project_name}.target.md"
    plan_path = zo_root / "plans" / f"{project_name}.md"

    candidates: list[tuple[Path, str]] = []
    if memory_dir.exists():
        candidates.append((memory_dir, "dir"))
    if target_path.exists():
        candidates.append((target_path, "file"))
    if plan_path.exists():
        candidates.append((plan_path, "file"))

    if not candidates:
        console.print(
            f"[yellow]Nothing to reset:[/] no ZO artifacts for "
            f"'{project_name}' found at {zo_root}. "
            f"(Checked {memory_dir}, {target_path}, {plan_path}.)"
        )
        return

    console.print(
        f"\n[{_AMBER}]The following will be DELETED:[/]"
    )
    for path, kind in candidates:
        console.print(f"  [red]x[/] {path}  [{_DIM}]({kind})[/]")
    console.print()
    console.print(
        f"[{_DIM}]Delivery repo is NEVER touched. "
        f"ZO will not remove user code or data.[/]"
    )
    console.print()

    if not skip_confirm:
        confirm = console.input(
            f"  [{_AMBER}]Type the project name to confirm ({project_name}):[/] "
        ).strip()
        if confirm != project_name:
            console.print("[yellow]Reset cancelled — name did not match.[/]")
            return

    for path, kind in candidates:
        if kind == "dir":
            shutil.rmtree(path)
        else:
            path.unlink()
        console.print(f"[green]Deleted:[/] {path}")

    console.print(
        f"\n[{_AMBER}]'{project_name}' is reset.[/] "
        f"You can re-run `zo init {project_name}` to start fresh."
    )


def _render_plan_template(
    *,
    project_name: str,
    env,  # EnvironmentInfo | None
    base_image: str,
    gpu_host: str | None,
    data_path: str | None,
) -> str:
    """Format the plan template with environment placeholders resolved."""
    if env is not None:
        env_platform = env.platform
        env_python = env.python_version
        env_docker = "yes" if env.docker_available else "no"
        env_gpu_avail = "yes" if env.gpu_count > 0 else "no"
        env_gpu_count = str(env.gpu_count)
        env_cuda = env.cuda_version or "(none detected)"
    else:
        env_platform = "TODO"
        env_python = "TODO"
        env_docker = "TODO"
        env_gpu_avail = "TODO"
        env_gpu_count = "TODO"
        env_cuda = "TODO"

    # Training target — if GPU host provided, training is remote; else use host.
    if gpu_host:
        resolved_gpu_host = gpu_host
        train_cuda = "TODO: verify CUDA version on GPU host"
    else:
        resolved_gpu_host = "local (same host as ZO)"
        train_cuda = env_cuda

    # Data layout — explicit when host is given, otherwise local assumption.
    if data_path and ":" in data_path:
        data_layout = "remote"
    elif data_path:
        data_layout = "local"
    else:
        data_layout = "TODO: local or remote"
    resolved_data_path = data_path or "TODO: path to data"

    return _PLAN_TEMPLATE.format(
        project_name=project_name,
        env_platform=env_platform,
        env_python=env_python,
        env_docker=env_docker,
        env_gpu_available=env_gpu_avail,
        env_gpu_count=env_gpu_count,
        env_cuda=env_cuda,
        gpu_host=resolved_gpu_host,
        base_image=base_image,
        train_cuda=train_cuda,
        data_layout=data_layout,
        data_path=resolved_data_path,
    )


def _launch_init_architect(*, project: str, hints: dict) -> None:
    """Launch the Init Architect agent in tmux for conversational init."""
    from zo.comms import CommsLogger
    from zo.wrapper import LifecycleWrapper

    zo_root = _zo_root()

    console.print(f"[{_AMBER}]Launching Init Architect...[/]")
    session_id = f"s-{uuid.uuid4().hex[:8]}"
    comms = CommsLogger(
        log_dir=zo_root / "logs" / "comms",
        project=project,
        session_id=session_id,
    )
    wrapper = LifecycleWrapper(
        comms=comms, log_dir=zo_root / "logs" / "wrapper",
    )

    prompt = _build_init_architect_prompt(project=project, hints=hints)
    # Grant access to existing repo if provided in hints
    extra_dirs: list[str] = []
    if hints.get("existing_repo"):
        extra_dirs.append(hints["existing_repo"])
    if hints.get("data_path"):
        extra_dirs.append(hints["data_path"])
    _launch_and_monitor(
        wrapper=wrapper,
        prompt=prompt,
        team_name=f"init-{project}",
        zo_root=zo_root,
        no_tmux=False,
        model="opus",
        max_turns=60,
        add_dirs=extra_dirs,
    )


def _build_init_architect_prompt(*, project: str, hints: dict) -> str:
    """Construct the Init Architect's prompt for a conversational init.

    Hints are values the user passed alongside the main command. The
    agent treats them as defaults and still confirms with the user.
    """
    hint_lines: list[str] = []
    for key, value in hints.items():
        if value is None:
            continue
        hint_lines.append(f"  - {key}: {value}")
    hints_block = "\n".join(hint_lines) if hint_lines else "  (none)"

    return (
        f"# Role\n\n"
        f"You are the **Init Architect** for project '{project}'.\n"
        f"Your agent definition is at "
        f".claude/agents/init-architect.md — read it for your full "
        f"protocol.\n\n"
        f"---\n\n"
        f"# Task\n\n"
        f"Conduct a short interview with the user, inspect the target "
        f"repo (if any), then call the headless ZO CLI to write all "
        f"init artifacts.\n\n"
        f"Never write files yourself — always route writes through "
        f"`zo init {project} --no-tmux ...` so the CLI remains the "
        f"single source of truth.\n\n"
        f"# CLI hints from invocation\n\n"
        f"{hints_block}\n\n"
        f"Ask the user about anything not listed above. Confirm hints "
        f"before using them.\n"
    )


@cli.command()
@click.argument("project_name")
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo. If omitted, resolved from "
    "targets/{project_name}.target.md.",
)
@click.option(
    "--clean", is_flag=True,
    help="Remove legacy artifacts from ZO repo after migration.",
)
def migrate(project_name: str, repo: str | None, clean: bool) -> None:
    """Migrate project state from ZO repo to delivery repo .zo/ directory.

    Copies memory (STATE.md, DECISION_LOG, PRIORS, sessions), plan, and
    target config into the delivery repo's .zo/ directory, making the
    project portable across machines via git.

    After migration, commit .zo/ in the delivery repo::

        cd /path/to/delivery && git add .zo/ && git commit

    Use --clean to remove the old artifacts from the ZO repo after
    verifying the migration succeeded.
    """
    import shutil

    from zo.project_config import (
        ProjectConfig,
        has_zo_dir,
        save_local_config,
        save_project_config,
    )

    _show_banner(project=project_name, mode="migrate")

    zo_root = _main_repo_root()

    # Resolve delivery repo path
    if repo:
        delivery_path = Path(repo).resolve()
    else:
        target_path = zo_root / "targets" / f"{project_name}.target.md"
        if not target_path.exists():
            console.print(
                f"[red bold]Target file not found:[/] {target_path}\n"
                f"Use [bold]--repo /path/to/delivery[/] to specify the "
                f"delivery repo path explicitly."
            )
            raise SystemExit(1)
        from zo.target import parse_target

        target = parse_target(target_path)
        delivery_path = Path(target.target_repo).resolve()

    if not delivery_path.is_dir():
        console.print(f"[red bold]Delivery repo not found:[/] {delivery_path}")
        raise SystemExit(1)

    # Check if already migrated
    if has_zo_dir(delivery_path):
        console.print(
            f"[{_DIM}]Delivery repo already has .zo/ — "
            f"checking for missing files.[/]"
        )

    # Source paths (legacy ZO repo layout)
    legacy_memory = zo_root / "memory" / project_name
    legacy_plan = zo_root / "plans" / f"{project_name}.md"
    legacy_target = zo_root / "targets" / f"{project_name}.target.md"

    # Destination paths (.zo/ in delivery repo)
    zo_dir = delivery_path / ".zo"
    zo_memory = zo_dir / "memory"
    zo_plans = zo_dir / "plans"

    # Create .zo/ structure
    for d in [zo_dir, zo_memory, zo_memory / "sessions", zo_plans]:
        d.mkdir(parents=True, exist_ok=True)

    # Write .zo/.gitignore
    gitignore = zo_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Machine-specific config (paths, GPU info, gate mode)\n"
            "local.yaml\n\n"
            "# SQLite databases (regenerated from DECISION_LOG)\n"
            "memory/index.db\n"
            "memory/draft_index.db\n",
            encoding="utf-8",
        )

    copied = 0

    # Copy memory files
    if legacy_memory.is_dir():
        for f in ["STATE.md", "DECISION_LOG.md", "PRIORS.md"]:
            src = legacy_memory / f
            dst = zo_memory / f
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                console.print(f"  [green]Copied:[/] {f}")
                copied += 1
            elif src.exists():
                console.print(f"  [{_DIM}]Already exists:[/] {f}")

        # Copy sessions
        sessions_src = legacy_memory / "sessions"
        sessions_dst = zo_memory / "sessions"
        if sessions_src.is_dir():
            for sf in sessions_src.iterdir():
                if sf.is_file():
                    dst = sessions_dst / sf.name
                    if not dst.exists():
                        shutil.copy2(sf, dst)
                        copied += 1
            session_count = sum(1 for _ in sessions_src.iterdir())
            if session_count:
                console.print(
                    f"  [green]Copied:[/] {session_count} session files"
                )

        # Copy index.db if exists (will be regenerated but saves time)
        for db in ["index.db", "draft_index.db"]:
            src = legacy_memory / db
            dst = zo_memory / db
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

        # Copy gate_mode into local.yaml
        gm_src = legacy_memory / "gate_mode"
        gm_content = ""
        if gm_src.exists():
            gm_content = gm_src.read_text(encoding="utf-8").strip()
    else:
        console.print(f"  [{_DIM}]No legacy memory found at {legacy_memory}[/]")
        gm_content = ""

    # Always write local.yaml — even without gate_mode, the user needs
    # environment detection on the current machine for portability.
    from zo.environment import detect_environment
    from zo.project_config import LocalConfig

    local_path = zo_dir / "local.yaml"
    if not local_path.exists():
        env = detect_environment()
        local = LocalConfig(
            gate_mode=gm_content or "supervised",
            gpu_count=env.gpu_count if env else 0,
            cuda_version=env.cuda_version if env else None,
            docker_available=env.docker_available if env else False,
            zo_repo_path=str(zo_root),
        )
        save_local_config(delivery_path, local)
        console.print(
            f"  [green]Local config written[/] (gate_mode="
            f"{gm_content or 'supervised'})"
        )

    # Copy plan
    if legacy_plan.exists():
        dst = zo_plans / f"{project_name}.md"
        if not dst.exists():
            shutil.copy2(legacy_plan, dst)
            console.print(f"  [green]Copied:[/] plan → .zo/plans/{project_name}.md")
            copied += 1
        else:
            console.print(f"  [{_DIM}]Plan already exists in .zo/[/]")
    else:
        console.print(f"  [{_DIM}]No legacy plan found[/]")

    # Generate .zo/config.yaml from target file
    config_path = zo_dir / "config.yaml"
    if not config_path.exists() and legacy_target.exists():
        from zo.target import parse_target

        target = parse_target(legacy_target)
        pc = ProjectConfig(
            project_name=project_name,
            branch=target.target_branch,
            agent_working_dirs=dict(target.agent_working_dirs),
            zo_only_paths=[".zo/memory/", ".zo/plans/"],
            git_author_name=target.git_author_name,
            git_author_email=target.git_author_email,
            enforce_isolation=target.enforce_isolation,
        )
        save_project_config(delivery_path, pc)
        console.print("  [green]Config created:[/] .zo/config.yaml")
        copied += 1
    elif not config_path.exists():
        # No target file — create minimal config
        pc = ProjectConfig(project_name=project_name)
        save_project_config(delivery_path, pc)
        console.print("  [green]Config created:[/] .zo/config.yaml (minimal)")
        copied += 1

    # Summary
    console.print(f"\n[{_AMBER}]Migration complete:[/] {copied} files copied")
    console.print(
        f"\nNext: [bold]cd {delivery_path} && git add .zo/ && "
        f"git commit -m 'feat: add ZO project state'[/]"
    )
    console.print(
        f"Then on new machine: [bold]zo continue --repo {delivery_path}[/]"
    )

    # Clean up legacy artifacts if requested
    if clean:
        console.print(f"\n[{_AMBER}]Cleaning legacy artifacts...[/]")
        if legacy_memory.is_dir():
            shutil.rmtree(legacy_memory)
            console.print(f"  Removed: {legacy_memory}")
        if legacy_plan.exists():
            legacy_plan.unlink()
            console.print(f"  Removed: {legacy_plan}")
        if legacy_target.exists():
            legacy_target.unlink()
            console.print(f"  Removed: {legacy_target}")
        console.print("[green]Legacy cleanup done.[/]")


@cli.command()
@click.argument("project_name", required=False, default=None)
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def status(project_name: str | None, repo: str | None) -> None:
    """Show current project status from STATE.md.

    Supports both .zo/ layout (delivery repo) and legacy layout.
    From inside a delivery repo with .zo/, project_name is optional.
    """
    from zo.project_config import has_zo_dir, load_project_config

    # Resolve project name from .zo/ if not given
    delivery = Path(repo).resolve() if repo else None
    if project_name is None:
        detect_path = delivery or Path.cwd()
        if has_zo_dir(detect_path):
            pc = load_project_config(detect_path)
            project_name = pc.project_name
            if delivery is None:
                delivery = detect_path
        else:
            console.print(
                "[red bold]No project name given and no .zo/ found in cwd.[/]"
            )
            raise SystemExit(1)

    _show_banner(project=project_name, mode="status")

    pctx = _load_project_context(project_name, delivery_repo=delivery)
    memory = pctx.make_memory()

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


@cli.group()
def gates() -> None:
    """Inspect and control gate modes for running projects."""


@gates.command("set")
@click.argument(
    "mode",
    type=click.Choice(["supervised", "auto", "full-auto"]),
)
@click.option(
    "--project", "-p", required=True,
    help="Project name whose gate mode to change.",
)
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def gates_set(mode: str, project: str, repo: str | None) -> None:
    """Set the gate mode for a project mid-session.

    Writes the mode to the project's gate_mode file so that
    the running orchestrator and wrapper pick it up dynamically.

    Supports both .zo/ layout and legacy layout.

    Valid modes: supervised, auto, full-auto.

    Usage::

        zo gates set auto --project my-project
        zo gates set full-auto -p my-project --repo ~/my-delivery
    """
    delivery = Path(repo).resolve() if repo else None
    pctx = _load_project_context(project, delivery_repo=delivery)
    memory = pctx.make_memory()

    if not memory.memory_root.exists():
        console.print(
            f"[red bold]No memory found for '{project}'.[/] "
            "Run [bold]zo init[/] or [bold]zo build[/] first."
        )
        raise SystemExit(1)

    # Normalise CLI string to the GateMode enum value
    gm = _gate_mode_from_str(mode)
    memory.write_gate_mode(gm.value)

    _show_banner(project=project, mode="gates", gate_mode=gm.value)
    console.print(f"  Gate mode set to: [{_AMBER}]{gm.value}[/]")


# ---------------------------------------------------------------------------
# Experiments — inspect the Phase 4 experiment registry
# ---------------------------------------------------------------------------


@cli.group()
def experiments() -> None:
    """Inspect the Phase 4 experiment registry for a project."""


def _experiments_dir_for(project: str, repo: str | None) -> Path:
    """Resolve the ``.zo/experiments/`` dir for a project.

    Exits with a helpful message when the delivery repo or registry
    cannot be found.
    """
    delivery = Path(repo).resolve() if repo else None
    pctx = _load_project_context(project, delivery_repo=delivery)
    target = pctx.make_target()
    delivery_repo = Path(target.target_repo)
    if not delivery_repo.is_dir():
        console.print(
            f"[red bold]Delivery repo not found:[/] {delivery_repo}\n"
            f"Pass [bold]--repo PATH[/] to override.",
        )
        raise SystemExit(1)
    return delivery_repo / ".zo" / "experiments"


def _format_metric(value: float | None) -> str:
    """Render a float metric for table cells; shows '—' for None."""
    if value is None:
        return "—"
    abs_v = abs(value)
    if abs_v >= 100 or abs_v == 0:
        return f"{value:.2f}"
    return f"{value:.4g}"


def _format_delta(value: float | None) -> str:
    """Render delta_vs_parent with a sign and color hint. No color hint
    when value is None (root)."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{_format_metric(value)}"


@experiments.command("list")
@click.option("--project", "-p", required=True, help="Project name")
@click.option(
    "--phase", default=None,
    help="Filter to one phase (e.g. phase_4).",
)
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def experiments_list(
    project: str, phase: str | None, repo: str | None,
) -> None:
    """List all experiments in the project's registry.

    Shows id, phase, parent, hypothesis summary, primary metric,
    delta_vs_parent, and status. Useful as a quick overview before
    diving into a specific experiment with ``zo experiments show``.
    """
    from zo.experiments import load_registry

    _show_banner(project=project, mode="experiments")
    exp_dir = _experiments_dir_for(project, repo)
    if not exp_dir.is_dir():
        console.print(
            f"  [{_DIM}]No experiments yet.[/]\n"
            f"  Registry will be created at "
            f"[bold]{exp_dir}[/] on first Phase 4 run.",
        )
        return

    registry = load_registry(exp_dir)
    rows = registry.experiments
    if phase:
        rows = [e for e in rows if e.phase == phase]
    if not rows:
        console.print(
            f"  [{_DIM}]No experiments match[/] "
            f"(phase filter: {phase or 'none'}).",
        )
        return

    table = Table(
        title=f"Experiments — {registry.project}",
        show_lines=False,
    )
    table.add_column("ID", style="bold")
    table.add_column("Phase")
    table.add_column("Parent", style=_DIM)
    table.add_column("Hypothesis")
    table.add_column("Metric")
    table.add_column("Δ parent", justify="right")
    table.add_column("Status")
    for exp in rows:
        status_style = {
            "running": _AMBER,
            "complete": "green",
            "failed": "red",
            "aborted": _DIM,
        }.get(str(exp.status), "")
        metric_cell = "—"
        delta_cell = "—"
        if exp.result is not None:
            pm = exp.result.primary_metric
            metric_cell = f"{pm.name}={_format_metric(pm.value)}"
            delta_cell = _format_delta(pm.delta_vs_parent)
        hypothesis_short = (
            exp.hypothesis[:48] + "…"
            if len(exp.hypothesis) > 49 else exp.hypothesis
        ) or "—"
        table.add_row(
            exp.id,
            exp.phase,
            exp.parent_id or "—",
            hypothesis_short,
            metric_cell,
            delta_cell,
            f"[{status_style}]{exp.status}[/]" if status_style else str(exp.status),
        )
    console.print(table)


@experiments.command("show")
@click.argument("exp_id")
@click.option("--project", "-p", required=True, help="Project name")
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def experiments_show(project: str, exp_id: str, repo: str | None) -> None:
    """Show full details for a single experiment.

    Prints registry metadata plus the contents of every authored
    markdown artifact (``hypothesis.md``, ``result.md``, ``diagnosis.md``,
    ``next.md``) when present. Use for deep inspection after
    ``zo experiments list`` narrows the field.
    """
    from zo.experiments import load_registry

    _show_banner(project=project, mode="experiments")
    exp_dir = _experiments_dir_for(project, repo)
    if not exp_dir.is_dir():
        console.print(f"  [red]No registry at {exp_dir}.[/]")
        raise SystemExit(1)

    registry = load_registry(exp_dir)
    exp = registry.find(exp_id)
    if exp is None:
        console.print(
            f"  [red bold]Experiment {exp_id} not found.[/]\n"
            f"  Registered ids: "
            f"{', '.join(e.id for e in registry.experiments) or '(none)'}",
        )
        raise SystemExit(1)

    console.print(f"\n  [{_AMBER}][bold]{exp.id}[/][/]  "
                  f"[{_DIM}]({exp.phase})[/]")
    console.print(f"  Parent:       {exp.parent_id or '—'}")
    console.print(f"  Status:       {exp.status}")
    console.print(f"  Created:      {exp.created.isoformat()}")
    console.print(f"  Artifacts:    {exp.artifacts_dir}")
    if exp.hypothesis:
        console.print(f"  Hypothesis:   {exp.hypothesis}")
    if exp.rationale:
        console.print(f"  Rationale:    {exp.rationale}")
    if exp.result is not None:
        pm = exp.result.primary_metric
        console.print(f"  Oracle tier:  [{_AMBER}]{exp.result.oracle_tier}[/]")
        console.print(
            f"  Primary:      {pm.name} = {_format_metric(pm.value)}  "
            f"(Δ parent: {_format_delta(pm.delta_vs_parent)})",
        )
        if exp.result.secondary_metrics:
            console.print(f"  [{_DIM}]Secondary metrics:[/]")
            for k, v in exp.result.secondary_metrics.items():
                console.print(f"    {k}: {_format_metric(v)}")
        if exp.result.shortfalls:
            console.print(f"  [{_DIM}]Shortfalls:[/]")
            for s in exp.result.shortfalls:
                console.print(f"    - {s}")
    if exp.next_ideas:
        console.print(f"  [{_DIM}]Next ideas:[/]")
        for idea in exp.next_ideas:
            console.print(f"    - {idea}")

    # Dump markdown artifacts if present.
    artifact_names = ["hypothesis.md", "result.md", "diagnosis.md", "next.md"]
    for name in artifact_names:
        path = Path(exp.artifacts_dir) / name
        if not path.is_file():
            continue
        console.print(f"\n  [{_AMBER}]── {name} ──[/]")
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            console.print(f"  {line}", markup=False, highlight=False)


@experiments.command("diff")
@click.argument("exp_a")
@click.argument("exp_b")
@click.option("--project", "-p", required=True, help="Project name")
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def experiments_diff(
    project: str, exp_a: str, exp_b: str, repo: str | None,
) -> None:
    """Diff two experiments across metrics, hypothesis, and shortfalls.

    Intended for sibling comparisons ("which of our two variants
    beat the other, and on what dimensions?") as well as
    parent-child comparisons.
    """
    from zo.experiments import load_registry

    _show_banner(project=project, mode="experiments")
    exp_dir = _experiments_dir_for(project, repo)
    registry = load_registry(exp_dir)
    a = registry.find(exp_a)
    b = registry.find(exp_b)
    if a is None or b is None:
        missing = [x for x, e in [(exp_a, a), (exp_b, b)] if e is None]
        console.print(
            f"  [red bold]Not found:[/] {', '.join(missing)}\n"
            f"  Registered ids: "
            f"{', '.join(e.id for e in registry.experiments) or '(none)'}",
        )
        raise SystemExit(1)

    console.print(
        f"\n  [{_AMBER}][bold]{a.id}[/] ↔ [bold]{b.id}[/][/]  "
        f"[{_DIM}](parents: {a.parent_id or '—'} / {b.parent_id or '—'})[/]\n",
    )

    table = Table(show_header=True, show_lines=False)
    table.add_column("Field", style="bold")
    table.add_column(a.id)
    table.add_column(b.id)
    table.add_column("Δ (b − a)", justify="right")

    # Hypothesis lines first (no delta).
    table.add_row(
        "hypothesis",
        (a.hypothesis[:40] + "…") if len(a.hypothesis) > 41 else (a.hypothesis or "—"),
        (b.hypothesis[:40] + "…") if len(b.hypothesis) > 41 else (b.hypothesis or "—"),
        "—",
    )
    table.add_row(
        "status", str(a.status), str(b.status), "—",
    )

    # Result-based metrics — only if both have results.
    if a.result is not None and b.result is not None:
        pm_a, pm_b = a.result.primary_metric, b.result.primary_metric
        if pm_a.name == pm_b.name:
            delta = pm_b.value - pm_a.value
            table.add_row(
                f"{pm_a.name} (primary)",
                _format_metric(pm_a.value), _format_metric(pm_b.value),
                _format_delta(delta),
            )
        else:
            table.add_row(
                "primary metric (name differs)",
                f"{pm_a.name}={_format_metric(pm_a.value)}",
                f"{pm_b.name}={_format_metric(pm_b.value)}",
                "—",
            )
        table.add_row(
            "oracle tier",
            a.result.oracle_tier, b.result.oracle_tier, "—",
        )
        # Secondary metrics shared between the two.
        shared = sorted(
            set(a.result.secondary_metrics) & set(b.result.secondary_metrics),
        )
        for k in shared:
            va, vb = a.result.secondary_metrics[k], b.result.secondary_metrics[k]
            table.add_row(
                k, _format_metric(va), _format_metric(vb),
                _format_delta(vb - va),
            )
    else:
        table.add_row(
            "result", "(none)" if a.result is None else "present",
            "(none)" if b.result is None else "present", "—",
        )

    console.print(table)

    # Shortfall diff — set-based so the reader sees what's new/gone.
    a_sf = set(a.result.shortfalls) if a.result else set()
    b_sf = set(b.result.shortfalls) if b.result else set()
    only_a = sorted(a_sf - b_sf)
    only_b = sorted(b_sf - a_sf)
    shared_sf = sorted(a_sf & b_sf)
    if only_a or only_b or shared_sf:
        console.print(f"\n  [{_DIM}]Shortfalls:[/]")
    for s in shared_sf:
        console.print(f"    = {s}")
    for s in only_a:
        console.print(f"    [{_AMBER}]− {a.id} only:[/] {s}")
    for s in only_b:
        console.print(f"    [{_AMBER}]+ {b.id} only:[/] {s}")


@cli.command("watch-training")
@click.option("--project", "-p", required=True, help="Project name")
@click.option("--interval", "-i", default=2.0, help="Refresh interval in seconds")
@click.option(
    "--repo", type=click.Path(exists=True, file_okay=False), default=None,
    help="Path to delivery repo with .zo/ directory.",
)
def watch_training(project: str, interval: float, repo: str | None) -> None:
    """Live training metrics dashboard.

    Tails the training metrics JSONL in the delivery repo and displays
    a persistent Rich panel with epoch progress, loss/metrics, checkpoints,
    and a sparkline.  Refreshes every INTERVAL seconds.

    Auto-launched by zo build during Phase 4 (training) via tmux split-pane.
    Can also be run standalone::

        zo watch-training --project my-project --repo ~/my-delivery
    """
    from zo.experiments import resolve_active_experiment_dir
    from zo.plan import parse_plan
    from zo.training_display import run_live_display

    # Resolve delivery repo from context (.zo/ or legacy)
    delivery = Path(repo).resolve() if repo else None
    pctx = _load_project_context(project, delivery_repo=delivery)
    target = pctx.make_target()
    delivery_repo = Path(target.target_repo)

    # Try to get oracle target from plan
    target_metric: float | None = None
    target_metric_name = ""
    plan_path = pctx.plan_path
    if plan_path.exists():
        try:
            plan = parse_plan(plan_path)
            if plan.oracle:
                target_metric = plan.oracle.target_threshold
                target_metric_name = plan.oracle.primary_metric or ""
        except Exception:
            pass

    # Resolve the active Phase 4 experiment dir; fall back to legacy
    # logs/training when no experiment exists yet (lets the dashboard
    # render its "Waiting…" panel instead of erroring).
    log_dir = resolve_active_experiment_dir(delivery_repo)
    if log_dir is None:
        log_dir = delivery_repo / ".zo" / "experiments"
    _show_banner(project=project, mode="watch-training")

    run_live_display(
        log_dir,
        interval=interval,
        target_metric=target_metric,
        target_metric_name=target_metric_name,
    )


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
    _show_banner(mode="preflight")

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
@click.option("--project", "-p", required=True, help="Project name for the generated plan")
@click.option(
    "--docs", multiple=True, type=click.Path(exists=True, path_type=Path),
    help="Source documents (requirements, scope of work, domain docs)",
)
@click.option(
    "--data", multiple=True, type=click.Path(exists=True, path_type=Path),
    help="Data files/dirs for the Data Scout to inspect",
)
@click.option("--description", "-d", default=None, help="Project description")
@click.option("--no-tmux", is_flag=True, help="Skip interactive drafting session")
def draft(
    project: str, docs: tuple[Path, ...], data: tuple[Path, ...],
    description: str | None, no_tmux: bool,
) -> None:
    """Draft a plan.md with a scout team.

    Launches a Plan Architect (Opus) that conversationally drafts the
    plan with you.  Optionally spawns scouts in the background:

    - **Data Scout** inspects --data paths (schema, distributions,
      quality flags, complexity signals)
    - **Research Scout** finds prior art and baselines for the domain

    All args are optional.  If nothing is provided, the Plan Architect
    asks you conversationally.

    Usage::

        zo draft -p my-project --docs ~/docs/ --data ~/data/
        zo draft -p cifar10 -d "CIFAR-10 CNN, PyTorch, 90%+ accuracy"
        zo draft -p my-project
    """
    from zo.draft import PlanDrafter

    _show_banner(project=project, mode="draft")

    zo_root = _zo_root()
    main_root = _main_repo_root()
    desc = description or ""
    doc_context = ""

    # Always write plans to main repo, not worktrees
    plan_root = main_root if main_root != zo_root else zo_root

    if docs:
        # --- Source documents provided: index and generate skeleton ---
        drafter = PlanDrafter(
            source_paths=list(docs), project_name=project,
            zo_root=plan_root,
        )

        console.print(
            f"[{_AMBER}]Indexing documents from "
            f"{len(docs)} path(s):[/]"
        )
        for sp in docs:
            console.print(f"  [{_DIM}]{sp}[/]")
        count = drafter.index_documents()
        console.print(f"[green]Indexed {count} documents.[/]")

        console.print(f"[{_AMBER}]Generating plan from documents...[/]")
        plan_path = drafter.generate_plan()
        doc_context = drafter.get_document_summaries()

    else:
        # --- No source documents: description or interactive ---
        if not desc:
            console.print(
                f"[{_AMBER}]No source documents provided.[/]\n"
                f"  [{_DIM}]Describe your project briefly "
                f"(goal, domain, method, target metric):[/]"
            )
            console.print()
            desc = console.input(f"  [{_AMBER}]>[/] ").strip()
            if not desc:
                console.print(
                    "[red bold]No description provided. Aborting.[/]"
                )
                raise SystemExit(1)

        drafter = PlanDrafter(
            project_name=project, zo_root=plan_root,
        )

        console.print(f"\n[{_AMBER}]Drafting plan for:[/] {project}")
        console.print(f"  [{_DIM}]Description:[/] {desc}")

        console.print(f"[{_AMBER}]Generating plan skeleton...[/]")
        plan_path = drafter.generate_plan_from_description(desc)

    if data:
        console.print(f"[{_AMBER}]Data paths for scout inspection:[/]")
        for dp in data:
            console.print(f"  [{_DIM}]{dp}[/]")

    console.print(f"[green]Plan skeleton:[/] {plan_path}")
    if plan_root != zo_root:
        console.print(
            f"  [{_DIM}]Written to main repo (not worktree)[/]"
        )

    valid = drafter.validate_draft(plan_path)
    if valid:
        console.print("[green bold]Plan passes schema validation.[/]")
    else:
        console.print(
            "[yellow bold]Plan has validation issues.[/] "
            "The drafting session will address them."
        )

    # --- Launch scout team session ---
    if not no_tmux:
        from zo.comms import CommsLogger
        from zo.wrapper import LifecycleWrapper

        console.print(
            f"\n[{_AMBER}]Launching draft scout team...[/]"
        )

        session_id = f"s-{uuid.uuid4().hex[:8]}"
        comms = CommsLogger(
            log_dir=zo_root / "logs" / "comms",
            project=project, session_id=session_id,
        )
        wrapper = LifecycleWrapper(
            comms=comms, log_dir=zo_root / "logs" / "wrapper",
        )

        draft_prompt = _build_draft_prompt(
            project=project,
            plan_path=plan_path,
            doc_context=doc_context,
            description=desc,
            data_paths=data,
            zo_root=zo_root,
        )

        # Grant Claude access to doc/data dirs + delivery repo so agents
        # don't trigger directory permission prompts mid-session.
        extra_dirs: list[str] = []
        for dp in docs:
            extra_dirs.append(str(dp.resolve()))
        for dp in data:
            extra_dirs.append(str(dp.resolve()))
        # Also grant access to delivery repo if target file exists
        target_path = (main_root / "targets" / f"{project}.target.md")
        if target_path.exists():
            try:
                from zo.target import parse_target
                tgt = parse_target(target_path)
                if tgt.target_repo:
                    extra_dirs.append(str(Path(tgt.target_repo).resolve()))
            except Exception:
                pass  # Non-critical

        _launch_and_monitor(
            wrapper=wrapper,
            prompt=draft_prompt,
            team_name=f"draft-{project}",
            zo_root=zo_root,
            no_tmux=False,
            model="opus",
            max_turns=100,
            add_dirs=extra_dirs,
        )

    drafter.close()


def _build_draft_prompt(
    *,
    project: str,
    plan_path: Path,
    doc_context: str,
    description: str,
    data_paths: tuple[Path, ...],
    zo_root: Path,
) -> str:
    """Construct the Plan Architect's prompt for a draft session."""
    build_cmd = f"zo build plans/{project}.md"

    # Context block
    context_parts: list[str] = []
    if doc_context:
        context_parts.append(f"## Indexed Document Context\n\n{doc_context}")
    if description:
        context_parts.append(
            f"## User Description\n\n{description}"
        )
    context_block = "\n\n".join(context_parts)

    # Scout spawn instructions
    scout_instructions: list[str] = []

    # Data Scout — only if data paths provided
    if data_paths:
        paths_str = ", ".join(str(p.resolve()) for p in data_paths)
        scout_instructions.append(
            f'2. Spawn a **Data Scout** teammate:\n'
            f'   ```\n'
            f'   Agent(name="data-scout", team_name="draft-{project}",\n'
            f'         prompt="Inspect the data at: {paths_str}. '
            f'Report schema, shape, distributions, quality flags, '
            f'and complexity signals. Send your findings back to me '
            f'via SendMessage.")\n'
            f'   ```'
        )

    # Research Scout — always
    objective_hint = description or "the project described in the skeleton plan"
    scout_instructions.append(
        f'{"3" if data_paths else "2"}. Spawn a **Research Scout** teammate:\n'
        f'   ```\n'
        f'   Agent(name="research-scout", '
        f'team_name="draft-{project}",\n'
        f'         prompt="Research prior art, SOTA approaches, baselines, '
        f'and open-source implementations for: {objective_hint}. '
        f'Send your findings back to me via SendMessage.")\n'
        f'   ```'
    )

    scout_block = "\n".join(scout_instructions)
    data_note = ""
    if not data_paths:
        data_note = (
            "\nNo data paths were provided. Ask the human where the "
            "data is. If they provide paths during conversation, you "
            "can spawn a Data Scout at that point.\n"
        )

    return (
        f"# Role\n\n"
        f"You are the Plan Architect for project '{project}'.\n"
        f"Your agent definition is at .claude/agents/plan-architect.md "
        f"— read it for your full protocol.\n\n"
        f"---\n\n"
        f"# Plan\n\n"
        f"A skeleton plan exists at `{plan_path}`. Read it first.\n\n"
        f"{context_block}\n\n"
        f"---\n\n"
        f"# Team Setup\n\n"
        f"Immediately:\n\n"
        f'1. Create a team: `TeamCreate(team_name="draft-{project}")`\n'
        f"{scout_block}\n\n"
        f"While scouts work in the background, begin your conversation "
        f"with the human. When scout messages arrive, acknowledge them "
        f"and weave their findings into the plan.\n"
        f"{data_note}\n"
        f"If scouts haven't reported within 5 minutes, proceed without "
        f"them.\n\n"
        f"---\n\n"
        f"# Conversation Flow\n\n"
        f"1. Read the skeleton plan and summarise what you understand\n"
        f"2. Ask about the objective — what exactly are we building?\n"
        f"3. Ask about data sources (incorporate Data Scout findings "
        f"when they arrive)\n"
        f"4. Ask about oracle metrics — how do we measure success?\n"
        f"5. Ask about domain context (incorporate Research Scout "
        f"findings when they arrive)\n"
        f"6. Ask about constraints — time, compute, regulatory\n"
        f"7. Fill in each section as you get answers\n"
        f"8. Validate against specs/plan.md schema\n\n"
        f"Write the completed plan to `{plan_path}`.\n\n"
        f"---\n\n"
        f"# Completion\n\n"
        f"When done, ask: 'Anything to adjust? If not, run "
        f"`{build_cmd}` to start building.'\n"
        f"Once confirmed, tell the user to type /exit.\n"
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TARGET_TEMPLATE = """\
---
project: {project_name}
target_repo: {target_repo}
target_branch: {target_branch}
worktree_base: .worktrees
git_author_name: ZO Agent
git_author_email: zo-agent@zero-operators.dev
agent_working_dirs:
  data-engineer: src/data/
  model-builder: src/model/
  ml-engineer: src/engineering/
  inference: src/inference/
  oracle-qa: reports/
  test-engineer: tests/
  xai-agent: reports/
  domain-evaluator: reports/
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

## Environment

Populated by `zo init` from host detection. Review and override where needed
(e.g. pin a specific CUDA version for reproducibility, or set data paths that
live on a remote server).

**Host (where ZO runs):**
- platform: {env_platform}
- python: {env_python}
- docker_available: {env_docker}
- gpu_available: {env_gpu_available}
- gpu_count: {env_gpu_count}
- cuda_version: {env_cuda}

**Training target (where Docker runs the model):**
- gpu_host: {gpu_host}
- base_image: {base_image}
- cuda_version: {train_cuda}

**Data:**
- data_layout: {data_layout}
- data_path: {data_path}
- docker_mounts:
  - host: {data_path}
    container: /project/data

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
