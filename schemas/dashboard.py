"""Dashboard payloads."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceTotals(BaseModel):
    conversations: int
    messages: int
    documents: int
    chunks: int
    memories: int
    prompts: int


class UsageTotals(BaseModel):
    calls: int
    failed_calls: int
    tokens_in: int
    tokens_out: int
    tokens_total: int
    # Zero on free tiers, which is the honest figure rather than a placeholder. Tokens are the
    # number that actually varies, so the UI leads with those.
    estimated_cost_usd: float
    average_latency_ms: int
    p95_latency_ms: int


class EventUsage(BaseModel):
    event: str
    calls: int
    tokens: int


class DailyUsage(BaseModel):
    date: str
    tokens: int


class ActivityEntry(BaseModel):
    event: str
    detail: str | None
    model: str | None
    tokens: int
    latency_ms: int
    status: str
    created_at: datetime


class TopMemory(BaseModel):
    content: str
    kind: str
    use_count: int


class DashboardResponse(BaseModel):
    totals: WorkspaceTotals
    usage: UsageTotals
    by_event: list[EventUsage] = Field(default_factory=list)
    daily: list[DailyUsage] = Field(default_factory=list)
    activity: list[ActivityEntry] = Field(default_factory=list)
    top_memories: list[TopMemory] = Field(default_factory=list)
    # So the UI can say "$0.00 because this provider is free" rather than implying it is free
    # everywhere.
    provider_chain: list[str] = Field(default_factory=list)
