"""RawEvent model.

An append-only log of raw payloads — inbound webhook bodies and real-time relay
events — kept for audit, replay and reprocessing. Storing the raw envelope means
we can re-run the normalizer/metrics engine after a logic change without losing
fidelity.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # e.g. "post_call_transcription", "user_transcript", "interruption", "ping"
    event_type: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="webhook")  # webhook|relay
    payload: Mapped[dict] = mapped_column(JSON)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<RawEvent {self.event_type} conv={self.conversation_id}>"
