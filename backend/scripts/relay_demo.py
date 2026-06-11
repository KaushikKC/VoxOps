"""Drive the live relay with a scripted conversation.

Streams ElevenLabs-style events to ``/relay/ingest/{agent_id}`` with realistic
pauses so the dashboard's **Live Monitor** shows an in-flight call, then ends it
(which persists the conversation). Run the backend first, then::

    python scripts/relay_demo.py
    # open http://localhost:5173/live  (or :8080/live under Docker)

Requires the ``websockets`` package (ships with uvicorn[standard]).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random

import websockets

SCRIPT = [
    ("user_transcript", {"user_transcript": "Hi, I'd like to check on my order status."}),
    ("ping", {"event_id": 1, "ping_ms": 47}),
    ("agent_response", {"agent_response": "Sure! Can you give me your order number?"}),
    ("user_transcript", {"user_transcript": "It's 48213, it was supposed to arrive yesterday."}),
    ("vad_score", {"vad_score": 0.91}),
    ("ping", {"event_id": 2, "ping_ms": 53}),
    ("agent_response", {"agent_response": "Thanks. Let me pull that up for you right now."}),
    ("interruption", {"event_id": 3}),
    ("user_transcript", {"user_transcript": "It's really frustrating, I needed it today."}),
    ("agent_response", {"agent_response": "I understand. It's out for delivery, arriving by 5pm."}),
    ("user_transcript", {"user_transcript": "Oh great, thank you so much!"}),
]


async def _receiver(ws) -> None:
    """Print everything the relay sends back — acks and supervisor control.

    This is what makes the takeover demo work: when you click "Take over" in the
    dashboard, the relay pushes a control message down this socket and it prints
    here (a real bridge would mute the AI / play the human's words to the user).
    """
    try:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "ack":
                frame = msg.get("frame", {})
                print(
                    f"    ↳ turns={frame.get('turn_count')} "
                    f"interrupts={frame.get('interruptions')} "
                    f"control={frame.get('control')}"
                )
            elif msg.get("type") == "control":
                action = msg.get("action")
                if action == "take_over":
                    print(f"  ⛔ AI MUTED — supervisor {msg.get('supervisor')} took over")
                elif action == "human_message":
                    print(f"  🗣  supervisor says: {msg.get('text')}")
                elif action == "hand_back":
                    print("  ✅ control handed back to the AI")
    except Exception:
        pass


async def run(base: str, agent_id: str, conversation_id: str, speed: float) -> None:
    uri = f"{base}/relay/ingest/{agent_id}?conversation_id={conversation_id}"
    async with websockets.connect(uri) as ws:
        print(f"streaming to {uri}")
        print("open the dashboard's Live Monitor and click 'Take over' while this runs.\n")
        recv = asyncio.create_task(_receiver(ws))
        for etype, payload in SCRIPT:
            event = {"type": etype, f"{etype}_event": payload}
            await ws.send(json.dumps(event))
            print(f"  {etype}")
            await asyncio.sleep(random.uniform(1.2, 2.4) / speed)
        await ws.send(json.dumps({"type": "end"}))
        await asyncio.sleep(0.2)
        recv.cancel()
        print(f"\nended — conversation {conversation_id} persisted.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live relay demo driver.")
    parser.add_argument("--base", default="ws://localhost:8000")
    parser.add_argument("--agent", default="agent_demo")
    parser.add_argument("--conversation-id", default=f"live_demo_{random.randint(1000, 9999)}")
    parser.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    args = parser.parse_args()
    asyncio.run(run(args.base, args.agent, args.conversation_id, args.speed))


if __name__ == "__main__":
    main()
