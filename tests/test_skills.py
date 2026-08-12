"""Skills and the prompt library.

The Phase 6 gate is ``test_every_registered_skill_runs`` — parameterised over the registry, so a
newly added skill is covered the moment it is registered, with no test to write.
"""
from __future__ import annotations

import pytest

from services import prompt_service
from skills import registry
from skills.base import CATEGORIES, Skill


# ------------------------------------------------------------------- the registry
def test_at_least_six_skills_are_registered():
    """The challenge asks for six. Fewer is a failure; more is fine."""
    assert len(registry.SKILLS) >= 6, f"only {len(registry.SKILLS)} registered"


@pytest.mark.parametrize("skill", registry.all_skills(), ids=lambda s: s.slug)
def test_every_skill_is_well_formed(skill: Skill):
    assert skill.slug and skill.slug.replace("_", "").isalnum()
    assert skill.name and skill.description
    assert skill.category in CATEGORIES
    assert len(skill.system_prompt.strip()) > 50, "a one-line system prompt is not a skill"
    assert skill.input_label


@pytest.mark.parametrize("skill", registry.all_skills(), ids=lambda s: s.slug)
def test_no_skill_uses_an_emoji_icon(skill: Skill):
    """Icons are lucide names. The no-emoji rule reaches the skill definitions too."""
    assert skill.icon.isascii() and "-" in skill.icon or skill.icon.isalpha()


def test_slugs_are_unique():
    assert len(registry.SKILLS) == len({s.slug for s in registry.all_skills()})


def test_registry_rejects_a_malformed_skill():
    """The dataclass validates itself, so a bad skill fails at import rather than at runtime."""
    with pytest.raises(ValueError):
        Skill(slug="x", name="X", category="not-a-category", description="d",
              icon="star", system_prompt="a" * 60)
    with pytest.raises(ValueError):
        Skill(slug="x", name="X", category="writing", description="d",
              icon="star", system_prompt="   ")


def test_skills_are_grouped_by_category():
    grouped = registry.by_category()
    assert sum(len(v) for v in grouped.values()) == len(registry.SKILLS)
    assert all(category in CATEGORIES for category in grouped)


# ------------------------------------------------------------------- execution
@pytest.fixture
def workspace(client, make_user):
    user = make_user()
    created = client.post("/api/workspaces", json={"name": "Research"}, headers=user["headers"])
    return {"id": created.json()["id"], "headers": user["headers"]}


@pytest.fixture
def stub_skill_llm(monkeypatch):
    """A model that answers text skills with prose and structured skills with a valid instance."""
    class Stub:
        last_used_model = "fake-model"
        last_used_provider = "fake"

        def complete(self, system, user):
            return f"Output for: {user[:40]}"

        def structured(self, system, user, schema):
            # Build a minimal valid instance of whatever shape the skill declared.
            def value_for(field):
                annotation = field.annotation
                origin = getattr(annotation, "__origin__", None)
                if origin is list:
                    inner = annotation.__args__[0]
                    if hasattr(inner, "model_fields"):
                        return [inner(**{k: value_for(v) for k, v in inner.model_fields.items()})]
                    return ["item one", "item two"]
                if hasattr(annotation, "model_fields"):
                    return annotation(**{k: value_for(v) for k, v in annotation.model_fields.items()})
                return "text"

            return schema(**{k: value_for(v) for k, v in schema.model_fields.items()})

    monkeypatch.setattr("services.chat_service.llm_for", lambda *a, **k: Stub())
    return Stub()


