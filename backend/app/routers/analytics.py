"""Analytics API: KPI summary, time-series and per-agent breakdown."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.api import AgentStats, KpiSummary, PipelineBreakdown, TimeSeriesPoint
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _since(days: int | None) -> datetime | None:
    return datetime.now(UTC) - timedelta(days=days) if days else None


@router.get("/summary", response_model=KpiSummary)
def summary(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    days: int | None = Query(default=None, ge=1, le=365),
) -> KpiSummary:
    """Headline KPI cards for the dashboard."""
    return analytics.kpi_summary(db, agent_id=agent_id, since=_since(days))


@router.get("/timeseries", response_model=list[TimeSeriesPoint])
def timeseries(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    days: int = Query(default=14, ge=1, le=365),
    bucket: str = Query(default="day", pattern="^(day|hour)$"),
) -> list[TimeSeriesPoint]:
    """Bucketed trend lines for charts."""
    return analytics.time_series(db, agent_id=agent_id, days=days, bucket=bucket)


@router.get("/agents", response_model=list[AgentStats])
def agents(
    db: Session = Depends(get_db),
    days: int | None = Query(default=None, ge=1, le=365),
) -> list[AgentStats]:
    """Per-agent performance breakdown."""
    return analytics.agent_stats(db, since=_since(days))


@router.get("/pipeline", response_model=PipelineBreakdown)
def pipeline(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    days: int | None = Query(default=None, ge=1, le=365),
) -> PipelineBreakdown:
    """Multi-vendor pipeline latency: true end-to-end + per-stage p95 + bottleneck."""
    return analytics.pipeline_breakdown(db, agent_id=agent_id, since=_since(days))
