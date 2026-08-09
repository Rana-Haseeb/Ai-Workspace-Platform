"""Phase 2 gate: workspaces are configurable and the configuration persists.

Runs in-process against a throwaway in-memory database. No server, no network, nothing left
behind.

    python scripts/verify_phase2.py

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
from db.base import Base                           # noqa: E402
from schemas.workspace import WORKSPACE_ICONS      # noqa: E402
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
    body = client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD}
    ).json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}}


def main() -> int:
    client = build_client()
    owner = register(client, "owner@example.com")
    other = register(client, "other@example.com")

    print("\n1. Creating a workspace")
    created = client.post(
        "/api/workspaces",
        json={"name": "Research", "description": "Vector DBs", "icon": "flask"},
        headers=owner["headers"],
    )
    check("created", created.status_code == 201, f"HTTP {created.status_code}")
    workspace = created.json()
    workspace_id = workspace["id"]
    check("assistant configuration created with it", "settings" in workspace)
    check("icon stored", workspace["icon"] == "flask", workspace["icon"])

    unknown_icon = client.post(
        "/api/workspaces", json={"name": "Odd", "icon": "🧠"}, headers=owner["headers"]
    )
    check(
        "emoji icon replaced with a lucide name",
        unknown_icon.json()["icon"] == "folder",
        unknown_icon.json()["icon"],
    )

    print("\n2. The eight configurable fields")
    fields = {
        "assistant_name": "Research analyst",
        "role": "Compares vector databases",
        "system_prompt": "Answer only from the supplied documents.",
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.9,
        "max_tokens": 4096,
        "personality": "socratic",
        "response_style": "bullets",
    }
    updated = client.patch(
        f"/api/workspaces/{workspace_id}/settings", json=fields, headers=owner["headers"]
    )
    check("all eight accepted", updated.status_code == 200, f"HTTP {updated.status_code}")
    for key, expected in fields.items():
        check(f"  {key}", updated.json().get(key) == expected, str(updated.json().get(key)))

    print("\n3. Validation")
    for label, payload in [
        ("temperature above 2.0 rejected", {"temperature": 2.5}),
        ("temperature below 0 rejected", {"temperature": -0.1}),
        ("max_tokens below 256 rejected", {"max_tokens": 100}),
        ("unknown personality rejected", {"personality": "grumpy"}),
        ("empty system prompt rejected", {"system_prompt": ""}),
        ("unknown model rejected", {"model": "gpt-9-ultra"}),
    ]:
        response = client.patch(
            f"/api/workspaces/{workspace_id}/settings", json=payload, headers=owner["headers"]
        )
        check(label, response.status_code == 422, f"HTTP {response.status_code}")

    print("\n4. Isolation still holds")
    for label, call in [
        ("another user cannot read settings",
         lambda: client.get(f"/api/workspaces/{workspace_id}/settings", headers=other["headers"])),
        ("another user cannot change settings",
         lambda: client.patch(f"/api/workspaces/{workspace_id}/settings",
                              json={"temperature": 2.0}, headers=other["headers"])),
        ("another user cannot rename",
         lambda: client.patch(f"/api/workspaces/{workspace_id}",
                              json={"name": "Hijacked"}, headers=other["headers"])),
        ("another user cannot delete",
         lambda: client.delete(f"/api/workspaces/{workspace_id}", headers=other["headers"])),
    ]:
        check(label, call().status_code == 403)

    print("\n5. THE GATE: configuration survives a reload")
    client.patch(
        f"/api/workspaces/{workspace_id}/settings",
        json={"temperature": 1.2, "system_prompt": "Be terse."},
        headers=owner["headers"],
    )
    fresh = client.get(f"/api/workspaces/{workspace_id}", headers=owner["headers"]).json()
    check("temperature persisted", fresh["settings"]["temperature"] == 1.2,
          str(fresh["settings"]["temperature"]))
    check("system prompt persisted", fresh["settings"]["system_prompt"] == "Be terse.")
    check("untouched fields kept their values", fresh["settings"]["max_tokens"] == 4096,
          str(fresh["settings"]["max_tokens"]))
    check("assistant name kept", fresh["settings"]["assistant_name"] == "Research analyst")

    print("\n6. Metadata the UI renders from")
    meta = client.get("/api/workspaces/meta", headers=owner["headers"]).json()
    check("icon list served by the API", meta["icons"] == WORKSPACE_ICONS,
          f"{len(meta['icons'])} icons")
    check("no emoji among them", all(i.isascii() for i in meta["icons"]))
    check("models offered", len(meta["models"]) > 0, f"{len(meta['models'])} models")

    print("\n7. Deleting a workspace")
    deleted = client.delete(f"/api/workspaces/{workspace_id}", headers=owner["headers"])
    check("deleted", deleted.status_code == 204, f"HTTP {deleted.status_code}")
    check(
        "gone afterwards",
        client.get(f"/api/workspaces/{workspace_id}", headers=owner["headers"]).status_code == 404,
    )

    if failures:
        print(f"\nPHASE 2 FAILED - {len(failures)} problem(s):")
        for problem in failures:
            print(f"   - {problem}")
        return 1

    print("\nPHASE 2 PASSED - workspace CRUD, 8 assistant fields, validation, persistence.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
