"""Tests for the real-time relay aggregation."""

from __future__ import annotations

from app.services.relay import LiveConversation


def _feed(live: LiveConversation, events: list[dict]) -> None:
    for e in events:
        live.handle_event(e)


def test_live_conversation_tracks_turns_and_interruptions():
    live = LiveConversation(agent_id="a1", conversation_id="c1")
    _feed(
        live,
        [
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "hi"}},
            {"type": "agent_response", "agent_response_event": {"agent_response": "hello"}},
            {"type": "ping", "ping_event": {"event_id": 1, "ping_ms": 40}},
            {"type": "ping", "ping_event": {"event_id": 2, "ping_ms": 60}},
            {"type": "interruption", "interruption_event": {"event_id": 3}},
            {"type": "vad_score", "vad_score_event": {"vad_score": 0.9}},
        ],
    )
    assert len(live.turns) == 2
    assert live.interruptions == 1
    assert live.turns[-1].interrupted is True  # the agent turn was interrupted
    assert live.avg_ping_ms == 50.0
    assert live.last_vad == 0.9


def test_agent_response_correction_marks_interruption():
    live = LiveConversation(agent_id="a1", conversation_id="c1")
    _feed(
        live,
        [
            {"type": "agent_response", "agent_response_event": {"agent_response": "let me check"}},
            {
                "type": "agent_response_correction",
                "agent_response_correction_event": {
                    "original_agent_response": "let me check that",
                    "corrected_agent_response": "sorry, go ahead",
                },
            },
        ],
    )
    assert live.interruptions == 1
    assert live.turns[-1].original_message == "let me check that"


def test_to_conversation_data_roundtrips_to_canonical_shape():
    live = LiveConversation(agent_id="a1", conversation_id="c1")
    _feed(
        live,
        [
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "hi"}},
            {"type": "agent_response", "agent_response_event": {"agent_response": "hello there"}},
        ],
    )
    data = live.to_conversation_data()
    assert data.agent_id == "a1"
    assert data.conversation_id == "c1"
    assert len(data.transcript) == 2
    assert data.metadata.conversation_initiation_source == "relay"


def test_frame_shape():
    live = LiveConversation(agent_id="a1", conversation_id="c1")
    frame = live.frame()
    assert frame["type"] == "frame"
    assert frame["conversation_id"] == "c1"
    assert frame["turn_count"] == 0
