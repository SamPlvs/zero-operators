"""Build the prompt + launch parameters for a ``zo report`` surrogate session.

The report session is a *non-orchestrating* Opus lead that verifies the
project's data/work/results and writes the LaTeX report, running concurrently
with the primary model session. It reads canonical context as a snapshot and
live experiment results from disk, writes artifacts to its own worktree branch,
and records its memory to the surrogate delta store — all of which consolidate
back when sessions close (see :mod:`zo.surrogate` and :mod:`zo.consolidate`).
"""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from zo.memory import MemoryManager
    from zo.surrogate import SurrogateLayout

__all__ = ["DEFAULT_REPORT_OBJECTIVE", "build_report_prompt", "report_add_dirs"]

DEFAULT_REPORT_OBJECTIVE = (
    "Verify the project's data, completed work, and results, then write and "
    "update the LaTeX report to reflect the current, verified state."
)


def report_add_dirs(surrogate: SurrogateLayout, main_delivery: Path) -> list[str]:
    """Directories the report lead needs ``--add-dir`` access to.

    The worktree (to write ``paper/`` on the report branch) and the main
    delivery repo (to read the live experiment results the primary session is
    still producing).
    """
    return [str(surrogate.worktree), str(main_delivery)]


def _memory_snapshot(canonical: MemoryManager) -> str:
    """Render a read-only snapshot of canonical priors + recent decisions."""
    lines: list[str] = []
    priors = [p for p in canonical.read_priors() if p.superseded_by is None]
    if priors:
        lines.append("**Project priors (accumulated learnings — honor these):**")
        for p in priors[:8]:
            evidence = f" — _{p.evidence}_" if p.evidence else ""
            lines.append(f"- ({p.category}) {p.statement}{evidence}")
    decisions = canonical.read_decisions()
    if decisions:
        lines.append("\n**Recent project decisions:**")
        lines.extend(f"- {d.title}" for d in decisions[-6:])
    if not lines:
        lines.append("_(canonical memory is empty — fresh project)_")
    return "\n".join(lines)


def build_report_prompt(
    *,
    project_name: str,
    surrogate: SurrogateLayout,
    canonical_memory: MemoryManager,
    main_delivery: Path,
    objective: str | None = None,
    paper_dir: str = "paper",
) -> str:
    """Assemble the Opus report-lead prompt for a surrogate session."""
    objective = objective or DEFAULT_REPORT_OBJECTIVE
    snapshot = _memory_snapshot(canonical_memory)
    wt = surrogate.worktree
    canon_mem = main_delivery / ".zo" / "memory"
    experiments = main_delivery / ".zo" / "experiments"
    s_mem = surrogate.memory_root

    return dedent(f"""\
        # Zero Operators — Report Session ({project_name})

        You are the **Report Lead** (Opus). This is a *surrogate* session running
        ALONGSIDE the primary model session on the same project. Your job is to
        verify and write the report — NOT to orchestrate phases or training.

        ## Mission

        {objective}

        ## Context snapshot (read-only)

        {snapshot}

        ## What to read (LIVE — the model session is still producing these)

        - **Experiment results / metrics:** `{experiments}/` — read every active
          and completed experiment's `result.md`, `metrics.jsonl`,
          `training_status.json`, and `diagnosis.md`.
        - **Canonical narrative for reference only:** `{canon_mem}/` — READ ONLY.
          Never write here; the primary session owns it.
        - The delivery repo's `reports/`, `src/`, configs, and STRUCTURE.md.

        ## Where to write

        - **The report (LaTeX):** `{wt}/{paper_dir}/` — your isolated worktree on
          branch `{surrogate.branch}`. Write/update `.tex`, figures, and
          `references.bib` here, and commit as you go.
        - **Your memory (deltas only):** `{s_mem}/`
          - Append decisions to `{s_mem}/DECISION_LOG.md`, **matching the exact
            entry format** of `{canon_mem}/DECISION_LOG.md`.
          - Append durable learnings to `{s_mem}/PRIORS.md`, matching the format
            of `{canon_mem}/PRIORS.md`.
          - ALWAYS write a final session summary under `{s_mem}/sessions/` — this
            is the guaranteed record that consolidates back.

        ## Team (reuse existing agents — Opus for the writing)

        - Use **TeamCreate** to start a report team.
        - Spawn **oracle-qa** to re-verify results against the experiment
          artifacts above: recompute/confirm the headline metrics and flag any
          claim the artifacts do not support.
        - Spawn **data-engineer** to re-verify the data lineage and quality
          behind those results.
        - Report writing is complex synthesis — do it yourself (you are Opus), or
          spawn **documentation-agent with `model="opus"`** as a dedicated
          writer. **Never** use a Haiku model for report prose.
        - Agents coordinate peer-to-peer via **SendMessage**. Verify FIRST, then
          write only the claims the verification supports.

        ## Hard boundaries (non-orchestrating session)

        - Do **NOT** write `{canon_mem}/` (STATE.md / DECISION_LOG.md /
          PRIORS.md). Read only.
        - Do **NOT** mutate `{experiments}/` — no minting or updating experiment
          status. Read only.
        - Do **NOT** advance phases, hold gates, or run training.
        - Your decisions, priors, summary, and report consolidate back into the
          canonical project automatically when sessions close (or via
          `zo consolidate`). Work entirely within the paths above.
        """)
