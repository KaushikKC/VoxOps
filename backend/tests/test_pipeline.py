"""Tests for multi-vendor pipeline latency math and the trace endpoint."""

from __future__ import annotations

import json

from app.schemas.elevenlabs import PipelineStage
from app.services.pipeline import (
    aggregate_conversation_pipeline,
    compute_turn_pipeline,
)


def _stage(stage, vendor, ms):
    return PipelineStage(stage=stage, vendor=vendor, duration_ms=ms)


def test_turn_pipeline_e2e_and_bottleneck():
    tp = compute_turn_pipeline(
        [
            _stage("asr", "deepgram", 100),
            _stage("llm", "openai", 900),
            _stage("tts", "elevenlabs", 300),
            _stage("transport", "twilio", 50),
        ]
    )
    assert tp is not None
    assert tp.e2e_latency_ms == 1350
    assert tp.bottleneck_stage == "llm"


def test_turn_pipeline_orders_stages_canonically():
    tp = compute_turn_pipeline(
        [_stage("tts", "elevenlabs", 300), _stage("asr", "deepgram", 100)]
    )
    assert [s["stage"] for s in tp.stages] == ["asr", "tts"]


def test_turn_pipeline_default_vendor_filled():
    tp = compute_turn_pipeline([{"stage": "llm", "duration_ms": 500}])
    assert tp.stages[0]["vendor"] == "openai"


def test_turn_pipeline_none_when_empty():
    assert compute_turn_pipeline(None) is None
    assert compute_turn_pipeline([]) is None


def test_conversation_pipeline_aggregates_bottleneck_distribution():
    t1 = compute_turn_pipeline([_stage("llm", "openai", 900), _stage("tts", "elevenlabs", 200)])
    t2 = compute_turn_pipeline([_stage("llm", "openai", 300), _stage("tts", "elevenlabs", 1200)])
    t3 = compute_turn_pipeline([_stage("llm", "openai", 1000), _stage("tts", "elevenlabs", 200)])
    agg = aggregate_conversation_pipeline([t1, t2, t3])
    # llm is the bottleneck in 2 of 3 turns.
    assert agg.bottleneck_stage == "llm"
    assert "llm" in agg.stage_latency_p95
    assert agg.e2e_latency_p95_ms is not None


# ---- trace endpoint (integration) ----


def _post_call(client, conversation_id="conv_trace"):
    payload = {
        "type": "post_call_transcription",
        "data": {
            "agent_id": "agent_t",
            "conversation_id": conversation_id,
            "transcript": [
                {"role": "user", "message": "hello", "time_in_call_secs": 1},
                {"role": "agent", "message": "hi there", "time_in_call_secs": 3},
            ],
            "metadata": {"call_duration_secs": 10},
        },
    }
    return client.post(
        "/webhooks/elevenlabs",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def test_trace_endpoint_enriches_existing_conversation(client):
    _post_call(client)
    # Before: no pipeline data.
    before = client.get("/conversations/conv_trace").json()
    assert before["e2e_latency_p95_ms"] is None

    trace = {
        "conversation_id": "conv_trace",
        "turns": [
            {
                "turn_index": 1,
                "stages": [
                    {"stage": "asr", "vendor": "deepgram", "duration_ms": 120},
                    {"stage": "llm", "vendor": "anthropic", "duration_ms": 800},
                    {"stage": "tts", "vendor": "elevenlabs", "duration_ms": 250},
                ],
            }
        ],
    }
    r = client.post("/traces", json=trace)
    assert r.status_code == 200
    detail = r.json()
    assert detail["e2e_latency_p95_ms"] == 1170
    assert detail["bottleneck_stage"] == "llm"
    agent_turn = next(t for t in detail["turns"] if t["turn_index"] == 1)
    assert agent_turn["e2e_latency_ms"] == 1170
    assert agent_turn["pipeline_stages"][0]["vendor"] == "deepgram"


def test_trace_unknown_conversation_404(client):
    r = client.post("/traces", json={"conversation_id": "nope", "turns": []})
    assert r.status_code == 404


def test_pipeline_analytics_reports_bottleneck(client):
    _post_call(client, "c_a")
    client.post(
        "/traces",
        json={
            "conversation_id": "c_a",
            "turns": [
                {
                    "turn_index": 1,
                    "stages": [
                        {"stage": "llm", "vendor": "openai", "duration_ms": 1500},
                        {"stage": "tts", "vendor": "elevenlabs", "duration_ms": 200},
                    ],
                }
            ],
        },
    )
    breakdown = client.get("/analytics/pipeline").json()
    assert breakdown["conversations"] == 1
    assert breakdown["dominant_bottleneck"] == "llm"
    stages = {s["stage"]: s for s in breakdown["stages"]}
    assert stages["llm"]["bottleneck_count"] == 1
    assert stages["llm"]["p95_ms"] == 1500
