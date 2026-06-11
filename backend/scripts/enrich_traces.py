"""Enrich a (real) conversation with multi-vendor pipeline stage timings.

ElevenLabs reports only its own (LLM/TTS) slice. In production your orchestrator
(Twilio/Vapi + the LLM layer) reports the rest via ``POST /traces``. This script
simulates that orchestrator for a conversation that's already been ingested
(e.g. via ``python -m app.backfill``): it reads the call's agent turns from the
running backend, attaches realistic ASR / LLM / TTS / transport stages — reusing
the *real* LLM time-to-first-byte from the call so the numbers stay consistent —
and posts them. The dashboard's true-E2E + bottleneck widgets then light up.

Usage (backend must be running, conversation already backfilled)::

    python scripts/enrich_traces.py conv_0701kv0qhb51fxrr5rkzx1enxayx
    python scripts/enrich_traces.py <id> --llm-vendor anthropic --base http://localhost:8000
"""

from __future__ import annotations

import argparse
import random
import sys

import httpx


def build_stages(turn: dict, llm_vendor: str) -> list[dict]:
    """Realistic stage timings (ms) for one agent turn."""
    # Reuse the real LLM TTFB when ElevenLabs reported it; otherwise approximate.
    llm_ms = turn.get("llm_ttfb_ms")
    if not llm_ms:
        llm_ms = round(random.uniform(300, 1400), 1)
    asr_ms = round(random.uniform(70, 180), 1)
    tts_ms = round(random.uniform(150, 450), 1)
    transport_ms = round(random.uniform(40, 120), 1)
    return [
        {"stage": "asr", "vendor": "deepgram", "duration_ms": asr_ms},
        {"stage": "llm", "vendor": llm_vendor, "duration_ms": round(float(llm_ms), 1)},
        {"stage": "tts", "vendor": "elevenlabs", "duration_ms": tts_ms},
        {"stage": "transport", "vendor": "twilio", "duration_ms": transport_ms},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach multi-vendor pipeline stages to a call.")
    parser.add_argument("conversation_id")
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--llm-vendor", default="openai")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    with httpx.Client(timeout=30) as client:
        # 1. Read the conversation's turns from the running backend.
        r = client.get(f"{base}/conversations/{args.conversation_id}")
        if r.status_code == 404:
            sys.exit(
                f"Conversation {args.conversation_id} not found. "
                "Run 'python -m app.backfill' first so it's imported."
            )
        r.raise_for_status()
        detail = r.json()

        agent_turns = [t for t in detail["turns"] if t["role"] == "agent"]
        if not agent_turns:
            sys.exit("No agent turns to enrich in this conversation.")

        trace = {
            "conversation_id": args.conversation_id,
            "turns": [
                {"turn_index": t["turn_index"], "stages": build_stages(t, args.llm_vendor)}
                for t in agent_turns
            ],
        }

        # 2. Post the stages; the backend recomputes E2E + bottleneck.
        resp = client.post(f"{base}/traces", json=trace)
        resp.raise_for_status()
        out = resp.json()

    print(f"Enriched {len(agent_turns)} agent turn(s) of {args.conversation_id}.")
    print(f"  true E2E p95: {out.get('e2e_latency_p95_ms')} ms")
    print(f"  dominant bottleneck: {out.get('bottleneck_stage')}")
    print("Open this conversation in the dashboard — the pipeline bars now appear.")


if __name__ == "__main__":
    main()
