"""Inbound ElevenLabs payload schemas.

These mirror the ``post_call_transcription`` webhook / Get Conversation Details
response. They are intentionally lenient (``extra="allow"``) because the
ElevenLabs payload is large and evolves; we model the fields the observability
engine needs and preserve the rest in the raw event log.

Reference shape::

    {
      "type": "post_call_transcription",
      "event_timestamp": 1739537297,
      "data": {
        "agent_id": "...", "conversation_id": "...", "status": "done",
        "transcript": [ { "role": "agent"|"user", "message": "...",
                          "time_in_call_secs": 3, "interrupted": false,
                          "conversation_turn_metrics": {"metrics": {
                              "convai_llm_service_ttfb": {"elapsed_time": 0.4},
                              "convai_llm_service_ttf_sentence": {"elapsed_time": 0.7}}},
                          "llm_usage": {...}, "tool_calls": [...] } ],
        "metadata": { "start_time_unix_secs": ..., "call_duration_secs": ...,
                      "cost": 1234, "termination_reason": "...",
                      "charging": { "llm_charge": ..., "call_charge": ...,
                                    "llm_usage": {...}, "tts_usage": {...},
                                    "asr_usage": {...} } },
        "analysis": { "call_successful": "success",
                      "transcript_summary": "...",
                      "evaluation_criteria_results": {...},
                      "data_collection_results": {...} }
      }
    }
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="allow")


class TurnMetricValue(_Lenient):
    elapsed_time: float | None = None


class TurnMetrics(_Lenient):
    """``conversation_turn_metrics`` — a map of metric name -> {elapsed_time}."""

    metrics: dict[str, TurnMetricValue] = Field(default_factory=dict)


class LLMUsageTurn(_Lenient):
    """Per-turn token usage; ElevenLabs nests categories with input/output."""

    model_config = ConfigDict(extra="allow")


class TranscriptTurn(_Lenient):
    role: str = "user"
    message: str | None = None
    time_in_call_secs: float = 0.0
    interrupted: bool = False
    original_message: str | None = None
    tool_calls: list | None = None
    tool_results: list | None = None
    conversation_turn_metrics: TurnMetrics | None = None
    llm_usage: dict | None = None
    source_medium: str | None = None


class ChargingModel(_Lenient):
    dev_discount: bool | None = None
    is_burst: bool | None = None
    tier: str | None = None
    llm_usage: dict | None = None
    llm_price: float | None = None
    llm_charge: float | None = None
    call_charge: float | None = None
    tts_usage: dict | None = None
    asr_usage: dict | None = None
    free_minutes_consumed: float | None = None
    free_llm_dollars_consumed: float | None = None


class MetadataModel(_Lenient):
    start_time_unix_secs: int | None = None
    accepted_time_unix_secs: int | None = None
    call_duration_secs: int = 0
    cost: int | None = None
    termination_reason: str | None = None
    main_language: str | None = None
    conversation_initiation_source: str | None = None
    charging: ChargingModel | None = None


class AnalysisModel(_Lenient):
    call_successful: str = "unknown"
    transcript_summary: str | None = None
    call_summary_title: str | None = None
    evaluation_criteria_results: dict | None = None
    data_collection_results: dict | None = None


class ConversationData(_Lenient):
    agent_id: str
    agent_name: str | None = None
    conversation_id: str
    status: str = "done"
    user_id: str | None = None
    version_id: str | None = None
    environment: str = "production"
    has_audio: bool = False
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    metadata: MetadataModel = Field(default_factory=MetadataModel)
    analysis: AnalysisModel | None = None


class PostCallWebhook(_Lenient):
    """Top-level ``post_call_transcription`` envelope."""

    type: str = "post_call_transcription"
    event_timestamp: int | None = None
    data: ConversationData
