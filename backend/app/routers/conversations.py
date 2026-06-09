"""Conversations API: list with filters, detail, and replay timeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Conversation
from app.schemas.api import (
    ConversationDetail,
    ConversationPage,
    ConversationSummary,
)
from app.services import audit

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _actor(request: Request) -> str:
    return request.headers.get("x-actor", "anonymous")


@router.get("", response_model=ConversationPage)
def list_conversations(
    db: Session = Depends(get_db),
    agent_id: str | None = None,
    status: str | None = None,
    success: str | None = Query(default=None, description="success|failure|unknown"),
    sentiment: str | None = Query(default=None, description="positive|neutral|negative"),
    breached_slo: bool | None = None,
    source: str | None = None,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationPage:
    """Paginated, filterable list of conversations (newest first)."""
    filters = []
    if agent_id:
        filters.append(Conversation.agent_id == agent_id)
    if status:
        filters.append(Conversation.status == status)
    if success:
        filters.append(Conversation.call_successful == success)
    if sentiment:
        filters.append(Conversation.sentiment_overall == sentiment)
    if breached_slo is not None:
        filters.append(Conversation.breached_slo == breached_slo)
    if source:
        filters.append(Conversation.source == source)

    total = db.execute(
        select(func.count()).select_from(Conversation).where(*filters)
    ).scalar_one()

    rows = db.execute(
        select(Conversation)
        .where(*filters)
        .order_by(Conversation.ingested_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    return ConversationPage(
        items=[ConversationSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _load_detail(db: Session, conversation_id: str) -> Conversation:
    conv = db.execute(
        select(Conversation)
        .options(selectinload(Conversation.turns))
        .where(Conversation.id == conversation_id)
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, request: Request, db: Session = Depends(get_db)
) -> ConversationDetail:
    """Full conversation incl. turn-by-turn timeline. Logs an audit 'view'."""
    conv = _load_detail(db, conversation_id)
    audit.record(
        db,
        actor=_actor(request),
        action="view",
        resource_type="conversation",
        resource_id=conversation_id,
        ip_address=request.client.host if request.client else None,
    )
    return ConversationDetail.model_validate(conv)


@router.get("/{conversation_id}/replay")
def replay_conversation(
    conversation_id: str, request: Request, db: Session = Depends(get_db)
) -> dict:
    """Ordered timeline for the replay view, with cumulative timing per turn.

    Logs an audit 'replay' action — replaying a transcript is an access event.
    """
    conv = _load_detail(db, conversation_id)
    audit.record(
        db,
        actor=_actor(request),
        action="replay",
        resource_type="conversation",
        resource_id=conversation_id,
        ip_address=request.client.host if request.client else None,
    )

    timeline = [
        {
            "turn_index": t.turn_index,
            "role": t.role,
            "message": t.message,
            "at_secs": t.time_in_call_secs,
            "interrupted": t.interrupted,
            "original_message": t.original_message,
            "llm_ttfb_ms": t.llm_ttfb_ms,
            "llm_ttf_sentence_ms": t.llm_ttf_sentence_ms,
            "sentiment": t.sentiment,
            "sentiment_score": t.sentiment_score,
            "tool_calls": t.tool_calls,
        }
        for t in conv.turns
    ]
    return {
        "conversation_id": conv.id,
        "agent_id": conv.agent_id,
        "duration_secs": conv.call_duration_secs,
        "summary": conv.transcript_summary,
        "timeline": timeline,
    }
