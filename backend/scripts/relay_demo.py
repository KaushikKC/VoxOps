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


async def run(base: str, agent_id: str, conversation_id: str, speed: float) -> None:
    uri = f"{base}/relay/ingest/{agent_id}?conversation_id={conversation_id}"
    async with websockets.connect(uri) as ws:
        print(f"streaming to {uri}")
        for etype, payload in SCRIPT:
            event = {"type": etype, f"{etype}_event": payload}
            await ws.send(json.dumps(event))
            ack = json.loads(await ws.recv())
            frame = ack.get("frame", {})
            print(
                f"  {etype:<24} turns={frame.get('turn_count')} "
                f"interrupts={frame.get('interruptions')} ping={frame.get('avg_ping_ms')}"
            )
            await asyncio.sleep(random.uniform(0.6, 1.6) / speed)
        await ws.send(json.dumps({"type": "end"}))
        print(f"ended — conversation {conversation_id} persisted.")


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
