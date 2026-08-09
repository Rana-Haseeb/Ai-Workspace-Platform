"""Workspace CRUD and assistant configuration.

The Phase 2 gate is ``test_settings_survive_a_reload`` — configuration written through the API
comes back unchanged from a fresh request, which is what "it persists" actually means.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def workspace(client, make_user):
    """A workspace owned by a fresh user, plus that user's auth headers."""
    user = make_user()
    created = client.post(
        "/api/workspaces",
        json={"name": "Research", "description": "Vector DB comparison", "icon": "flask"},
        headers=user["headers"],
    )
    assert created.status_code == 201, created.text
    return {"id": created.json()["id"], "headers": user["headers"], "body": created.json()}


# ----------------------------------------------------------------------- create
def test_create_returns_the_workspace_with_its_settings(workspace):
    body = workspace["body"]
    assert body["name"] == "Research"
    assert body["icon"] == "flask"
    assert body["settings"]["temperature"] == 0.3
    assert body["settings"]["max_tokens"] == 2048
    assert body["settings"]["assistant_name"] == "Research assistant"


def test_unknown_icon_falls_back_instead_of_failing(client, make_user):
    """An icon is decoration; it must not be able to block creating a workspace."""
    user = make_user()
    created = client.post(
        "/api/workspaces", json={"name": "Odd", "icon": "not-a-real-icon"}, headers=user["headers"]
    )
    assert created.status_code == 201
    assert created.json()["icon"] == "folder"


def test_emoji_icon_is_replaced_with_a_lucide_name(client, make_user):
    user = make_user()
    created = client.post("/api/workspaces", json={"name": "Emoji", "icon": "🧠"},
                          headers=user["headers"])
    assert created.status_code == 201
    assert created.json()["icon"] == "folder"


def test_blank_name_is_rejected(client, make_user):
    user = make_user()
    assert client.post("/api/workspaces", json={"name": ""},
                       headers=user["headers"]).status_code == 422


# ------------------------------------------------------------------------ read
def test_metadata_lists_the_choices_the_server_will_accept(client, make_user):
    user = make_user()
    meta = client.get("/api/workspaces/meta", headers=user["headers"]).json()
    assert "folder" in meta["icons"]
    assert all(isinstance(m["id"], str) and m["label"] for m in meta["models"])
    assert "professional" in meta["personalities"]
    assert "balanced" in meta["response_styles"]


def test_meta_route_is_not_shadowed_by_the_id_route(client, make_user):
    """`/meta` is declared before `/{workspace_id}`; this locks that ordering in."""
    user = make_user()
    assert client.get("/api/workspaces/meta", headers=user["headers"]).status_code == 200


# ---------------------------------------------------------------------- update
def test_rename_only_changes_what_was_sent(client, workspace):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}",
        json={"name": "Renamed"},
        headers=workspace["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    # Untouched fields survive a partial update.
    assert body["description"] == "Vector DB comparison"
    assert body["icon"] == "flask"


def test_another_user_cannot_rename_your_workspace(client, workspace, make_user):
    intruder = make_user("intruder@example.com")
    response = client.patch(
        f"/api/workspaces/{workspace['id']}",
        json={"name": "Hijacked"},
        headers=intruder["headers"],
    )
    assert response.status_code == 403


def test_another_user_cannot_delete_your_workspace(client, workspace, make_user):
    intruder = make_user("intruder@example.com")
    assert client.delete(
        f"/api/workspaces/{workspace['id']}", headers=intruder["headers"]
    ).status_code == 403
    # Still there for the owner.
    assert client.get(
        f"/api/workspaces/{workspace['id']}", headers=workspace["headers"]
    ).status_code == 200


def test_delete_removes_the_workspace_and_its_settings(client, workspace, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import AssistantSettings

    assert client.delete(
        f"/api/workspaces/{workspace['id']}", headers=workspace["headers"]
    ).status_code == 204
    assert client.get(
        f"/api/workspaces/{workspace['id']}", headers=workspace["headers"]
    ).status_code == 404

    session = sessionmaker(bind=engine)()
    assert session.query(AssistantSettings).filter_by(workspace_id=workspace["id"]).count() == 0
    session.close()


# ------------------------------------------------------- assistant configuration
def test_all_eight_configurable_fields_can_be_changed(client, workspace):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={
            "assistant_name": "Research analyst",
            "role": "Compares vector databases",
            "system_prompt": "Answer only from the supplied documents.",
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.9,
            "max_tokens": 4096,
            "personality": "socratic",
            "response_style": "bullets",
        },
        headers=workspace["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assistant_name"] == "Research analyst"
    assert body["role"] == "Compares vector databases"
    assert body["system_prompt"] == "Answer only from the supplied documents."
    assert body["model"] == "llama-3.3-70b-versatile"
    assert body["temperature"] == 0.9
    assert body["max_tokens"] == 4096
    assert body["personality"] == "socratic"
    assert body["response_style"] == "bullets"


# ------------------------------------------------------------- THE PHASE 2 GATE
def test_settings_survive_a_reload(client, workspace):
    """Change temperature and the system prompt, then re-read from scratch."""
    client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"temperature": 1.4, "system_prompt": "Be terse."},
        headers=workspace["headers"],
    )

    fresh = client.get(
        f"/api/workspaces/{workspace['id']}", headers=workspace["headers"]
    ).json()
    assert fresh["settings"]["temperature"] == 1.4
    assert fresh["settings"]["system_prompt"] == "Be terse."
    # And the fields that were not sent kept their values.
    assert fresh["settings"]["max_tokens"] == 2048
    assert fresh["settings"]["personality"] == "professional"


