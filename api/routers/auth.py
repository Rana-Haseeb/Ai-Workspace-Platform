"""Registration, login, logout, and "who am I".

Routers stay thin on purpose: validate, call a service, shape a response. The rules about what
makes a valid registration or a successful login live in :mod:`services.auth_service`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from api.deps import ACCESS_COOKIE, CurrentUser, DbSession
from core.config import settings
from core.security import create_access_token
from db.models import Log
from schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from services.auth_service import EmailAlreadyRegistered, authenticate_user, register_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_session(response: Response, user_id: int) -> str:
    """Sign a token and attach it as an httpOnly cookie."""
    token = create_access_token(user_id)
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=token,
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,          # unreadable from JavaScript, so XSS cannot steal the session
        samesite="lax",         # not sent on cross-site POSTs, which blocks basic CSRF
        secure=not settings.is_sqlite(),   # HTTPS-only in production; SQLite implies local dev
        path="/",
    )
    return token


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: DbSession) -> AuthResponse:
    try:
        user = register_user(db, payload.email, payload.password, payload.display_name)
    except EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    token = _issue_session(response, user.id)
    db.add(Log(user_id=user.id, event="auth", detail="register", status="ok"))
    db.commit()
    return AuthResponse(user=UserResponse.model_validate(user), access_token=token)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        # One message for both "no such account" and "wrong password". Telling them apart is
        # how an attacker confirms which addresses are registered here.
        db.add(Log(event="auth", detail="login failed", status="failed"))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = _issue_session(response, user.id)
    db.add(Log(user_id=user.id, event="auth", detail="login", status="ok"))
    db.commit()
    return AuthResponse(user=UserResponse.model_validate(user), access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Clear the session cookie.

    A signed JWT cannot be revoked server-side without a denylist, so a token already copied out
    of the browser stays valid until it expires. Clearing the cookie is what logout means here,
    and the short expiry is what bounds the rest. The security review says so explicitly rather
    than implying logout does more than it does.
    """
    response.delete_cookie(key=ACCESS_COOKIE, path="/")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
