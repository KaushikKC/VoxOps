"""Tests for the supervisor human-in-the-loop takeover flow."""

from __future__ import annotations


def test_takeover_sends_control_to_producer(client):
    with client.websocket_connect("/relay/ingest/agent_x?conversation_id=tk1") as ws:
        ws.send_json(
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "help"}}
        )
        ws.receive_json()

        r = client.post("/relay/tk1/takeover", params={"supervisor": "alice"})
        assert r.status_code == 200
        assert r.json()["control"] == "human"

        # The producer/bridge should be told to stop the AI.
        control = ws.receive_json()
        assert control["type"] == "control"
        assert control["action"] == "take_over"
        assert control["supervisor"] == "alice"

        ws.send_json({"type": "end"})


def test_human_message_injects_agent_turn_and_persists(client):
    with client.websocket_connect("/relay/ingest/agent_x?conversation_id=tk2") as ws:
        ws.send_json(
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "hi"}}
        )
        ws.receive_json()
        client.post("/relay/tk2/takeover", params={"supervisor": "bob"})
        ws.receive_json()  # take_over control

        client.post("/relay/tk2/say", json={"text": "This is Bob, happy to help."})
        human = ws.receive_json()
        assert human["action"] == "human_message"
        assert human["text"] == "This is Bob, happy to help."

        ws.send_json({"type": "end"})

    detail = client.get("/conversations/tk2").json()
    assert detail["human_takeover"] is True
    assert detail["supervisor"] == "bob"
    human_turns = [t for t in detail["turns"] if t["source_medium"] == "human_supervisor"]
    assert len(human_turns) == 1
    assert human_turns[0]["message"] == "This is Bob, happy to help."


def test_handback_returns_control(client):
    with client.websocket_connect("/relay/ingest/agent_x?conversation_id=tk3") as ws:
        ws.send_json(
            {"type": "agent_response", "agent_response_event": {"agent_response": "hello"}}
        )
        ws.receive_json()
        client.post("/relay/tk3/takeover", params={"supervisor": "carol"})
        ws.receive_json()

        r = client.post("/relay/tk3/handback")
        assert r.json()["control"] == "ai"
        control = ws.receive_json()
        assert control["action"] == "hand_back"

        ws.send_json({"type": "end"})


def test_say_rejected_without_takeover(client):
    with client.websocket_connect("/relay/ingest/agent_x?conversation_id=tk4") as ws:
        ws.send_json(
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "hi"}}
        )
        ws.receive_json()
        # No takeover yet -> say must be rejected.
        r = client.post("/relay/tk4/say", json={"text": "should fail"})
        assert r.status_code == 409
        ws.send_json({"type": "end"})


def test_takeover_unknown_call_404(client):
    assert client.post("/relay/nope/takeover").status_code == 404
