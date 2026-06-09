"""Audit API: read the access log of who viewed/replayed/searched transcripts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog
from app.schemas.api import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut])
def list_audit(
    db: Session = Depends(get_db),
    actor: str | None = None,
    action: str | None = None,
    resource_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogOut]:
    """Most recent audit entries, newest first."""
    filters = []
    if actor:
        filters.append(AuditLog.actor == actor)
    if action:
        filters.append(AuditLog.action == action)
    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)
    rows = db.execute(
        select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc()).limit(limit)
    ).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]
