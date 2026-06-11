"""Multi-vendor pipeline latency.

A single conversational turn in a real deployment is a relay race across several
vendors:

    user stops speaking
        → ASR finalize        (e.g. Deepgram)
        → LLM generation TTFB (e.g. OpenAI / Anthropic)
        → TTS first audio     (ElevenLabs)
        → transport delivery  (e.g. Twilio / Vapi)
    → first audio reaches the user

**ElevenLabs only sees the TTS stage.** The *true end-to-end latency* — the time
between the user finishing their sentence and the first chunk of audio coming
back — is the sum of every stage, and the **bottleneck** is the slowest one.
This module computes both, per turn and aggregated per call, so an operator can
tell whether a slow turn was the LLM thinking or ElevenLabs buffering.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.elevenlabs import PipelineStage
from app.services.metrics import percentile

# Canonical display order; unknown stages sort after these.
STAGE_ORDER = ["asr", "endpointing", "llm", "tts", "transport"]

# Sensible default vendor labels when a stage omits one.
DEFAULT_VENDORS = {
    "asr": "deepgram",
    "endpointing": "vad",
    "llm": "openai",
    "tts": "elevenlabs",
    "transport": "twilio",
}


def stage_sort_key(stage: str) -> int:
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else len(STAGE_ORDER)


@dataclass
class TurnPipeline:
    e2e_latency_ms: float
    bottleneck_stage: str | None
    stages: list[dict]  # normalized [{stage, vendor, duration_ms}], ordered


def compute_turn_pipeline(stages: list[PipelineStage] | list[dict] | None) -> TurnPipeline | None:
    """End-to-end latency and bottleneck for a single turn from its stages."""
    if not stages:
        return None

    normalized: list[dict] = []
    for s in stages:
        if isinstance(s, PipelineStage):
            stage, vendor, duration = s.stage, s.vendor, s.duration_ms
        else:
            stage = s.get("stage", "unknown")
            vendor = s.get("vendor")
            duration = float(s.get("duration_ms", 0.0))
        normalized.append(
            {
                "stage": stage,
                "vendor": vendor or DEFAULT_VENDORS.get(stage, "unknown"),
                "duration_ms": round(float(duration), 2),
            }
        )

    normalized.sort(key=lambda s: stage_sort_key(s["stage"]))
    e2e = round(sum(s["duration_ms"] for s in normalized), 2)
    bottleneck = max(normalized, key=lambda s: s["duration_ms"])["stage"] if normalized else None
    return TurnPipeline(e2e_latency_ms=e2e, bottleneck_stage=bottleneck, stages=normalized)


@dataclass
class ConversationPipeline:
    e2e_latency_p50_ms: float | None
    e2e_latency_p95_ms: float | None
    bottleneck_stage: str | None
    stage_latency_p95: dict[str, float] | None


def aggregate_conversation_pipeline(turn_pipelines: list[TurnPipeline]) -> ConversationPipeline:
    """Roll per-turn pipelines up to call-level e2e + per-stage p95 + bottleneck."""
    if not turn_pipelines:
        return ConversationPipeline(None, None, None, None)

    e2e_values = [tp.e2e_latency_ms for tp in turn_pipelines]

    # Per-stage durations across all turns.
    by_stage: dict[str, list[float]] = {}
    bottleneck_counts: dict[str, int] = {}
    for tp in turn_pipelines:
        for s in tp.stages:
            by_stage.setdefault(s["stage"], []).append(s["duration_ms"])
        if tp.bottleneck_stage:
            bottleneck_counts[tp.bottleneck_stage] = (
                bottleneck_counts.get(tp.bottleneck_stage, 0) + 1
            )

    stage_p95 = {
        stage: round(percentile(values, 95) or 0.0, 2)
        for stage, values in sorted(by_stage.items(), key=lambda kv: stage_sort_key(kv[0]))
    }
    dominant = max(bottleneck_counts, key=bottleneck_counts.get) if bottleneck_counts else None

    return ConversationPipeline(
        e2e_latency_p50_ms=percentile(e2e_values, 50),
        e2e_latency_p95_ms=percentile(e2e_values, 95),
        bottleneck_stage=dominant,
        stage_latency_p95=stage_p95 or None,
    )
