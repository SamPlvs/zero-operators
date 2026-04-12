"""Jupyter notebook generator for Zero Operators ML workflow phases.

Generates pre-populated ``.ipynb`` notebooks in the delivery repo's
``notebooks/`` directory after each workflow phase completes.  Notebooks
contain real, runnable code that loads project artefacts (CSVs, JSON
configs, reports) so the user can explore results interactively.

Typical usage::

    from zo.notebooks import generate_phase_notebook
    path = generate_phase_notebook(
        phase_id="1",
        phase_name="Data Review",
        delivery_repo=Path("/tmp/my-project"),
        artifacts=["data/processed/train.csv"],
        phase_summary="Explored raw data and documented quality issues.",
    )
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003, TCH003 — used at runtime

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NB_FORMAT_VERSION = 4
"""Notebook format major version used by *nbformat*."""

_STANDARD_IMPORTS = """\
from pathlib import Path

import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

plt.style.use("seaborn-v0_8-whitegrid")
"""

_PROJECT_ROOT_CELL = 'PROJECT_ROOT = Path("..").resolve()\n'


# ---------------------------------------------------------------------------
# Per-phase cell builders
# ---------------------------------------------------------------------------


def _cells_data_review(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 1: Data Review."""
    csv_path = _first_match(artifacts, ".csv") or "data/processed/train.csv"
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_code_cell(
        f'# Load processed data\n'
        f'try:\n'
        f'    df = pd.read_csv(PROJECT_ROOT / "{csv_path}")\n'
        f'    print("Shape:", df.shape)\n'
        f'    df.head()\n'
        f'except FileNotFoundError:\n'
        f'    print("CSV not found at {csv_path} — run the data pipeline first.")\n'
        f'    df = pd.DataFrame()\n'
    ))
    cells.append(new_code_cell(
        'if not df.empty:\n'
        '    print(df.describe())\n'
    ))
    cells.append(new_code_cell(
        '# Missing-value heatmap\n'
        'if not df.empty:\n'
        '    fig, ax = plt.subplots(figsize=(10, 6))\n'
        '    sns.heatmap(df.isnull(), cbar=True, yticklabels=False, ax=ax)\n'
        '    ax.set_title("Missing Values")\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
    ))
    cells.append(new_code_cell(
        '# Feature distributions\n'
        'if not df.empty:\n'
        '    numeric_cols = df.select_dtypes(include="number").columns[:12]\n'
        '    if len(numeric_cols):\n'
        '        df[numeric_cols].hist(figsize=(12, 8), bins=30)\n'
        '        plt.suptitle("Feature Distributions")\n'
        '        plt.tight_layout()\n'
        '        plt.show()\n'
    ))
    cells.append(new_markdown_cell(
        '## Data Quality\n\n'
        '```python\n'
        '# Load data quality report if available\n'
        'report_path = PROJECT_ROOT / "reports/data_quality_report.md"\n'
        '```\n'
    ))
    cells.append(new_code_cell(
        'report_path = PROJECT_ROOT / "reports/data_quality_report.md"\n'
        'if report_path.exists():\n'
        '    print(report_path.read_text())\n'
        'else:\n'
        '    print("No data quality report found.")\n'
    ))
    return cells


def _cells_feature_engineering(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 2: Feature Engineering."""
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_code_cell(
        '# Load feature selection results\n'
        'feat_path = PROJECT_ROOT / "reports/feature_selection.json"\n'
        'try:\n'
        '    with open(feat_path) as f:\n'
        '        feat_data = json.load(f)\n'
        '    print(json.dumps(feat_data, indent=2))\n'
        'except FileNotFoundError:\n'
        '    feat_data = {}\n'
        '    print("Feature selection report not found.")\n'
    ))
    cells.append(new_code_cell(
        '# Feature importance bar chart\n'
        'if feat_data and "importance" in feat_data:\n'
        '    imp = feat_data["importance"]\n'
        '    names = list(imp.keys())\n'
        '    values = list(imp.values())\n'
        '    fig, ax = plt.subplots(figsize=(10, 6))\n'
        '    ax.barh(names, values)\n'
        '    ax.set_xlabel("Importance")\n'
        '    ax.set_title("Feature Importance")\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
    ))
    cells.append(new_markdown_cell('## Selected Features\n'))
    return cells


def _cells_model_design(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 3: Model Design."""
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_markdown_cell(
        '## Architecture\n\n'
        'Load architecture rationale from reports.\n'
    ))
    cells.append(new_code_cell(
        'arch_path = PROJECT_ROOT / "reports/architecture_rationale.md"\n'
        'if arch_path.exists():\n'
        '    print(arch_path.read_text())\n'
        'else:\n'
        '    print("Architecture rationale not found.")\n'
    ))
    cells.append(new_code_cell(
        '# Print model config\n'
        'config_path = PROJECT_ROOT / "configs/model_config.json"\n'
        'try:\n'
        '    with open(config_path) as f:\n'
        '        config = json.load(f)\n'
        '    print(json.dumps(config, indent=2))\n'
        'except FileNotFoundError:\n'
        '    print("Model config not found.")\n'
    ))
    return cells


