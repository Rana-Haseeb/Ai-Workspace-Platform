"""Documents, chunks and citations."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int
    chunk_count: int
    status: Literal["pending", "processing", "ready", "failed"]
    error: str | None
    created_at: datetime


class CitationResponse(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    page: int | None
    snippet: str
    score: float


class ChunkResponse(BaseModel):
    """One chunk, for the citation viewer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ordinal: int
    text: str
    page: int | None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=20)


class SearchResponse(BaseModel):
    query: str
    # Which retrieval systems actually contributed: "bm25", "vector", "bm25+vector", or "none".
    mode: str
    citations: list[CitationResponse]
    took_ms: int
    # Present when vector search was configured but unavailable, so the UI can explain a
    # keyword-only result instead of silently degrading.
    vector_error: str | None = None


class KnowledgeBaseStatus(BaseModel):
    """What the workspace's knowledge base can currently do."""

    documents: int
    chunks: int
    embedded_chunks: int
    embedding_backend: str
    retrieval_mode: str
    semantic_search_available: bool
