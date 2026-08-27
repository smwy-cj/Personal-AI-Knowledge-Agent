"""Provider-neutral embedding cache and exact cosine vector search."""

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional, Protocol, Sequence, Tuple

from .knowledge import (
    KeywordSearchQuery,
    KnowledgeSearchResult,
    VectorSyncResult,
)
from .knowledge_repository import SQLiteKnowledgeRepository
from .models import utc_now


class EmbeddingProvider(Protocol):
    @property
    def provider_id(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        ...


class InvalidEmbedding(ValueError):
    pass


class SQLiteVectorIndex:
    """Stores provider-versioned embeddings and performs exact cosine search.

    Exact scanning is intentional for the local MVP. An ANN backend can later
    implement the same public contract without changing retrieval callers.
    """

    def __init__(
        self,
        repository: SQLiteKnowledgeRepository,
        provider: EmbeddingProvider,
        batch_size: int = 32,
        minimum_query_score: Optional[float] = None,
    ) -> None:
        if not provider.provider_id.strip():
            raise ValueError("embedding provider_id must be non-empty")
        if provider.dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        if batch_size <= 0:
            raise ValueError("embedding batch_size must be positive")
        if minimum_query_score is not None and not 0 <= minimum_query_score <= 1:
            raise ValueError("minimum_query_score must be between 0 and 1")
        self.repository = repository
        self.provider = provider
        self.batch_size = batch_size
        self.minimum_query_score = minimum_query_score
        self.database_path = repository.database_path
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                    chunk_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    embedded_at TEXT NOT NULL,
                    FOREIGN KEY(chunk_id) REFERENCES knowledge_chunks(chunk_id) ON DELETE CASCADE,
                    PRIMARY KEY(chunk_id, provider_id)
                );
                CREATE INDEX IF NOT EXISTS idx_embeddings_provider
                    ON knowledge_embeddings(provider_id, chunk_id);
                """
            )

    def sync(self) -> VectorSyncResult:
        rows = self.repository.keyword_candidates_fallback(None, None, [])
        current_ids = {row["chunk_id"] for row in rows}
        with self._connect() as connection:
            stored_rows = connection.execute(
                """
                SELECT chunk_id, content_hash, dimension FROM knowledge_embeddings
                WHERE provider_id = ?
                """,
                (self.provider.provider_id,),
            ).fetchall()
        stored = {
            row["chunk_id"]: (row["content_hash"], row["dimension"])
            for row in stored_rows
        }

        pending: List[Tuple[sqlite3.Row, str, str]] = []
        unchanged = 0
        for row in rows:
            text = _embedding_text(row)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if stored.get(row["chunk_id"]) == (content_hash, self.provider.dimension):
                unchanged += 1
            else:
                pending.append((row, text, content_hash))

        embedded = 0
        for start in range(0, len(pending), self.batch_size):
            batch = pending[start : start + self.batch_size]
            vectors = list(self.provider.embed([item[1] for item in batch]))
            if len(vectors) != len(batch):
                raise InvalidEmbedding("provider returned an unexpected vector count")
            records = []
            for (row, _, content_hash), vector in zip(batch, vectors):
                normalized = _validate_vector(vector, self.provider.dimension)
                records.append(
                    (
                        row["chunk_id"],
                        self.provider.provider_id,
                        content_hash,
                        self.provider.dimension,
                        json.dumps(normalized, separators=(",", ":")),
                        utc_now(),
                    )
                )
            with self._connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO knowledge_embeddings(
                        chunk_id, provider_id, content_hash, dimension,
                        vector_json, embedded_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id, provider_id) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        dimension = excluded.dimension,
                        vector_json = excluded.vector_json,
                        embedded_at = excluded.embedded_at
                    """,
                    records,
                )
            embedded += len(records)

        stale_ids = set(stored) - current_ids
        deleted = 0
        if stale_ids:
            with self._connect() as connection:
                for chunk_id in stale_ids:
                    cursor = connection.execute(
                        """
                        DELETE FROM knowledge_embeddings
                        WHERE chunk_id = ? AND provider_id = ?
                        """,
                        (chunk_id, self.provider.provider_id),
                    )
                    deleted += cursor.rowcount
        return VectorSyncResult(embedded=embedded, unchanged=unchanged, deleted=deleted)

    def search(self, query: KeywordSearchQuery) -> List[KnowledgeSearchResult]:
        query_vectors = list(self.provider.embed([query.text]))
        if len(query_vectors) != 1:
            raise InvalidEmbedding("provider must return exactly one query vector")
        query_vector = _validate_vector(query_vectors[0], self.provider.dimension)
        tags = [tag.strip().lstrip("#") for tag in query.tags if tag.strip()]
        candidate_rows = self.repository.keyword_candidates_fallback(
            query.vault_id, query.path_prefix, tags
        )
        by_id = {row["chunk_id"]: row for row in candidate_rows}
        if not by_id:
            return []
        placeholders = ",".join("?" for _ in by_id)
        parameters: List[object] = [self.provider.provider_id]
        parameters.extend(by_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, dimension, vector_json FROM knowledge_embeddings
                WHERE provider_id = ? AND chunk_id IN (%s)
                """ % placeholders,
                parameters,
            ).fetchall()
        scored = []
        for vector_row in rows:
            if vector_row["dimension"] != self.provider.dimension:
                raise InvalidEmbedding(
                    "cached embedding dimension does not match provider; run vector sync"
                )
            vector = _validate_vector(
                json.loads(vector_row["vector_json"]), self.provider.dimension
            )
            score = _cosine_similarity(query_vector, vector)
            scored.append((score, by_id[vector_row["chunk_id"]]))
        scored.sort(key=lambda item: (-item[0], item[1]["relative_path"], item[1]["ordinal"]))
        if not scored:
            return []
        top_score = max(0.0, min(1.0, (scored[0][0] + 1.0) / 2.0))
        if (
            self.minimum_query_score is not None
            and top_score < self.minimum_query_score
        ):
            return []
        return [
            _vector_result(row, max(0.0, min(1.0, (score + 1.0) / 2.0)))
            for score, row in scored[: query.limit]
        ]


def _embedding_text(row: sqlite3.Row) -> str:
    return "%s\n%s\n%s" % (row["title"], row["heading"] or "", row["content"])


def _validate_vector(vector: Sequence[float], dimension: int) -> List[float]:
    if len(vector) != dimension:
        raise InvalidEmbedding(
            "embedding dimension mismatch: expected %s, got %s" % (dimension, len(vector))
        )
    normalized = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in normalized):
        raise InvalidEmbedding("embedding contains a non-finite value")
    if not any(value != 0.0 for value in normalized):
        raise InvalidEmbedding("embedding vector must not be all zeros")
    return normalized


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise InvalidEmbedding("cosine similarity requires non-zero vectors")
    return numerator / (left_norm * right_norm)


def _vector_result(row: sqlite3.Row, score: float) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        vault_id=row["vault_id"],
        relative_path=row["relative_path"],
        title=row["title"],
        heading=row["heading"],
        heading_path=json.loads(row["heading_path_json"]),
        content=row["content"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        score=score,
        match_method="vector",
        matched_terms=[],
    )
