"""Document upload, listing, search and citation lookup.

Uploads are validated, written to disk, and recorded as ``pending``; the parse-chunk-embed
pipeline then runs in a background task. The request returns as soon as the bytes are safe,
which keeps a 40-page PDF from holding an HTTP connection open for ten seconds.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from core.config import settings
from core.logging import get_logger
from db.base import SessionLocal
from db.models import Chunk, Document, Embedding
from schemas.document import (
    ChunkResponse,
    CitationResponse,
    DocumentResponse,
    KnowledgeBaseStatus,
    SearchRequest,
    SearchResponse,
)
from services import document_service, embedding_service, ingestion_service, retrieval_service

log = get_logger("documents")

router = APIRouter(prefix="/api/workspaces/{workspace_id}/documents", tags=["documents"])


def _safe_stored_name(filename: str) -> str:
    """A collision-proof name that keeps the extension and discards everything else.

    The original filename is stored in the database for display; it never reaches the
    filesystem. That closes path traversal (``../../etc/passwd``) by construction rather than by
    sanitising, and it means two people uploading ``report.pdf`` do not overwrite each other.
    """
    suffix = Path(filename).suffix.lower()
    return f"{uuid.uuid4().hex}{suffix}"


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace: OwnedWorkspace,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentResponse:
    contents = await file.read()

    try:
        suffix, mime_type = document_service.validate_upload(
            file.filename or "upload", len(contents)
        )
    except document_service.UnsupportedDocument as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))

    upload_dir = settings.upload_dir / str(workspace.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / _safe_stored_name(file.filename or "upload")
    stored_path.write_bytes(contents)

    document = Document(
        workspace_id=workspace.id,
        filename=(file.filename or "upload")[:255],
        stored_path=str(stored_path),
        mime_type=mime_type,
        size_bytes=len(contents),
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background.add_task(ingestion_service.ingest, SessionLocal, document.id)
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(workspace: OwnedWorkspace, db: DbSession) -> list[DocumentResponse]:
    rows = db.execute(
        select(Document)
        .where(Document.workspace_id == workspace.id)
        .order_by(Document.created_at.desc())
    ).scalars().all()
    return [DocumentResponse.model_validate(d) for d in rows]


@router.get("/status", response_model=KnowledgeBaseStatus)
def knowledge_base_status(workspace: OwnedWorkspace, db: DbSession) -> KnowledgeBaseStatus:
    """What this workspace's knowledge base can actually do right now.

    The UI uses this to say "keyword search only" out loud rather than quietly returning worse
    results when embeddings are unavailable.
    """
    documents = db.execute(
        select(func.count(Document.id)).where(Document.workspace_id == workspace.id)
    ).scalar_one()
    chunks = db.execute(
        select(func.count(Chunk.id))
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.workspace_id == workspace.id)
    ).scalar_one()
    embedded = db.execute(
        select(func.count(Embedding.id))
        .join(Chunk, Chunk.id == Embedding.chunk_id)
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.workspace_id == workspace.id)
    ).scalar_one()

    return KnowledgeBaseStatus(
        documents=documents,
        chunks=chunks,
        embedded_chunks=embedded,
        embedding_backend=embedding_service.describe(),
        retrieval_mode=settings.retrieval_mode,
        semantic_search_available=embedding_service.is_configured() and embedded > 0,
    )


@router.post("/search", response_model=SearchResponse)
def search_documents(
    payload: SearchRequest, workspace: OwnedWorkspace, db: DbSession
) -> SearchResponse:
    started = time.perf_counter()
    result = retrieval_service.retrieve(db, workspace.id, payload.query, payload.top_k)
    return SearchResponse(
        query=payload.query,
        mode=result.mode,
        citations=[CitationResponse(**c.to_dict()) for c in result.citations],
        took_ms=int((time.perf_counter() - started) * 1000),
        vector_error=result.vector_error,
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
def document_chunks(
    document_id: int, workspace: OwnedWorkspace, db: DbSession
) -> list[ChunkResponse]:
    """Every chunk of one document, in order. This is what a citation chip opens."""
    document = db.execute(
        select(Document).where(
            Document.id == document_id, Document.workspace_id == workspace.id
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    rows = db.execute(
        select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.ordinal)
    ).scalars().all()
    return [ChunkResponse.model_validate(c) for c in rows]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, workspace: OwnedWorkspace, db: DbSession) -> None:
    document = db.execute(
        select(Document).where(
            Document.id == document_id, Document.workspace_id == workspace.id
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Remove the file too. A deleted document that leaves its bytes on disk is a data-retention
    # problem, not a tidiness one.
    try:
        Path(document.stored_path).unlink(missing_ok=True)
    except OSError as error:
        log.warning("Could not delete %s: %s", document.stored_path, error)

    db.delete(document)      # chunks and embeddings cascade
    db.commit()
