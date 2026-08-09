"""Authentication, sessions, and tenant isolation.

The test that matters most here is ``test_a_user_cannot_read_another_users_workspace``. It is
the Phase 1 gate and the runnable answer to "how would you isolate user data?".
"""
from __future__ import annotations

import time

import pytest

from core.security import create_access_token, decode_token, hash_password, verify_password
from db.models import User
from services.auth_service import (
    EmailAlreadyRegistered,
    authenticate_user,
    normalise_email,
    register_user,
)


# --------------------------------------------------------------------- hashing
def test_password_hash_is_not_the_password():
    hashed = hash_password("correct-horse-battery")
    assert "correct-horse-battery" not in hashed
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct-horse-battery", hashed)
    assert not verify_password("Correct-horse-battery", hashed)


def test_same_password_hashes_differently_each_time():
    """argon2 salts every hash, so two users with the same password are not detectable."""
    assert hash_password("same-password") != hash_password("same-password")


def test_long_passwords_are_not_truncated():
    """The bcrypt defect this project avoids: two 72+ byte passwords must stay distinguishable."""
    base = "a" * 72
    hashed = hash_password(base + "ONE")
    assert not verify_password(base + "TWO", hashed)


def test_verify_returns_false_on_a_malformed_hash():
    assert verify_password("anything", "not-a-hash") is False


# ---------------------------------------------------------------------- tokens
def test_token_round_trips_to_the_user_id():
    assert decode_token(create_access_token(42)) == 42


def test_expired_token_is_rejected():
    token = create_access_token(1, expires_minutes=-1)
    assert decode_token(token) is None


def test_tampered_token_is_rejected():
    token = create_access_token(1)
    head, payload, signature = token.split(".")
    forged = f"{head}.{payload}.{signature[:-4] + 'AAAA'}"
    assert decode_token(forged) is None


def test_garbage_token_is_rejected():
    for value in ["", "abc", "a.b.c", "Bearer x"]:
        assert decode_token(value) is None


# --------------------------------------------------------------- service layer
def test_email_is_normalised(db):
    user = register_user(db, "  Ali@Example.COM ", "correct-horse-battery")
    assert user.email == "ali@example.com"
    assert normalise_email("  A@B.C ") == "a@b.c"


def test_registering_twice_is_rejected_case_insensitively(db):
    register_user(db, "ali@example.com", "correct-horse-battery")
    with pytest.raises(EmailAlreadyRegistered):
        register_user(db, "ALI@example.com", "another-password")


def test_authenticate_rejects_wrong_password_and_unknown_email(db):
    register_user(db, "ali@example.com", "correct-horse-battery")
    assert authenticate_user(db, "ali@example.com", "correct-horse-battery") is not None
    assert authenticate_user(db, "ali@example.com", "wrong") is None
    assert authenticate_user(db, "nobody@example.com", "correct-horse-battery") is None


def test_deactivated_user_cannot_authenticate(db):
    user = register_user(db, "ali@example.com", "correct-horse-battery")
    user.is_active = False
    db.commit()
    assert authenticate_user(db, "ali@example.com", "correct-horse-battery") is None


def test_unknown_email_takes_comparable_time_to_a_wrong_password(db):
    """Guards the timing-equalisation in authenticate_user.

    A bare early return made "no such user" roughly 100x faster than "wrong password", which is
    enough to enumerate registered addresses. The bound is deliberately loose — this asserts the
    dummy verification still happens, not a precise timing.
    """
    register_user(db, "ali@example.com", "correct-horse-battery")

    start = time.perf_counter()
    authenticate_user(db, "ali@example.com", "wrong-password")
    wrong_password = time.perf_counter() - start

    start = time.perf_counter()
    authenticate_user(db, "nobody@example.com", "wrong-password")
    unknown_email = time.perf_counter() - start

    assert unknown_email > wrong_password * 0.2


# -------------------------------------------------------------------- HTTP API
def test_register_returns_a_user_without_the_password_hash(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "ali@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "ali@example.com"
    assert "password" not in response.text
    assert "password_hash" not in response.text


def test_register_sets_an_httponly_cookie(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "ali@example.com", "password": "correct-horse-battery"},
    )
    cookie = response.headers["set-cookie"]
    assert "aiw_access=" in cookie
    # httpOnly is what stops an XSS bug from reading the session out of the page.
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


