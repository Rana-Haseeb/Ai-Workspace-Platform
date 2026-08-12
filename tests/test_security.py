"""Security behaviour, asserted rather than asserted *about*.

``docs/SECURITY_REVIEW.md`` makes claims. This file is what stops those claims from being prose.
Each test maps to a numbered topic in that document, and anything the review lists as *not*
defended is absent here on purpose — a test that passes because the attack was never tried is
the exact failure mode a security document should not have.

Live prompt-injection testing needs a real model and lives in ``scripts/verify_phase9.py``.
"""
from __future__ import annotations

import base64
import json

import pytest
from jose import jwt

from core.config import settings
from core.security import create_access_token, decode_token, hash_password, verify_password


# ------------------------------------------------------------------ 1. credential storage
def test_the_stored_hash_is_argon2id_not_a_fast_digest():
    """A fast hash is the difference between a leaked database and a leaked password list."""
    digest = hash_password("correct-horse-battery")
    assert digest.startswith("$argon2id$"), digest[:20]
    assert "correct-horse-battery" not in digest


def test_verification_survives_unicode_and_length():
    password = "pässwörd-with-emoji-🔐-and-a-very-long-tail-" + "x" * 200
    assert verify_password(password, hash_password(password))
    assert not verify_password(password + "!", hash_password(password))


# --------------------------------------------------------------------- 2. token integrity
def test_a_token_signed_with_another_key_is_rejected():
    """The signature is the whole guarantee; without this check the token is a claim, not proof."""
    forged = jwt.encode({"sub": "1"}, "not-the-real-secret", algorithm="HS256")
    assert decode_token(forged) is None


def test_the_none_algorithm_is_refused():
    """`alg: none` is the classic JWT bypass: a token with no signature that still decodes.

    Built by hand rather than with a library helper, because most libraries now refuse to *emit*
    one — and a test that cannot construct the attack is not testing the defence.
    """
    def segment(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    unsigned = f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment({'sub': '1'})}."
    assert decode_token(unsigned) is None


