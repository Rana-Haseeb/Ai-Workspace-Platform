"""Conversations, messages, titling, search and streaming.

The Phase 3 gate is ``test_history_survives_a_restart`` — a brand-new application instance,
sharing only the database, sees the same transcript.
"""
from __future__ import annotations

import json

import pytest

from db.models import AssistantSettings
from services.chat_service import HISTORY_LIMIT, build_messages, build_system_prompt


@pytest.fixture
def workspace(client, make_user):
    user = make_user()
    created = client.post(
        "/api/workspaces", json={"name": "Research"}, headers=user["headers"]
    )
    return {"id": created.json()["id"], "headers": user["headers"]}


@pytest.fixture
def conversation(client, workspace):
    created = client.post(
        f"/api/workspaces/{workspace['id']}/conversations",
        json={},
        headers=workspace["headers"],
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def send(client, workspace, conversation_id, text):
    return client.post(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation_id}/messages",
        json={"content": text},
        headers=workspace["headers"],
    )


# ------------------------------------------------------------ prompt assembly
def test_system_prompt_combines_prompt_role_personality_and_style():
    settings_row = AssistantSettings(
        system_prompt="Answer from the documents.",
        role="Vector database analyst",
        personality="socratic",
        response_style="bullets",
    )
    prompt = build_system_prompt(settings_row)
    assert "Answer from the documents." in prompt
    assert "Vector database analyst" in prompt
    assert "question" in prompt.lower()      # the socratic instruction
    assert "bullet" in prompt.lower()        # the bullets instruction


def test_history_is_trimmed_to_the_recent_window():
    """Old turns fall out of the window; the system prompt and the new message never do."""
    settings_row = AssistantSettings()

    class Fake:
        def __init__(self, i):
            self.role = "user" if i % 2 == 0 else "assistant"
            self.content = f"message {i}"

    history = [Fake(i) for i in range(HISTORY_LIMIT * 2)]
    messages = build_messages(settings_row, history, "the new question")

    assert messages[0][0] == "system"
    assert messages[-1] == ("user", "the new question")
    assert len(messages) == HISTORY_LIMIT + 2
    assert "message 0" not in [c for _, c in messages]


def test_system_messages_in_history_are_not_replayed():
    settings_row = AssistantSettings()

    class Fake:
        def __init__(self, role, content):
            self.role, self.content = role, content

    history = [Fake("system", "leaked"), Fake("user", "kept")]
    contents = [c for _, c in build_messages(settings_row, history, "new")]
    assert "leaked" not in contents
    assert "kept" in contents


# ------------------------------------------------------------------ transcript
def test_sending_a_message_stores_both_sides(client, workspace, conversation, fake_llm):
    response = send(client, workspace, conversation, "Which vector store should we use?")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == fake_llm.reply


def test_transcript_comes_back_in_order(client, workspace, conversation, fake_llm):
    send(client, workspace, conversation, "first")
    send(client, workspace, conversation, "second")

    messages = client.get(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        headers=workspace["headers"],
    ).json()["messages"]

    assert [m["content"] for m in messages][::2] == ["first", "second"]
    assert len(messages) == 4


def test_the_model_receives_the_previous_turns(client, workspace, conversation, fake_llm):
    send(client, workspace, conversation, "my favourite colour is teal")
    send(client, workspace, conversation, "what did I just say?")

    last_call = fake_llm.seen_messages[-1]
    assert ("user", "my favourite colour is teal") in last_call
    assert last_call[-1] == ("user", "what did I just say?")


def test_usage_is_recorded_on_the_message(client, workspace, conversation, fake_llm):
    body = send(client, workspace, conversation, "hello").json()
    assistant = body["assistant_message"]
    assert assistant["model"] == "fake-model"
    assert assistant["tokens_out"] > 0
    assert assistant["latency_ms"] >= 0


