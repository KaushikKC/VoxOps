"""Conversation model.

One row per call/session. Raw ElevenLabs fields are stored alongside
denormalized, computed observability metrics so the dashboard can filter and
aggregate without recomputing on every request.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"

    # ElevenLabs ``conversation_id`` as primary key.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )

    # --- Raw ElevenLabs metadata ---
    status: Mapped[str] = mapped_column(String, default="done", index=True)
    start_time_unix_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    call_duration_secs: Mapped[int] = mapped_column(Integer, default=0)
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    main_language: Mapped[str | None] = mapped_column(String, nullable=True)
    environment: Mapped[str] = mapped_column(String, default="production")
    version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    initiation_source: Mapped[str | None] = mapped_column(String, nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Analysis (from ElevenLabs or our judge) ---
    call_successful: Mapped[str] = mapped_column(String, default="unknown", index=True)
    transcript_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_title: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluation_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_collection: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Computed observability metrics (denormalized) ---
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    user_turn_count: Mapped[int] = mapped_column(Integer, default=0)
    agent_turn_count: Mapped[int] = mapped_column(Integer, default=0)
    interruption_count: Mapped[int] = mapped_column(Integer, default=0)
    interruption_rate: Mapped[float] = mapped_column(Float, default=0.0)
    # Talk ratio = agent words / (agent words + user words).
    talk_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    llm_ttfb_p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttfb_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttfb_max_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttf_sentence_p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    sentiment_overall: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Cost breakdown (USD), mirroring ElevenLabs billing ---
    cost_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_call_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_llm_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_tts_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cost_asr_usd: Mapped[float] = mapped_column(Float, default=0.0)
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    # ElevenLabs reports cost in credits; keep the raw value for reconciliation.
    cost_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- SLO state ---
    breached_slo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # --- Human-in-the-loop ---
    # True if a supervisor took over the call from the AI agent at any point.
    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    supervisor: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Provenance --- (source: webhook|relay|backfill|simulator)
    source: Mapped[str] = mapped_column(String, default="webhook")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship(back_populates="conversations")  # noqa: F821
    turns: Mapped[list["Turn"]] = relationship(  # noqa: F821
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Turn.turn_index",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Conversation {self.id} agent={self.agent_id} status={self.status}>"
