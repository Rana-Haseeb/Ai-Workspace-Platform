"""Workspaces.

Phase 1 scope: create, list, and read one — the minimum needed to demonstrate that one user
cannot reach another user's data. Phase 2 adds update and delete, and the assistant-settings
sub-resource.

Every route here takes its owner from ``CurrentUser`` (derived from the signed token) and never
from the request body. A ``user_id`` field in a payload would be a request from the client to
choose whose data it operates on.
"""
from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from api.deps import CurrentUser, DbSession, OwnedWorkspace
from db.models import AssistantSettings, Workspace
from schemas.workspace import WorkspaceCreate, WorkspaceResponse

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate, user: CurrentUser, db: DbSession
) -> WorkspaceResponse:
    workspace = Workspace(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
    )
    # The settings row is created here rather than lazily, so every workspace has an assistant
    # configuration from the moment it exists and no downstream code has to handle its absence.
    workspace.settings = AssistantSettings()
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(user: CurrentUser, db: DbSession) -> list[WorkspaceResponse]:
    rows = db.execute(
        select(Workspace)
        .where(Workspace.user_id == user.id)
        .order_by(Workspace.created_at.desc())
    ).scalars().all()
    return [WorkspaceResponse.model_validate(w) for w in rows]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace: OwnedWorkspace) -> WorkspaceResponse:
    """Ownership is enforced by the dependency, so this function cannot forget to check."""
    return WorkspaceResponse.model_validate(workspace)
