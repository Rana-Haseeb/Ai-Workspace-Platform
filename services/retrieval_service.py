"""Finding the chunks that answer a question, and turning them into citations.

**Hybrid, not vector-only.** Embeddings are good at meaning and bad at exact strings: a query for
``pgvector`` or ``ISO 27001`` or a product code often ranks a paragraph *about* the topic above
the one that literally names it. BM25 is the reverse. Running both and fusing the rankings gets
the strengths of each, and it means the knowledge base still works when no embedding provider is
configured at all.

**Fusion by rank, not by score.** A cosine similarity and a BM25 score are not on the same
scale and normalising them against each other is guesswork that changes with every corpus.
Reciprocal Rank Fusion only uses each result's *position*, so the two systems can disagree about
magnitude and still combine sensibly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.logging import get_logger
from db.models import Chunk, Document
from services import embedding_service
from services.vector_store import get_vector_store

log = get_logger("retrieval")

# The constant in Reciprocal Rank Fusion. 60 is the value from the original paper and is not
# tuned here; it flattens the difference between ranks 1 and 2 so a single system cannot
# dominate on its own confidence.
RRF_K = 60

# A snippet long enough to judge whether the citation supports the claim, short enough that six
# of them do not crowd out the conversation.
SNIPPET_CHARS = 400


@dataclass
class Citation:
    """One retrieved chunk, in the shape the API and the UI both use."""

    chunk_id: int
    document_id: int
    filename: str
    page: int | None
    snippet: str
    score: float

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "page": self.page,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }


@dataclass
class RetrievalResult:
    citations: list[Citation] = field(default_factory=list)
    mode: str = "none"
    vector_error: str | None = None

    def context_block(self) -> str:
        """The chunks formatted for the model, each tagged so it can be cited by number."""
        if not self.citations:
            return ""
        parts = []
        for index, citation in enumerate(self.citations, start=1):
            location = f"{citation.filename}"
            if citation.page:
                location += f", page {citation.page}"
            parts.append(f"[{index}] ({location})\n{citation.snippet}")
        return "\n\n".join(parts)


def _tokenise(text: str) -> list[str]:
    """Lowercased word tokens. Deliberately simple — no stemming, no stop-word list.

    Stemming would make ``embedding`` match ``embed`` but also ``universe`` match ``university``,
    and on a technical corpus the exact term is usually the one that matters.
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def _bm25_ranking(db: Session, workspace_id: int, query: str, limit: int) -> list[int]:
    """Chunk ids ranked by BM25, best first.

    Relevance is decided by **token overlap**, not by the sign of the BM25 score. BM25's IDF term
    goes negative for any word appearing in more than half the corpus, so on a workspace holding
    one short document — the normal case for a new user, and for a demo — every genuinely
    matching chunk scores below zero. Filtering on ``score > 0`` there discards exactly the
    results the user was looking for.

    So: overlap decides *whether* a chunk is a candidate, and BM25 decides *what order* the
    candidates come in. BM25 is a good ranker at every corpus size; it is only its absolute
    scale that is meaningless when the corpus is tiny.
    """
    from rank_bm25 import BM25Okapi

    rows = db.execute(
        select(Chunk.id, Chunk.text)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.workspace_id == workspace_id)
    ).all()
    if not rows:
        return []

    query_tokens = set(_tokenise(query))
    if not query_tokens:
        return []

    corpus = [_tokenise(text) for _, text in rows]
    # A corpus where every document is empty after tokenising would divide by zero in BM25.
    if not any(corpus):
        return []

    candidates = [i for i, tokens in enumerate(corpus) if query_tokens & set(tokens)]
    if not candidates:
        return []

    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(list(query_tokens))
    candidates.sort(key=lambda i: -scores[i])
    return [rows[i][0] for i in candidates[:limit]]


def _fuse(rankings: list[list[int]], limit: int) -> list[int]:
    """Reciprocal Rank Fusion over several ranked id lists."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + position + 1)
    return sorted(scores, key=lambda cid: -scores[cid])[:limit]


def retrieve(
    db: Session, workspace_id: int, query: str, top_k: int | None = None
) -> RetrievalResult:
    """The chunks most likely to answer ``query`` within one workspace.

    Never raises on a retrieval failure. If embeddings are unavailable — no key, quota exhausted,
    provider down — it degrades to keyword search and records why, because an answer without
    citations beats an error page.
    """
    top_k = top_k or settings.retrieval_top_k
    mode = settings.retrieval_mode
    # Each system contributes more candidates than the final list, so fusion has something to
    # disagree about.
    pool = top_k * 3

    rankings: list[list[int]] = []
    used: list[str] = []
    vector_error: str | None = None

    if mode in {"bm25", "hybrid"}:
        keyword = _bm25_ranking(db, workspace_id, query, pool)
        if keyword:
            rankings.append(keyword)
            used.append("bm25")

    if mode in {"vector", "hybrid"} and embedding_service.is_configured():
        try:
            vector = get_vector_store().search(
                db, workspace_id, embedding_service.embed_query(query), pool
            )
            if vector:
                rankings.append([m.chunk_id for m in vector])
                used.append("vector")
        except Exception as error:  # noqa: BLE001
            vector_error = str(error)[:200]
            log.warning("Vector search unavailable, using keyword only: %s", vector_error)

    if not rankings:
        return RetrievalResult(mode="none", vector_error=vector_error)

    chunk_ids = _fuse(rankings, top_k)
    if not chunk_ids:
        return RetrievalResult(mode="+".join(used), vector_error=vector_error)

    rows = db.execute(
        select(Chunk, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    by_id = {chunk.id: (chunk, filename) for chunk, filename in rows}

    citations = []
    for position, chunk_id in enumerate(chunk_ids):
        if chunk_id not in by_id:
            continue
        chunk, filename = by_id[chunk_id]
        snippet = chunk.text[:SNIPPET_CHARS]
        if len(chunk.text) > SNIPPET_CHARS:
            snippet = snippet.rsplit(" ", 1)[0] + "…"
        citations.append(
            Citation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                page=chunk.page,
                snippet=snippet,
                # Fused rank turned back into a 0-1 figure for display. It is a rank, not a
                # probability, and the UI labels it as relevance rather than confidence.
                score=1.0 - (position / max(len(chunk_ids), 1)),
            )
        )

    return RetrievalResult(citations=citations, mode="+".join(used), vector_error=vector_error)


GROUNDING_INSTRUCTION = """You have been given excerpts from the user's documents, numbered [1], [2] and so on.

Rules for using them:
- Prefer the excerpts over your own knowledge when they cover the question.
- Cite the number in square brackets immediately after any claim that comes from an excerpt.
- If the excerpts do not answer the question, say so plainly and answer from general knowledge, making clear which part is which.
- Never invent a citation number that is not in the list."""
