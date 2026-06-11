"""Multi-vendor trace ingestion.

In a multi-vendor stack, the per-turn stage timings ElevenLabs can't see (ASR,
LLM, telephony transport) are known to your **orchestrator** — the layer wiring
Twilio/Vapi + OpenAI/Anthropic + ElevenLabs together. It reports them here, keyed
by ``conversation_id`` + ``turn_index``, and the dashboard recomputes true
end-to-end latency and the bottleneck stage.

This is decoupled from the ElevenLabs webhook on purpose: traces may arrive
before or after the post-call transcript, so this endpoint enriches whatever
turns already exist.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Conversation, RawEvent
from app.schemas.api import ConversationDetail
from app.schemas.elevenlabs import PipelineStage
from app.services.ingest import recompute_conversation_pipeline

logger = logging.getLogger("observability.traces")

router = APIRouter(prefix="/traces", tags=["traces"])


class TurnTrace(BaseModel):
    turn_index: int
    stages: list[PipelineStage]


class TraceIngest(BaseModel):
    conversation_id: str
    turns: list[TurnTrace] = Field(default_factory=list)


@router.post("", response_model=ConversationDetail)
def ingest_trace(payload: TraceIngest, db: Session = Depends(get_db)) -> ConversationDetail:
    """Attach multi-vendor stage timings to an existing conversation's turns."""
    conv = db.execute(
        select(Conversation)
        .options(selectinload(Conversation.turns))
        .where(Conversation.id == payload.conversation_id)
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    db.add(
        RawEvent(
            conversation_id=payload.conversation_id,
            event_type="pipeline_trace",
            source="trace",
            payload=payload.model_dump(mode="json"),
        )
    )

    stages_by_index = {t.turn_index: t.stages for t in payload.turns}
    matched = 0
    for turn in conv.turns:
        if turn.turn_index in stages_by_index:
            turn.pipeline_stages = [s.model_dump() for s in stages_by_index[turn.turn_index]]
            matched += 1

    recompute_conversation_pipeline(conv)
    db.commit()
    db.refresh(conv)
    logger.info("Trace enriched %s (%d turns)", payload.conversation_id, matched)
    return ConversationDetail.model_validate(conv)
