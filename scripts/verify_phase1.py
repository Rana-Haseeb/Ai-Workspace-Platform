"""Phase 1 gate: authentication works and users are isolated from each other.

Runs the whole flow in-process against a throwaway in-memory database, so it needs no server,
no network and no fixtures, and leaves nothing behind.

    python scripts/verify_phase1.py

Exits non-zero on any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient          # noqa: E402
from sqlalchemy import create_engine               # noqa: E402
from sqlalchemy.orm import sessionmaker            # noqa: E402
from sqlalchemy.pool import StaticPool             # noqa: E402

from api.deps import get_db                        # noqa: E402
from api.main import create_app                    # noqa: E402
from core.security import create_access_token, decode_token, hash_password, verify_password  # noqa: E402
from db.base import Base                           # noqa: E402
import db.models                                   # noqa: E402,F401

PASSWORD = "correct-horse-battery"
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        failures.append(label)


def build_client() -> TestClient:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def register(client: TestClient, email: str) -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"id": body["user"]["id"], "headers": {"Authorization": f"Bearer {body['access_token']}"}}


def main() -> int:
    print("\n1. Password hashing")
    hashed = hash_password(PASSWORD)
    check("argon2id, not plaintext", hashed.startswith("$argon2id$") and PASSWORD not in hashed)
    check("correct password verifies", verify_password(PASSWORD, hashed))
    check("wrong password rejected", not verify_password("wrong", hashed))
    check("salted per hash", hash_password(PASSWORD) != hash_password(PASSWORD))
    long_base = "a" * 72
    check(
        "no 72-byte truncation (the bcrypt defect)",
        not verify_password(long_base + "TWO", hash_password(long_base + "ONE")),
    )

    print("\n2. Session tokens")
    check("round-trips to the user id", decode_token(create_access_token(7)) == 7)
    check("expired token rejected", decode_token(create_access_token(7, expires_minutes=-1)) is None)
    token = create_access_token(7)
    forged = token[:-4] + "AAAA"
    check("tampered signature rejected", decode_token(forged) is None)

    client = build_client()

    print("\n3. Registration and login")
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    check("two accounts created", alice["id"] != bob["id"])

    duplicate = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )
    check("duplicate email rejected", duplicate.status_code == 409, f"HTTP {duplicate.status_code}")

    weak = client.post("/api/auth/register", json={"email": "x@example.com", "password": "short"})
    check("short password rejected", weak.status_code == 422, f"HTTP {weak.status_code}")

    wrong_password = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "wrong"}
    )
    unknown_user = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    check(
        "login failures are indistinguishable",
        wrong_password.status_code == unknown_user.status_code == 401
        and wrong_password.json()["detail"] == unknown_user.json()["detail"],
        wrong_password.json()["detail"],
    )

    cookie = duplicate.headers.get("set-cookie", "") or client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    ).headers.get("set-cookie", "")
    check("session cookie is httpOnly", "httponly" in cookie.lower())
    check("session cookie is SameSite=Lax", "samesite=lax" in cookie.lower())

    print("\n4. Tenant isolation")
    created = client.post(
        "/api/workspaces", json={"name": "Alice research"}, headers=alice["headers"]
    )
    check("owner can create", created.status_code == 201, f"HTTP {created.status_code}")
    workspace_id = created.json()["id"]

    own = client.get(f"/api/workspaces/{workspace_id}", headers=alice["headers"])
    check("owner can read it", own.status_code == 200, f"HTTP {own.status_code}")

    other = client.get(f"/api/workspaces/{workspace_id}", headers=bob["headers"])
    check("another user gets 403", other.status_code == 403, f"HTTP {other.status_code}")

    client.cookies.clear()
    anonymous = client.get(f"/api/workspaces/{workspace_id}")
    check("anonymous gets 401", anonymous.status_code == 401, f"HTTP {anonymous.status_code}")

    bob_list = client.get("/api/workspaces", headers=bob["headers"]).json()
    check("listing shows only your own", bob_list == [], f"{len(bob_list)} rows")

    injected = client.post(
        "/api/workspaces",
        json={"name": "Injected", "user_id": bob["id"]},
        headers=alice["headers"],
    )
    still_empty = client.get("/api/workspaces", headers=bob["headers"]).json()
    check(
        "user_id in the body is ignored",
        injected.status_code == 201 and still_empty == [],
        f"{len(still_empty)} rows on the other account",
    )

    print("\n5. Response hygiene")
    me = client.get("/api/auth/me", headers=alice["headers"])
    check("no password hash in any response", "password" not in me.text.lower())
    health = client.get("/api/health").json()
    check("health endpoint leaks nothing", "key" not in str(health).lower())

    if failures:
        print(f"\nPHASE 1 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 1 PASSED - argon2 hashing, signed sessions, and 403 isolation verified.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
