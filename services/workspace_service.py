"""Workspace and assistant-configuration logic. No FastAPI in here.

Ownership is *not* re-checked in this module. The API layer resolves a workspace through
``get_owned_workspace`` before anything here is called, so these functions receive a workspace
that already belongs to the caller. Checking twice would suggest the check is optional
somewhere, which is exactly the confusion that leads to a route forgetting it.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import SELECTABLE_MODELS
from db.models import AssistantSettings, Workspace
from schemas.settings import AssistantSettingsUpdate
from schemas.workspace import WORKSPACE_ICONS, WorkspaceCreate, WorkspaceUpdate


class UnknownModel(Exception):
    """Raised when a workspace asks for a model the deployment does not offer."""


def _validated_icon(icon: str | None) -> str | None:
    """Fall back to the default rather than rejecting an unknown icon.

    An icon is decoration. Refusing to save a whole workspace because of it would trade a
    cosmetic problem for a functional one.
    """
    if icon is None:
        return None
    return icon if icon in WORKSPACE_ICONS else "folder"


def list_workspaces(db: Session, user_id: int) -> list[Workspace]:
    return list(
        db.execute(
            select(Workspace)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.created_at.desc())
        ).scalars()
    )


def create_workspace(db: Session, user_id: int, payload: WorkspaceCreate) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        icon=_validated_icon(payload.icon) or "folder",
    )
    # Created eagerly so every workspace has an assistant configuration from the moment it
    # exists, and no downstream code has to handle its absence.
    workspace.settings = AssistantSettings(
        assistant_name=f"{payload.name.strip()} assistant"[:120],
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


def update_workspace(db: Session, workspace: Workspace, payload: WorkspaceUpdate) -> Workspace:
    """Rename, re-describe or re-icon a workspace. Only the fields sent are touched."""
    fields = payload.model_dump(exclude_unset=True)

    if "name" in fields and fields["name"] is not None:
        workspace.name = fields["name"].strip()
    if "description" in fields:
        description = (fields["description"] or "").strip()
        workspace.description = description or None
    if "icon" in fields:
        workspace.icon = _validated_icon(fields["icon"]) or workspace.icon

    db.commit()
    db.refresh(workspace)
    return workspace


def delete_workspace(db: Session, workspace: Workspace) -> None:
    """Delete a workspace and everything inside it.

    The cascade is declared on the relationships, so conversations, messages, documents, chunks
    and embeddings all go with it. Memory items scoped to this workspace go too; memory scoped
    to the user (``workspace_id`` NULL) survives, because it was never about this workspace.
    """
    db.delete(workspace)
    db.commit()


def update_settings(
    db: Session, workspace: Workspace, payload: AssistantSettingsUpdate
) -> AssistantSettings:
    """Apply only the fields the client actually sent.

    ``exclude_unset`` is what distinguishes "model: null, use the deployment default" from
    "model not mentioned, leave it alone". Without it, every partial update would silently reset
    every field the form did not include.
    """
    fields = payload.model_dump(exclude_unset=True)

    if "model" in fields and fields["model"] is not None:
        if fields["model"] not in SELECTABLE_MODELS:
            raise UnknownModel(fields["model"])

    settings_row = workspace.settings
    for key, value in fields.items():
        setattr(settings_row, key, value.strip() if isinstance(value, str) else value)

    db.commit()
    db.refresh(settings_row)
    return settings_row
