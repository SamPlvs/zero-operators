"""Semantic index for Zero Operators memory layer.

Provides embedding-based search over DECISION_LOG entries, PRIORS, and
session summaries so the orchestrator can ask natural-language questions
like "What did we decide about feature selection?" and retrieve the most
relevant entries.

Storage is SQLite (stdlib).  Embeddings come from ``fastembed`` which is
an *optional* dependency — when missing the index degrades gracefully to
substring matching.

Typical usage::

    from zo.semantic import SemanticIndex
    idx = SemanticIndex(db_path=Path("memory/alpha/index.db"))
    idx.index_decisions(decisions)
    results = idx.query("feature selection approach")
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from zo._memory_models import DecisionEntry, PriorEntry  # noqa: TC001

__all__ = [
    "IndexEntry",
    "SearchResult",
    "SemanticIndex",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False
    np = None  # type: ignore[assignment]

try:
    from fastembed import TextEmbedding  # type: ignore[import-untyped]

    _HAS_FASTEMBED = True
except ImportError:
    _HAS_FASTEMBED = False
    TextEmbedding = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class IndexEntry(BaseModel):
    """A single indexed item in the semantic search database."""

    entry_id: str = Field(description="Unique ID (e.g. decision title hash)")
    summary: str = Field(description="1-line summary (embedded for matching)")
    full_text: str = Field(description="Complete entry text (returned on retrieval)")
    source: str = Field(description="'decision' | 'prior' | 'session'")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="When the entry was created",
    )


class SearchResult(BaseModel):
    """A search result with relevance score."""

    entry: IndexEntry
    score: float = Field(description="Cosine similarity score (0-1)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    entry_id   TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    full_text  TEXT NOT NULL,
    source     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    embedding  BLOB
)
"""


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Cosine similarity in [0, 1] (clamped; embeddings are typically
        positive so negative values are rare but we protect anyway).
    """
    dot = float(np.dot(a, b))
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return max(0.0, dot / denom)


def _extract_summary(decision: DecisionEntry) -> str:
    """Extract a 1-line summary from a decision's title and outcome.

    Args:
        decision: The decision log entry.

    Returns:
        A concise summary string suitable for embedding.
    """
    parts = [decision.title]
    if decision.outcome and decision.outcome != "pending":
        parts.append(f"→ {decision.outcome}")
    return " ".join(parts)


def _entry_id_for(source: str, text: str) -> str:
    """Deterministic entry ID from source type and text content.

    Args:
        source: Entry source type (decision, prior, session).
        text: Text to hash.

    Returns:
        A stable hex ID.
    """
    raw = f"{source}:{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _embedding_to_bytes(embedding: np.ndarray) -> bytes:
    """Serialize a numpy array to bytes for SQLite storage."""
    return embedding.astype(np.float32).tobytes()


def _bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize bytes back to a numpy float32 array."""
    return np.frombuffer(data, dtype=np.float32).copy()


# ---------------------------------------------------------------------------
# SemanticIndex
# ---------------------------------------------------------------------------


