"""Long-term memory: ranking, scoping, extraction, injection, and the user's control over it.

The Phase 5 gate is ``test_a_preference_survives_into_a_brand_new_session`` — a fact stated in
one conversation reaches a different conversation in a different application instance.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from db.models import MemoryItem
from services import memory_service
from services.memory_service import RECENCY_HALF_LIFE_DAYS, rank_score


def _item(**kwargs) -> MemoryItem:
    """A MemoryItem with sane values, for pure ranking tests that need no database."""
    defaults = {
        "content": "x",
        "kind": "fact",
        "importance": 0.5,
        "is_pinned": False,
        "created_at": datetime.now(timezone.utc),
    }
    return MemoryItem(**{**defaults, **kwargs})


# ----------------------------------------------------------------------- ranking
def test_a_more_important_memory_outranks_a_less_important_one_of_the_same_age():
    now = datetime.now(timezone.utc)
    assert rank_score(_item(importance=0.9), now) > rank_score(_item(importance=0.2), now)


def test_an_older_memory_decays_below_a_newer_one_of_equal_importance():
    now = datetime.now(timezone.utc)
    fresh = _item(importance=0.5, created_at=now)
    stale = _item(importance=0.5, created_at=now - timedelta(days=60))
    assert rank_score(fresh, now) > rank_score(stale, now)


def test_decay_halves_over_one_half_life():
    now = datetime.now(timezone.utc)
    fresh = _item(importance=1.0, created_at=now)
    aged = _item(importance=1.0, created_at=now - timedelta(days=RECENCY_HALF_LIFE_DAYS))
    assert rank_score(aged, now) == pytest.approx(rank_score(fresh, now) * 0.5, rel=0.02)


def test_a_memory_never_decays_to_nothing():
    """Old is not the same as forgotten — a two-year-old preference still counts for something."""
    now = datetime.now(timezone.utc)
    ancient = _item(importance=0.8, created_at=now - timedelta(days=730))
    assert rank_score(ancient, now) > 0


def test_importance_can_beat_recency():
    """A strong old preference should outrank a trivial thing said this morning."""
    now = datetime.now(timezone.utc)
    strong_old = _item(importance=0.95, created_at=now - timedelta(days=7))
    weak_new = _item(importance=0.15, created_at=now)
    assert rank_score(strong_old, now) > rank_score(weak_new, now)


def test_pinned_beats_everything():
    now = datetime.now(timezone.utc)
    pinned = _item(importance=0.01, is_pinned=True, created_at=now - timedelta(days=365))
    assert rank_score(pinned, now) > rank_score(_item(importance=1.0, created_at=now), now)


# ---------------------------------------------------------- retrieval and scoping
@pytest.fixture
def user_with_workspaces(db):
    from db.models import AssistantSettings, User, Workspace

    user = User(email="a@b.c", password_hash="x")
    first = Workspace(name="Research")
    first.settings = AssistantSettings()
    second = Workspace(name="Marketing")
    second.settings = AssistantSettings()
    user.workspaces.extend([first, second])
    db.add(user)
    db.commit()
    return user, first, second


def test_a_preference_follows_the_user_into_every_workspace(db, user_with_workspaces):
    user, first, second = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=None, kind="preference",
                      content="Prefers concise answers", importance=0.9))
    db.commit()

    assert any("concise" in m.content for m in memory_service.retrieve(db, user.id, first.id))
    assert any("concise" in m.content for m in memory_service.retrieve(db, user.id, second.id))


def test_a_workspace_fact_does_not_leak_into_another_workspace(db, user_with_workspaces):
    """A project-specific detail is wrong advice somewhere else."""
    user, first, second = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="fact",
                      content="This project uses Postgres 16", importance=0.8))
    db.commit()

    assert any("Postgres" in m.content for m in memory_service.retrieve(db, user.id, first.id))
    assert not any("Postgres" in m.content for m in memory_service.retrieve(db, user.id, second.id))


def test_another_users_memories_are_never_returned(db, user_with_workspaces):
    from db.models import User

    user, first, _ = user_with_workspaces
    intruder = User(email="other@example.com", password_hash="x")
    db.add(intruder)
    db.commit()
    db.add(MemoryItem(user_id=intruder.id, workspace_id=None, kind="fact",
                      content="Secret about someone else", importance=1.0))
    db.commit()

    assert memory_service.retrieve(db, user.id, first.id) == []


def test_retrieval_is_capped(db, user_with_workspaces):
    from core.config import settings

    user, first, _ = user_with_workspaces
    for i in range(30):
        db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="fact",
                          content=f"fact {i}", importance=0.9))
    db.commit()

    assert len(memory_service.retrieve(db, user.id, first.id)) == settings.memory_max_items_in_context


def test_low_importance_memories_are_filtered_out(db, user_with_workspaces):
    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="fact",
                      content="barely worth keeping", importance=0.05))
    db.commit()
    assert memory_service.retrieve(db, user.id, first.id) == []


def test_a_pinned_memory_bypasses_the_importance_filter(db, user_with_workspaces):
    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="pinned",
                      content="Always answer in British English", importance=0.01, is_pinned=True))
    db.commit()
    assert len(memory_service.retrieve(db, user.id, first.id)) == 1


def test_using_a_memory_records_it(db, user_with_workspaces):
    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="fact",
                      content="uses pytest", importance=0.7))
    db.commit()

    items = memory_service.retrieve(db, user.id, first.id)
    memory_service.mark_used(db, items)
    assert items[0].use_count == 1
    assert items[0].last_used_at is not None


def test_context_block_is_empty_when_there_is_nothing_to_say():
    assert memory_service.context_block([]) == ""


def test_context_block_lists_the_memories():
    block = memory_service.context_block([_item(content="Prefers concise answers")])
    assert "Prefers concise answers" in block
    # The assistant should apply memory, not narrate it.
    assert "without announcing" in block


# ------------------------------------------------------ THE MEMORY-IS-NOT-RAG LINE
def test_memory_retrieval_ignores_the_question(db, user_with_workspaces):
    """The load-bearing difference from RAG.

    ``retrieve`` takes no query argument at all. A stated preference has to apply to a question
    that never mentions it — no similarity function connects "I prefer short answers" to "how
    does pgvector index?", so similarity is the wrong tool for this job.
    """
    import inspect

    signature = inspect.signature(memory_service.retrieve)
    assert "query" not in signature.parameters
    assert "question" not in signature.parameters

    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=first.id, kind="preference",
                      content="Prefers answers under three sentences", importance=0.9))
    db.commit()

    # Retrieved identically regardless of what is being asked.
    assert len(memory_service.retrieve(db, user.id, first.id)) == 1


# -------------------------------------------------------------------- extraction
class FakeExtractor:
    """Stands in for the model during extraction, returning a fixed result."""

    def __init__(self, memories):
        self.memories = memories
        self.seen_user_prompt = ""

    def structured(self, system, user, schema):
        self.seen_user_prompt = user
        return schema(memories=self.memories)


@pytest.fixture
def stub_extractor(monkeypatch):
    from services.memory_service import ExtractedMemory

    holder = {}

    def install(memories):
        fake = FakeExtractor([ExtractedMemory(**m) for m in memories])
        monkeypatch.setattr("services.chat_service.llm_for", lambda *a, **k: fake)
        holder["fake"] = fake
        return fake

    holder["install"] = install
    return holder


def test_extraction_stores_what_the_model_found(db, user_with_workspaces, stub_extractor):
    user, first, _ = user_with_workspaces
    stub_extractor["install"]([
        {"kind": "preference", "content": "Prefers concise answers", "importance": 0.9},
        {"kind": "fact", "content": "Works on a vector database migration", "importance": 0.7},
    ])

    stored = memory_service.extract_and_store(
        db, user.id, first, first.settings,
        "I like short answers. I am migrating our search onto a vector database.",
    )
    assert len(stored) == 2
    assert {item.content for item in stored} == {
        "Prefers concise answers", "Works on a vector database migration"
    }


def test_preferences_are_stored_user_wide_and_facts_stay_in_the_workspace(
    db, user_with_workspaces, stub_extractor
):
    user, first, _ = user_with_workspaces
    stub_extractor["install"]([
        {"kind": "preference", "content": "Prefers British English", "importance": 0.8},
        {"kind": "fact", "content": "This project targets Postgres 16", "importance": 0.7},
    ])

    stored = memory_service.extract_and_store(
        db, user.id, first, first.settings, "Please use British spelling. We target Postgres 16."
    )
    by_content = {item.content: item for item in stored}
    assert by_content["Prefers British English"].workspace_id is None
    assert by_content["This project targets Postgres 16"].workspace_id == first.id


def test_a_duplicate_is_not_stored_twice(db, user_with_workspaces, stub_extractor):
    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=None, kind="preference",
                      content="Prefers concise answers", importance=0.9))
    db.commit()

    # Same fact, different punctuation and case — still the same fact.
    stub_extractor["install"](
        [{"kind": "preference", "content": "prefers concise answers.", "importance": 0.9}]
    )
    assert memory_service.extract_and_store(
        db, user.id, first, first.settings, "Reminder that I like short answers please."
    ) == []


def test_existing_memories_are_shown_to_the_extractor(db, user_with_workspaces, stub_extractor):
    """So the model can avoid repeating itself, not just be de-duplicated afterwards."""
    user, first, _ = user_with_workspaces
    db.add(MemoryItem(user_id=user.id, workspace_id=None, kind="preference",
                      content="Prefers concise answers", importance=0.9))
    db.commit()

    fake = stub_extractor["install"]([])
    memory_service.extract_and_store(
        db, user.id, first, first.settings, "Some new message with enough length to qualify."
    )
    assert "Prefers concise answers" in fake.seen_user_prompt


def test_short_messages_do_not_trigger_an_extraction_call(db, user_with_workspaces, stub_extractor):
    """"ok" and "thanks" contain nothing durable, and a call for them is pure waste."""
    user, first, _ = user_with_workspaces
    fake = stub_extractor["install"]([{"kind": "fact", "content": "x", "importance": 0.9}])

    assert memory_service.extract_and_store(db, user.id, first, first.settings, "ok thanks") == []
    assert fake.seen_user_prompt == ""


def test_extraction_failure_is_swallowed(db, user_with_workspaces, monkeypatch):
    """Memory is an enhancement. A failure must not cost the conversation that produced it."""
    class Broken:
        def structured(self, system, user, schema):
            raise RuntimeError("provider down")

    monkeypatch.setattr("services.chat_service.llm_for", lambda *a, **k: Broken())
    user, first, _ = user_with_workspaces

    assert memory_service.extract_and_store(
        db, user.id, first, first.settings, "A message long enough to trigger extraction."
    ) == []


def test_extraction_is_skipped_when_the_workspace_turns_memory_off(
    db, user_with_workspaces, stub_extractor
):
    user, first, _ = user_with_workspaces
    first.settings.use_memory = False
    db.commit()
    fake = stub_extractor["install"]([{"kind": "fact", "content": "x", "importance": 0.9}])

    assert memory_service.extract_and_store(
        db, user.id, first, first.settings, "A message long enough to trigger extraction."
    ) == []
    assert fake.seen_user_prompt == ""


# ------------------------------------------------------------------- the HTTP API
@pytest.fixture
def workspace(client, make_user):
    user = make_user()
    created = client.post("/api/workspaces", json={"name": "Research"}, headers=user["headers"])
    return {"id": created.json()["id"], "headers": user["headers"]}


def test_memory_can_be_added_read_edited_and_deleted(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/memory"

    created = client.post(base, json={"content": "Prefers dark mode", "kind": "preference",
                                      "importance": 0.8}, headers=workspace["headers"])
    assert created.status_code == 201, created.text
    memory_id = created.json()["id"]

    listed = client.get(base, headers=workspace["headers"]).json()
    assert any(m["content"] == "Prefers dark mode" for m in listed)

    edited = client.patch(f"{base}/{memory_id}",
                          json={"content": "Prefers dark mode everywhere", "is_pinned": True},
                          headers=workspace["headers"]).json()
    assert edited["content"] == "Prefers dark mode everywhere"
    assert edited["is_pinned"] is True

    assert client.delete(f"{base}/{memory_id}",
                         headers=workspace["headers"]).status_code == 204
    assert client.get(base, headers=workspace["headers"]).json() == []


def test_the_list_says_which_memories_are_actually_in_context(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/memory"
    client.post(base, json={"content": "Important preference", "importance": 0.9},
                headers=workspace["headers"])
    client.post(base, json={"content": "Barely relevant", "importance": 0.05},
                headers=workspace["headers"])

    listed = client.get(base, headers=workspace["headers"]).json()
    by_content = {m["content"]: m for m in listed}
    assert by_content["Important preference"]["in_context"] is True
    assert by_content["Barely relevant"]["in_context"] is False


def test_status_summarises_what_is_remembered(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/memory"
    client.post(base, json={"content": "A preference", "kind": "preference", "importance": 0.9},
                headers=workspace["headers"])
    client.post(base, json={"content": "A fact", "kind": "fact", "importance": 0.7},
                headers=workspace["headers"])

    body = client.get(f"{base}/status", headers=workspace["headers"]).json()
    assert body["total"] == 2
    assert body["by_kind"] == {"preference": 1, "fact": 1}
    assert body["enabled"] is True


def test_forget_everything_clears_the_lot(client, workspace):
    base = f"/api/workspaces/{workspace['id']}/memory"
    for i in range(3):
        client.post(base, json={"content": f"Memory {i}"}, headers=workspace["headers"])

    assert client.delete(base, headers=workspace["headers"]).status_code == 204
    assert client.get(base, headers=workspace["headers"]).json() == []


def test_another_user_cannot_read_or_edit_your_memories(client, workspace, make_user):
    base = f"/api/workspaces/{workspace['id']}/memory"
    memory_id = client.post(base, json={"content": "Private preference"},
                            headers=workspace["headers"]).json()["id"]
    intruder = make_user("intruder@example.com")

    assert client.get(base, headers=intruder["headers"]).status_code == 403
    assert client.patch(f"{base}/{memory_id}", json={"content": "hijacked"},
                        headers=intruder["headers"]).status_code == 403
    assert client.delete(f"{base}/{memory_id}",
                         headers=intruder["headers"]).status_code == 403


# ------------------------------------------------------------- chat integration
def test_memories_are_injected_into_the_prompt(client, workspace, fake_llm):
    client.post(f"/api/workspaces/{workspace['id']}/memory",
                json={"content": "Prefers answers in British English", "kind": "preference",
                      "importance": 0.9},
                headers=workspace["headers"])
    conversation = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]

    client.post(f"/api/workspaces/{workspace['id']}/conversations/{conversation}/messages",
                json={"content": "How does indexing work?"}, headers=workspace["headers"])

    system_blocks = [c for role, c in fake_llm.seen_messages[0] if role == "system"]
    assert any("British English" in block for block in system_blocks)


def test_the_reply_records_which_memories_it_used(client, workspace, fake_llm):
    client.post(f"/api/workspaces/{workspace['id']}/memory",
                json={"content": "Works in fintech", "importance": 0.8},
                headers=workspace["headers"])
    conversation = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]

    reply = client.post(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/messages",
        json={"content": "What should I build next?"}, headers=workspace["headers"]
    ).json()

    used = reply["assistant_message"]["memory_used"]
    assert used and used[0]["content"] == "Works in fintech"


def test_turning_memory_off_stops_injection(client, workspace, fake_llm):
    client.post(f"/api/workspaces/{workspace['id']}/memory",
                json={"content": "Prefers British English", "importance": 0.9},
                headers=workspace["headers"])
    client.patch(f"/api/workspaces/{workspace['id']}/settings",
                 json={"use_memory": False}, headers=workspace["headers"])
    conversation = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]

    reply = client.post(
        f"/api/workspaces/{workspace['id']}/conversations/{conversation}/messages",
        json={"content": "How does indexing work?"}, headers=workspace["headers"]
    ).json()
    assert reply["assistant_message"]["memory_used"] == []


def test_streaming_sends_memory_in_the_start_event(client, workspace, fake_llm):
    client.post(f"/api/workspaces/{workspace['id']}/memory",
                json={"content": "Prefers bullet points", "importance": 0.9},
                headers=workspace["headers"])
    conversation = client.post(f"/api/workspaces/{workspace['id']}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]

    with client.stream(
        "POST", f"/api/workspaces/{workspace['id']}/conversations/{conversation}/stream",
        json={"content": "Explain indexing"}, headers=workspace["headers"],
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line.strip()]

    start = events[0]
    assert start["type"] == "start"
    assert start["memory_used"][0]["content"] == "Prefers bullet points"


# --------------------------------------------------------------- THE PHASE 5 GATE
def test_a_preference_survives_into_a_brand_new_session(client, workspace, fake_llm, engine):
    """Stated in one conversation, applied in another — in a different application instance.

    This is the whole promise of long-term memory: not that the model can see earlier turns of
    the same conversation (that is just history), but that something learned last week reaches a
    conversation started today in a process that has been restarted since.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from api.deps import get_db
    from api.main import create_app
    from services.memory_service import ExtractedMemory

    # --- Session 1: the user states a preference, and the extractor records it. ---
    class Extractor:
        last_used_model = "fake-model"
        last_used_provider = "fake"

        def structured(self, system, user, schema):
            return schema(memories=[ExtractedMemory(
                kind="preference",
                content="Prefers answers in British English with no bullet points",
                importance=0.9,
            )])
        def chat(self, messages):
            return "Understood."
        def complete(self, system, user):
            return "Preferences"

    import services.chat_service as chat_service
    original = chat_service.llm_for
    chat_service.llm_for = lambda *a, **k: Extractor()
    try:
        first_conversation = client.post(
            f"/api/workspaces/{workspace['id']}/conversations", json={},
            headers=workspace["headers"]
        ).json()["id"]
        client.post(
            f"/api/workspaces/{workspace['id']}/conversations/{first_conversation}/messages",
            json={"content": "Please always answer in British English and never use bullet points."},
            headers=workspace["headers"],
        )
    finally:
        chat_service.llm_for = original

    # --- A brand-new application instance. Only the database is shared. ---
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    restarted = create_app()
    restarted.dependency_overrides[get_db] = override

    captured: list[list[tuple[str, str]]] = []

    class Recorder:
        last_used_model = "fake-model"
        last_used_provider = "fake"

        def chat(self, messages):
            captured.append(messages)
            return "A reply."

        def complete(self, system, user):
            return "Title"

        def structured(self, system, user, schema):
            return schema(memories=[])

    chat_service.llm_for = lambda *a, **k: Recorder()
    try:
        with TestClient(restarted) as after:
            second_conversation = after.post(
                f"/api/workspaces/{workspace['id']}/conversations", json={},
                headers=workspace["headers"]
            ).json()["id"]

            reply = after.post(
                f"/api/workspaces/{workspace['id']}/conversations/{second_conversation}/messages",
                json={"content": "What is a vector database?"},
                headers=workspace["headers"],
            )
            assert reply.status_code == 200, reply.text
    finally:
        chat_service.llm_for = original

    # The preference reached the new session's prompt, in a conversation that never mentioned it.
    system_blocks = [c for role, c in captured[0] if role == "system"]
    assert any("British English" in block for block in system_blocks), system_blocks

    # And it is attributed on the message, so the UI can show what was applied.
    used = reply.json()["assistant_message"]["memory_used"]
    assert any("British English" in m["content"] for m in used)
