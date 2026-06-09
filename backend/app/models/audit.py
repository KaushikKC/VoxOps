"""AuditLog model.

Records who viewed or exported a conversation. A replay/audit dashboard for
voice agents handles transcripts that often contain PII, so access itself is an
auditable event.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, default="anonymous", index=True)
    action: Mapped[str] = mapped_column(String, index=True)  # view|replay|export|search
    resource_type: Mapped[str] = mapped_column(String)  # conversation|agent|dashboard
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<AuditLog {self.actor} {self.action} {self.resource_type}:{self.resource_id}>"