def _cells_training(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 4: Training."""
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_code_cell(
        '# Load training logs\n'
        'log_path = PROJECT_ROOT / "logs/training_log.json"\n'
        'try:\n'
        '    with open(log_path) as f:\n'
        '        train_log = json.load(f)\n'
        '    epochs = [e["epoch"] for e in train_log]\n'
        '    train_loss = [e["train_loss"] for e in train_log]\n'
        '    val_loss = [e.get("val_loss") for e in train_log]\n'
        'except (FileNotFoundError, KeyError):\n'
        '    train_log, epochs, train_loss, val_loss = [], [], [], []\n'
        '    print("Training log not found or malformed.")\n'
    ))
    cells.append(new_code_cell(
        '# Loss curves\n'
        'if epochs:\n'
        '    fig, ax = plt.subplots(figsize=(10, 5))\n'
        '    ax.plot(epochs, train_loss, label="Train Loss")\n'
        '    if any(v is not None for v in val_loss):\n'
        '        ax.plot(epochs, val_loss, label="Val Loss")\n'
        '    ax.set_xlabel("Epoch")\n'
        '    ax.set_ylabel("Loss")\n'
        '    ax.set_title("Training Loss Curves")\n'
        '    ax.legend()\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
    ))
    cells.append(new_code_cell(
        '# Learning rate schedule\n'
        'lr_path = PROJECT_ROOT / "logs/lr_schedule.json"\n'
        'try:\n'
        '    with open(lr_path) as f:\n'
        '        lr_data = json.load(f)\n'
        '    fig, ax = plt.subplots(figsize=(10, 4))\n'
        '    ax.plot(lr_data["step"], lr_data["lr"])\n'
        '    ax.set_xlabel("Step")\n'
        '    ax.set_ylabel("Learning Rate")\n'
        '    ax.set_title("LR Schedule")\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
        'except (FileNotFoundError, KeyError):\n'
        '    print("LR schedule not available.")\n'
    ))
    cells.append(new_markdown_cell('## Training Results\n'))
    return cells


def _cells_analysis(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 5: Analysis."""
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_code_cell(
        '# Confusion matrix\n'
        'cm_path = PROJECT_ROOT / "reports/confusion_matrix.json"\n'
        'try:\n'
        '    with open(cm_path) as f:\n'
        '        cm = json.load(f)\n'
        '    import numpy as np\n'
        '    cm_array = np.array(cm["matrix"])\n'
        '    fig, ax = plt.subplots(figsize=(8, 6))\n'
        '    sns.heatmap(cm_array, annot=True, fmt="d", cmap="Blues", ax=ax)\n'
        '    ax.set_xlabel("Predicted")\n'
        '    ax.set_ylabel("Actual")\n'
        '    ax.set_title("Confusion Matrix")\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
        'except (FileNotFoundError, KeyError):\n'
        '    print("Confusion matrix not found.")\n'
    ))
    cells.append(new_code_cell(
        '# Feature importance / SHAP\n'
        'shap_path = PROJECT_ROOT / "reports/feature_importance.json"\n'
        'try:\n'
        '    with open(shap_path) as f:\n'
        '        shap_data = json.load(f)\n'
        '    names = list(shap_data.keys())\n'
        '    vals = list(shap_data.values())\n'
        '    fig, ax = plt.subplots(figsize=(10, 6))\n'
        '    ax.barh(names, vals)\n'
        '    ax.set_xlabel("Importance")\n'
        '    ax.set_title("Feature Importance / SHAP Values")\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
        'except FileNotFoundError:\n'
        '    print("Feature importance data not found.")\n'
    ))
    cells.append(new_markdown_cell('## Analysis Summary\n'))
    return cells