def test_partial_update_does_not_reset_the_other_fields(client, workspace):
    client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"assistant_name": "Analyst", "temperature": 0.7},
        headers=workspace["headers"],
    )
    client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"max_tokens": 1024},
        headers=workspace["headers"],
    )

    settings_row = client.get(
        f"/api/workspaces/{workspace['id']}/settings", headers=workspace["headers"]
    ).json()
    assert settings_row["assistant_name"] == "Analyst"
    assert settings_row["temperature"] == 0.7
    assert settings_row["max_tokens"] == 1024


@pytest.mark.parametrize(
    "payload",
    [
        {"temperature": 2.5},        # above the provider ceiling
        {"temperature": -0.1},
        {"max_tokens": 100},         # truncates mid-sentence
        {"max_tokens": 99999},
        {"personality": "grumpy"},   # not one of the five
        {"response_style": "haiku"},
        {"system_prompt": ""},
    ],
)
def test_out_of_range_settings_are_rejected(client, workspace, payload):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json=payload,
        headers=workspace["headers"],
    )
    assert response.status_code == 422, f"{payload} was accepted"


def test_unknown_model_is_rejected_with_a_helpful_message(client, workspace):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"model": "gpt-9-ultra"},
        headers=workspace["headers"],
    )
    assert response.status_code == 422
    assert "not available" in response.json()["detail"]


def test_model_can_be_reset_to_the_deployment_default(client, workspace):
    client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"model": "llama-3.3-70b-versatile"},
        headers=workspace["headers"],
    )
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"model": None},
        headers=workspace["headers"],
    )
    assert response.status_code == 200
    assert response.json()["model"] is None


def test_another_user_cannot_read_or_change_your_settings(client, workspace, make_user):
    intruder = make_user("intruder@example.com")
    assert client.get(
        f"/api/workspaces/{workspace['id']}/settings", headers=intruder["headers"]
    ).status_code == 403
    assert client.patch(
        f"/api/workspaces/{workspace['id']}/settings",
        json={"temperature": 2.0},
        headers=intruder["headers"],
    ).status_code == 403


def test_each_workspace_has_its_own_configuration(client, make_user):
    """Two workspaces of the same user must not share settings."""
    user = make_user()
    first = client.post("/api/workspaces", json={"name": "One"},
                        headers=user["headers"]).json()["id"]
    second = client.post("/api/workspaces", json={"name": "Two"},
                         headers=user["headers"]).json()["id"]

    client.patch(f"/api/workspaces/{first}/settings", json={"temperature": 1.9},
                 headers=user["headers"])

    assert client.get(f"/api/workspaces/{second}/settings",
                      headers=user["headers"]).json()["temperature"] == 0.3
