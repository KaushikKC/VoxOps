"""Tests for the offline sentiment analyzer."""

from __future__ import annotations

from app.services.sentiment import analyze_conversation, score_text


def test_positive_text():
    s = score_text("Thank you so much, this is great and helpful")
    assert s.label == "positive"
    assert s.score > 0


def test_negative_text():
    s = score_text("This is terrible and useless, I am so frustrated")
    assert s.label == "negative"
    assert s.score < 0


def test_neutral_text():
    s = score_text("I have a meeting at noon")
    assert s.label == "neutral"


def test_empty_text_is_neutral():
    assert score_text("").label == "neutral"
    assert score_text(None).label == "neutral"


def test_conversation_respects_elevenlabs_success():
    analysis = analyze_conversation(
        ["this is awful"], "user: this is awful", evaluated_success="success"
    )
    # ElevenLabs' own verdict wins for task completion.
    assert analysis.task_completed == "success"


def test_conversation_tail_weighting_positive_ending():
    analysis = analyze_conversation(
        ["I am frustrated", "actually that is perfect now, thank you"],
        "transcript",
        evaluated_success=None,
    )
    assert analysis.sentiment_label in {"positive", "neutral"}
    assert analysis.source == "offline"
