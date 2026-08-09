"""Workspaces and their assistant configuration.

Every route takes its owner from ``CurrentUser`` (derived from the signed token) and never from
the request body, and every route addressing a specific workspace resolves it through
``OwnedWorkspace``, which is where the ownership check lives.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from core.config import SELECTABLE_MODELS
from db.models import Log
from schemas.settings import (
    AssistantSettingsResponse,
    AssistantSettingsUpdate,
    ModelOption,
)
from schemas.workspace import (
    WORKSPACE_ICONS,
    WorkspaceCreate,
    WorkspaceDetail,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from services import workspace_service

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("/meta", response_model=dict)
def workspace_metadata() -> dict:
    """Choices the settings and create screens offer.

    Served from the backend so the picker cannot drift from what the server will accept — the
    frontend renders whatever this returns rather than keeping its own copy of the list.
    """
    return {
        "icons": WORKSPACE_ICONS,
        "models": [ModelOption(id=k, label=v).model_dump() for k, v in SELECTABLE_MODELS.items()],
        "personalities": ["professional", "friendly", "concise", "socratic", "enthusiastic"],
        "response_styles": ["balanced", "detailed", "brief", "bullets", "technical"],
    }


@router.post("", response_model=WorkspaceDetail, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: DbSession
) -> WorkspaceDetail:
    workspace = workspace_service.create_workspace(db, user.id, payload)
    db.add(Log(user_id=user.id, workspace_id=workspace.id, event="workspace",
               detail="created", status="ok"))
    db.commit()
    return WorkspaceDetail.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceResponse]:
    rows = workspace_service.list_workspaces(db, user.id)
    return [WorkspaceResponse.model_validate(w) for w in rows]


@router.get("/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(workspace: OwnedWorkspace) -> WorkspaceDetail:
    return WorkspaceDetail.model_validate(workspace)


@router.patch("/{workspace_id}", response_model=WorkspaceDetail)
def update_workspace(
    payload: WorkspaceUpdate, workspace: OwnedWorkspace, db: DbSession
) -> WorkspaceDetail:
    updated = workspace_service.update_workspace(db, workspace, payload)
    return WorkspaceDetail.model_validate(updated)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace: OwnedWorkspace, user: CurrentUser, db: DbSession) -> None:
    db.add(Log(user_id=user.id, event="workspace",
               detail=f"deleted {workspace.name!r}", status="ok"))
    workspace_service.delete_workspace(db, workspace)


# ------------------------------------------------------- assistant configuration
@router.get("/{workspace_id}/settings", response_model=AssistantSettingsResponse)
def get_settings(workspace: OwnedWorkspace) -> AssistantSettingsResponse:
    return AssistantSettingsResponse.model_validate(workspace.settings)


@router.patch("/{workspace_id}/settings", response_model=AssistantSettingsResponse)
def update_settings(
    payload: AssistantSettingsUpdate, workspace: OwnedWorkspace, db: DbSession
) -> AssistantSettingsResponse:
    try:
        updated = workspace_service.update_settings(db, workspace, payload)
    except workspace_service.UnknownModel as unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Model {unknown.args[0]!r} is not available. "
                   f"Choose one of: {', '.join(SELECTABLE_MODELS)}",
        )
    return AssistantSettingsResponse.model_validate(updated)
