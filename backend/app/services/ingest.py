"""Ingestion / normalization.

Turns a parsed ElevenLabs ``post_call_transcription`` payload into persisted
``Conversation`` + ``Turn`` rows with all observability metrics computed. The
operation is **idempotent**: re-delivering the same ``conversation_id`` updates
the existing record (ElevenLabs retries transcription webhooks).
"""

from __future__ import annotations

import logging
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Agent, Conversation, Turn
from app.schemas.elevenlabs import ConversationData, TranscriptTurn
from app.services import sentiment
from app.services.cost import compute_cost
from app.services.metrics import compute_call_metrics, extract_turn_latencies
from app.services.pipeline import (
    TurnPipeline,
    aggregate_conversation_pipeline,
    compute_turn_pipeline,
)

logger = logging.getLogger("observability.ingest")
settings = get_settings()


def _sum_turn_tokens(turn: TranscriptTurn, keys: tuple[str, ...]) -> int | None:
    if not turn.llm_usage:
        return None
    from app.services.cost import _sum_tokens  # local import; shared helper

    value = _sum_tokens(turn.llm_usage, keys)
    return value or None


def _upsert_agent(db: Session, data: ConversationData) -> Agent:
    agent = db.get(Agent, data.agent_id)
    if agent is None:
        agent = Agent(id=data.agent_id, name=data.agent_name)
        db.add(agent)
    elif data.agent_name and agent.name != data.agent_name:
        agent.name = data.agent_name
    return agent


def _started_at(data: ConversationData):
    from datetime import datetime

    ts = data.metadata.start_time_unix_secs
    if ts:
        return datetime.fromtimestamp(ts, tz=UTC)
    return None


def _evaluates_slo_breach(ttfb_p95: float | None) -> bool:
    return ttfb_p95 is not None and ttfb_p95 > settings.slo_llm_ttfb_p95_ms


