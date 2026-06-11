"""Audit logging helper.

Centralizes writing ``AuditLog`` rows so every read of a PII-bearing transcript
(view, replay, export, search) is recorded consistently.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger("observability.audit")


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
) -> AuditLog | None:
    """Append an audit entry. Best-effort: a failed audit write must never break
    the request it is recording (e.g. viewing a transcript), so any error is
    logged and swallowed rather than propagated.
    """
    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    try:
        db.add(entry)
        if commit:
            db.commit()
        return entry
    except Exception as exc:  # e.g. read-only DB / replica
        logger.warning("audit log write failed (%s %s): %s", action, resource_id, exc)
        db.rollback()
        return None
