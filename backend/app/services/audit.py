"""Audit logging helper.

Centralizes writing ``AuditLog`` rows so every read of a PII-bearing transcript
(view, replay, export, search) is recorded consistently.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
    commit: bool = True,
) -> AuditLog:
    """Append an audit entry. Commits by default for fire-and-forget call sites."""
    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