def ingest_conversation(
    db: Session, data: ConversationData, *, source: str = "webhook"
) -> Conversation:
    """Normalize a conversation payload into the store and return the row."""
    _upsert_agent(db, data)

    metrics = compute_call_metrics(data.transcript)
    cost = compute_cost(data.metadata)

    analysis = data.analysis
    eval_success = analysis.call_successful if analysis else None
    user_messages = [t.message or "" for t in data.transcript if t.role == "user"]
    transcript_text = "\n".join(
        f"{t.role}: {t.message}" for t in data.transcript if t.message
    )
    conv_analysis = sentiment.analyze_conversation(
        user_messages, transcript_text, evaluated_success=eval_success
    )

    # Idempotent upsert of the conversation row.
    conv = db.get(Conversation, data.conversation_id)
    if conv is None:
        conv = Conversation(id=data.conversation_id)
        db.add(conv)
    else:
        # Replace turns on re-delivery.
        for turn in list(conv.turns):
            db.delete(turn)
        conv.turns.clear()

    conv.agent_id = data.agent_id
    conv.status = data.status
    conv.start_time_unix_secs = data.metadata.start_time_unix_secs
    conv.started_at = _started_at(data)
    conv.call_duration_secs = data.metadata.call_duration_secs
    conv.termination_reason = data.metadata.termination_reason
    conv.main_language = data.metadata.main_language
    conv.environment = data.environment
    conv.version_id = data.version_id
    conv.initiation_source = data.metadata.conversation_initiation_source
    conv.has_audio = data.has_audio
    conv.source = source

    # Analysis
    conv.call_successful = conv_analysis.task_completed
    conv.transcript_summary = analysis.transcript_summary if analysis else None
    conv.summary_title = analysis.call_summary_title if analysis else None
    conv.evaluation_criteria = analysis.evaluation_criteria_results if analysis else None
    conv.data_collection = analysis.data_collection_results if analysis else None
    conv.sentiment_overall = conv_analysis.sentiment_label
    conv.sentiment_score = conv_analysis.sentiment_score

    # Metrics
    conv.turn_count = metrics.turn_count
    conv.user_turn_count = metrics.user_turn_count
    conv.agent_turn_count = metrics.agent_turn_count
    conv.interruption_count = metrics.interruption_count
    conv.interruption_rate = metrics.interruption_rate
    conv.talk_ratio = metrics.talk_ratio
    conv.llm_ttfb_p50_ms = metrics.llm_ttfb_p50_ms
    conv.llm_ttfb_p95_ms = metrics.llm_ttfb_p95_ms
    conv.llm_ttfb_max_ms = metrics.llm_ttfb_max_ms
    conv.llm_ttf_sentence_p95_ms = metrics.llm_ttf_sentence_p95_ms

    # Cost
    conv.cost_total_usd = cost.total_usd
    conv.cost_call_usd = cost.call_usd
    conv.cost_llm_usd = cost.llm_usd
    conv.cost_tts_usd = cost.tts_usd
    conv.cost_asr_usd = cost.asr_usd
    conv.llm_input_tokens = cost.input_tokens
    conv.llm_output_tokens = cost.output_tokens
    conv.cost_credits = cost.credits

    conv.breached_slo = _evaluates_slo_breach(metrics.llm_ttfb_p95_ms)

    # Build turns
    turn_pipelines: list[TurnPipeline] = []
    for index, t in enumerate(data.transcript):
        ttfb, ttf_sentence = extract_turn_latencies(t)
        turn_sentiment = sentiment.score_text(t.message) if t.role == "user" else None
        pipeline = compute_turn_pipeline(t.pipeline_stages)
        if pipeline is not None:
            turn_pipelines.append(pipeline)
        conv.turns.append(
            Turn(
                turn_index=index,
                role=t.role,
                message=t.message,
                time_in_call_secs=t.time_in_call_secs,
                interrupted=t.interrupted,
                original_message=t.original_message,
                llm_ttfb_ms=ttfb,
                llm_ttf_sentence_ms=ttf_sentence,
                e2e_latency_ms=pipeline.e2e_latency_ms if pipeline else None,
                bottleneck_stage=pipeline.bottleneck_stage if pipeline else None,
                pipeline_stages=pipeline.stages if pipeline else None,
                llm_input_tokens=_sum_turn_tokens(t, ("input", "prompt")),
                llm_output_tokens=_sum_turn_tokens(t, ("output", "completion")),
                tool_calls=t.tool_calls,
                tool_results=t.tool_results,
                sentiment=turn_sentiment.label if turn_sentiment else None,
                sentiment_score=turn_sentiment.score if turn_sentiment else None,
                source_medium=t.source_medium,
            )
        )

    # Conversation-level pipeline aggregates.
    conv_pipeline = aggregate_conversation_pipeline(turn_pipelines)
    conv.e2e_latency_p50_ms = conv_pipeline.e2e_latency_p50_ms
    conv.e2e_latency_p95_ms = conv_pipeline.e2e_latency_p95_ms
    conv.bottleneck_stage = conv_pipeline.bottleneck_stage
    conv.stage_latency_p95 = conv_pipeline.stage_latency_p95

    db.flush()
    logger.info(
        "Ingested conversation %s (agent=%s turns=%d ttfb_p95=%s cost=$%.4f)",
        conv.id,
        conv.agent_id,
        conv.turn_count,
        conv.llm_ttfb_p95_ms,
        conv.cost_total_usd,
    )
    return conv


def recompute_conversation_pipeline(conv: Conversation) -> None:
    """Recompute per-turn and call-level pipeline metrics from stored turns.

    Used after the ``/traces`` endpoint attaches multi-vendor stage timings to an
    already-ingested conversation.
    """
    turn_pipelines: list[TurnPipeline] = []
    for turn in conv.turns:
        pipeline = compute_turn_pipeline(turn.pipeline_stages)
        if pipeline is None:
            continue
        turn.e2e_latency_ms = pipeline.e2e_latency_ms
        turn.bottleneck_stage = pipeline.bottleneck_stage
        turn.pipeline_stages = pipeline.stages
        turn_pipelines.append(pipeline)

    conv_pipeline = aggregate_conversation_pipeline(turn_pipelines)
    conv.e2e_latency_p50_ms = conv_pipeline.e2e_latency_p50_ms
    conv.e2e_latency_p95_ms = conv_pipeline.e2e_latency_p95_ms
    conv.bottleneck_stage = conv_pipeline.bottleneck_stage
    conv.stage_latency_p95 = conv_pipeline.stage_latency_p95


def list_recent_conversation_ids(db: Session, limit: int = 100) -> list[str]:
    rows = db.execute(
        select(Conversation.id).order_by(Conversation.ingested_at.desc()).limit(limit)
    ).scalars()
    return list(rows)
