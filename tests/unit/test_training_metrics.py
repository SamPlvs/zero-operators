"""Unit tests for zo.training_metrics and zo.training_display."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zo.training_metrics import (
    TrainingMetricsEntry,
    TrainingStatus,
    ZOTrainingCallback,
    read_metrics_history,
    read_training_status,
)

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs" / "training"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def callback(log_dir: Path) -> ZOTrainingCallback:
    return ZOTrainingCallback(
        log_dir=log_dir,
        experiment_id="exp-001",
        experiment_name="TestNet / CIFAR-10",
    )


# ------------------------------------------------------------------ #
# TrainingMetricsEntry
# ------------------------------------------------------------------ #


class TestTrainingMetricsEntry:
    def test_to_json_roundtrip(self) -> None:
        entry = TrainingMetricsEntry(
            timestamp="2026-04-12T10:00:00+00:00",
            event="epoch_end",
            experiment_id="exp-001",
            experiment_name="test",
            epoch=5,
            total_epochs=100,
            metrics={"train_loss": 0.5, "val_loss": 0.6},
            learning_rate=1e-3,
        )
        line = entry.to_json()
        parsed = json.loads(line)
        assert parsed["event"] == "epoch_end"
        assert parsed["epoch"] == 5
        assert parsed["metrics"]["train_loss"] == 0.5

    def test_to_json_minimal(self) -> None:
        entry = TrainingMetricsEntry(
            timestamp="2026-04-12T10:00:00+00:00",
            event="training_start",
            experiment_id="exp-001",
            experiment_name="test",
        )
        parsed = json.loads(entry.to_json())
        assert parsed["epoch"] is None
        assert parsed["metrics"] == {}


# ------------------------------------------------------------------ #
# ZOTrainingCallback
# ------------------------------------------------------------------ #


class TestZOTrainingCallback:
    def test_training_start_creates_files(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        callback.on_training_start(total_epochs=10, config={"lr": 1e-3})

        assert (log_dir / "metrics.jsonl").exists()
        assert (log_dir / "training_status.json").exists()

        status = read_training_status(log_dir)
        assert status is not None
        assert status.total_epochs == 10
        assert status.is_training is True

    def test_epoch_end_appends_metrics(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        callback.on_training_start(total_epochs=5)
        callback.on_epoch_end(
            epoch=0, total_epochs=5,
            metrics={"train_loss": 0.9, "val_loss": 0.95},
            learning_rate=1e-3,
        )
        callback.on_epoch_end(
            epoch=1, total_epochs=5,
            metrics={"train_loss": 0.7, "val_loss": 0.8},
            learning_rate=1e-3,
        )

        history = read_metrics_history(log_dir)
        epoch_entries = [e for e in history if e.event == "epoch_end"]
        assert len(epoch_entries) == 2
        assert epoch_entries[0].epoch == 0
        assert epoch_entries[1].metrics["train_loss"] == 0.7

    def test_best_metrics_tracked(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        callback.on_training_start(total_epochs=3)
        callback.on_epoch_end(0, 3, {"train_loss": 0.9, "val_acc": 0.6})
        callback.on_epoch_end(1, 3, {"train_loss": 0.5, "val_acc": 0.8})
        callback.on_epoch_end(2, 3, {"train_loss": 0.7, "val_acc": 0.75})

        status = read_training_status(log_dir)
        assert status is not None
        # Best loss is lowest
        assert status.best_metrics["train_loss"] == 0.5
        # Best accuracy is highest
        assert status.best_metrics["val_acc"] == 0.8

    def test_checkpoint_saved(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        callback.on_training_start(total_epochs=10)
        callback.on_epoch_end(5, 10, {"val_acc": 0.85})
        callback.on_checkpoint_saved(
            path="models/ckpt/epoch_5.pt",
            epoch=5,
            metrics={"val_acc": 0.85},
        )

        history = read_metrics_history(log_dir)
        ckpt_entries = [e for e in history if e.event == "checkpoint_saved"]
        assert len(ckpt_entries) == 1
        assert ckpt_entries[0].checkpoint_path == "models/ckpt/epoch_5.pt"
        assert ckpt_entries[0].metrics["val_acc"] == 0.85

    def test_training_end_marks_complete(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        callback.on_training_start(total_epochs=2)
        callback.on_epoch_end(0, 2, {"loss": 0.5})
        callback.on_epoch_end(1, 2, {"loss": 0.3})
        callback.on_training_end(final_metrics={"loss": 0.3, "acc": 0.92})

        status = read_training_status(log_dir)
        assert status is not None
        assert status.is_training is False

    def test_full_roundtrip(self, callback: ZOTrainingCallback, log_dir: Path) -> None:
        """Simulate a full training run and verify all data is readable."""
        callback.on_training_start(total_epochs=5, config={"lr": 1e-3, "architecture": "ResNet"})

        for epoch in range(5):
            loss = 1.0 - epoch * 0.15
            callback.on_epoch_end(
                epoch=epoch, total_epochs=5,
                metrics={"train_loss": loss, "val_loss": loss + 0.05},
                learning_rate=1e-3 * (0.9 ** epoch),
            )
            if epoch % 2 == 0:
                callback.on_checkpoint_saved(
                    path=f"models/ckpt/ep{epoch}.pt",
                    epoch=epoch,
                    metrics={"val_loss": loss + 0.05},
                )

        callback.on_training_end(final_metrics={"val_loss": 0.45})

        # Verify JSONL
        history = read_metrics_history(log_dir)
        assert len(history) == 1 + 5 + 3 + 1  # start + 5 epochs + 3 ckpts + end
        assert history[0].event == "training_start"
        assert history[-1].event == "training_end"

        # Verify status snapshot
        status = read_training_status(log_dir)
        assert status is not None
        assert status.is_training is False
        assert status.experiment_name == "TestNet / CIFAR-10"
        assert len(status.checkpoints) == 3
        assert len(status.metrics_history) == 5
        assert status.config["architecture"] == "ResNet"

    def test_creates_log_dir(self, tmp_path: Path) -> None:
        """Callback creates the log directory if it doesn't exist."""
        new_dir = tmp_path / "deep" / "nested" / "training"
        cb = ZOTrainingCallback(log_dir=new_dir, experiment_id="e1")
        cb.on_training_start(total_epochs=1)
        assert (new_dir / "metrics.jsonl").exists()


