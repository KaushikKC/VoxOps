"""Real-time relay API.

Three surfaces:

* ``WS /relay/ingest/{agent_id}`` — a producer (a browser client, or a bridge to
  the ElevenLabs conversation WebSocket) streams ElevenLabs events as JSON. The
  relay logs each event, updates live metrics, broadcasts observability frames
  to monitors, and persists the conversation when the stream ends.
* ``WS /relay/monitor`` — dashboards subscribe here to receive live frames.
* ``GET /relay/active`` — REST snapshot of in-flight calls.
* ``POST /relay/{id}/takeover|handback|say`` — supervisor human-in-the-loop
  control: assume control of a live call from the AI, send messages as the
  agent, and hand control back.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect

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


async def _drain_control(ws: WebSocket, conversation_id: str) -> None:
    """Forward supervisor control commands down to the producer/bridge socket."""
    queue = manager.control_queue(conversation_id)
    if queue is None:
        return
    while True:
        message = await queue.get()
        await ws.send_json(message)


@router.websocket("/ingest/{agent_id}")
async def ingest_stream(ws: WebSocket, agent_id: str) -> None:
    """Accept a live stream of ElevenLabs events for a single call.

    Runs a background task that pushes supervisor control commands (take over,
    hand back, human messages) back down to the producer in real time.
    """
    await ws.accept()
    conversation_id = ws.query_params.get("conversation_id") or f"live_{uuid.uuid4().hex[:12]}"
    live = manager.start(agent_id, conversation_id)
    logger.info("Relay started agent=%s conversation=%s", agent_id, conversation_id)

    control_task = asyncio.create_task(_drain_control(ws, conversation_id))
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
        control_task.cancel()
        manager.end(conversation_id)
        # Persist the accumulated conversation through the normalizer.
        if live.turns:
            data = live.to_conversation_data()
            conv = ingest_conversation(db, data, source="relay")
            conv.human_takeover = live.had_takeover
            conv.supervisor = live.supervisor
            evaluate_conversation_alerts(db, conv)
            db.commit()
            await manager.broadcast(
                {"type": "ended", "conversation_id": conversation_id, "turns": conv.turn_count}
            )
            logger.info(
                "Relay persisted conversation %s (%d turns)", conversation_id, conv.turn_count
            )
        db.close()


def _require_live(conversation_id: str):
    live = manager.get(conversation_id)
    if live is None:
        raise HTTPException(status_code=404, detail="no active call with that id")
    return live


@router.post("/{conversation_id}/takeover")
async def takeover(conversation_id: str, supervisor: str = "supervisor") -> dict:
    """A human supervisor assumes control of a live call from the AI agent."""
    _require_live(conversation_id)
    live = await manager.take_over(conversation_id, supervisor)
    return {"status": "human_control", "conversation_id": conversation_id, "supervisor": supervisor,
            "control": live.control if live else "human"}


@router.post("/{conversation_id}/handback")
async def handback(conversation_id: str) -> dict:
    """Return control of a live call to the AI agent."""
    _require_live(conversation_id)
    live = await manager.hand_back(conversation_id)
    return {"status": "ai_control", "conversation_id": conversation_id,
            "control": live.control if live else "ai"}


@router.post("/{conversation_id}/say")
async def say(conversation_id: str, text: str = Body(..., embed=True)) -> dict:
    """Send a supervisor message, delivered to the user as the agent.

    Only valid while the call is under human control (call ``takeover`` first).
    """
    live = _require_live(conversation_id)
    if live.control != "human":
        raise HTTPException(status_code=409, detail="call is not under human control")
    await manager.say(conversation_id, text)
    return {"status": "sent", "conversation_id": conversation_id, "turns": len(live.turns)}
