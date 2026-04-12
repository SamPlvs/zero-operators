"""Unit tests for zo.notebooks — Jupyter notebook generator."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime in fixtures

import nbformat
import pytest

from zo.notebooks import generate_phase_notebook

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def delivery_repo(tmp_path: Path) -> Path:
    """Return a temporary delivery repo directory."""
    return tmp_path / "delivery"


# ---------------------------------------------------------------------------
# Phase definitions used across tests
# ---------------------------------------------------------------------------

PHASES = [
    ("1", "Data Review"),
    ("2", "Feature Engineering"),
    ("3", "Model Design"),
    ("4", "Training"),
    ("5", "Analysis"),
    ("6", "Packaging"),
]

# Minimum expected cell counts per phase:
#   3 header cells (title markdown, imports code, project-root code)
#   + phase-specific cells
EXPECTED_MIN_CELLS = {
    "1": 3 + 6,   # load, describe, heatmap, histogram, quality md, quality code
    "2": 3 + 3,   # load feat, bar chart, markdown
    "3": 3 + 3,   # arch markdown, arch code, config code
    "4": 3 + 4,   # load logs, loss curves, lr schedule, results markdown
    "5": 3 + 3,   # confusion matrix, shap, summary markdown
    "6": 3 + 3,   # model card markdown, card code, benchmark code
}


# ---------------------------------------------------------------------------
# Generation and validation for every phase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase_id, phase_name", PHASES)
def test_generates_valid_notebook(
    delivery_repo: Path,
    phase_id: str,
    phase_name: str,
) -> None:
    """Each phase produces a valid nbformat v4 notebook file."""
    path = generate_phase_notebook(
        phase_id=phase_id,
        phase_name=phase_name,
        delivery_repo=delivery_repo,
        artifacts=[],
        phase_summary="Test summary.",
    )

    assert path.exists()
    assert path.suffix == ".ipynb"

    # Validate with nbformat (raises on invalid notebook)
    nb = nbformat.read(str(path), as_version=4)
    nbformat.validate(nb)


@pytest.mark.parametrize("phase_id, phase_name", PHASES)
def test_cell_count(
    delivery_repo: Path,
    phase_id: str,
    phase_name: str,
) -> None:
    """Each phase notebook has at least the expected number of cells."""
    path = generate_phase_notebook(
        phase_id=phase_id,
        phase_name=phase_name,
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    nb = nbformat.read(str(path), as_version=4)
    assert len(nb.cells) >= EXPECTED_MIN_CELLS[phase_id]


@pytest.mark.parametrize("phase_id, phase_name", PHASES)
def test_cell_types(
    delivery_repo: Path,
    phase_id: str,
    phase_name: str,
) -> None:
    """Header cells have the correct types: markdown, code, code."""
    path = generate_phase_notebook(
        phase_id=phase_id,
        phase_name=phase_name,
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    nb = nbformat.read(str(path), as_version=4)

    assert nb.cells[0].cell_type == "markdown", "First cell must be markdown title"
    assert nb.cells[1].cell_type == "code", "Second cell must be code imports"
    assert nb.cells[2].cell_type == "code", "Third cell must be PROJECT_ROOT"


# ---------------------------------------------------------------------------
# Header content
# ---------------------------------------------------------------------------


def test_title_contains_phase_info(delivery_repo: Path) -> None:
    """Title markdown cell includes phase number and name."""
    path = generate_phase_notebook(
        phase_id="1",
        phase_name="Data Review",
        delivery_repo=delivery_repo,
        artifacts=[],
        phase_summary="Quality looks good.",
    )
    nb = nbformat.read(str(path), as_version=4)
    title_src = nb.cells[0].source

    assert "Phase 1" in title_src
    assert "Data Review" in title_src
    assert "Quality looks good." in title_src


def test_imports_cell_content(delivery_repo: Path) -> None:
    """Imports cell contains the standard library imports."""
    path = generate_phase_notebook(
        phase_id="2",
        phase_name="Feature Engineering",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    nb = nbformat.read(str(path), as_version=4)
    imports_src = nb.cells[1].source

    assert "import pandas as pd" in imports_src
    assert "import matplotlib.pyplot as plt" in imports_src
    assert "import seaborn as sns" in imports_src


def test_project_root_cell(delivery_repo: Path) -> None:
    """PROJECT_ROOT cell sets the project root via relative path."""
    path = generate_phase_notebook(
        phase_id="3",
        phase_name="Model Design",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    nb = nbformat.read(str(path), as_version=4)
    root_src = nb.cells[2].source

    assert "PROJECT_ROOT" in root_src
    assert 'Path("..")' in root_src


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------


def test_output_path_structure(delivery_repo: Path) -> None:
    """Notebook is written to notebooks/ with the correct filename."""
    path = generate_phase_notebook(
        phase_id="4",
        phase_name="Training",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    assert path.parent.name == "phase"
    assert path.parent.parent.name == "notebooks"
    assert path.name == "phase_4_training.ipynb"


def test_ampersand_in_name(delivery_repo: Path) -> None:
    """Phase names with '&' are sanitised to 'and' in the filename."""
    path = generate_phase_notebook(
        phase_id="2",
        phase_name="Feature Engineering & Selection",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    assert "and" in path.stem
    assert "&" not in path.stem


# ---------------------------------------------------------------------------
# Artifacts influence cells
# ---------------------------------------------------------------------------


def test_data_review_uses_artifact_csv(delivery_repo: Path) -> None:
    """Phase 1 notebook references the CSV artifact path when provided."""
    path = generate_phase_notebook(
        phase_id="1",
        phase_name="Data Review",
        delivery_repo=delivery_repo,
        artifacts=["data/processed/features.csv"],
    )
    nb = nbformat.read(str(path), as_version=4)
    # The load cell should reference the provided CSV
    load_cell = nb.cells[3].source
    assert "features.csv" in load_cell


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_invalid_phase_raises(delivery_repo: Path) -> None:
    """An unknown phase_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown phase_id"):
        generate_phase_notebook(
            phase_id="99",
            phase_name="Bogus",
            delivery_repo=delivery_repo,
            artifacts=[],
        )


# ---------------------------------------------------------------------------
# Notebook directory creation
# ---------------------------------------------------------------------------


def test_creates_notebooks_directory(delivery_repo: Path) -> None:
    """The notebooks/phase/ subdirectory is created automatically."""
    assert not (delivery_repo / "notebooks" / "phase").exists()
    generate_phase_notebook(
        phase_id="6",
        phase_name="Packaging",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    assert (delivery_repo / "notebooks" / "phase").is_dir()


# ---------------------------------------------------------------------------
# Kernel metadata
# ---------------------------------------------------------------------------


def test_kernel_metadata(delivery_repo: Path) -> None:
    """Notebook metadata includes a Python 3 kernelspec."""
    path = generate_phase_notebook(
        phase_id="5",
        phase_name="Analysis",
        delivery_repo=delivery_repo,
        artifacts=[],
    )
    nb = nbformat.read(str(path), as_version=4)
    assert nb.metadata.kernelspec["name"] == "python3"
    assert nb.metadata.kernelspec["language"] == "python"
