"""Training metrics protocol and callback for Zero Operators.

Provides a lightweight, framework-agnostic callback that training scripts
use to emit structured metrics.  The callback writes JSONL to a known
location so ``zo watch-training`` (and the auto-split tmux pane) can tail
and render a live dashboard.

Two files are produced:

* **metrics.jsonl** — append-only log of every event (epoch ends,
  checkpoint saves, training start/end).  This is the history.
* **training_status.json** — overwritten each epoch with the latest
  snapshot.  This is the "current state" fast-read file.

Usage in a training script::

    from zo.training_metrics import ZOTrainingCallback

    cb = ZOTrainingCallback(
        log_dir="logs/training",
        experiment_id="exp-003",
        experiment_name="ResNet-18 / CIFAR-10",
    )
    cb.on_training_start(total_epochs=100, config={"lr": 3e-4, "batch": 128})

    for epoch in range(100):
        train_loss = train_one_epoch(...)
        val_metrics = validate(...)
        cb.on_epoch_end(
            epoch=epoch,
            total_epochs=100,
            metrics={"train_loss": train_loss, "val_loss": val_metrics["loss"],
                     "val_acc": val_metrics["accuracy"]},
            learning_rate=scheduler.get_last_lr()[0],
        )
        if should_save:
            torch.save(ckpt, path)
            cb.on_checkpoint_saved(path=str(path), epoch=epoch,
                                   metrics={"val_acc": val_metrics["accuracy"]})

    cb.on_training_end(final_metrics={"val_acc": best_acc})
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "ZOTrainingCallback",
    "TrainingMetricsEntry",
    "TrainingStatus",
    "read_training_status",
    "read_metrics_history",
]

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TrainingMetricsEntry:
    """One line in ``metrics.jsonl``."""

    timestamp: str
    event: str  # training_start | epoch_end | checkpoint_saved | training_end
    experiment_id: str
    experiment_name: str
    epoch: int | None = None
    total_epochs: int | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    learning_rate: float | None = None
    checkpoint_path: str | None = None
    wall_time_seconds: float | None = None
    gpu_memory_mb: float | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialise to a single JSON line (no trailing newline)."""
        return json.dumps(asdict(self), default=str)


