"""Storing an uploaded file: parse, chunk, embed, persist.

Ingestion runs in a background task rather than inside the upload request. A 40-page PDF is
roughly 90 chunks and five embedding batches — several seconds — and holding the HTTP request
open for that means the browser shows a frozen upload with no progress. Instead the row is
created immediately with ``status="pending"`` and the UI polls it.

Embedding failure is not ingestion failure. If the embedding provider is down or out of quota
the chunks are still stored and the document is still searchable by keyword; the row records
that vectors are missing so the UI can say so and the user can retry.
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.orm import Session

from core.logging import get_logger
from db.models import Chunk as ChunkRow
from db.models import Document, Embedding, Log
from services import document_service, embedding_service

log = get_logger("ingestion")


def ingest(session_factory, document_id: int) -> None:
    """Parse, chunk, embed and store one document. Safe to call in a background thread.

    Takes a session *factory* rather than a session: the request that scheduled this has already
    returned and closed its own.
    """
    db: Session = session_factory()
    try:
        document = db.get(Document, document_id)
        if document is None:
            log.warning("Document %s vanished before ingestion", document_id)
            return

        document.status = "processing"
        db.commit()

        started = time.perf_counter()
        path = Path(document.stored_path)
        suffix = path.suffix.lower()

        try:
            pages, chunks = document_service.parse(path, suffix)
        except (document_service.UnsupportedDocument, document_service.EmptyDocument) as error:
            document.status = "failed"
            document.error = str(error)
            db.add(Log(workspace_id=document.workspace_id, event="upload",
                       detail=f"{document.filename}: {error}", status="failed"))
            db.commit()
            return

        document.page_count = len(pages)
        document.chunk_count = len(chunks)

        rows = [
            ChunkRow(
                document_id=document.id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                page=chunk.page,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
            for chunk in chunks
        ]
        db.add_all(rows)
        db.commit()

        embedded = 0
        embedding_error: str | None = None
        if embedding_service.is_configured():
            try:
                vectors = embedding_service.embed_documents([c.text for c in chunks])
                db.add_all([
                    Embedding(
                        chunk_id=row.id,
                        model=embedding_service.settings.embedding_model,
                        dim=len(vector),
                        vector=vector,
                    )
                    for row, vector in zip(rows, vectors)
                ])
                db.commit()
                embedded = len(vectors)
            except Exception as error:  # noqa: BLE001
                # Deliberately not fatal: keyword search still works without vectors.
                embedding_error = str(error)[:300]
                db.rollback()
                log.warning("Embedding failed for %s: %s", document.filename, embedding_error)

        elapsed = time.perf_counter() - started
        document.status = "ready"
        document.error = (
            f"Stored without embeddings ({embedding_error}). Keyword search still works."
            if embedding_error
            else None
        )
        db.add(Log(
            workspace_id=document.workspace_id,
            event="upload",
            detail=f"{document.filename}: {len(pages)} pages, {len(chunks)} chunks, "
                   f"{embedded} embedded",
            latency_ms=int(elapsed * 1000),
            status="ok" if not embedding_error else "degraded",
        ))
        db.commit()

        log.info(
            "Ingested %s in %.2fs: %d pages, %d chunks, %d embedded",
            document.filename, elapsed, len(pages), len(chunks), embedded,
        )
    except Exception as error:  # noqa: BLE001
        log.exception("Ingestion crashed for document %s", document_id)
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.status = "failed"
            document.error = str(error)[:300]
            db.commit()
    finally:
        db.close()
