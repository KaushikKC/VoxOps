"""Conversation simulator / seeder.

Generates realistic ``post_call_transcription`` payloads so the entire dashboard
is demoable without a paid ElevenLabs account. Calls are spread over a trailing
window with a realistic spread of latency (some breaching the SLO),
interruptions, sentiment and outcomes.

Usage::

    python -m app.simulator --calls 50 --days 14         # seed DB directly
    python -m app.simulator --calls 50 --url http://localhost:8000  # via webhook

The ``--url`` mode signs each request with the configured webhook secret so it
exercises the full HMAC-verified ingestion path.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import UTC, datetime, timedelta

from app.schemas.elevenlabs import (
    AnalysisModel,
    ChargingModel,
    ConversationData,
    MetadataModel,
    PipelineStage,
    TranscriptTurn,
    TurnMetrics,
    TurnMetricValue,
)

# LLM brains vary by deployment; pick one per simulated call.
_LLM_VENDORS = ["openai", "anthropic"]

# (agent_id, agent_name, scenario title, [(role, message), ...], base_outcome)
_SCENARIOS = [
    (
        "agent_support",
        "Support Assistant",
        "Refund request resolved",
        [
            ("agent", "Thanks for calling support, how can I help you today?"),
            ("user", "Hi, I was charged twice for my subscription this month."),
            ("agent", "I'm sorry about that. Let me pull up your account and check."),
            ("user", "Okay, thank you. It's really frustrating to see a double charge."),
            ("agent", "I can see the duplicate charge and I've issued a full refund."),
            ("user", "Oh great, thank you so much. That was quick and helpful."),
        ],
        "success",
    ),
    (
        "agent_support",
        "Support Assistant",
        "Login issue unresolved",
        [
            ("agent", "Hi there, what can I help you with?"),
            ("user", "I can't log in, the password reset email never arrives."),
            ("agent", "Let me check. Can you confirm the email on the account?"),
            ("user", "This is so annoying, I've tried five times already."),
            ("agent", "I understand. I've triggered a manual reset, please check now."),
            ("user", "Still nothing. This is useless, I give up."),
        ],
        "failure",
    ),
    (
        "agent_booking",
        "Booking Concierge",
        "Restaurant reservation booked",
        [
            ("agent", "Hello! Would you like to make a reservation?"),
            ("user", "Yes, a table for four this Friday at 7pm please."),
            ("agent", "Wonderful, I have a table for four on Friday at 7pm. Your name?"),
            ("user", "Perfect, it's under Kaushik."),
            ("agent", "All set, Kaushik. You'll get a confirmation text shortly."),
            ("user", "Amazing, thanks a lot!"),
        ],
        "success",
    ),
    (
        "agent_sales",
        "Sales Qualifier",
        "Demo scheduled",
        [
            ("agent", "Hi, I saw you signed up — what brought you to us?"),
            ("user", "We're evaluating voice agents for our call center."),
            ("agent", "Great fit. How many calls do you handle per day?"),
            ("user", "Around two thousand. We care a lot about latency and cost."),
            ("agent", "Understood. Let's book a demo to show our reliability tooling."),
            ("user", "Sure, that works. Send me a calendar invite."),
        ],
        "success",
    ),
    (
        "agent_billing",
        "Billing Bot",
        "Plan downgrade",
        [
            ("agent", "Hi, how can I help with your billing today?"),
            ("user", "I want to downgrade to the cheaper plan, it's too expensive."),
            ("agent", "No problem, I can switch you to the Starter plan effective now."),
            ("user", "Okay good. Will I lose my data?"),
            ("agent", "No, your data is retained. The change is applied."),
            ("user", "Alright, thanks."),
        ],
        "success",
    ),
]


def _latency_for_turn(slow: bool) -> float:
    """Return an LLM TTFB in seconds; slow calls breach the SLO."""
    if slow:
        return round(random.uniform(1.6, 3.2), 3)
    return round(random.uniform(0.25, 1.1), 3)


def _pipeline_stages(ttfb_secs: float, llm_vendor: str, slow_tts: bool) -> list[PipelineStage]:
    """Realistic multi-vendor stage breakdown for one agent turn (ms).

    The LLM stage mirrors the ElevenLabs-reported TTFB; the other stages come
    from the vendors ElevenLabs cannot see. Occasionally TTS (ElevenLabs audio
    buffering) is the bottleneck rather than the LLM.
    """
    asr_ms = round(random.uniform(70, 180), 1)
    tts_ms = round(random.uniform(900, 1600) if slow_tts else random.uniform(120, 420), 1)
    return [
        PipelineStage(stage="asr", vendor="deepgram", duration_ms=asr_ms),
        PipelineStage(stage="llm", vendor=llm_vendor, duration_ms=round(ttfb_secs * 1000, 1)),
        PipelineStage(stage="tts", vendor="elevenlabs", duration_ms=tts_ms),
        PipelineStage(
            stage="transport", vendor="twilio", duration_ms=round(random.uniform(40, 120), 1)
        ),
    ]


def _build_conversation(index: int, now: datetime, days: int) -> ConversationData:
    agent_id, agent_name, title, script, base_outcome = random.choice(_SCENARIOS)
    slow = random.random() < 0.22  # ~22% of calls are slow (LLM bottleneck)
    interrupt = random.random() < 0.3
    llm_vendor = random.choice(_LLM_VENDORS)

    start = now - timedelta(
        days=random.uniform(0, days),
        hours=random.uniform(0, 23),
        minutes=random.uniform(0, 59),
    )
    start_unix = int(start.timestamp())

    turns: list[TranscriptTurn] = []
    t = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    for i, (role, message) in enumerate(script):
        t += round(random.uniform(1.5, 4.0), 1)
        if role == "agent":
            ttfb = _latency_for_turn(slow)
            metrics = TurnMetrics(
                metrics={
                    "convai_llm_service_ttfb": TurnMetricValue(elapsed_time=ttfb),
                    "convai_llm_service_ttf_sentence": TurnMetricValue(
                        elapsed_time=round(ttfb + random.uniform(0.1, 0.5), 3)
                    ),
                }
            )
            in_tok = random.randint(150, 600)
            out_tok = random.randint(40, 200)
            total_input_tokens += in_tok
            total_output_tokens += out_tok
            interrupted = interrupt and i == len(script) - 2
            # ~15% of turns have ElevenLabs TTS as the bottleneck instead of LLM.
            slow_tts = not slow and random.random() < 0.15
            turns.append(
                TranscriptTurn(
                    role="agent",
                    message=message,
                    time_in_call_secs=t,
                    interrupted=interrupted,
                    conversation_turn_metrics=metrics,
                    llm_usage={"category": {"input_tokens": in_tok, "output_tokens": out_tok}},
                    pipeline_stages=_pipeline_stages(ttfb, llm_vendor, slow_tts),
                )
            )
        else:
            turns.append(
                TranscriptTurn(role="user", message=message, time_in_call_secs=t)
            )

    duration = int(t + random.uniform(1, 3))
    call_charge = round(duration / 60.0 * 0.08, 5)
    llm_charge = round(
        total_input_tokens / 1000 * 0.0005 + total_output_tokens / 1000 * 0.0015, 5
    )

    return ConversationData(
        agent_id=agent_id,
        agent_name=agent_name,
        conversation_id=f"sim_{start_unix}_{index}",
        status="done",
        has_audio=True,
        transcript=turns,
        metadata=MetadataModel(
            start_time_unix_secs=start_unix,
            call_duration_secs=duration,
            cost=int((call_charge + llm_charge) * 1000),
            termination_reason="user_ended",
            main_language="en",
            conversation_initiation_source="simulator",
            charging=ChargingModel(
                call_charge=call_charge,
                llm_charge=llm_charge,
                llm_usage={
                    "category": {
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                    }
                },
            ),
        ),
        analysis=AnalysisModel(
            call_successful=base_outcome,
            transcript_summary=f"{title}.",
            call_summary_title=title,
        ),
    )


def seed_direct(calls: int, days: int) -> None:
    """Ingest generated conversations straight into the database."""
    from app.database import SessionLocal, init_db
    from app.services import search
    from app.services.alerting import evaluate_conversation_alerts
    from app.services.ingest import ingest_conversation

    init_db()
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        for i in range(calls):
            data = _build_conversation(i, now, days)
            conv = ingest_conversation(db, data, source="simulator")
            evaluate_conversation_alerts(db, conv)
            db.commit()
            search.index_conversation_safe(conv.id, data)
        print(f"Seeded {calls} conversations directly into the database.")
    finally:
        db.close()


def seed_via_http(calls: int, days: int, url: str) -> None:
    """POST generated conversations through the HMAC-verified webhook."""
    import hashlib
    import hmac

    import httpx

    from app.config import get_settings

    settings = get_settings()
    secret = settings.elevenlabs_webhook_secret
    now = datetime.now(UTC)
    endpoint = url.rstrip("/") + "/webhooks/elevenlabs"

    with httpx.Client(timeout=30) as client:
        for i in range(calls):
            data = _build_conversation(i, now, days)
            body = json.dumps(
                {
                    "type": "post_call_transcription",
                    "event_timestamp": int(time.time()),
                    "data": data.model_dump(mode="json"),
                }
            ).encode()
            headers = {"content-type": "application/json"}
            if secret:
                ts = int(time.time())
                sig = hmac.new(
                    secret.encode(), f"{ts}.".encode() + body, hashlib.sha256
                ).hexdigest()
                headers["elevenlabs-signature"] = f"t={ts},v0={sig}"
            resp = client.post(endpoint, content=body, headers=headers)
            resp.raise_for_status()
    print(f"Posted {calls} conversations to {endpoint}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the observability dashboard.")
    parser.add_argument("--calls", type=int, default=50, help="number of conversations")
    parser.add_argument("--days", type=int, default=14, help="spread over the last N days")
    parser.add_argument("--url", type=str, default=None, help="POST via webhook at this base URL")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducibility")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    if args.url:
        seed_via_http(args.calls, args.days, args.url)
    else:
        seed_direct(args.calls, args.days)


if __name__ == "__main__":
    main()
