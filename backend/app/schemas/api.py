"""Outbound API schemas — the contract the React frontend consumes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────── Conversations ────────────────────────────


class TurnOut(_ORM):
    turn_index: int
    role: str
    message: str | None
    time_in_call_secs: float
    interrupted: bool
    original_message: str | None
    llm_ttfb_ms: float | None
    llm_ttf_sentence_ms: float | None
    llm_input_tokens: int | None
    llm_output_tokens: int | None
    tool_calls: list | None
    sentiment: str | None
    sentiment_score: float | None
    source_medium: str | None


class ConversationSummary(_ORM):
    """Compact row for the conversations list."""

    id: str
    agent_id: str
    status: str
    started_at: datetime | None
    call_duration_secs: int
    call_successful: str
    summary_title: str | None
    turn_count: int
    interruption_count: int
    interruption_rate: float
    llm_ttfb_p95_ms: float | None
    sentiment_overall: str | None
    sentiment_score: float | None
    cost_total_usd: float
    breached_slo: bool
    human_takeover: bool
    supervisor: str | None
    source: str


class ConversationDetail(ConversationSummary):
    """Full conversation incl. turn-by-turn timeline for the replay/audit view."""

    transcript_summary: str | None
    main_language: str | None
    environment: str
    termination_reason: str | None
    evaluation_criteria: dict | None
    data_collection: dict | None
    talk_ratio: float | None
    user_turn_count: int
    agent_turn_count: int
    llm_ttfb_p50_ms: float | None
    llm_ttfb_max_ms: float | None
    llm_ttf_sentence_p95_ms: float | None
    cost_call_usd: float
    cost_llm_usd: float
    cost_tts_usd: float
    cost_asr_usd: float
    llm_input_tokens: int
    llm_output_tokens: int
    ingested_at: datetime
    turns: list[TurnOut]


class ConversationPage(BaseModel):
    items: list[ConversationSummary]
    total: int
    limit: int
    offset: int


# ──────────────────────────── Analytics ────────────────────────────


class KpiSummary(BaseModel):
    total_conversations: int
    success_rate: float
    avg_duration_secs: float
    llm_ttfb_p50_ms: float | None
    llm_ttfb_p95_ms: float | None
    interruption_rate: float
    avg_cost_usd: float
    total_cost_usd: float
    negative_sentiment_rate: float
    slo_breach_rate: float


class TimeSeriesPoint(BaseModel):
    bucket: str  # ISO date/hour
    conversations: int
    success_rate: float
    llm_ttfb_p95_ms: float | None
    interruption_rate: float
    avg_cost_usd: float


class AgentStats(BaseModel):
    agent_id: str
    agent_name: str | None
    conversations: int
    success_rate: float
    llm_ttfb_p95_ms: float | None
    interruption_rate: float
    avg_cost_usd: float


# ──────────────────────────── Alerts & audit ────────────────────────────


class AlertOut(_ORM):
    id: int
    conversation_id: str | None
    agent_id: str | None
    rule: str
    severity: str
    message: str
    threshold: float | None
    observed_value: float | None
    resolved: bool
    created_at: datetime


class AuditLogOut(_ORM):
    id: int
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict | None
    created_at: datetime


# ──────────────────────────── Semantic search ────────────────────────────


class SearchHit(BaseModel):
    conversation_id: str
    score: float
    snippet: str
    role: str | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
