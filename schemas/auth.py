"""Request and response models for authentication.

These are the API contract. FastAPI validates against them before a router function runs and
generates the OpenAPI docs from them, so a field constraint written here is enforced *and*
documented in one place.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # 8 is the NIST minimum. No composition rules (a symbol, a digit, a capital) — they push
    # people toward predictable substitutions like "Password1!" while blocking passphrases,
    # which are stronger. Length is the property that matters.
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """A user as the client sees them. Note what is absent: ``password_hash``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    display_name: str | None
    created_at: datetime


class AuthResponse(BaseModel):
    """Returned by register and login.

    The token is also set as an httpOnly cookie, which is what the browser actually uses. It is
    returned in the body as well so non-browser clients — the test suite, ``/docs``, curl — can
    authenticate with a bearer header.
    """

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