def test_the_chat_call_is_logged_for_the_dashboard(client, workspace, conversation, fake_llm, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import Log

    send(client, workspace, conversation, "hello")

    session = sessionmaker(bind=engine)()
    entries = session.query(Log).filter_by(event="chat").all()
    assert len(entries) == 1
    assert entries[0].status == "ok"
    assert entries[0].workspace_id == workspace["id"]
    session.close()


def test_empty_message_is_rejected(client, workspace, conversation, fake_llm):
    assert send(client, workspace, conversation, "").status_code == 422


# --------------------------------------------------------------------- titling
def test_first_message_generates_a_title(client, workspace, conversation, fake_llm):
    body = send(client, workspace, conversation, "Compare pgvector and Qdrant").json()
    assert body["title"] == fake_llm.title


def test_later_messages_do_not_retitle(client, workspace, conversation, fake_llm):
    send(client, workspace, conversation, "first")
    client.patch(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        json={"title": "Renamed by hand"},
        headers=workspace["headers"],
    )
    body = send(client, workspace, conversation, "second").json()
    assert body["title"] == "Renamed by hand"


def test_title_falls_back_to_the_message_when_the_model_fails(
    client, workspace, conversation, monkeypatch, fake_llm
):
    """A naming failure must not cost the user their message."""
    def explode(system, user):
        raise RuntimeError("provider down")

    monkeypatch.setattr(fake_llm, "complete", explode)

    body = send(client, workspace, conversation, "Compare pgvector and Qdrant").json()
    assert body["title"] == "Compare pgvector and Qdrant"
    assert body["assistant_message"]["content"] == fake_llm.reply


# ---------------------------------------------------------- rename, pin, delete
def test_rename_pin_and_tag(client, workspace, conversation, fake_llm):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        json={"title": "Vector DB decision", "is_pinned": True, "tags": ["research", "  db  "]},
        headers=workspace["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Vector DB decision"
    assert body["is_pinned"] is True
    assert body["tags"] == ["db", "research"]


def test_tags_are_deduplicated_and_capped(client, workspace, conversation):
    response = client.patch(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        json={"tags": ["a", "a", "a"] + [f"t{i}" for i in range(20)]},
        headers=workspace["headers"],
    )
    tags = response.json()["tags"]
    assert len(tags) <= 12
    assert len(tags) == len(set(tags))


def test_pinned_conversations_sort_first(client, workspace, fake_llm):
    first = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                        headers=workspace["headers"]).json()["id"]
    second = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                         headers=workspace["headers"]).json()["id"]
    client.patch(f"/api/workspaces/{workspace['id']}/conversations/{first}",
                 json={"is_pinned": True}, headers=workspace["headers"])

    listed = client.get(f"/api/workspaces/{workspace['id']}/conversations",
                        headers=workspace["headers"]).json()
    assert listed[0]["id"] == first
    assert second in [c["id"] for c in listed]


def test_delete_removes_the_conversation_and_its_messages(
    client, workspace, conversation, fake_llm, engine
):
    from sqlalchemy.orm import sessionmaker

    from db.models import Message

    send(client, workspace, conversation, "hello")
    assert client.delete(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        headers=workspace["headers"],
    ).status_code == 204

    session = sessionmaker(bind=engine)()
    assert session.query(Message).filter_by(conversation_id=conversation).count() == 0
    session.close()


# ---------------------------------------------------------------------- search
def test_search_matches_titles_and_message_bodies(client, workspace, fake_llm):
    first = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                        headers=workspace["headers"]).json()["id"]
    second = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                         headers=workspace["headers"]).json()["id"]

    send(client, workspace, first, "tell me about pgvector indexes")
    send(client, workspace, second, "how do I roast coffee")

    client.patch(f"/api/workspaces/{workspace['id']}/conversations/{first}",
                 json={"title": "Storage"}, headers=workspace["headers"])
    client.patch(f"/api/workspaces/{workspace['id']}/conversations/{second}",
                 json={"title": "Kitchen"}, headers=workspace["headers"])

    # Matches a message body, not the title.
    by_body = client.get(f"/api/workspaces/{workspace['id']}/conversations?q=pgvector",
                         headers=workspace["headers"]).json()
    assert [c["id"] for c in by_body] == [first]

    # Matches a title, not any message.
    by_title = client.get(f"/api/workspaces/{workspace['id']}/conversations?q=Kitchen",
                          headers=workspace["headers"]).json()
    assert [c["id"] for c in by_title] == [second]


def test_search_is_case_insensitive(client, workspace, conversation, fake_llm):
    send(client, workspace, conversation, "Something about PGVECTOR here")
    found = client.get(f"/api/workspaces/{workspace['id']}/conversations?q=pgvector",
                       headers=workspace["headers"]).json()
    assert len(found) == 1


def test_list_shows_message_count_and_preview(client, workspace, conversation, fake_llm):
    send(client, workspace, conversation, "the opening question")
    listed = client.get(f"/api/workspaces/{workspace['id']}/conversations",
                        headers=workspace["headers"]).json()
    assert listed[0]["message_count"] == 2
    assert "opening question" in listed[0]["preview"]