def _cells_packaging(artifacts: list[str]) -> list[nbformat.NotebookNode]:
    """Return cells for Phase 6: Packaging."""
    cells: list[nbformat.NotebookNode] = []

    cells.append(new_markdown_cell(
        '## Model Card\n\n'
        'Load model card from reports.\n'
    ))
    cells.append(new_code_cell(
        'card_path = PROJECT_ROOT / "reports/model_card.md"\n'
        'if card_path.exists():\n'
        '    print(card_path.read_text())\n'
        'else:\n'
        '    print("Model card not found.")\n'
    ))
    cells.append(new_code_cell(
        '# Inference benchmark results\n'
        'bench_path = PROJECT_ROOT / "reports/inference_benchmark.json"\n'
        'try:\n'
        '    with open(bench_path) as f:\n'
        '        bench = json.load(f)\n'
        '    for k, v in bench.items():\n'
        '        print(f"{k}: {v}")\n'
        'except FileNotFoundError:\n'
        '    print("Inference benchmark not found.")\n'
    ))
    return cells


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------

_PHASE_BUILDERS: dict[str, callable] = {
    "1": _cells_data_review,
    "2": _cells_feature_engineering,
    "3": _cells_model_design,
    "4": _cells_training,
    "5": _cells_analysis,
    "6": _cells_packaging,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_match(artifacts: list[str], suffix: str) -> str | None:
    """Return the first artifact path ending with *suffix*, or ``None``."""
    for a in artifacts:
        if a.endswith(suffix):
            return a
    return None


def _build_header_cells(
    phase_id: str,
    phase_name: str,
    phase_summary: str,
) -> list[nbformat.NotebookNode]:
    """Build the three standard header cells present in every notebook."""
    summary_block = f"\n\n{phase_summary}" if phase_summary else ""
    title_cell = new_markdown_cell(
        f"# Phase {phase_id}: {phase_name}{summary_block}\n"
    )
    import_cell = new_code_cell(_STANDARD_IMPORTS)
    root_cell = new_code_cell(_PROJECT_ROOT_CELL)
    return [title_cell, import_cell, root_cell]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_phase_notebook(
    phase_id: str,
    phase_name: str,
    delivery_repo: Path,
    artifacts: list[str],
    phase_summary: str = "",
) -> Path:
    """Generate a Jupyter notebook for a completed workflow phase.

    Creates a ``.ipynb`` file in ``{delivery_repo}/notebooks/`` containing
    pre-populated cells tailored to *phase_id*.  The notebook uses real,
    runnable code that loads project artefacts via relative paths from
    ``PROJECT_ROOT``.

    Args:
        phase_id: Phase number as a string (``"1"`` through ``"6"``).
        phase_name: Human-readable phase name, e.g. ``"Data Review"``.
        delivery_repo: Absolute path to the delivery repository root.
        artifacts: List of artifact paths relative to *delivery_repo*.
        phase_summary: Optional paragraph summarising phase outcomes.

    Returns:
        Absolute path to the generated ``.ipynb`` file.

    Raises:
        ValueError: If *phase_id* is not one of ``"1"`` through ``"6"``.
    """
    if phase_id not in _PHASE_BUILDERS:
        raise ValueError(
            f"Unknown phase_id {phase_id!r}. "
            f"Expected one of {sorted(_PHASE_BUILDERS)}."
        )

    # Header cells (always present)
    cells = _build_header_cells(phase_id, phase_name, phase_summary)

    # Phase-specific cells
    builder = _PHASE_BUILDERS[phase_id]
    cells.extend(builder(artifacts))

    # Assemble notebook
    nb = new_notebook(cells=cells)
    nb.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    # Write to disk
    safe_name = phase_name.lower().replace(" ", "_").replace("&", "and")
    nb_dir = delivery_repo / "notebooks" / "phase"
    nb_dir.mkdir(parents=True, exist_ok=True)
    nb_path = nb_dir / f"phase_{phase_id}_{safe_name}.ipynb"
    with open(nb_path, "w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)

    return nb_path
