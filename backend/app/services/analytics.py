"""Analytics aggregations.

SQL-backed rollups powering the dashboard KPI cards, time-series charts and
per-agent breakdown. Latency percentiles are computed in Python from the
per-conversation p95 values (SQLite has no native percentile function), which is
accurate enough for a fleet view and keeps the query portable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Conversation
from app.schemas.api import (
    AgentStats,
    KpiSummary,
    PipelineBreakdown,
    StageStat,
    TimeSeriesPoint,
)
from app.services.metrics import percentile
from app.services.pipeline import DEFAULT_VENDORS, stage_sort_key


def _base_filters(query, agent_id: str | None, since: datetime | None):
    if agent_id:
        query = query.where(Conversation.agent_id == agent_id)
    if since:
        query = query.where(Conversation.ingested_at >= since)
    return query


def kpi_summary(
    db: Session, *, agent_id: str | None = None, since: datetime | None = None
) -> KpiSummary:
    rows = db.execute(
        _base_filters(select(Conversation), agent_id, since)
    ).scalars().all()
    total = len(rows)
    if total == 0:
        return KpiSummary(
            total_conversations=0,
            success_rate=0.0,
            avg_duration_secs=0.0,
            llm_ttfb_p50_ms=None,
            llm_ttfb_p95_ms=None,
            e2e_latency_p95_ms=None,
            interruption_rate=0.0,
            avg_cost_usd=0.0,
            total_cost_usd=0.0,
            negative_sentiment_rate=0.0,
            slo_breach_rate=0.0,
        )

    successes = sum(1 for r in rows if r.call_successful == "success")
    negatives = sum(1 for r in rows if r.sentiment_overall == "negative")
    breaches = sum(1 for r in rows if r.breached_slo)
    ttfb_p50s = [r.llm_ttfb_p50_ms for r in rows if r.llm_ttfb_p50_ms is not None]
    ttfb_p95s = [r.llm_ttfb_p95_ms for r in rows if r.llm_ttfb_p95_ms is not None]
    e2e_p95s = [r.e2e_latency_p95_ms for r in rows if r.e2e_latency_p95_ms is not None]
    total_cost = sum(r.cost_total_usd for r in rows)

    return KpiSummary(
        total_conversations=total,
        success_rate=round(successes / total, 4),
        avg_duration_secs=round(sum(r.call_duration_secs for r in rows) / total, 2),
        llm_ttfb_p50_ms=percentile(ttfb_p50s, 50) if ttfb_p50s else None,
        llm_ttfb_p95_ms=percentile(ttfb_p95s, 95) if ttfb_p95s else None,
        e2e_latency_p95_ms=percentile(e2e_p95s, 95) if e2e_p95s else None,
        interruption_rate=round(sum(r.interruption_rate for r in rows) / total, 4),
        avg_cost_usd=round(total_cost / total, 6),
        total_cost_usd=round(total_cost, 4),
        negative_sentiment_rate=round(negatives / total, 4),
        slo_breach_rate=round(breaches / total, 4),
    )


def time_series(
    db: Session,
    *,
    agent_id: str | None = None,
    days: int = 14,
    bucket: str = "day",
) -> list[TimeSeriesPoint]:
    """Bucketed time series over the trailing ``days`` window."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        _base_filters(select(Conversation), agent_id, since).order_by(
            Conversation.ingested_at
        )
    ).scalars().all()

    fmt = "%Y-%m-%d" if bucket == "day" else "%Y-%m-%dT%H:00"
    grouped: dict[str, list[Conversation]] = {}
    for r in rows:
        key = (r.started_at or r.ingested_at).strftime(fmt)
        grouped.setdefault(key, []).append(r)

    points: list[TimeSeriesPoint] = []
    for key in sorted(grouped):
        items = grouped[key]
        n = len(items)
        successes = sum(1 for r in items if r.call_successful == "success")
        ttfb_p95s = [r.llm_ttfb_p95_ms for r in items if r.llm_ttfb_p95_ms is not None]
        points.append(
            TimeSeriesPoint(
                bucket=key,
                conversations=n,
                success_rate=round(successes / n, 4),
                llm_ttfb_p95_ms=percentile(ttfb_p95s, 95) if ttfb_p95s else None,
                interruption_rate=round(sum(r.interruption_rate for r in items) / n, 4),
                avg_cost_usd=round(sum(r.cost_total_usd for r in items) / n, 6),
            )
        )
    return points