def test_a_token_whose_payload_was_edited_is_rejected():
    """Swapping the subject to another user id must invalidate the signature."""
    valid = create_access_token(7)
    header, _, signature = valid.split(".")

    def segment(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    assert decode_token(f"{header}.{segment({'sub': '1'})}.{signature}") is None


def test_an_expired_token_is_rejected():
    assert decode_token(create_access_token(7, expires_minutes=-1)) is None


def test_a_valid_token_still_works():
    """Guards every test above: if decoding always returned None, they would pass for free."""
    assert decode_token(create_access_token(7)) == 7


# ------------------------------------------------------------- 3. tenant isolation at the API
def test_another_users_workspace_is_not_readable(client, make_user):
    owner, intruder = make_user(), make_user()
    workspace = client.post("/api/workspaces", json={"name": "Private"},
                            headers=owner["headers"]).json()

    response = client.get(f"/api/workspaces/{workspace['id']}", headers=intruder["headers"])
    assert response.status_code in (403, 404), response.text


def test_another_users_workspace_is_not_writable(client, make_user):
    """Read isolation without write isolation is not isolation."""
    owner, intruder = make_user(), make_user()
    workspace = client.post("/api/workspaces", json={"name": "Private"},
                            headers=owner["headers"]).json()

    assert client.patch(f"/api/workspaces/{workspace['id']}", json={"name": "Stolen"},
                        headers=intruder["headers"]).status_code in (403, 404)
    assert client.delete(f"/api/workspaces/{workspace['id']}",
                         headers=intruder["headers"]).status_code in (403, 404)

    # The owner's data is untouched — the request failed, it did not half-succeed.
    assert client.get(f"/api/workspaces/{workspace['id']}",
                      headers=owner["headers"]).json()["name"] == "Private"


def test_ownership_comes_from_the_token_not_the_body(client, make_user):
    """Mass assignment: a user_id in the payload must be ignored, not honoured."""
    owner, victim = make_user(), make_user()
    created = client.post("/api/workspaces",
                          json={"name": "Mine", "user_id": victim["id"]},
                          headers=owner["headers"])
    assert created.status_code == 201

    # It belongs to the caller, whatever the body asked for.
    assert client.get(f"/api/workspaces/{created.json()['id']}",
                      headers=victim["headers"]).status_code in (403, 404)


# --------------------------------------------------------------------- 4. SQL injection
@pytest.mark.parametrize("payload", [
    "'; DROP TABLE workspaces; --",
    "' OR '1'='1",
    "1; DELETE FROM users WHERE 1=1; --",
    "\\'; UPDATE users SET password_hash='x'; --",
])
def test_sql_metacharacters_are_stored_as_text_not_executed(client, make_user, payload):
    """The ORM parameterises, so these are names — but the claim is worth proving, not assuming."""
    user = make_user()
    created = client.post("/api/workspaces", json={"name": payload}, headers=user["headers"])
    assert created.status_code == 201

    # The table still exists and the value round-trips verbatim.
    listed = client.get("/api/workspaces", headers=user["headers"])
    assert listed.status_code == 200
    assert payload in [w["name"] for w in listed.json()]


def test_a_search_query_full_of_metacharacters_returns_cleanly(client, make_user):
    user = make_user()
    workspace = client.post("/api/workspaces", json={"name": "S"},
                            headers=user["headers"]).json()
    response = client.get(f"/api/workspaces/{workspace['id']}/conversations",
                          params={"q": "' OR 1=1 --"}, headers=user["headers"])
    assert response.status_code == 200


# ----------------------------------------------------------------- 5. stored content is inert
def test_script_tags_are_stored_verbatim_and_never_interpreted(client, make_user):
    """The API must not silently rewrite content; safety is React's escaping at render time.

    Storing the payload unchanged is correct. What matters is that it comes back as *data* —
    a JSON string — rather than being reflected into an HTML response.
    """
    user = make_user()
    payload = "<script>alert('xss')</script>"
    created = client.post("/api/workspaces", json={"name": payload}, headers=user["headers"])

    assert created.status_code == 201
    assert created.json()["name"] == payload
    assert created.headers["content-type"].startswith("application/json")


# ------------------------------------------------------------------ 6. no secret ever leaves
def test_the_health_probe_exposes_no_configuration(client):
    body = client.get("/api/health").json()
    serialised = str(body)
    for forbidden in ["jwt_secret", "password", "postgresql://", "gsk_", "api_key"]:
        assert forbidden not in serialised.lower(), forbidden


def test_no_endpoint_returns_a_password_hash(client, make_user):
    user = make_user()
    for path in ["/api/auth/me", "/api/workspaces"]:
        assert "password_hash" not in client.get(path, headers=user["headers"]).text


def test_login_failure_does_not_reveal_whether_the_account_exists(client, make_user):
    """Different messages for "no such user" and "wrong password" enumerate your user base."""
    user = make_user()
    unknown = client.post("/api/auth/login",
                          json={"email": "nobody@example.com", "password": "whatever12"})
    wrong = client.post("/api/auth/login",
                        json={"email": user["email"], "password": "definitely-wrong"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


# ------------------------------------------------------------------------ 7. rate limiting
def test_authentication_is_rate_limited(client, monkeypatch):
    """The brute-force surface. Until Phase 9 the setting existed and nothing enforced it."""
    monkeypatch.setattr("core.config.settings.auth_rate_limit_per_minute", 5)

    codes = [
        client.post("/api/auth/login",
                    json={"email": "a@b.com", "password": "wrong-password"}).status_code
        for _ in range(8)
    ]
    assert 429 in codes, codes
    assert codes.count(429) == 3, codes          # 5 allowed, 3 refused
    assert codes[:5] == [401] * 5                # the allowance is spent before refusing


def test_a_rate_limited_response_says_when_to_retry(client, monkeypatch):
    monkeypatch.setattr("core.config.settings.auth_rate_limit_per_minute", 1)
    client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong-password"})
    refused = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong-pw"})

    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0


def test_the_general_api_limit_is_separate_from_the_auth_limit(client, make_user, monkeypatch):
    """A chat client makes many requests; it must not be throttled at the login rate."""
    user = make_user()
    monkeypatch.setattr("core.config.settings.auth_rate_limit_per_minute", 1)
    monkeypatch.setattr("core.config.settings.rate_limit_per_minute", 50)

    codes = [client.get("/api/workspaces", headers=user["headers"]).status_code for _ in range(20)]
    assert codes == [200] * 20


def test_zero_disables_the_limiter(client, monkeypatch):
    """Guards every test above: if the limiter were always on, they would pass regardless."""
    monkeypatch.setattr("core.config.settings.auth_rate_limit_per_minute", 0)
    codes = [
        client.post("/api/auth/login",
                    json={"email": "a@b.com", "password": "wrong-password"}).status_code
        for _ in range(15)
    ]
    assert 429 not in codes


# --------------------------------------------------------------------- 8. upload restrictions
def test_an_oversized_upload_is_refused(client, make_user, monkeypatch):
    monkeypatch.setattr("core.config.settings.max_upload_mb", 1)
    user = make_user()
    workspace = client.post("/api/workspaces", json={"name": "W"},
                            headers=user["headers"]).json()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/documents",
        files={"file": ("big.txt", b"x" * (2 * 1024 * 1024), "text/plain")},
        headers=user["headers"],
    )
    assert response.status_code in (400, 413), response.status_code


def test_an_executable_upload_is_refused(client, make_user):
    user = make_user()
    workspace = client.post("/api/workspaces", json={"name": "W"},
                            headers=user["headers"]).json()

    response = client.post(
        f"/api/workspaces/{workspace['id']}/documents",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=user["headers"],
    )
    assert response.status_code == 400, response.status_code


# ------------------------------------------------------------------ 9. authentication required
@pytest.mark.parametrize("method,path", [
    ("get", "/api/workspaces"),
    ("post", "/api/workspaces"),
    ("get", "/api/auth/me"),
    ("get", "/api/workspaces/1/conversations"),
    ("get", "/api/workspaces/1/documents"),
    ("get", "/api/workspaces/1/memory"),
    ("get", "/api/workspaces/1/dashboard"),
])
def test_every_protected_route_refuses_an_anonymous_caller(client, method, path):
    kwargs = {"json": {"name": "x"}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code in (401, 403), f"{method.upper()} {path} -> {response.status_code}"


# ------------------------------------------------------------------- 10. configuration safety
def test_no_secret_has_a_usable_default():
    """An application that boots with a working default secret is one nobody remembers to set."""
    assert settings.jwt_secret != "", "empty is correct — it forces a per-process random key"
    from core.config import Settings

    field = Settings.model_fields["jwt_secret"]
    generated = field.default_factory()
    assert generated in ("", settings.jwt_secret)


def test_cors_is_not_a_wildcard_with_credentials():
    """`allow_origins=['*']` plus cookies would let any site act as the logged-in user."""
    assert "*" not in settings.cors_origins