# ------------------------------------------------------------------- streaming
def test_streaming_yields_tokens_then_a_done_event(client, workspace, conversation, fake_llm):
    with client.stream(
        "POST",
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/stream",
        json={"content": "hello"},
        headers=workspace["headers"],
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    kinds = [e["type"] for e in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    tokens = [e["text"] for e in events if e["type"] == "token"]
    # More than one chunk is the whole point — a single chunk is not streaming.
    assert len(tokens) > 1
    assert "".join(tokens).strip() == fake_llm.reply


def test_streamed_reply_is_persisted(client, workspace, conversation, fake_llm):
    with client.stream(
        "POST",
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/stream",
        json={"content": "hello"},
        headers=workspace["headers"],
    ) as response:
        list(response.iter_lines())

    messages = client.get(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        headers=workspace["headers"],
    ).json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"].strip() == fake_llm.reply


def test_stream_reports_provider_failure_as_an_event(
    client, workspace, conversation, fake_llm, monkeypatch
):
    from services.llm_service import LLMError

    def explode(messages):
        raise LLMError("every provider is rate limited")
        yield  # pragma: no cover — makes this a generator

    monkeypatch.setattr(fake_llm, "stream_chat", explode)

    with client.stream(
        "POST",
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/stream",
        json={"content": "hello"},
        headers=workspace["headers"],
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    assert events[-1]["type"] == "error"
    assert "rate limited" in events[-1]["detail"]


def test_a_failed_turn_is_logged_as_failed(client, workspace, conversation, monkeypatch, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import Log
    from services.llm_service import LLMError

    class Broken:
        last_used_model = None
        last_used_provider = None

        def chat(self, messages):
            raise LLMError("provider exploded")

        def complete(self, system, user):
            return "title"

    monkeypatch.setattr("services.chat_service.get_llm", lambda **kwargs: Broken())

    response = send(client, workspace, conversation, "hello")
    assert response.status_code == 502

    session = sessionmaker(bind=engine)()
    assert session.query(Log).filter_by(event="chat", status="failed").count() == 1
    session.close()


# ------------------------------------------------------------------- isolation
def test_another_user_cannot_read_your_conversation(client, workspace, conversation, make_user, fake_llm):
    send(client, workspace, conversation, "private notes")
    intruder = make_user("intruder@example.com")

    assert client.get(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        headers=intruder["headers"],
    ).status_code == 403
    assert client.get(
        f"/api/workspaces/{workspace['id']}/conversations", headers=intruder["headers"]
    ).status_code == 403
    assert client.post(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/messages",
        json={"content": "hi"},
        headers=intruder["headers"],
    ).status_code == 403


def test_a_conversation_from_another_workspace_is_not_reachable(client, workspace, make_user, fake_llm):
    """Both ids are checked, so a conversation id cannot be smuggled across workspaces."""
    other = client.post("/api/workspaces", json={"name": "Other"},
                        headers=workspace["headers"]).json()["id"]
    foreign = client.post(f"/api/workspaces/{other}/conversations", json={},
                          headers=workspace["headers"]).json()["id"]

    assert client.get(
        f"/api/workspaces/{workspace['id']}/conversations/{foreign}",
        headers=workspace["headers"],
    ).status_code == 404


# ------------------------------------------------------------ THE PHASE 3 GATE
def test_history_survives_a_restart(client, workspace, conversation, fake_llm, engine, monkeypatch):
    """A brand-new application instance, sharing only the database, sees the same transcript."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from api.main import create_app

    send(client, workspace, conversation, "remember this line")
    client.patch(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
        json={"title": "Persisted conversation"},
        headers=workspace["headers"],
    )

    # A second application object — new app, new routers, new dependency graph. Only the
    # database is shared, which is exactly what surviving a server restart means.
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    restarted = create_app()
    restarted.dependency_overrides[get_db] = override

    with TestClient(restarted) as after:
        detail = after.get(
            f"/api/workspaces/{workspace['id']}/conversations/{conversation}",
            headers=workspace["headers"],
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["title"] == "Persisted conversation"
        assert [m["content"] for m in body["messages"]][0] == "remember this line"

        found = after.get(
            f"/api/workspaces/{workspace['id']}/conversations?q=remember",
            headers=workspace["headers"],
        ).json()
        assert [c["id"] for c in found] == [conversation]