class SemanticIndex:
    """Lightweight embedding-based search over ZO memory documents.

    Uses SQLite for storage and ``fastembed`` for embeddings.  When
    fastembed is not installed the index still stores entries and falls
    back to substring matching on the summary field.

    Args:
        db_path: Path to the SQLite database file.
        model_name: fastembed model identifier.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        self._db_path = Path(db_path)
        self._model_name = model_name
        self._embedder: TextEmbedding | None = None  # type: ignore[type-arg]

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

        # Try loading the embedding model
        if _HAS_FASTEMBED and _HAS_NUMPY:
            try:
                self._embedder = TextEmbedding(model_name=model_name)
                logger.debug("Loaded fastembed model: %s", model_name)
            except Exception:
                logger.warning(
                    "Failed to load fastembed model '%s'; "
                    "falling back to text search.",
                    model_name,
                    exc_info=True,
                )
        else:
            missing = []
            if not _HAS_NUMPY:
                missing.append("numpy")
            if not _HAS_FASTEMBED:
                missing.append("fastembed")
            logger.warning(
                "Optional dependencies not available (%s); "
                "semantic index will use text-based fallback.",
                ", ".join(missing),
            )

    # -- Embedding helpers --------------------------------------------------

    def _embed(self, text: str) -> np.ndarray | None:
        """Embed a single text string, returning None if unavailable."""
        if self._embedder is None or np is None:
            return None
        # fastembed returns a generator; take the first result
        vectors = list(self._embedder.embed([text]))
        if vectors:
            return np.array(vectors[0], dtype=np.float32)
        return None  # pragma: no cover

    @property
    def has_embeddings(self) -> bool:
        """Whether the index can produce vector embeddings."""
        return self._embedder is not None

    # -- Public API ---------------------------------------------------------

    def index_entry(self, entry: IndexEntry) -> None:
        """Add or update a single entry in the index.

        Args:
            entry: The entry to index.
        """
        emb = self._embed(entry.summary)
        emb_bytes = _embedding_to_bytes(emb) if emb is not None else None

        self._conn.execute(
            """
            INSERT OR REPLACE INTO entries
                (entry_id, summary, full_text, source, timestamp, embedding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.entry_id,
                entry.summary,
                entry.full_text,
                entry.source,
                entry.timestamp,
                emb_bytes,
            ),
        )
        self._conn.commit()

    def index_decisions(self, decisions: list[DecisionEntry]) -> None:
        """Index all decisions from memory.

        Extracts a summary from each decision's title and outcome, then
        stores the full decision text for retrieval.

        Args:
            decisions: List of decision log entries.
        """
        for d in decisions:
            summary = _extract_summary(d)
            full_text = self._render_decision_text(d)
            entry = IndexEntry(
                entry_id=_entry_id_for("decision", d.title),
                summary=summary,
                full_text=full_text,
                source="decision",
                timestamp=d.timestamp.isoformat(),
            )
            self.index_entry(entry)

    def index_priors(self, priors: list[PriorEntry]) -> None:
        """Index all priors from memory.

        Uses the prior's statement as the summary for embedding.

        Args:
            priors: List of prior entries.
        """
        for p in priors:
            full_text = (
                f"Category: {p.category}\n"
                f"Statement: {p.statement}\n"
                f"Evidence: {p.evidence}\n"
                f"Confidence: {p.confidence}"
            )
            entry = IndexEntry(
                entry_id=_entry_id_for("prior", p.statement),
                summary=p.statement,
                full_text=full_text,
                source="prior",
            )
            self.index_entry(entry)

    def query(self, query_text: str, top_k: int = 5) -> list[SearchResult]:
        """Semantic search over the index.

        When fastembed is available, computes cosine similarity between
        the query embedding and all stored embeddings.  Otherwise falls
        back to case-insensitive substring matching on the summary field.

        Args:
            query_text: Natural-language query string.
            top_k: Maximum number of results to return.

        Returns:
            Results sorted by descending relevance score.
        """
        if self._embedder is not None and _HAS_NUMPY:
            return self._query_semantic(query_text, top_k)
        return self._query_text_fallback(query_text, top_k)

    def rebuild_index(
        self,
        decisions: list[DecisionEntry],
        priors: list[PriorEntry],
    ) -> None:
        """Full rebuild from scratch.

        Clears the existing index and re-indexes all decisions and
        priors.  Intended to be called at session end.

        Args:
            decisions: All decision log entries for the project.
            priors: All prior entries for the project.
        """
        self.clear()
        self.index_decisions(decisions)
        self.index_priors(priors)

    def count(self) -> int:
        """Return the number of entries in the index."""
        row = self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()
        return row[0] if row else 0

    def clear(self) -> None:
        """Remove all entries from the index."""
        self._conn.execute("DELETE FROM entries")
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # -- Internal -----------------------------------------------------------

    def _query_semantic(
        self, query_text: str, top_k: int
    ) -> list[SearchResult]:
        """Vector-based query using cosine similarity."""
        query_emb = self._embed(query_text)
        if query_emb is None:
            return self._query_text_fallback(query_text, top_k)

        rows = self._conn.execute(
            "SELECT entry_id, summary, full_text, source, timestamp, embedding "
            "FROM entries WHERE embedding IS NOT NULL"
        ).fetchall()

        scored: list[SearchResult] = []
        for row in rows:
            entry_id, summary, full_text, source, ts, emb_bytes = row
            stored_emb = _bytes_to_embedding(emb_bytes)
            score = _cosine_similarity(query_emb, stored_emb)
            entry = IndexEntry(
                entry_id=entry_id,
                summary=summary,
                full_text=full_text,
                source=source,
                timestamp=ts,
            )
            scored.append(SearchResult(entry=entry, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def _query_text_fallback(
        self, query_text: str, top_k: int
    ) -> list[SearchResult]:
        """Substring-based fallback when embeddings are not available.

        Scores each entry by the fraction of query words found in the
        summary (case-insensitive).
        """
        query_lower = query_text.lower()
        query_words = [w for w in query_lower.split() if len(w) > 2]

        rows = self._conn.execute(
            "SELECT entry_id, summary, full_text, source, timestamp FROM entries"
        ).fetchall()

        scored: list[SearchResult] = []
        for row in rows:
            entry_id, summary, full_text, source, ts = row
            summary_lower = summary.lower()

            # Score: fraction of query words present in summary
            if not query_words:
                score = 1.0 if query_lower in summary_lower else 0.0
            else:
                hits = sum(1 for w in query_words if w in summary_lower)
                score = hits / len(query_words)

            if score > 0.0:
                entry = IndexEntry(
                    entry_id=entry_id,
                    summary=summary,
                    full_text=full_text,
                    source=source,
                    timestamp=ts,
                )
                scored.append(SearchResult(entry=entry, score=score))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    @staticmethod
    def _render_decision_text(d: DecisionEntry) -> str:
        """Render a full decision entry as plain text for retrieval."""
        lines = [
            f"Decision: {d.title}",
            f"Timestamp: {d.timestamp.isoformat()}",
            f"Context: {d.context}",
            f"Decision: {d.decision}",
            f"Rationale: {d.rationale}",
        ]
        if d.alternatives_considered:
            lines.append(f"Alternatives: {d.alternatives_considered}")
        lines.append(f"Outcome: {d.outcome}")
        lines.append(f"Confidence: {d.confidence}")
        return "\n".join(lines)
