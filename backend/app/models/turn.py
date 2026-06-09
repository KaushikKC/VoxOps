"""Turn model — one row per conversation turn (user or agent)."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)

    role: Mapped[str] = mapped_column(String)  # "user" | "agent"
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_in_call_secs: Mapped[float] = mapped_column(Float, default=0.0)

    # Barge-in: the user interrupted the agent during this turn.
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    original_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Per-turn latency (agent turns), from conversation_turn_metrics ---
    llm_ttfb_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ttf_sentence_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Per-turn token usage (agent turns) ---
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Tooling ---
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_results: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- Per-turn sentiment (user turns primarily) ---
    sentiment: Mapped[str | None] = mapped_column(String, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    source_medium: Mapped[str | None] = mapped_column(String, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Turn {self.conversation_id}#{self.turn_index} {self.role}>"
