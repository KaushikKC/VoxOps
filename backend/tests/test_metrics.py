"""Tests for the metrics engine (percentiles, interruptions, talk ratio)."""

from __future__ import annotations

from app.schemas.elevenlabs import TranscriptTurn, TurnMetrics, TurnMetricValue
from app.services.metrics import (
    compute_call_metrics,
    extract_turn_latencies,
    percentile,
)


def test_percentile_empty():
    assert percentile([], 95) is None


def test_percentile_single():
    assert percentile([42.0], 95) == 42.0


def test_percentile_interpolation():
    values = [10, 20, 30, 40, 50]
    assert percentile(values, 50) == 30.0
    assert percentile(values, 0) == 10.0
    assert percentile(values, 100) == 50.0


def test_extract_turn_latencies_converts_seconds_to_ms():
    turn = TranscriptTurn(
        role="agent",
        conversation_turn_metrics=TurnMetrics(
            metrics={
                "convai_llm_service_ttfb": TurnMetricValue(elapsed_time=0.5),
                "convai_llm_service_ttf_sentence": TurnMetricValue(elapsed_time=0.8),
            }
        ),
    )
    ttfb, ttf_sentence = extract_turn_latencies(turn)
    assert ttfb == 500.0
    assert ttf_sentence == 800.0


def test_extract_turn_latencies_none_when_absent():
    assert extract_turn_latencies(TranscriptTurn(role="user")) == (None, None)


def _agent(msg, ttfb=None, interrupted=False):
    metrics = None
    if ttfb is not None:
        metrics = TurnMetrics(
            metrics={"convai_llm_service_ttfb": TurnMetricValue(elapsed_time=ttfb)}
        )
    return TranscriptTurn(
        role="agent", message=msg, conversation_turn_metrics=metrics, interrupted=interrupted
    )


def _user(msg):
    return TranscriptTurn(role="user", message=msg)


def test_compute_call_metrics_counts_and_rates():
    turns = [
        _agent("hello there friend", ttfb=0.4),
        _user("hi"),
        _agent("how can i help you", ttfb=0.6, interrupted=True),
        _user("i need help"),
    ]
    m = compute_call_metrics(turns)
    assert m.turn_count == 4
    assert m.agent_turn_count == 2
    assert m.user_turn_count == 2
    assert m.interruption_count == 1
    assert m.interruption_rate == 0.5  # 1 interruption / 2 agent turns
    assert m.llm_ttfb_p50_ms is not None
    assert m.llm_ttfb_max_ms == 600.0


def test_talk_ratio_is_agent_word_fraction():
    turns = [_agent("one two three"), _user("four")]  # 3 agent words, 1 user word
    m = compute_call_metrics(turns)
    assert m.talk_ratio == 0.75


def test_no_agent_turns_safe():
    m = compute_call_metrics([_user("hi"), _user("bye")])
    assert m.interruption_rate == 0.0
    assert m.llm_ttfb_p95_ms is None
