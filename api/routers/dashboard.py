"""The workspace dashboard, and conversation export."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from core.config import settings
from db.models import Conversation
from schemas.dashboard import DashboardResponse
from services import dashboard_service, export_service

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(workspace: OwnedWorkspace, user: CurrentUser, db: DbSession) -> DashboardResponse:
    """Every figure here is a live aggregate, not a stored counter."""
    return DashboardResponse(
        totals=dashboard_service.workspace_totals(db, workspace, user.id),
        usage=dashboard_service.usage_totals(db, workspace.id),
        by_event=dashboard_service.usage_by_event(db, workspace.id),
        daily=dashboard_service.daily_usage(db, workspace.id),
        activity=dashboard_service.recent_activity(db, workspace.id),
        top_memories=dashboard_service.top_memories(db, user.id, workspace.id),
        provider_chain=settings.provider_chain(),
    )


@router.get("/conversations/{conversation_id}/export", response_class=PlainTextResponse)
def export_conversation(
    conversation_id: int,
    workspace: OwnedWorkspace,
    db: DbSession,
    download: bool = Query(default=False, description="Send as a file attachment"),
) -> PlainTextResponse:
    """One conversation as Markdown.

    ``download=false`` returns it inline, which is what the print view renders for PDF.
    ``download=true`` sets a Content-Disposition header so the browser saves a .md file.
    """
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.workspace_id == workspace.id
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    markdown = export_service.conversation_to_markdown(db, workspace, conversation)
    headers = {}
    if download:
        filename = export_service.safe_filename(conversation.title)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return PlainTextResponse(markdown, media_type="text/markdown; charset=utf-8", headers=headers)