class TestForExperimentFactory:
    """Tests for ZOTrainingCallback.for_experiment — the experiment-dir factory."""

    def test_log_dir_is_registry_over_exp_id(self, tmp_path: Path) -> None:
        cb = ZOTrainingCallback.for_experiment(
            registry_dir=tmp_path / ".zo" / "experiments",
            experiment_id="exp-007",
            experiment_name="TFT baseline",
        )
        cb.on_training_start(total_epochs=1)
        assert (tmp_path / ".zo" / "experiments" / "exp-007" / "metrics.jsonl").exists()

    def test_experiment_id_propagates(self, tmp_path: Path) -> None:
        cb = ZOTrainingCallback.for_experiment(
            registry_dir=tmp_path, experiment_id="exp-007",
        )
        cb.on_training_start(total_epochs=1)
        history = read_metrics_history(tmp_path / "exp-007")
        assert history[0].experiment_id == "exp-007"

    def test_name_defaults_to_id_when_empty(self, tmp_path: Path) -> None:
        cb = ZOTrainingCallback.for_experiment(
            registry_dir=tmp_path, experiment_id="exp-007",
        )
        cb.on_training_start(total_epochs=1)
        history = read_metrics_history(tmp_path / "exp-007")
        assert history[0].experiment_name == "exp-007"


# ------------------------------------------------------------------ #
# Readers
# ------------------------------------------------------------------ #


class TestReaders:
    def test_read_status_missing_file(self, tmp_path: Path) -> None:
        assert read_training_status(tmp_path) is None

    def test_read_status_corrupt_file(self, log_dir: Path) -> None:
        (log_dir / "training_status.json").write_text("not json", encoding="utf-8")
        assert read_training_status(log_dir) is None

    def test_read_history_missing_file(self, tmp_path: Path) -> None:
        assert read_metrics_history(tmp_path) == []

    def test_read_history_skips_bad_lines(self, log_dir: Path) -> None:
        content = (
            '{"timestamp":"t","event":"epoch_end","experiment_id":"e","experiment_name":"n","epoch":1}\n'
            "bad line\n"
            '{"timestamp":"t","event":"epoch_end","experiment_id":"e","experiment_name":"n","epoch":2}\n'
        )
        (log_dir / "metrics.jsonl").write_text(content, encoding="utf-8")
        entries = read_metrics_history(log_dir)
        assert len(entries) == 2


# ------------------------------------------------------------------ #
# Display renderer
# ------------------------------------------------------------------ #


class TestTrainingDisplay:
    def test_render_waiting_panel(self) -> None:
        from zo.training_display import render_waiting_panel

        panel = render_waiting_panel()
        assert panel is not None
        assert "Training Dashboard" in str(panel.title)

    def test_render_training_panel(self) -> None:
        from zo.training_display import render_training_panel

        status = TrainingStatus(
            experiment_id="exp-001",
            experiment_name="TestNet",
            epoch=10,
            total_epochs=50,
            metrics={"train_loss": 0.3, "val_loss": 0.35, "val_acc": 0.88},
            best_metrics={"train_loss": 0.25, "val_loss": 0.32, "val_acc": 0.90},
            learning_rate=1e-3,
            wall_time_seconds=120.0,
            is_training=True,
            checkpoints=[
                {"epoch": 5, "path": "ckpt/ep5.pt", "metrics": {"val_acc": 0.85},
                 "timestamp": "2026-04-12T10:00:00+00:00"},
            ],
            metrics_history=[
                {"epoch": i, "train_loss": 1.0 - i * 0.07} for i in range(10)
            ],
        )
        panel = render_training_panel(status, target_metric=0.95, target_metric_name="val_acc")
        assert panel is not None

    def test_render_completed_training(self) -> None:
        from zo.training_display import render_training_panel

        status = TrainingStatus(
            experiment_id="exp-002",
            experiment_name="Done",
            epoch=100,
            total_epochs=100,
            metrics={"val_acc": 0.95},
            best_metrics={"val_acc": 0.95},
            is_training=False,
            wall_time_seconds=3600.0,
        )
        panel = render_training_panel(status)
        assert panel is not None

    def test_sparkline(self) -> None:
        from zo.training_display import _sparkline

        assert _sparkline([]) == ""
        assert _sparkline([1.0]) == ""
        result = _sparkline([1.0, 0.5, 0.3, 0.1])
        assert len(result) == 4
        # First value (highest) should be the tallest bar
        assert result[0] == "\u2588"  # full block
