"""The dashboard and conversation export.

The Phase 7 gate is ``test_every_dashboard_number_matches_raw_sql`` — the API's figures are
compared against independent COUNT queries. A dashboard that disagrees with the database is
worse than no dashboard, because it is trusted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from services import dashboard_service


@pytest.fixture
def workspace(client, make_user):
    user = make_user()
    created = client.post("/api/workspaces", json={"name": "Research"}, headers=user["headers"])
    return {"id": created.json()["id"], "headers": user["headers"], "user_id": user["id"]}


@pytest.fixture
def populated(client, workspace, fake_llm):
    """A workspace with a bit of everything, so the counts have something to count."""
    base = f"/api/workspaces/{workspace['id']}"

    for index in range(2):
        conversation = client.post(f"{base}/conversations", json={},
                                   headers=workspace["headers"]).json()["id"]
        client.post(f"{base}/conversations/{conversation}/messages",
                    json={"content": f"Question number {index}"}, headers=workspace["headers"])

    client.post(base + "/documents",
                files={"file": ("notes.txt", b"pgvector stores embeddings in Postgres." * 20,
                                "text/plain")},
                headers=workspace["headers"])
    client.post(f"{base}/memory", json={"content": "Prefers concise answers", "importance": 0.9},
                headers=workspace["headers"])
    client.post(f"{base}/prompts", json={"title": "P", "body": "body"},
                headers=workspace["headers"])
    return workspace


# ------------------------------------------------------------- THE PHASE 7 GATE
def test_every_dashboard_number_matches_raw_sql(client, populated, engine):
    """Compare the API's totals against independent COUNT queries."""
    from sqlalchemy.orm import sessionmaker

    from db.models import (
        Chunk, Conversation, Document, MemoryItem, Message, PromptTemplate,
    )

    body = client.get(f"/api/workspaces/{populated['id']}/dashboard",
                      headers=populated["headers"]).json()
    totals = body["totals"]

    session = sessionmaker(bind=engine)()
    workspace_id, user_id = populated["id"], populated["user_id"]

    expected = {
        "conversations": session.execute(
            select(func.count(Conversation.id)).where(Conversation.workspace_id == workspace_id)
        ).scalar_one(),
        "messages": session.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.workspace_id == workspace_id)
        ).scalar_one(),
        "documents": session.execute(
            select(func.count(Document.id)).where(Document.workspace_id == workspace_id)
        ).scalar_one(),
        "chunks": session.execute(
            select(func.count(Chunk.id))
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.workspace_id == workspace_id)
        ).scalar_one(),
        "memories": session.execute(
            select(func.count(MemoryItem.id)).where(MemoryItem.user_id == user_id)
        ).scalar_one(),
        "prompts": session.execute(
            select(func.count(PromptTemplate.id)).where(
                PromptTemplate.user_id == user_id, PromptTemplate.is_current.is_(True)
            )
        ).scalar_one(),
    }
    session.close()

    for key, value in expected.items():
        assert totals[key] == value, f"dashboard said {key}={totals[key]}, SQL said {value}"

    # And the counts are not all trivially zero, which would make the comparison meaningless.
    assert totals["conversations"] == 2
    assert totals["messages"] == 4
    assert totals["documents"] == 1


def test_token_totals_match_the_logs(client, populated, engine):
    from sqlalchemy.orm import sessionmaker

    from db.models import Log

    usage = client.get(f"/api/workspaces/{populated['id']}/dashboard",
                       headers=populated["headers"]).json()["usage"]

    session = sessionmaker(bind=engine)()
    rows = session.execute(
        select(Log.tokens_in, Log.tokens_out, Log.latency_ms)
        .where(Log.workspace_id == populated["id"])
    ).all()
    session.close()

    assert usage["tokens_in"] == sum(r[0] or 0 for r in rows)
    assert usage["tokens_out"] == sum(r[1] or 0 for r in rows)
    assert usage["tokens_total"] == usage["tokens_in"] + usage["tokens_out"]

    # "Calls" means rows that did work. Administrative events — a workspace created, a memory
    # added by hand — are logged for the activity feed but never touched a provider, and
    # counting them would make the number meaningless.
    work = [r for r in rows if (r[0] or 0) or (r[1] or 0) or (r[2] or 0)]
    assert usage["calls"] == len(work)
    assert len(work) < len(rows), "the fixture should include at least one admin-only log row"


# -------------------------------------------------------------------- the maths
def test_cost_is_zero_on_a_free_provider():
    """Groq and Google are priced at zero in the registry, so this is honest, not a placeholder."""
    assert dashboard_service.estimate_cost("groq", 1_000_000, 1_000_000) == 0.0


def test_cost_is_computed_for_a_paid_provider():
    # gpt-4o-mini: $0.15 per 1M in, $0.60 per 1M out.
    cost = dashboard_service.estimate_cost("openai", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)


def test_an_unknown_provider_costs_nothing_rather_than_crashing():
    assert dashboard_service.estimate_cost(None, 1000, 1000) == 0.0
    assert dashboard_service.estimate_cost("who?", 1000, 1000) == 0.0


def test_percentile_picks_the_slow_tail():
    values = list(range(1, 101))
    assert dashboard_service._percentile(values, 95) == 96
    assert dashboard_service._percentile([], 95) == 0


