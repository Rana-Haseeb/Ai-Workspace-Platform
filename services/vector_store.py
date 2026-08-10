"""Similarity search over stored embeddings, behind an interface.

The interface is the point. Today there is one implementation: vectors live in a JSON column and
cosine similarity is computed in numpy. That runs identically on SQLite and PostgreSQL, needs no
extension, and is genuinely fast at this scale — a few thousand chunks is a single small matrix
multiply, well under a millisecond.

It does not scale to millions of chunks, and it is not meant to. When it stops being enough the
answer is a second implementation of :class:`VectorStore` backed by pgvector, and the only code
that changes is the one line that picks a store. That is the difference between a design and a
shortcut, and it is the honest answer to "how would you scale the knowledge base?".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.logging import get_logger
from db.models import Chunk, Document, Embedding

log = get_logger("vectors")


@dataclass
class Match:
    chunk_id: int
    document_id: int
    score: float


class VectorStore(ABC):
    """Nearest-neighbour search scoped to one workspace."""

    @abstractmethod
    def search(
        self, db: Session, workspace_id: int, query_vector: list[float], top_k: int
    ) -> list[Match]:
        ...


class JsonCosineStore(VectorStore):
    """Cosine similarity over vectors stored as JSON, computed with numpy.

    Loads every vector in the workspace on each search. That is the honest cost of the design:
    at 5,000 chunks × 768 dimensions it is roughly 15 MB and a few milliseconds, which is fine;
    at a million chunks it would not be, which is what the pgvector path is for.
    """

    def search(
        self, db: Session, workspace_id: int, query_vector: list[float], top_k: int
    ) -> list[Match]:
        rows = db.execute(
            select(Embedding.chunk_id, Chunk.document_id, Embedding.vector)
            .join(Chunk, Chunk.id == Embedding.chunk_id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.workspace_id == workspace_id)
        ).all()

        if not rows:
            return []

        matrix = np.asarray([row[2] for row in rows], dtype=np.float32)
        query = np.asarray(query_vector, dtype=np.float32)

        # Guard against a dimension change between ingestion and query — switching
        # EMBEDDING_DIM without re-ingesting would otherwise raise deep inside numpy.
        if matrix.shape[1] != query.shape[0]:
            log.warning(
                "Stored vectors are %dd but the query is %dd. Re-ingest the documents after "
                "changing EMBEDDING_DIM.", matrix.shape[1], query.shape[0]
            )
            return []

        # Normalise, then a single dot product gives every cosine at once.
        matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix_norms[matrix_norms == 0] = 1.0
        query_norm = np.linalg.norm(query) or 1.0

        scores = (matrix / matrix_norms) @ (query / query_norm)

        top = np.argsort(-scores)[:top_k]
        return [
            Match(chunk_id=rows[i][0], document_id=rows[i][1], score=float(scores[i]))
            for i in top
        ]


def get_vector_store() -> VectorStore:
    """The active store.

    One line, deliberately. When pgvector arrives it is chosen here based on the dialect, and
    nothing that calls ``search`` has to know.
    """
    return JsonCosineStore()
