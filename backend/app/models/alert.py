"""Alert model — SLO breaches raised by the alerting engine."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # e.g. "latency_p95", "success_rate", "interruption_rate"
    rule: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, default="warning")  # info|warning|critical
    message: Mapped[str] = mapped_column(Text)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Alert {self.rule} sev={self.severity} resolved={self.resolved}>"
