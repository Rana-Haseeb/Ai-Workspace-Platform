"""Shared FastAPI dependencies: the database session, the current user, and ownership checks.

``get_owned_workspace`` is the single chokepoint for tenant isolation. Every route that touches
workspace-scoped data depends on it rather than reading a ``workspace_id`` from the request and
querying with it. That is deliberate: isolation implemented once, in one function, is auditable;
isolation implemented per-route is a rule someone eventually forgets.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

from core.security import decode_token
from db.base import SessionLocal
from db.models import User, Workspace

ACCESS_COOKIE = "aiw_access"


def get_db():
    """A request-scoped session, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def _token_from(authorization: str | None, cookie: str | None) -> str | None:
    """Prefer the bearer header, fall back to the cookie.

    The browser uses the httpOnly cookie, which JavaScript cannot read and therefore cannot leak
    through an XSS bug. The header exists so ``/docs``, curl and the test suite can authenticate
    without a cookie jar.
    """
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return cookie or None


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    aiw_access: Annotated[str | None, Cookie()] = None,
) -> User:
    """The authenticated user, or 401.

    The user is loaded fresh from the database on every request rather than trusted from the
    token body, so deactivating or deleting an account takes effect immediately instead of when
    the token happens to expire.
    """
    unauthorised = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = _token_from(authorization, aiw_access)
    if token is None:
        raise unauthorised

    user_id = decode_token(token)
    if user_id is None:
        raise unauthorised

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorised
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_owned_workspace(
    db: DbSession,
    user: CurrentUser,
    workspace_id: Annotated[int, Path()],
) -> Workspace:
    """The workspace, if it belongs to the caller. 403 otherwise.

    403 rather than 404 is a deliberate, arguable choice. 404 would hide whether the workspace
    exists at all, which leaks marginally less; 403 states the rule plainly and is what the
    frontend needs in order to show "you don't have access" rather than "not found". The ids are
    sequential integers, so existence is already guessable and little is being protected by
    pretending otherwise. The security review documents this trade-off.
    """
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if workspace.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This workspace belongs to another user",
        )
    return workspace


OwnedWorkspace = Annotated[Workspace, Depends(get_owned_workspace)]