def test_daily_usage_fills_quiet_days_with_zero(client, populated):
    daily = client.get(f"/api/workspaces/{populated['id']}/dashboard",
                       headers=populated["headers"]).json()["daily"]
    assert len(daily) == dashboard_service.ACTIVITY_DAYS
    # Dates ascend and none are skipped.
    dates = [entry["date"] for entry in daily]
    assert dates == sorted(dates)
    assert all(isinstance(entry["tokens"], int) for entry in daily)


def test_usage_is_broken_down_by_what_caused_the_call(client, populated):
    by_event = client.get(f"/api/workspaces/{populated['id']}/dashboard",
                          headers=populated["headers"]).json()["by_event"]
    events = {entry["event"] for entry in by_event}
    # Chat and the document upload both logged, so the breakdown is not a single bar.
    assert "chat" in events
    assert "upload" in events


def test_recent_activity_is_newest_first(client, populated):
    activity = client.get(f"/api/workspaces/{populated['id']}/dashboard",
                          headers=populated["headers"]).json()["activity"]
    assert len(activity) > 0
    timestamps = [entry["created_at"] for entry in activity]
    assert timestamps == sorted(timestamps, reverse=True)


def test_top_memories_lists_only_ones_that_were_used(client, workspace, fake_llm):
    base = f"/api/workspaces/{workspace['id']}"
    client.post(f"{base}/memory", json={"content": "Used memory", "importance": 0.9},
                headers=workspace["headers"])
    client.post(f"{base}/memory", json={"content": "Never used", "importance": 0.02},
                headers=workspace["headers"])

    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]
    client.post(f"{base}/conversations/{conversation}/messages", json={"content": "hello there"},
                headers=workspace["headers"])

    top = client.get(f"{base}/dashboard", headers=workspace["headers"]).json()["top_memories"]
    assert [m["content"] for m in top] == ["Used memory"]


def test_another_users_data_is_not_counted(client, workspace, make_user, fake_llm):
    """Two users on one deployment must not see each other's numbers."""
    other = make_user("other@example.com")
    other_workspace = client.post("/api/workspaces", json={"name": "Theirs"},
                                  headers=other["headers"]).json()["id"]
    conversation = client.post(f"/api/workspaces/{other_workspace}/conversations", json={},
                               headers=other["headers"]).json()["id"]
    client.post(f"/api/workspaces/{other_workspace}/conversations/{conversation}/messages",
                json={"content": "their private question"}, headers=other["headers"])

    mine = client.get(f"/api/workspaces/{workspace['id']}/dashboard",
                      headers=workspace["headers"]).json()
    assert mine["totals"]["conversations"] == 0
    assert mine["usage"]["calls"] == 0


def test_another_user_cannot_read_your_dashboard(client, workspace, make_user):
    intruder = make_user("intruder@example.com")
    assert client.get(f"/api/workspaces/{workspace['id']}/dashboard",
                      headers=intruder["headers"]).status_code == 403


# -------------------------------------------------------------------- export
def test_export_contains_the_whole_conversation(client, workspace, fake_llm):
    base = f"/api/workspaces/{workspace['id']}"
    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]
    client.post(f"{base}/conversations/{conversation}/messages",
                json={"content": "What is pgvector?"}, headers=workspace["headers"])

    response = client.get(f"{base}/conversations/{conversation}/export",
                          headers=workspace["headers"])
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]

    text = response.text
    assert "What is pgvector?" in text
    assert fake_llm.reply in text
    assert "### You" in text
    assert workspace_name_in(text)


def workspace_name_in(text: str) -> bool:
    return "Research" in text


def test_export_includes_citations_and_memory(client, workspace, fake_llm):
    base = f"/api/workspaces/{workspace['id']}"
    client.post(f"{base}/memory", json={"content": "Prefers British English", "importance": 0.9},
                headers=workspace["headers"])
    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]
    client.post(f"{base}/conversations/{conversation}/messages",
                json={"content": "A question"}, headers=workspace["headers"])

    text = client.get(f"{base}/conversations/{conversation}/export",
                      headers=workspace["headers"]).text
    assert "Applied from memory" in text
    assert "Prefers British English" in text


def test_export_as_download_sets_a_filename(client, workspace, fake_llm):
    base = f"/api/workspaces/{workspace['id']}"
    conversation = client.post(f"{base}/conversations", json={"title": "Vector DB decision"},
                               headers=workspace["headers"]).json()["id"]
    response = client.get(f"{base}/conversations/{conversation}/export?download=true",
                          headers=workspace["headers"])
    assert "attachment" in response.headers["content-disposition"]
    assert "Vector-DB-decision.md" in response.headers["content-disposition"]


def test_a_filename_cannot_contain_path_characters():
    from services.export_service import safe_filename

    name = safe_filename("../../etc/passwd: report?")
    assert "/" not in name and "\\" not in name and ":" not in name
    assert name.endswith(".md")


def test_another_user_cannot_export_your_conversation(client, workspace, make_user, fake_llm):
    base = f"/api/workspaces/{workspace['id']}"
    conversation = client.post(f"{base}/conversations", json={},
                               headers=workspace["headers"]).json()["id"]
    intruder = make_user("intruder@example.com")
    assert client.get(f"{base}/conversations/{conversation}/export",
                      headers=intruder["headers"]).status_code == 403
