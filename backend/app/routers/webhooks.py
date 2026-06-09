"""ElevenLabs webhook ingestion endpoint.

Receives ``post_call_transcription`` (and tolerates other event types), verifies
the HMAC signature, appends the raw payload to the event log, and normalizes the
conversation into the observability store.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import RawEvent
from app.schemas.elevenlabs import PostCallWebhook
from app.services import search
from app.services.alerting import evaluate_conversation_alerts
from app.services.ingest import ingest_conversation
from app.services.security import SignatureError, verify_webhook

logger = logging.getLogger("observability.webhooks")
settings = get_settings()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/elevenlabs", status_code=status.HTTP_200_OK)
async def elevenlabs_webhook(
    request: Request,
    db: Session = Depends(get_db),
    elevenlabs_signature: str | None = Header(default=None),
) -> dict:
    """Ingest an ElevenLabs post-call webhook.

    Always returns 200 quickly on success so ElevenLabs does not retry. Returns
    401 on signature failure and 422 on an unparseable body.
    """
    raw_body = await request.body()

    if settings.elevenlabs_verify_signature:
        try:
            verify_webhook(
                body=raw_body,
                signature_header=elevenlabs_signature or "",
                secret=settings.elevenlabs_webhook_secret,
                max_age_seconds=settings.webhook_max_age_seconds,
            )
        except SignatureError as exc:
            logger.warning("Webhook signature rejected: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
            ) from exc

    try:
        payload = PostCallWebhook.model_validate_json(raw_body)
    except Exception as exc:
        logger.warning("Unparseable webhook body: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid webhook payload",
        ) from exc

    # Append-only raw log for replay/reprocessing.
    db.add(
        RawEvent(
            conversation_id=payload.data.conversation_id,
            event_type=payload.type,
            source="webhook",
            payload=payload.model_dump(mode="json"),
        )
    )

    if payload.type != "post_call_transcription":
        # Audio / failure events are logged but not normalized here.
        db.commit()
        return {"status": "logged", "type": payload.type}

    conversation = ingest_conversation(db, payload.data, source="webhook")
    evaluate_conversation_alerts(db, conversation)
    db.commit()

    # Index transcript for semantic search (best-effort, never blocks ingest).
    search.index_conversation_safe(conversation.id, payload.data)

    return {
        "status": "ingested",
        "conversation_id": conversation.id,
        "turns": conversation.turn_count,
        "breached_slo": conversation.breached_slo,
    }
