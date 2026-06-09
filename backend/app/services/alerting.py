"""SLO alerting.

Evaluates a freshly ingested conversation against configured SLOs and raises
``Alert`` rows for breaches. Per-conversation rules fire on a single call;
fleet-level rules (success rate, interruption rate) are evaluated over a rolling
window by :func:`evaluate_fleet_alerts`.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, Conversation

logger = logging.getLogger("observability.alerting")
settings = get_settings()


def _raise(
    db: Session,
    *,
    rule: str,
    severity: str,
    message: str,
    threshold: float | None,
    observed: float | None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
) -> Alert:
    alert = Alert(
        conversation_id=conversation_id,
        agent_id=agent_id,
        rule=rule,
        severity=severity,
        message=message,
        threshold=threshold,
        observed_value=observed,
    )
    db.add(alert)
    logger.info("ALERT [%s] %s", severity, message)
    return alert


def evaluate_conversation_alerts(db: Session, conv: Conversation) -> list[Alert]:
    """Per-conversation SLO checks. Idempotent: clears prior alerts for the call."""
    # Re-delivery of a webhook re-evaluates the call; drop stale alerts first so
    # we don't accumulate duplicates.
    for existing in db.execute(
        select(Alert).where(Alert.conversation_id == conv.id)
    ).scalars():
        db.delete(existing)

    alerts: list[Alert] = []

    if conv.llm_ttfb_p95_ms is not None and conv.llm_ttfb_p95_ms > settings.slo_llm_ttfb_p95_ms:
        alerts.append(
            _raise(
                db,
                rule="latency_p95",
                severity="warning",
                message=(
                    f"Conversation {conv.id} LLM TTFB p95 "
                    f"{conv.llm_ttfb_p95_ms:.0f}ms exceeds "
                    f"{settings.slo_llm_ttfb_p95_ms:.0f}ms SLO"
                ),
                threshold=settings.slo_llm_ttfb_p95_ms,
                observed=conv.llm_ttfb_p95_ms,
                conversation_id=conv.id,
                agent_id=conv.agent_id,
            )
        )

    if conv.interruption_rate > settings.slo_interruption_rate_max:
        alerts.append(
            _raise(
                db,
                rule="interruption_rate",
                severity="warning",
                message=(
                    f"Conversation {conv.id} interruption rate "
                    f"{conv.interruption_rate:.0%} exceeds "
                    f"{settings.slo_interruption_rate_max:.0%} SLO"
                ),
                threshold=settings.slo_interruption_rate_max,
                observed=conv.interruption_rate,
                conversation_id=conv.id,
                agent_id=conv.agent_id,
            )
        )

    if conv.call_successful == "failure":
        alerts.append(
            _raise(
                db,
                rule="task_failure",
                severity="critical",
                message=f"Conversation {conv.id} did not complete its task",
                threshold=None,
                observed=None,
                conversation_id=conv.id,
                agent_id=conv.agent_id,
            )
        )

    return alerts


def evaluate_fleet_alerts(db: Session, window: int = 50) -> list[Alert]:
    """Fleet-level SLOs over the most recent ``window`` conversations."""
    recent_ids = db.execute(
        select(Conversation.id).order_by(Conversation.ingested_at.desc()).limit(window)
    ).scalars().all()
    if not recent_ids:
        return []

    total = len(recent_ids)
    successes = db.execute(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.id.in_(recent_ids), Conversation.call_successful == "success")
    ).scalar_one()
    success_rate = successes / total

    alerts: list[Alert] = []
    if success_rate < settings.slo_success_rate_min:
        alerts.append(
            _raise(
                db,
                rule="success_rate",
                severity="critical",
                message=(
                    f"Fleet success rate {success_rate:.0%} over last {total} calls "
                    f"is below {settings.slo_success_rate_min:.0%} SLO"
                ),
                threshold=settings.slo_success_rate_min,
                observed=success_rate,
            )
        )
    return alerts
