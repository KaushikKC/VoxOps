"""Alerts API: list SLO breaches, re-evaluate fleet SLOs, resolve alerts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert
from app.schemas.api import AlertOut
from app.services.alerting import evaluate_fleet_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    db: Session = Depends(get_db),
    resolved: bool | None = None,
    severity: str | None = None,
    agent_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AlertOut]:
    filters = []
    if resolved is not None:
        filters.append(Alert.resolved == resolved)
    if severity:
        filters.append(Alert.severity == severity)
    if agent_id:
        filters.append(Alert.agent_id == agent_id)
    rows = db.execute(
        select(Alert).where(*filters).order_by(Alert.created_at.desc()).limit(limit)
    ).scalars().all()
    return [AlertOut.model_validate(r) for r in rows]


@router.post("/evaluate-fleet", response_model=list[AlertOut])
def evaluate_fleet(
    db: Session = Depends(get_db),
    window: int = Query(default=50, ge=1, le=1000),
) -> list[AlertOut]:
    """Evaluate fleet-level SLOs (e.g. success rate) over a rolling window."""
    alerts = evaluate_fleet_alerts(db, window=window)
    db.commit()
    return [AlertOut.model_validate(a) for a in alerts]


@router.post("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db)) -> AlertOut:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.resolved = True
    db.commit()
    return AlertOut.model_validate(alert)
