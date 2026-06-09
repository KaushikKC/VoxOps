"""Metrics engine.

Pure functions that turn a list of turns into call-level observability metrics:
latency percentiles (LLM time-to-first-byte and time-to-first-sentence),
interruption (barge-in) rate, and talk ratio. Kept dependency-free so the math
is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.elevenlabs import TranscriptTurn

# ElevenLabs metric keys inside ``conversation_turn_metrics.metrics``.
_TTFB_KEY = "convai_llm_service_ttfb"
_TTF_SENTENCE_KEY = "convai_llm_service_ttf_sentence"


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolation percentile (``p`` in 0..100). ``None`` if empty."""
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * frac)


def extract_turn_latencies(turn: TranscriptTurn) -> tuple[float | None, float | None]:
    """Return ``(ttfb_ms, ttf_sentence_ms)`` for a turn, if present.

    ElevenLabs reports ``elapsed_time`` in seconds; we convert to milliseconds.
    """
    if turn.conversation_turn_metrics is None:
        return None, None
    metrics = turn.conversation_turn_metrics.metrics or {}

    def _ms(key: str) -> float | None:
        entry = metrics.get(key)
        if entry is None or entry.elapsed_time is None:
            return None
        return round(entry.elapsed_time * 1000.0, 2)

    return _ms(_TTFB_KEY), _ms(_TTF_SENTENCE_KEY)


def _word_count(message: str | None) -> int:
    return len(message.split()) if message else 0


@dataclass
class CallMetrics:
    turn_count: int
    user_turn_count: int
    agent_turn_count: int
    interruption_count: int
    interruption_rate: float
    talk_ratio: float | None
    llm_ttfb_p50_ms: float | None
    llm_ttfb_p95_ms: float | None
    llm_ttfb_max_ms: float | None
    llm_ttf_sentence_p95_ms: float | None


def compute_call_metrics(turns: list[TranscriptTurn]) -> CallMetrics:
    """Aggregate per-turn data into call-level metrics."""
    ttfb_values: list[float] = []
    ttf_sentence_values: list[float] = []
    agent_words = 0
    user_words = 0
    interruptions = 0
    user_turns = 0
    agent_turns = 0

    for turn in turns:
        if turn.role == "agent":
            agent_turns += 1
            agent_words += _word_count(turn.message)
            ttfb, ttf_sentence = extract_turn_latencies(turn)
            if ttfb is not None:
                ttfb_values.append(ttfb)
            if ttf_sentence is not None:
                ttf_sentence_values.append(ttf_sentence)
        elif turn.role == "user":
            user_turns += 1
            user_words += _word_count(turn.message)
        if turn.interrupted:
            interruptions += 1

    total_words = agent_words + user_words
    talk_ratio = (agent_words / total_words) if total_words else None
    # Interruption rate is normalized against agent turns (the turns that *can*
    # be interrupted). Falls back to 0 when there are no agent turns.
    interruption_rate = (interruptions / agent_turns) if agent_turns else 0.0

    return CallMetrics(
        turn_count=len(turns),
        user_turn_count=user_turns,
        agent_turn_count=agent_turns,
        interruption_count=interruptions,
        interruption_rate=round(interruption_rate, 4),
        talk_ratio=round(talk_ratio, 4) if talk_ratio is not None else None,
        llm_ttfb_p50_ms=percentile(ttfb_values, 50),
        llm_ttfb_p95_ms=percentile(ttfb_values, 95),
        llm_ttfb_max_ms=max(ttfb_values) if ttfb_values else None,
        llm_ttf_sentence_p95_ms=percentile(ttf_sentence_values, 95),
    )