# ------------------------------------------------------------- THE PHASE 6 GATE
@pytest.mark.parametrize("skill", registry.all_skills(), ids=lambda s: s.slug)
def test_every_registered_skill_runs(client, workspace, stub_skill_llm, skill: Skill):
    """Parameterised over the registry: adding a skill adds a test case automatically."""
    response = client.post(
        f"/api/workspaces/{workspace['id']}/skills/{skill.slug}/run",
        json={"input": "Some input long enough to be meaningful for any skill."},
        headers=workspace["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["slug"] == skill.slug
    assert body["output"].strip(), "the skill produced nothing"
    if skill.output_schema is not None:
        assert body["structured"], "a structured skill returned no structure"
    else:
        assert body["structured"] is None


def test_the_skill_list_matches_the_registry(client, workspace, stub_skill_llm):
    listed = client.get(f"/api/workspaces/{workspace['id']}/skills",
                        headers=workspace["headers"]).json()
    assert {s["slug"] for s in listed} == set(registry.SKILLS)


def test_running_a_skill_increments_its_count(client, workspace, stub_skill_llm):
    base = f"/api/workspaces/{workspace['id']}"
    client.post(f"{base}/skills/summarize/run", json={"input": "Some text to condense."},
                headers=workspace["headers"])
    listed = client.get(f"{base}/skills", headers=workspace["headers"]).json()
    assert next(s for s in listed if s["slug"] == "summarize")["use_count"] == 1


def test_a_skill_run_is_logged(client, workspace, stub_skill_llm, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import Log

    client.post(f"/api/workspaces/{workspace['id']}/skills/swot/run",
                json={"input": "Launching a paid tier."}, headers=workspace["headers"])

    session = sessionmaker(bind=engine)()
    entries = session.query(Log).filter_by(event="skill").all()
    assert len(entries) == 1 and entries[0].detail == "swot"
    session.close()


def test_an_unknown_skill_lists_the_real_ones(client, workspace, stub_skill_llm):
    response = client.post(f"/api/workspaces/{workspace['id']}/skills/nonsense/run",
                           json={"input": "x"}, headers=workspace["headers"])
    assert response.status_code == 404
    assert "summarize" in response.json()["detail"]


def test_a_document_skill_receives_the_excerpts(client, workspace, stub_skill_llm, monkeypatch):
    """`uses_documents` must actually reach retrieval, not just be metadata."""
    seen = {}

    class Recorder:
        last_used_model = "fake-model"
        last_used_provider = "fake"

        def complete(self, system, user):
            seen["user"] = user
            return "answer"

    monkeypatch.setattr("services.chat_service.llm_for", lambda *a, **k: Recorder())
    monkeypatch.setattr(
        "services.chat_service.retrieve_context",
        lambda db, ws, s, q: __import__(
            "services.retrieval_service", fromlist=["x"]
        ).RetrievalResult(
            citations=[__import__("services.retrieval_service", fromlist=["x"]).Citation(
                chunk_id=1, document_id=1, filename="handbook.pdf", page=7,
                snippet="The passing score is 70.", score=0.9)],
            mode="bm25",
        ),
    )

    client.post(f"/api/workspaces/{workspace['id']}/skills/research/run",
                json={"input": "What is the passing score?"}, headers=workspace["headers"])
    assert "handbook.pdf" in seen["user"]
    assert "passing score is 70" in seen["user"]


def test_a_non_document_skill_does_not_search(client, workspace, monkeypatch):
    called = {"n": 0}

    def counting_retrieve(*args, **kwargs):
        called["n"] += 1
        from services.retrieval_service import RetrievalResult
        return RetrievalResult()

    monkeypatch.setattr("services.chat_service.retrieve_context", counting_retrieve)

    class Stub:
        last_used_model = last_used_provider = "fake"
        def complete(self, system, user): return "out"

    monkeypatch.setattr("services.chat_service.llm_for", lambda *a, **k: Stub())

    client.post(f"/api/workspaces/{workspace['id']}/skills/email/run",
                json={"input": "Tell the client we are late."}, headers=workspace["headers"])
    assert called["n"] == 0


def test_another_user_cannot_run_skills_in_your_workspace(client, workspace, make_user, stub_skill_llm):
    intruder = make_user("intruder@example.com")
    assert client.post(f"/api/workspaces/{workspace['id']}/skills/summarize/run",
                       json={"input": "x"}, headers=intruder["headers"]).status_code == 403


# --------------------------------------------------------------- prompt library
def test_creating_and_listing_prompts(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    created = client.post(base, json={"title": "Bug report", "body": "Describe the bug: {details}",
                                      "category": "programming"},
                          headers=workspace["headers"])
    assert created.status_code == 201, created.text
    assert created.json()["version"] == 1
    assert created.json()["is_current"] is True

    listed = client.get(base, headers=workspace["headers"]).json()
    assert [p["title"] for p in listed] == ["Bug report"]


def test_editing_creates_a_version_and_keeps_the_old_text(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    first = client.post(base, json={"title": "Summary", "body": "Summarise: {text}"},
                        headers=workspace["headers"]).json()

    second = client.patch(f"{base}/{first['id']}",
                          json={"body": "Summarise in three bullets: {text}"},
                          headers=workspace["headers"]).json()

    assert second["id"] != first["id"], "editing overwrote instead of versioning"
    assert second["version"] == 2
    assert second["parent_id"] == first["id"]

    history = client.get(f"{base}/{second['id']}/history", headers=workspace["headers"]).json()
    assert [h["version"] for h in history] == [1, 2]
    assert history[0]["body"] == "Summarise: {text}", "the original text was lost"


def test_only_the_current_version_is_listed(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    first = client.post(base, json={"title": "P", "body": "v1"},
                        headers=workspace["headers"]).json()
    client.patch(f"{base}/{first['id']}", json={"body": "v2"}, headers=workspace["headers"])
    client.patch(f"{base}/{first['id'] + 1}", json={"body": "v3"}, headers=workspace["headers"])

    listed = client.get(base, headers=workspace["headers"]).json()
    assert len(listed) == 1
    assert listed[0]["body"] == "v3"
    assert listed[0]["version"] == 3


def test_an_edit_that_changes_nothing_does_not_create_a_version(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    first = client.post(base, json={"title": "P", "body": "unchanged"},
                        headers=workspace["headers"]).json()
    same = client.patch(f"{base}/{first['id']}", json={"body": "unchanged"},
                        headers=workspace["headers"]).json()
    assert same["id"] == first["id"]
    assert same["version"] == 1


def test_use_count_survives_an_edit(client, workspace):
    """A prompt used forty times is still that prompt after a wording change."""
    base = f"/api/workspaces/{workspace['id']}/prompts"
    first = client.post(base, json={"title": "P", "body": "v1"},
                        headers=workspace["headers"]).json()
    for _ in range(3):
        client.post(f"{base}/{first['id']}/use", headers=workspace["headers"])

    second = client.patch(f"{base}/{first['id']}", json={"body": "v2"},
                          headers=workspace["headers"]).json()
    assert second["use_count"] == 3


def test_deleting_removes_every_version(client, workspace, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import PromptTemplate

    base = f"/api/workspaces/{workspace['id']}/prompts"
    first = client.post(base, json={"title": "P", "body": "v1"},
                        headers=workspace["headers"]).json()
    second = client.patch(f"{base}/{first['id']}", json={"body": "v2"},
                          headers=workspace["headers"]).json()

    assert client.delete(f"{base}/{second['id']}",
                         headers=workspace["headers"]).status_code == 204

    session = sessionmaker(bind=engine)()
    assert session.query(PromptTemplate).count() == 0, "an orphaned version survived"
    session.close()


def test_prompts_can_be_filtered_by_category(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    client.post(base, json={"title": "A", "body": "x", "category": "writing"},
                headers=workspace["headers"])
    client.post(base, json={"title": "B", "body": "y", "category": "programming"},
                headers=workspace["headers"])

    writing = client.get(f"{base}?category=writing", headers=workspace["headers"]).json()
    assert [p["title"] for p in writing] == ["A"]


def test_a_global_prompt_appears_in_every_workspace(client, workspace):
    other = client.post("/api/workspaces", json={"name": "Other"},
                        headers=workspace["headers"]).json()["id"]
    client.post(f"/api/workspaces/{workspace['id']}/prompts",
                json={"title": "Everywhere", "body": "x", "workspace_scoped": False},
                headers=workspace["headers"])

    listed = client.get(f"/api/workspaces/{other}/prompts", headers=workspace["headers"]).json()
    assert [p["title"] for p in listed] == ["Everywhere"]


def test_another_user_cannot_read_or_edit_your_prompts(client, workspace, make_user):
    base = f"/api/workspaces/{workspace['id']}/prompts"
    prompt_id = client.post(base, json={"title": "Private", "body": "x"},
                            headers=workspace["headers"]).json()["id"]
    intruder = make_user("intruder@example.com")

    assert client.get(base, headers=intruder["headers"]).status_code == 403
    assert client.patch(f"{base}/{prompt_id}", json={"body": "hijacked"},
                        headers=intruder["headers"]).status_code == 403
    assert client.delete(f"{base}/{prompt_id}",
                         headers=intruder["headers"]).status_code == 403


def test_version_history_can_be_walked_from_any_version(db):
    """History is reachable whichever revision you happen to hold."""
    from db.models import User

    user = User(email="p@b.c", password_hash="x")
    db.add(user)
    db.commit()

    v1 = prompt_service.create(db, user.id, None, "P", "v1")
    v2 = prompt_service.edit(db, v1, body="v2")
    v3 = prompt_service.edit(db, v2, body="v3")

    for holding in (v1, v2, v3):
        chain = prompt_service.version_history(db, holding)
        assert [p.body for p in chain] == ["v1", "v2", "v3"]


# ---------------------------------------------- running a skill inside a chat
def test_a_skill_run_from_a_conversation_is_stored_in_it(client, workspace, stub_skill_llm):
    """Otherwise the output exists only in component state and vanishes on reload."""
    base = f"/api/workspaces/{workspace['id']}"
    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]

    response = client.post(
        f"{base}/skills/swot/run",
        json={"input": "Launching a paid tier.", "conversation_id": conversation},
        headers=workspace["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["message_id"] is not None

    messages = client.get(f"{base}/conversations/{conversation}",
                          headers=workspace["headers"]).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"].startswith("/swot ")
    assert messages[1]["content"] == response.json()["output"]


def test_a_skill_run_without_a_conversation_stores_nothing(client, workspace, stub_skill_llm, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import Message

    client.post(f"/api/workspaces/{workspace['id']}/skills/summarize/run",
                json={"input": "Some text."}, headers=workspace["headers"])

    session = sessionmaker(bind=engine)()
    assert session.query(Message).count() == 0
    session.close()


def test_a_conversation_from_another_workspace_is_rejected(client, workspace, stub_skill_llm):
    other = client.post("/api/workspaces", json={"name": "Other"},
                        headers=workspace["headers"]).json()["id"]
    foreign = client.post(f"/api/workspaces/{other}/conversations", json={},
                          headers=workspace["headers"]).json()["id"]

    response = client.post(
        f"/api/workspaces/{workspace['id']}/skills/summarize/run",
        json={"input": "text", "conversation_id": foreign},
        headers=workspace["headers"],
    )
    assert response.status_code == 404


def test_a_skill_run_titles_a_new_conversation(client, workspace, stub_skill_llm):
    base = f"/api/workspaces/{workspace['id']}"
    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]
    client.post(f"{base}/skills/swot/run",
                json={"input": "Launching a paid tier.", "conversation_id": conversation},
                headers=workspace["headers"])

    detail = client.get(f"{base}/conversations/{conversation}",
                        headers=workspace["headers"]).json()
    assert detail["title"] != "New conversation"
    assert "SWOT" in detail["title"]