@dataclass
class TrainingStatus:
    """Current training state, read from ``training_status.json``."""

    experiment_id: str = ""
    experiment_name: str = ""
    epoch: int = 0
    total_epochs: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    best_metrics: dict[str, float] = field(default_factory=dict)
    learning_rate: float | None = None
    wall_time_seconds: float = 0.0
    gpu_memory_mb: float | None = None
    is_training: bool = False
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    metrics_history: list[dict[str, float]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------


class ZOTrainingCallback:
    """Drop-in callback for PyTorch training loops.

    Pure Python, no dependencies beyond stdlib.  Training scripts import
    this and call the ``on_*`` methods at the appropriate points.

    Args:
        log_dir: Directory for ``metrics.jsonl`` and ``training_status.json``.
            Relative to the delivery repo root (e.g. ``"logs/training"``).
        experiment_id: Short identifier, e.g. ``"exp-003"``.
        experiment_name: Human-readable label, e.g. ``"ResNet-18 / CIFAR-10"``.
    """

    def __init__(
        self,
        log_dir: str | Path,
        experiment_id: str,
        experiment_name: str = "",
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._experiment_id = experiment_id
        self._experiment_name = experiment_name or experiment_id

        self._metrics_path = self._log_dir / "metrics.jsonl"
        self._status_path = self._log_dir / "training_status.json"

        self._start_time: float = 0.0
        self._best_metrics: dict[str, float] = {}
        self._checkpoints: list[dict[str, Any]] = []
        self._history: list[dict[str, float]] = []
        self._config: dict[str, Any] = {}

    # --- Public API ---

    def on_training_start(
        self,
        total_epochs: int,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Call before the training loop begins."""
        self._start_time = time.monotonic()
        self._config = config or {}
        entry = TrainingMetricsEntry(
            timestamp=_now_iso(),
            event="training_start",
            experiment_id=self._experiment_id,
            experiment_name=self._experiment_name,
            total_epochs=total_epochs,
            config=self._config,
        )
        self._append(entry)
        self._write_status(epoch=0, total_epochs=total_epochs, metrics={},
                           is_training=True)

    def on_epoch_end(
        self,
        epoch: int,
        total_epochs: int,
        metrics: dict[str, float],
        learning_rate: float | None = None,
        gpu_memory_mb: float | None = None,
    ) -> None:
        """Call after each epoch completes."""
        wall = time.monotonic() - self._start_time if self._start_time else 0.0
        self._update_best(metrics)
        self._history.append({"epoch": epoch, **metrics})

        entry = TrainingMetricsEntry(
            timestamp=_now_iso(),
            event="epoch_end",
            experiment_id=self._experiment_id,
            experiment_name=self._experiment_name,
            epoch=epoch,
            total_epochs=total_epochs,
            metrics=metrics,
            learning_rate=learning_rate,
            wall_time_seconds=round(wall, 1),
            gpu_memory_mb=gpu_memory_mb,
        )
        self._append(entry)
        self._write_status(
            epoch=epoch, total_epochs=total_epochs, metrics=metrics,
            learning_rate=learning_rate, wall_time_seconds=wall,
            gpu_memory_mb=gpu_memory_mb, is_training=True,
        )

    def on_checkpoint_saved(
        self,
        path: str,
        epoch: int,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """Call after a checkpoint is written to disk."""
        ckpt_record = {
            "epoch": epoch,
            "path": path,
            "metrics": metrics or {},
            "timestamp": _now_iso(),
        }
        self._checkpoints.append(ckpt_record)
        # Keep only last 10 checkpoints in memory
        if len(self._checkpoints) > 10:
            self._checkpoints = self._checkpoints[-10:]

        entry = TrainingMetricsEntry(
            timestamp=_now_iso(),
            event="checkpoint_saved",
            experiment_id=self._experiment_id,
            experiment_name=self._experiment_name,
            epoch=epoch,
            metrics=metrics or {},
            checkpoint_path=path,
        )
        self._append(entry)

    def on_training_end(
        self,
        final_metrics: dict[str, float] | None = None,
    ) -> None:
        """Call after training completes."""
        wall = time.monotonic() - self._start_time if self._start_time else 0.0
        entry = TrainingMetricsEntry(
            timestamp=_now_iso(),
            event="training_end",
            experiment_id=self._experiment_id,
            experiment_name=self._experiment_name,
            metrics=final_metrics or {},
            wall_time_seconds=round(wall, 1),
        )
        self._append(entry)
        self._write_status(
            epoch=self._history[-1]["epoch"] if self._history else 0,
            total_epochs=0, metrics=final_metrics or {},
            wall_time_seconds=wall, is_training=False,
        )

    # --- Internals ---

    def _append(self, entry: TrainingMetricsEntry) -> None:
        """Append one JSON line to metrics.jsonl."""
        with open(self._metrics_path, "a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")

    def _write_status(
        self,
        epoch: int,
        total_epochs: int,
        metrics: dict[str, float],
        *,
        learning_rate: float | None = None,
        wall_time_seconds: float = 0.0,
        gpu_memory_mb: float | None = None,
        is_training: bool = True,
    ) -> None:
        """Overwrite training_status.json with current state."""
        # Keep last 30 history entries for sparkline
        recent = self._history[-30:] if self._history else []
        status = TrainingStatus(
            experiment_id=self._experiment_id,
            experiment_name=self._experiment_name,
            epoch=epoch,
            total_epochs=total_epochs,
            metrics=metrics,
            best_metrics=dict(self._best_metrics),
            learning_rate=learning_rate,
            wall_time_seconds=round(wall_time_seconds, 1),
            gpu_memory_mb=gpu_memory_mb,
            is_training=is_training,
            checkpoints=list(self._checkpoints[-5:]),
            metrics_history=recent,
            config=self._config,
        )
        tmp = self._status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(status), default=str), encoding="utf-8")
        tmp.replace(self._status_path)

    def _update_best(self, metrics: dict[str, float]) -> None:
        """Track best value for each metric (lower = better for *loss*)."""
        for key, val in metrics.items():
            is_loss = "loss" in key.lower()
            current_best = self._best_metrics.get(key)
            if (
                current_best is None
                or (is_loss and val < current_best)
                or (not is_loss and val > current_best)
            ):
                self._best_metrics[key] = val


# ---------------------------------------------------------------------------
# Readers — used by the display module
# ---------------------------------------------------------------------------


def read_training_status(log_dir: Path) -> TrainingStatus | None:
    """Read the latest training snapshot from ``training_status.json``.

    Returns ``None`` if the file doesn't exist or is corrupt.
    """
    status_path = log_dir / "training_status.json"
    if not status_path.exists():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        return TrainingStatus(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def read_metrics_history(log_dir: Path) -> list[TrainingMetricsEntry]:
    """Read all entries from ``metrics.jsonl``.

    Returns an empty list if the file doesn't exist.  Silently skips
    malformed lines.
    """
    metrics_path = log_dir / "metrics.jsonl"
    if not metrics_path.exists():
        return []
    entries: list[TrainingMetricsEntry] = []
    try:
        text = metrics_path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entries.append(TrainingMetricsEntry(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()