def test_short_password_is_rejected_before_reaching_the_database(client):
    response = client.post(
        "/api/auth/register", json={"email": "ali@example.com", "password": "short"}
    )
    assert response.status_code == 422


def test_invalid_email_is_rejected(client):
    response = client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": "correct-horse-battery"}
    )
    assert response.status_code == 422


def test_duplicate_registration_returns_409(client, make_user):
    user = make_user()
    response = client.post(
        "/api/auth/register", json={"email": user["email"], "password": "correct-horse-battery"}
    )
    assert response.status_code == 409


def test_login_failure_does_not_reveal_whether_the_account_exists(client, make_user):
    user = make_user()

    wrong_password = client.post(
        "/api/auth/login", json={"email": user["email"], "password": "wrong-password"}
    )
    no_such_user = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]


def test_me_requires_authentication(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_authenticated_user(client, make_user):
    user = make_user()
    response = client.get("/api/auth/me", headers=user["headers"])
    assert response.status_code == 200
    assert response.json()["email"] == user["email"]


def test_logout_clears_the_cookie(client, make_user):
    make_user()   # the client now holds a session cookie
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_a_deleted_user_is_rejected_even_with_a_valid_token(client, make_user, engine):
    """Identity is re-read per request, so deletion takes effect immediately."""
    from sqlalchemy.orm import sessionmaker

    user = make_user()
    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 200

    session = sessionmaker(bind=engine)()
    session.delete(session.get(User, user["id"]))
    session.commit()
    session.close()

    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401


# ------------------------------------------------------- THE PHASE 1 GATE
def test_a_user_cannot_read_another_users_workspace(client, make_user):
    """One user's workspace is unreachable by another. This is the isolation guarantee."""
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    created = client.post(
        "/api/workspaces", json={"name": "Alice research"}, headers=alice["headers"]
    )
    assert created.status_code == 201, created.text
    workspace_id = created.json()["id"]

    # Alice can read her own.
    assert client.get(
        f"/api/workspaces/{workspace_id}", headers=alice["headers"]
    ).status_code == 200

    # Bob cannot.
    forbidden = client.get(f"/api/workspaces/{workspace_id}", headers=bob["headers"])
    assert forbidden.status_code == 403, forbidden.text

    # And an anonymous caller is stopped one step earlier, at authentication. The cookie jar has
    # to be emptied first: registering set a session cookie, so a header-less request would
    # otherwise still be authenticated as whoever registered last.
    client.cookies.clear()
    assert client.get(f"/api/workspaces/{workspace_id}").status_code == 401


def test_listing_workspaces_only_returns_your_own(client, make_user):
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    client.post("/api/workspaces", json={"name": "Alice A"}, headers=alice["headers"])
    client.post("/api/workspaces", json={"name": "Alice B"}, headers=alice["headers"])
    client.post("/api/workspaces", json={"name": "Bob only"}, headers=bob["headers"])

    alice_names = {w["name"] for w in client.get(
        "/api/workspaces", headers=alice["headers"]).json()}
    bob_names = {w["name"] for w in client.get(
        "/api/workspaces", headers=bob["headers"]).json()}

    assert alice_names == {"Alice A", "Alice B"}
    assert bob_names == {"Bob only"}


def test_creating_a_workspace_cannot_assign_it_to_another_user(client, make_user):
    """Ownership comes from the token. A user_id in the body must not be honoured."""
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")

    created = client.post(
        "/api/workspaces",
        json={"name": "Injected", "user_id": bob["id"]},
        headers=alice["headers"],
    )
    assert created.status_code == 201

    assert client.get("/api/workspaces", headers=bob["headers"]).json() == []
    assert len(client.get("/api/workspaces", headers=alice["headers"]).json()) == 1


def test_every_new_workspace_gets_an_assistant_configuration(client, make_user, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import AssistantSettings

    alice = make_user()
    created = client.post(
        "/api/workspaces", json={"name": "Research"}, headers=alice["headers"]
    )
    workspace_id = created.json()["id"]

    session = sessionmaker(bind=engine)()
    settings_row = session.query(AssistantSettings).filter_by(workspace_id=workspace_id).one()
    assert settings_row.temperature == 0.3
    assert settings_row.max_tokens == 2048
    session.close()


def test_health_reports_no_secrets(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "password" not in str(body).lower()
    assert "key" not in str(body).lower()
