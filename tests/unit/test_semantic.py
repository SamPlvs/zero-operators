"""Tests for zo.semantic — the semantic index module.

Tests are split into two groups:

1. Tests that always run (no fastembed/numpy required) — these exercise
   the text-based fallback path, model validation, and SQLite storage.
2. Tests that require fastembed + numpy — these exercise the vector
   embedding path and are skipped when the dependencies are absent.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

from zo._memory_models import Confidence, DecisionEntry, PriorEntry
from zo.semantic import (
    IndexEntry,
    SearchResult,
    SemanticIndex,
    _entry_id_for,
    _extract_summary,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Detect optional dependencies for conditional tests
# ---------------------------------------------------------------------------

_has_fastembed = importlib.util.find_spec("fastembed") is not None
_has_numpy = importlib.util.find_spec("numpy") is not None

needs_fastembed = pytest.mark.skipif(
    not (_has_fastembed and _has_numpy),
    reason="fastembed and/or numpy not installed",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test_index.db"


@pytest.fixture()
def index(db_path: Path) -> SemanticIndex:
    """Create a SemanticIndex with the default model (may or may not load)."""
    idx = SemanticIndex(db_path)
    yield idx
    idx.close()


@pytest.fixture()
def no_embed_index(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> SemanticIndex:
    """Create a SemanticIndex that is forced into text-fallback mode."""
    import zo.semantic as sem_mod

    monkeypatch.setattr(sem_mod, "_HAS_FASTEMBED", False)
    monkeypatch.setattr(sem_mod, "_HAS_NUMPY", False)
    idx = SemanticIndex(db_path)
    yield idx
    idx.close()


@pytest.fixture()
def sample_decisions() -> list[DecisionEntry]:
    """A small set of decision entries for testing."""
    return [
        DecisionEntry(
            title="Use PyTorch for model training",
            context="Evaluating ML frameworks",
            decision="Adopt PyTorch",
            rationale="Team expertise and ecosystem",
            outcome="adopted",
            confidence=Confidence.HIGH,
        ),
        DecisionEntry(
            title="Feature selection approach",
            context="Need to reduce dimensionality",
            decision="Use mutual information",
            rationale="Works with mixed feature types",
            outcome="implemented",
            confidence=Confidence.MEDIUM,
        ),
        DecisionEntry(
            title="Deployment strategy",
            context="Choosing between k8s and lambda",
            decision="Use Kubernetes",
            rationale="Long-running workloads",
            outcome="pending",
            confidence=Confidence.LOW,
        ),
    ]


@pytest.fixture()
def sample_priors() -> list[PriorEntry]:
    """A small set of prior entries for testing."""
    return [
        PriorEntry(
            category="ml",
            statement="Batch normalization improves training stability",
            evidence="Observed during experiment 3",
            confidence=Confidence.HIGH,
        ),
        PriorEntry(
            category="infra",
            statement="Pod memory limits should be 2x average usage",
            evidence="OOM incidents in staging",
            confidence=Confidence.MEDIUM,
        ),
    ]


# ===================================================================
# Model tests (always run)
# ===================================================================


class TestModels:
    """Test IndexEntry and SearchResult pydantic models."""

    def test_index_entry_required_fields(self) -> None:
        entry = IndexEntry(
            entry_id="abc123",
            summary="test summary",
            full_text="full text here",
            source="decision",
        )
        assert entry.entry_id == "abc123"
        assert entry.source == "decision"
        # timestamp should be auto-set
        assert entry.timestamp

    def test_index_entry_custom_timestamp(self) -> None:
        ts = "2026-04-09T10:00:00+00:00"
        entry = IndexEntry(
            entry_id="x",
            summary="s",
            full_text="f",
            source="prior",
            timestamp=ts,
        )
        assert entry.timestamp == ts

    def test_search_result(self) -> None:
        entry = IndexEntry(
            entry_id="a",
            summary="s",
            full_text="f",
            source="session",
        )
        result = SearchResult(entry=entry, score=0.87)
        assert result.score == pytest.approx(0.87)
        assert result.entry.entry_id == "a"


# ===================================================================
# Helper function tests
# ===================================================================


class TestHelpers:
    """Test pure helper functions."""

    def test_extract_summary_with_outcome(self) -> None:
        d = DecisionEntry(title="Use Redis", outcome="adopted")
        assert _extract_summary(d) == "Use Redis → adopted"

    def test_extract_summary_pending(self) -> None:
        d = DecisionEntry(title="Use Redis", outcome="pending")
        assert _extract_summary(d) == "Use Redis"

    def test_extract_summary_empty_outcome(self) -> None:
        d = DecisionEntry(title="Use Redis", outcome="")
        assert _extract_summary(d) == "Use Redis"

    def test_entry_id_deterministic(self) -> None:
        id1 = _entry_id_for("decision", "hello")
        id2 = _entry_id_for("decision", "hello")
        assert id1 == id2

    def test_entry_id_differs_by_source(self) -> None:
        id1 = _entry_id_for("decision", "hello")
        id2 = _entry_id_for("prior", "hello")
        assert id1 != id2


# ===================================================================
# Index creation and SQLite storage tests (always run)
# ===================================================================


class TestIndexCreation:
    """Test index creation and SQLite file handling."""

    def test_creates_db_file(self, db_path: Path) -> None:
        idx = SemanticIndex(db_path)
        assert db_path.exists()
        idx.close()

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "index.db"
        idx = SemanticIndex(deep_path)
        assert deep_path.exists()
        idx.close()

    def test_empty_index_count(self, index: SemanticIndex) -> None:
        assert index.count() == 0

    def test_empty_index_query(self, index: SemanticIndex) -> None:
        results = index.query("anything")
        assert results == []


# ===================================================================
# Text-fallback tests (always run, forced no-embed)
# ===================================================================


class TestTextFallback:
    """Test the substring-matching fallback (no fastembed)."""

    def test_no_embedder_loaded(self, no_embed_index: SemanticIndex) -> None:
        assert not no_embed_index.has_embeddings

    def test_index_and_retrieve_entry(
        self, no_embed_index: SemanticIndex
    ) -> None:
        entry = IndexEntry(
            entry_id="e1",
            summary="feature selection approach",
            full_text="Decided to use mutual information for feature selection",
            source="decision",
        )
        no_embed_index.index_entry(entry)
        assert no_embed_index.count() == 1

        results = no_embed_index.query("feature selection")
        assert len(results) == 1
        assert results[0].entry.entry_id == "e1"
        assert results[0].score > 0

    def test_query_no_match(self, no_embed_index: SemanticIndex) -> None:
        entry = IndexEntry(
            entry_id="e1",
            summary="database migration strategy",
            full_text="Decided to use Alembic",
            source="decision",
        )
        no_embed_index.index_entry(entry)
        results = no_embed_index.query("kubernetes deployment")
        assert len(results) == 0

    def test_query_ranking(self, no_embed_index: SemanticIndex) -> None:
        """Entries with more matching words should rank higher."""
        entries = [
            IndexEntry(
                entry_id="e1",
                summary="feature selection using mutual information",
                full_text="f1",
                source="decision",
            ),
            IndexEntry(
                entry_id="e2",
                summary="feature engineering pipeline",
                full_text="f2",
                source="decision",
            ),
        ]
        for e in entries:
            no_embed_index.index_entry(e)

        results = no_embed_index.query("feature selection")
        assert len(results) == 2
        # e1 matches both "feature" and "selection", e2 matches only "feature"
        assert results[0].entry.entry_id == "e1"
        assert results[0].score > results[1].score

    def test_top_k_limits_results(
        self, no_embed_index: SemanticIndex
    ) -> None:
        for i in range(10):
            no_embed_index.index_entry(
                IndexEntry(
                    entry_id=f"e{i}",
                    summary=f"test entry {i}",
                    full_text=f"full {i}",
                    source="decision",
                )
            )
        results = no_embed_index.query("test entry", top_k=3)
        assert len(results) == 3

    def test_index_decisions(
        self,
        no_embed_index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
    ) -> None:
        no_embed_index.index_decisions(sample_decisions)
        assert no_embed_index.count() == 3

        results = no_embed_index.query("feature selection")
        assert len(results) >= 1
        # The feature selection decision should be found
        summaries = [r.entry.summary for r in results]
        assert any("feature selection" in s.lower() for s in summaries)

    def test_index_decisions_summary_extraction(
        self,
        no_embed_index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
    ) -> None:
        """Verify that outcome is included in summary when not pending."""
        no_embed_index.index_decisions(sample_decisions)
        rows = no_embed_index._conn.execute(
            "SELECT summary FROM entries WHERE source='decision'"
        ).fetchall()
        summaries = [r[0] for r in rows]

        # "adopted" should appear in PyTorch decision summary
        assert any("adopted" in s for s in summaries)
        # "pending" should NOT appear in deployment decision summary
        assert not any("pending" in s for s in summaries)

    def test_index_priors(
        self,
        no_embed_index: SemanticIndex,
        sample_priors: list[PriorEntry],
    ) -> None:
        no_embed_index.index_priors(sample_priors)
        assert no_embed_index.count() == 2

        results = no_embed_index.query("batch normalization")
        assert len(results) >= 1
        assert "batch normalization" in results[0].entry.summary.lower()

    def test_index_priors_uses_statement(
        self,
        no_embed_index: SemanticIndex,
        sample_priors: list[PriorEntry],
    ) -> None:
        """Priors should use the statement field as the summary."""
        no_embed_index.index_priors(sample_priors)
        rows = no_embed_index._conn.execute(
            "SELECT summary FROM entries WHERE source='prior'"
        ).fetchall()
        statements = {p.statement for p in sample_priors}
        for row in rows:
            assert row[0] in statements

    def test_rebuild_index(
        self,
        no_embed_index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
        sample_priors: list[PriorEntry],
    ) -> None:
        # Add some initial data
        no_embed_index.index_entry(
            IndexEntry(
                entry_id="stale",
                summary="old stuff",
                full_text="old",
                source="decision",
            )
        )
        assert no_embed_index.count() == 1

        # Rebuild should clear and re-index
        no_embed_index.rebuild_index(sample_decisions, sample_priors)
        assert no_embed_index.count() == len(sample_decisions) + len(sample_priors)

        # Old entry should be gone
        rows = no_embed_index._conn.execute(
            "SELECT 1 FROM entries WHERE entry_id='stale'"
        ).fetchall()
        assert len(rows) == 0

    def test_clear(self, no_embed_index: SemanticIndex) -> None:
        no_embed_index.index_entry(
            IndexEntry(
                entry_id="x",
                summary="s",
                full_text="f",
                source="decision",
            )
        )
        assert no_embed_index.count() == 1
        no_embed_index.clear()
        assert no_embed_index.count() == 0

    def test_upsert_entry(self, no_embed_index: SemanticIndex) -> None:
        """Inserting with same entry_id should update, not duplicate."""
        entry = IndexEntry(
            entry_id="dup",
            summary="version 1",
            full_text="v1",
            source="decision",
        )
        no_embed_index.index_entry(entry)
        assert no_embed_index.count() == 1

        entry2 = IndexEntry(
            entry_id="dup",
            summary="version 2",
            full_text="v2",
            source="decision",
        )
        no_embed_index.index_entry(entry2)
        assert no_embed_index.count() == 1

        # Should have the updated summary
        row = no_embed_index._conn.execute(
            "SELECT summary FROM entries WHERE entry_id='dup'"
        ).fetchone()
        assert row[0] == "version 2"

    def test_full_text_returned_on_query(
        self, no_embed_index: SemanticIndex
    ) -> None:
        """Query should return the full_text, not just the summary."""
        no_embed_index.index_entry(
            IndexEntry(
                entry_id="e1",
                summary="feature selection",
                full_text=(
                    "Complete decision text with all the details"
                    " about feature selection using MI"
                ),
                source="decision",
            )
        )
        results = no_embed_index.query("feature selection")
        assert "Complete decision text" in results[0].entry.full_text


# ===================================================================
# Embedding-based tests (require fastembed + numpy)
# ===================================================================


@needs_fastembed
class TestSemanticEmbeddings:
    """Tests that exercise the real embedding path."""

    def test_embedder_loaded(self, index: SemanticIndex) -> None:
        assert index.has_embeddings

    def test_semantic_query_relevance(
        self,
        index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
    ) -> None:
        """Semantically similar queries should return relevant results."""
        index.index_decisions(sample_decisions)

        results = index.query("machine learning framework choice")
        assert len(results) >= 1
        # PyTorch decision should appear somewhere in top results
        texts = [r.entry.full_text.lower() for r in results]
        assert any("pytorch" in t for t in texts)

    def test_semantic_scores_are_valid(
        self,
        index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
    ) -> None:
        """Scores should be between 0 and 1."""
        index.index_decisions(sample_decisions)
        results = index.query("deployment")
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_semantic_results_sorted(
        self,
        index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
    ) -> None:
        """Results should be sorted by descending score."""
        index.index_decisions(sample_decisions)
        results = index.query("feature selection method")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_embedding_stored_in_db(self, index: SemanticIndex) -> None:
        """Entries should have non-null embeddings when fastembed is present."""
        index.index_entry(
            IndexEntry(
                entry_id="e1",
                summary="test embedding storage",
                full_text="full",
                source="decision",
            )
        )
        row = index._conn.execute(
            "SELECT embedding FROM entries WHERE entry_id='e1'"
        ).fetchone()
        assert row[0] is not None
        assert len(row[0]) > 0

    def test_rebuild_preserves_embeddings(
        self,
        index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
        sample_priors: list[PriorEntry],
    ) -> None:
        """After rebuild, semantic search should still work."""
        index.rebuild_index(sample_decisions, sample_priors)
        results = index.query("training stability")
        assert len(results) >= 1

    def test_mixed_decisions_and_priors(
        self,
        index: SemanticIndex,
        sample_decisions: list[DecisionEntry],
        sample_priors: list[PriorEntry],
    ) -> None:
        """Query should search across both decisions and priors."""
        index.index_decisions(sample_decisions)
        index.index_priors(sample_priors)
        total = len(sample_decisions) + len(sample_priors)
        assert index.count() == total

        # Query about ML should find both decisions and priors
        results = index.query("machine learning training", top_k=10)
        sources = {r.entry.source for r in results}
        # We expect at least decisions to be found
        assert "decision" in sources
