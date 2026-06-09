"""Sentiment & task-completion analysis.

Two-tier design so the service runs anywhere:

* **Per-turn sentiment** uses a fast, deterministic lexicon analyzer (no network,
  no cost) — appropriate when scoring every user utterance.
* **Conversation-level analysis** (overall sentiment trajectory + did the call
  achieve its task) uses Claude when ``ANTHROPIC_API_KEY`` is set, falling back
  to an aggregation of per-turn scores otherwise.

The Claude path uses the latest small, fast model (Haiku) by default and is
wrapped so any API/network failure degrades gracefully to the offline path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger("observability.sentiment")
settings = get_settings()

# Compact opinion lexicon. Deliberately small but covers common support-call
# affect; extend via data if needed.
_POSITIVE = {
    "thanks", "thank", "great", "perfect", "awesome", "good", "helpful", "love",
    "appreciate", "excellent", "wonderful", "happy", "glad", "yes", "resolved",
    "fixed", "works", "working", "nice", "amazing", "fantastic", "sure", "okay",
}
_NEGATIVE = {
    "no", "not", "never", "angry", "frustrated", "frustrating", "annoyed",
    "annoying", "useless", "terrible", "awful", "bad", "worst", "hate", "wrong",
    "broken", "cancel", "refund", "complaint", "stupid", "ridiculous", "slow",
    "unacceptable", "disappointed", "confused", "problem", "issue", "error",
}
_INTENSIFIERS = {"very", "really", "so", "extremely", "totally", "absolutely"}

_LABEL_THRESHOLD = 0.15


@dataclass
class TurnSentiment:
    label: str  # positive | neutral | negative
    score: float  # -1.0 .. 1.0


@dataclass
class ConversationAnalysis:
    sentiment_label: str
    sentiment_score: float
    task_completed: str  # success | failure | unknown
    rationale: str | None = None
    source: str = "offline"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def score_text(text: str | None) -> TurnSentiment:
    """Deterministic lexicon sentiment for a single utterance."""
    if not text:
        return TurnSentiment(label="neutral", score=0.0)

    tokens = _tokenize(text)
    if not tokens:
        return TurnSentiment(label="neutral", score=0.0)

    raw = 0.0
    weight = 1.0
    for token in tokens:
        if token in _INTENSIFIERS:
            weight = 1.5
            continue
        if token in _POSITIVE:
            raw += 1.0 * weight
        elif token in _NEGATIVE:
            raw -= 1.0 * weight
        weight = 1.0

    # Normalize by sqrt(length) so longer messages aren't unfairly amplified.
    norm = raw / max(len(tokens) ** 0.5, 1.0)
    score = max(-1.0, min(1.0, norm))

    if score > _LABEL_THRESHOLD:
        label = "positive"
    elif score < -_LABEL_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"
    return TurnSentiment(label=label, score=round(score, 4))


def _aggregate_offline(
    user_messages: list[str], evaluated_success: str | None
) -> ConversationAnalysis:
    scores = [score_text(m).score for m in user_messages if m]
    if scores:
        # Weight the tail of the conversation more heavily — how the user feels
        # at the end is the strongest signal of the call's outcome.
        weights = [1.0 + i / max(len(scores) - 1, 1) for i in range(len(scores))]
        avg = sum(s * w for s, w in zip(scores, weights, strict=False)) / sum(weights)
    else:
        avg = 0.0

    if avg > _LABEL_THRESHOLD:
        label = "positive"
    elif avg < -_LABEL_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"

    if evaluated_success in {"success", "failure"}:
        task = evaluated_success
    else:
        task = "success" if avg >= 0 else "unknown"

    return ConversationAnalysis(
        sentiment_label=label,
        sentiment_score=round(avg, 4),
        task_completed=task,
        source="offline",
    )


def analyze_conversation(
    user_messages: list[str],
    transcript_text: str,
    evaluated_success: str | None = None,
) -> ConversationAnalysis:
    """Overall sentiment + task-completion judgment for a conversation.

    Uses Claude when configured; otherwise aggregates per-turn lexicon scores.
    ElevenLabs' own ``call_successful`` (passed as ``evaluated_success``) is
    always respected when present.
    """
    if settings.use_claude_sentiment:
        try:
            return _analyze_with_claude(transcript_text, evaluated_success)
        except Exception as exc:  # pragma: no cover - network/SDK variability
            logger.warning("Claude analysis failed, using offline fallback: %s", exc)

    return _aggregate_offline(user_messages, evaluated_success)


def _analyze_with_claude(
    transcript_text: str, evaluated_success: str | None
) -> ConversationAnalysis:  # pragma: no cover - requires network + key
    """Conversation analysis via the Claude API."""
    import json

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = (
        "You are evaluating a voice-agent call transcript. Respond with ONLY a "
        "JSON object: {\"sentiment_label\": positive|neutral|negative, "
        "\"sentiment_score\": number in [-1,1], \"task_completed\": "
        "success|failure|unknown, \"rationale\": short string}.\n\n"
        f"Transcript:\n{transcript_text[:8000]}"
    )
    message = client.messages.create(
        model=settings.sentiment_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if block.type == "text")
    data = json.loads(text[text.find("{") : text.rfind("}") + 1])

    task = data.get("task_completed", "unknown")
    if evaluated_success in {"success", "failure"}:
        task = evaluated_success

    return ConversationAnalysis(
        sentiment_label=data.get("sentiment_label", "neutral"),
        sentiment_score=float(data.get("sentiment_score", 0.0)),
        task_completed=task,
        rationale=data.get("rationale"),
        source="claude",
    )
