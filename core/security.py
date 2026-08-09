"""Password hashing and session tokens.

**Why argon2 and not bcrypt.** bcrypt silently truncates input at 72 bytes, so two different long
passwords can hash identically — a real defect, not a theoretical one. argon2id is the current
password-hashing competition winner and has no such limit. ``argon2-cffi`` also salts every hash
itself, so there is no salt to store or get wrong.

**Why the token is a JWT and what it does not contain.** The token carries the user id and an
expiry, and nothing else. No email, no role, no workspace list. Anything else would be a copy of
database state that goes stale the moment the database changes, and a JWT payload is *readable
by anyone holding it* — signed, not encrypted. Everything the request needs beyond identity is
looked up fresh from the database on each call.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from core.config import settings
from core.logging import get_logger

log = get_logger("security")

_hasher = PasswordHasher()


def _signing_key() -> str:
    """The JWT signing key, or a per-process random one in development.

    An empty ``JWT_SECRET`` must never fall back to a hard-coded default — that would make every
    deployment of this code share a key, so anyone with the source could mint valid tokens. A
    random per-process key is safe instead; the only cost is that logins do not survive a restart,
    which the warning says out loud so it is never mistaken for a bug.
    """
    if settings.jwt_secret:
        return settings.jwt_secret
    global _EPHEMERAL_KEY
    if _EPHEMERAL_KEY is None:
        _EPHEMERAL_KEY = secrets.token_urlsafe(48)
        log.warning(
            "JWT_SECRET is not set. Using a random key for this process only — every login "
            "will be invalidated when the server restarts. Set JWT_SECRET in .env: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return _EPHEMERAL_KEY


_EPHEMERAL_KEY: str | None = None


# ------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    """argon2id hash, salt included. The plaintext is never stored or logged."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True if ``password`` matches. Returns False rather than raising on a malformed hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


# ---------------------------------------------------------------------- tokens
def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    """Sign a token identifying ``user_id``."""
    minutes = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),          # the JWT spec requires `sub` to be a string
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(payload, _signing_key(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> int | None:
    """The user id inside a valid, unexpired token, or None.

    Every failure mode — bad signature, expired, malformed, missing subject — returns None
    rather than raising, so callers cannot accidentally distinguish them. A caller that knows
    *why* a token failed tends to leak that difference back to the client.
    """
    try:
        payload = jwt.decode(token, _signing_key(), algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        return int(subject) if subject is not None else None
    except (JWTError, ValueError, TypeError):
        return None
