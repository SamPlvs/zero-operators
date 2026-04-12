"""Rich-based training dashboard renderer for Zero Operators.

Reads from ``training_status.json`` and ``metrics.jsonl`` produced by
:class:`zo.training_metrics.ZOTrainingCallback`, then renders a
persistent, in-place-updating Rich panel.

Used by:

* ``zo watch-training`` CLI command (standalone)
* Auto-split tmux pane during ``zo build`` Phase 4

The public entry point is :func:`run_live_display`, which starts a
``rich.live.Live`` loop refreshing every *interval* seconds.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from zo.training_metrics import TrainingStatus, read_training_status

__all__ = [
    "render_training_panel",
    "run_live_display",
]

# ZO brand colours
_AMBER = "#F0C040"
_DIM = "#8a6020"

# Unicode block characters for sparklines (8 levels)
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------


def _sparkline(values: list[float], width: int = 24) -> str:
    """Render a sequence of floats as a Unicode sparkline.

    Uses the last *width* values.  Returns an empty string if fewer
    than 2 values are available.
    """
    vals = values[-width:]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = hi - lo if hi != lo else 1.0
    return "".join(
        _SPARK_CHARS[min(int((v - lo) / span * 7), 7)] for v in vals
    )


# ---------------------------------------------------------------------------
# Time formatting
# ---------------------------------------------------------------------------


def _fmt_time(seconds: float) -> str:
    """Format seconds as ``Xh Ym Zs`` or ``Ym Zs``."""
    s = int(seconds)
    if s >= 3600:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}h {m}m {sec}s"
    m, sec = divmod(s, 60)
    return f"{m}m {sec}s"


def _eta(status: TrainingStatus) -> str:
    """Estimate time remaining based on wall_time / epochs done."""
    if status.epoch <= 0 or status.total_epochs <= 0:
        return "—"
    done = status.epoch
    remaining = status.total_epochs - done
    if done == 0:
        return "—"
    per_epoch = status.wall_time_seconds / done
    return _fmt_time(per_epoch * remaining)


def _time_ago(ts: str) -> str:
    """Return a human-readable 'Xm ago' string from an ISO timestamp."""
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(ts)
        delta = (datetime.now(UTC) - dt).total_seconds()
        if delta < 60:
            return f"{int(delta)}s ago"
        if delta < 3600:
            return f"{int(delta / 60)}m ago"
        return f"{int(delta / 3600)}h ago"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_training_panel(
    status: TrainingStatus,
    target_metric: float | None = None,
    target_metric_name: str = "",
) -> Panel:
    """Build a Rich Panel showing the current training state.

    Args:
        status: Current training snapshot.
        target_metric: Oracle target threshold (from plan).
        target_metric_name: Name of the primary metric.

    Returns:
        A Rich Panel that can be printed or used in a Live display.
    """
    parts: list[Any] = []

    # --- Header ---
    header = Text()
    header.append("  ", style="bold")
    header.append(status.experiment_name or status.experiment_id, style=f"bold {_AMBER}")
    if status.config:
        model = status.config.get("architecture", status.config.get("model", ""))
        if model:
            header.append(f"  ({model})", style=_DIM)
    parts.append(header)
    parts.append(Text())  # blank line

    # --- Progress bar ---
    if status.total_epochs > 0:
        pct = status.epoch / status.total_epochs
        pbar_text = Text()
        pbar_text.append(
            f"  Epoch {status.epoch}/{status.total_epochs}  ",
            style="bold",
        )
        parts.append(pbar_text)

        pbar = ProgressBar(total=status.total_epochs, completed=status.epoch,
                           width=40, style=_DIM, complete_style=_AMBER,
                           finished_style="green")
        pbar_line = Text()
        pbar_line.append("  ")
        parts.append(pbar_line)
        parts.append(pbar)

        info_line = Text()
        info_line.append(f"  {pct:.0%}", style="bold")
        info_line.append(f"  ETA: {_eta(status)}", style=_DIM)
        if status.wall_time_seconds > 0:
            info_line.append(f"  Elapsed: {_fmt_time(status.wall_time_seconds)}", style=_DIM)
        parts.append(info_line)
        parts.append(Text())

    # --- Metrics table ---
    if status.metrics:
        table = Table(show_header=True, header_style=f"bold {_AMBER}",
                      box=None, padding=(0, 2), show_edge=False)
        table.add_column("Metric", style="bold", min_width=14)
        table.add_column("Current", justify="right", min_width=10)
        table.add_column("Best", justify="right", min_width=10)
        table.add_column("Target", justify="right", min_width=10)

        for key, val in status.metrics.items():
            best = status.best_metrics.get(key)
            best_str = f"{best:.4f}" if best is not None else "—"
            target_str = "—"
            is_target = (
                target_metric is not None
                and target_metric_name
                and key.lower() == target_metric_name.lower()
            )
            if is_target:
                target_str = f"{target_metric:.4f}"
            table.add_row(key, f"{val:.4f}", best_str, target_str)

        if status.learning_rate is not None:
            table.add_row("learning_rate", f"{status.learning_rate:.2e}", "—", "—")
        if status.gpu_memory_mb is not None:
            table.add_row("gpu_mem_mb", f"{status.gpu_memory_mb:.0f}", "—", "—")

        parts.append(table)
        parts.append(Text())

    # --- Loss sparkline ---
    loss_key = _find_loss_key(status.metrics)
    if loss_key and status.metrics_history:
        loss_vals = [
            h[loss_key] for h in status.metrics_history if loss_key in h
        ]
        spark = _sparkline(loss_vals)
        if spark:
            spark_line = Text()
            spark_line.append(f"  {loss_key} ", style=_DIM)
            spark_line.append(spark, style=_AMBER)
            parts.append(spark_line)
            parts.append(Text())

    # --- Checkpoints ---
    if status.checkpoints:
        ckpt_header = Text()
        ckpt_header.append("  Checkpoints:", style=f"bold {_AMBER}")
        parts.append(ckpt_header)
        for ckpt in reversed(status.checkpoints[-5:]):
            ep = ckpt.get("epoch", "?")
            path = ckpt.get("path", "")
            ts = ckpt.get("timestamp", "")
            ckpt_metrics = ckpt.get("metrics", {})
            metric_str = "  ".join(
                f"{k}={v:.4f}" for k, v in ckpt_metrics.items()
            )
            line = Text()
            line.append(f"  \u2713 ep{ep}", style="green")
            if metric_str:
                line.append(f"  {metric_str}", style="bold")
            short_path = Path(path).name if path else ""
            if short_path:
                line.append(f"  {short_path}", style=_DIM)
            ago = _time_ago(ts)
            if ago:
                line.append(f"  {ago}", style=_DIM)
            parts.append(line)

    # --- Status line ---
    status_line = Text()
    state = "Training" if status.is_training else "Completed"
    style = _AMBER if status.is_training else "green"
    status_line.append(f"\n  {state}", style=style)
    if status.wall_time_seconds > 0:
        status_line.append(
            f"  | Total: {_fmt_time(status.wall_time_seconds)}", style=_DIM,
        )
    parts.append(status_line)

    title = f"[{_AMBER}]Training Dashboard[/{_AMBER}]"
    return Panel(
        Group(*parts),
        title=title,
        border_style=_AMBER,
        padding=(0, 1),
    )


def render_waiting_panel() -> Panel:
    """Render a placeholder panel when no training data exists yet."""
    content = Text()
    content.append("\n  Waiting for training to start...\n", style=_DIM)
    content.append("  Metrics will appear when the model-builder\n", style=_DIM)
    content.append("  begins training with ZOTrainingCallback.\n", style=_DIM)
    return Panel(
        content,
        title=f"[{_AMBER}]Training Dashboard[/{_AMBER}]",
        border_style=_DIM,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Live display loop
# ---------------------------------------------------------------------------


def run_live_display(
    log_dir: Path,
    *,
    interval: float = 2.0,
    target_metric: float | None = None,
    target_metric_name: str = "",
) -> None:
    """Start a Rich Live display that refreshes every *interval* seconds.

    Blocks until the training completes or the user presses Ctrl-C.

    Args:
        log_dir: Path to the ``logs/training/`` directory in the delivery repo.
        interval: Refresh interval in seconds.
        target_metric: Oracle target threshold (from plan.md).
        target_metric_name: Name of the primary metric.
    """
    from rich.live import Live

    console = Console()

    with Live(render_waiting_panel(), console=console, refresh_per_second=1) as live:
        try:
            while True:
                status = read_training_status(log_dir)
                if status is None:
                    live.update(render_waiting_panel())
                else:
                    panel = render_training_panel(
                        status,
                        target_metric=target_metric,
                        target_metric_name=target_metric_name,
                    )
                    live.update(panel)
                    if not status.is_training:
                        # Training complete — show final state and exit
                        time.sleep(2)
                        break
                time.sleep(interval)
        except KeyboardInterrupt:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_loss_key(metrics: dict[str, float]) -> str:
    """Find the first key containing 'loss' (case-insensitive)."""
    for key in metrics:
        if "loss" in key.lower():
            return key
    return ""
