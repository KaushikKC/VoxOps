"""Real-time relay API.

Three surfaces:

* ``WS /relay/ingest/{agent_id}`` — a producer (a browser client, or a bridge to
  the ElevenLabs conversation WebSocket) streams ElevenLabs events as JSON. The
  relay logs each event, updates live metrics, broadcasts observability frames
  to monitors, and persists the conversation when the stream ends.
* ``WS /relay/monitor`` — dashboards subscribe here to receive live frames.
* ``GET /relay/active`` — REST snapshot of in-flight calls.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import SessionLocal
from app.models import RawEvent
from app.services.alerting import evaluate_conversation_alerts
from app.services.ingest import ingest_conversation
from app.services.relay import manager

logger = logging.getLogger("observability.relay")

router = APIRouter(prefix="/relay", tags=["relay"])


@router.get("/active")
def active_calls() -> dict:
    """Snapshot of currently in-flight live conversations."""
    return {"active": manager.active}


@router.websocket("/monitor")
async def monitor(ws: WebSocket) -> None:
    """Dashboard subscription stream of live observability frames."""
    await ws.accept()
    manager.subscribe(ws)
    try:
        # Send the current snapshot immediately on connect.
        await ws.send_json({"type": "snapshot", "active": manager.active})
        while True:
            # Keep the socket alive; we don't expect inbound messages.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(ws)


@router.websocket("/ingest/{agent_id}")
async def ingest_stream(ws: WebSocket, agent_id: str) -> None:
    """Accept a live stream of ElevenLabs events for a single call."""
    await ws.accept()
    conversation_id = ws.query_params.get("conversation_id") or f"live_{uuid.uuid4().hex[:12]}"
    live = manager.start(agent_id, conversation_id)
    logger.info("Relay started agent=%s conversation=%s", agent_id, conversation_id)

    db = SessionLocal()
    try:
        while True:
            event = await ws.receive_json()

            # A control frame {"type": "end"} closes and persists the call.
            if event.get("type") == "end":
                break

            db.add(
                RawEvent(
                    conversation_id=live.conversation_id,
                    event_type=event.get("type", "unknown"),
                    source="relay",
                    payload=event,
                )
            )
            live.handle_event(event)
            await manager.broadcast(live.frame())

            # Echo the latest frame back to the producer (useful for testing).
            await ws.send_json({"type": "ack", "frame": live.frame()})

        db.commit()
    except WebSocketDisconnect:
        logger.info("Relay producer disconnected: %s", conversation_id)
    finally:
        manager.end(conversation_id)
        # Persist the accumulated conversation through the normalizer.
        if live.turns:
            data = live.to_conversation_data()
            conv = ingest_conversation(db, data, source="relay")
            evaluate_conversation_alerts(db, conv)
            db.commit()
            await manager.broadcast(
                {"type": "ended", "conversation_id": conversation_id, "turns": conv.turn_count}
            )
            logger.info(
                "Relay persisted conversation %s (%d turns)", conversation_id, conv.turn_count
            )
        db.close()
