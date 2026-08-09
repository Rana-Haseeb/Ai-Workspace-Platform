"""Registration and login. No FastAPI in here — this module is plain Python over a session.

The separation is not decoration. It means every rule below can be tested by calling a function,
with no server, no client and no HTTP, and it means the same logic could be driven by a CLI or a
background job without change.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.security import hash_password, verify_password
from db.models import User


class EmailAlreadyRegistered(Exception):
    """Raised by :func:`register_user` when the address is taken."""


def normalise_email(email: str) -> str:
    """Lowercased and stripped.

    Without this, ``Ali@x.com`` and ``ali@x.com`` register as two accounts and the second person
    to sign up gets a confusing "email already registered" only some of the time.
    """
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(func.lower(User.email) == normalise_email(email))
    ).scalar_one_or_none()


def register_user(
    db: Session, email: str, password: str, display_name: str | None = None
) -> User:
    """Create a user. Raises :class:`EmailAlreadyRegistered` if the address is taken."""
    address = normalise_email(email)
    if get_user_by_email(db, address) is not None:
        raise EmailAlreadyRegistered(address)

    user = User(
        email=address,
        password_hash=hash_password(password),
        display_name=(display_name or "").strip() or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """The user if the credentials are correct, else None.

    A missing account still runs a hash verification against a throwaway hash. Returning early
    would make "no such user" measurably faster than "wrong password", which is enough to
    enumerate who has an account here.
    """
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


# Computed once at import so the timing-equalising path above costs the same as a real check.
_DUMMY_HASH = hash_password("not-a-real-password")