def agent_stats(db: Session, *, since: datetime | None = None) -> list[AgentStats]:
    agents = db.execute(select(Agent)).scalars().all()
    out: list[AgentStats] = []
    for agent in agents:
        rows = db.execute(
            _base_filters(select(Conversation), agent.id, since)
        ).scalars().all()
        if not rows:
            continue
        n = len(rows)
        successes = sum(1 for r in rows if r.call_successful == "success")
        ttfb_p95s = [r.llm_ttfb_p95_ms for r in rows if r.llm_ttfb_p95_ms is not None]
        out.append(
            AgentStats(
                agent_id=agent.id,
                agent_name=agent.name,
                conversations=n,
                success_rate=round(successes / n, 4),
                llm_ttfb_p95_ms=percentile(ttfb_p95s, 95) if ttfb_p95s else None,
                interruption_rate=round(sum(r.interruption_rate for r in rows) / n, 4),
                avg_cost_usd=round(sum(r.cost_total_usd for r in rows) / n, 6),
            )
        )
    out.sort(key=lambda a: a.conversations, reverse=True)
    return out


def pipeline_breakdown(
    db: Session, *, agent_id: str | None = None, since: datetime | None = None
) -> PipelineBreakdown:
    """Fleet-level multi-vendor latency: per-stage p95 + bottleneck distribution."""
    rows = db.execute(
        _base_filters(select(Conversation), agent_id, since).where(
            Conversation.e2e_latency_p95_ms.is_not(None)
        )
    ).scalars().all()

    if not rows:
        return PipelineBreakdown(
            conversations=0,
            e2e_latency_p50_ms=None,
            e2e_latency_p95_ms=None,
            dominant_bottleneck=None,
            stages=[],
        )

    e2e_p50s = [r.e2e_latency_p50_ms for r in rows if r.e2e_latency_p50_ms is not None]
    e2e_p95s = [r.e2e_latency_p95_ms for r in rows if r.e2e_latency_p95_ms is not None]

    # Aggregate per-stage p95 across calls and count bottleneck occurrences.
    by_stage: dict[str, list[float]] = {}
    bottleneck_counts: dict[str, int] = {}
    for r in rows:
        for stage, p95 in (r.stage_latency_p95 or {}).items():
            by_stage.setdefault(stage, []).append(p95)
        if r.bottleneck_stage:
            bottleneck_counts[r.bottleneck_stage] = bottleneck_counts.get(r.bottleneck_stage, 0) + 1

    stage_p95 = {
        stage: round(percentile(values, 95) or 0.0, 2) for stage, values in by_stage.items()
    }
    total_p95 = sum(stage_p95.values()) or 1.0

    stages = [
        StageStat(
            stage=stage,
            vendor=DEFAULT_VENDORS.get(stage, "unknown"),
            p95_ms=p95,
            share_of_e2e=round(p95 / total_p95, 4),
            bottleneck_count=bottleneck_counts.get(stage, 0),
        )
        for stage, p95 in sorted(stage_p95.items(), key=lambda kv: stage_sort_key(kv[0]))
    ]
    dominant = max(bottleneck_counts, key=bottleneck_counts.get) if bottleneck_counts else None

    return PipelineBreakdown(
        conversations=len(rows),
        e2e_latency_p50_ms=percentile(e2e_p50s, 50) if e2e_p50s else None,
        e2e_latency_p95_ms=percentile(e2e_p95s, 95) if e2e_p95s else None,
        dominant_bottleneck=dominant,
        stages=stages,
    )
