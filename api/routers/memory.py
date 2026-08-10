"""Reading and editing what the assistant remembers about you.

Memory is written automatically, which makes it the part of the platform a user is most likely to
want control over. Everything the extractor stores can be read, corrected, re-weighted, pinned or
deleted here — a system that silently accumulates claims about someone and offers no way to see
them is one nobody should trust.

Routes are nested under a workspace so they inherit the ownership check, but the data they
return is **user-scoped**: memories with a null ``workspace_id`` follow the person everywhere and
appear in every workspace's list.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from core.config import settings
from db.models import Log, MemoryItem
from schemas.memory import MemoryCreate, MemoryResponse, MemoryStatus, MemoryUpdate
from services import memory_service

router = APIRouter(prefix="/api/workspaces/{workspace_id}/memory", tags=["memory"])


def _load(db, user_id: int, memory_id: int) -> MemoryItem:
    """A memory belonging to this user. Filtering on ``user_id`` is the isolation check."""
    item = db.execute(
        select(MemoryItem).where(MemoryItem.id == memory_id, MemoryItem.user_id == user_id)
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return item


def _to_response(item: MemoryItem, now: datetime, in_context_ids: set[int]) -> MemoryResponse:
    response = MemoryResponse.model_validate(item)
    score = memory_service.rank_score(item, now)
    # Pinned items score infinity internally; report 1.0 so the number stays displayable.
    response.rank_score = round(min(score, 1.0), 4)
    response.in_context = item.id in in_context_ids
    return response


@router.get("", response_model=list[MemoryResponse])
def list_memories(workspace: OwnedWorkspace, user: CurrentUser, db: DbSession) -> list[MemoryResponse]:
    """Everything remembered here, ordered exactly as it would be injected."""
    now = datetime.now(timezone.utc)
    items = memory_service.candidates(db, user.id, workspace.id)
    in_context = {m.id for m in memory_service.retrieve(db, user.id, workspace.id)}

    items.sort(key=lambda item: memory_service.rank_score(item, now), reverse=True)
    return [_to_response(item, now, in_context) for item in items]


@router.get("/status", response_model=MemoryStatus)
def memory_status(workspace: OwnedWorkspace, user: CurrentUser, db: DbSession) -> MemoryStatus:
    items = memory_service.candidates(db, user.id, workspace.id)
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1

    return MemoryStatus(
        total=len(items),
        pinned=sum(1 for item in items if item.is_pinned),
        in_context=len(memory_service.retrieve(db, user.id, workspace.id)),
        by_kind=by_kind,
        enabled=settings.memory_enabled and workspace.settings.use_memory,
        max_in_context=settings.memory_max_items_in_context,
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> MemoryResponse:
    """Add a memory by hand, rather than waiting for the extractor to notice it."""
    item = MemoryItem(
        user_id=user.id,
        workspace_id=workspace.id if payload.workspace_scoped else None,
        kind=payload.kind,
        content=payload.content.strip(),
        importance=payload.importance,
    )
    db.add(item)
    db.add(Log(user_id=user.id, workspace_id=workspace.id, event="memory",
               detail="added by hand", status="ok"))
    db.commit()
    db.refresh(item)
    return _to_response(item, datetime.now(timezone.utc), set())


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int, payload: MemoryUpdate, workspace: OwnedWorkspace,
    user: CurrentUser, db: DbSession,
) -> MemoryResponse:
    """Correct, re-weight, or pin a memory.

    Correcting matters: the extractor is a language model reading conversation, so it will
    occasionally record something subtly wrong. A memory that cannot be fixed is worse than no
    memory, because it silently shapes every future answer.
    """
    item = _load(db, user.id, memory_id)
    fields = payload.model_dump(exclude_unset=True)

    if "content" in fields and fields["content"]:
        item.content = fields["content"].strip()
    if "kind" in fields and fields["kind"]:
        item.kind = fields["kind"]
    if "importance" in fields and fields["importance"] is not None:
        item.importance = fields["importance"]
    if "is_pinned" in fields and fields["is_pinned"] is not None:
        item.is_pinned = fields["is_pinned"]

    db.commit()
    db.refresh(item)
    in_context = {m.id for m in memory_service.retrieve(db, user.id, workspace.id)}
    return _to_response(item, datetime.now(timezone.utc), in_context)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int, workspace: OwnedWorkspace, user: CurrentUser, db: DbSession
) -> None:
    db.delete(_load(db, user.id, memory_id))
    db.add(Log(user_id=user.id, workspace_id=workspace.id, event="memory",
               detail="deleted", status="ok"))
    db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def forget_everything(workspace: OwnedWorkspace, user: CurrentUser, db: DbSession) -> None:
    """Delete every memory visible in this workspace, including the user-wide ones.

    A single, obvious way to make the assistant forget. Anything less than "all of it" is a
    privacy control people cannot reason about.
    """
    for item in memory_service.candidates(db, user.id, workspace.id):
        db.delete(item)
    db.add(Log(user_id=user.id, workspace_id=workspace.id, event="memory",
               detail="forgot everything", status="ok"))
    db.commit()
