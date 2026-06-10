"""Integration tests exercising the HTTP + WebSocket API end to end."""

from __future__ import annotations

import json


def _payload(conversation_id="conv_test_1", successful="success", slow=False):
    ttfb = 2.4 if slow else 0.4
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1739537297,
        "data": {
            "agent_id": "agent_test",
            "agent_name": "Test Bot",
            "conversation_id": conversation_id,
            "status": "done",
            "has_audio": True,
            "transcript": [
                {
                    "role": "agent",
                    "message": "Hello, how can I help?",
                    "time_in_call_secs": 1,
                    "conversation_turn_metrics": {
                        "metrics": {"convai_llm_service_ttfb": {"elapsed_time": ttfb}}
                    },
                },
                {
                    "role": "user",
                    "message": "I am frustrated, my refund is broken",
                    "time_in_call_secs": 4,
                    "interrupted": True,
                },
                {"role": "user", "message": "thanks, perfect now", "time_in_call_secs": 8},
            ],
            "metadata": {
                "start_time_unix_secs": 1739537200,
                "call_duration_secs": 30,
                "cost": 120,
                "charging": {"call_charge": 0.04, "llm_charge": 0.01},
            },
            "analysis": {
                "call_successful": successful,
                "transcript_summary": "A test call.",
                "call_summary_title": "Test call",
            },
        },
    }


def _post(client, payload):
    return client.post(
        "/webhooks/elevenlabs",
        content=json.dumps(payload),
        headers={"content-type": "application/json"},
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook_ingests_and_computes_metrics(client):
    r = _post(client, _payload(slow=True))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ingested"
    assert body["turns"] == 3
    assert body["breached_slo"] is True  # 2400ms > 1500ms SLO

    detail = client.get("/conversations/conv_test_1").json()
    assert detail["interruption_count"] == 1
    assert detail["agent_turn_count"] == 1
    assert detail["cost_total_usd"] == 0.05
    assert len(detail["turns"]) == 3


def test_webhook_idempotent(client):
    _post(client, _payload())
    _post(client, _payload())  # re-deliver
    page = client.get("/conversations").json()
    assert page["total"] == 1  # not duplicated
    # alerts not duplicated either
    detail = client.get("/conversations/conv_test_1").json()
    assert detail["turn_count"] == 3


def test_webhook_rejects_unparseable_body(client):
    r = client.post(
        "/webhooks/elevenlabs",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


def test_conversation_list_filters(client):
    _post(client, _payload("c_ok", successful="success"))
    _post(client, _payload("c_fail", successful="failure"))
    failures = client.get("/conversations?success=failure").json()
    assert failures["total"] == 1
    assert failures["items"][0]["id"] == "c_fail"


def test_analytics_summary(client):
    _post(client, _payload("c1", successful="success", slow=False))
    _post(client, _payload("c2", successful="failure", slow=True))
    summary = client.get("/analytics/summary").json()
    assert summary["total_conversations"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["slo_breach_rate"] == 0.5


def test_replay_and_audit(client):
    _post(client, _payload())
    replay = client.get("/conversations/conv_test_1/replay").json()
    assert "timeline" in replay
    assert len(replay["timeline"]) == 3
    # the view + replay should have been audited
    audit = client.get("/audit").json()
    actions = {a["action"] for a in audit}
    assert "replay" in actions


def test_missing_conversation_404(client):
    assert client.get("/conversations/nope").status_code == 404


def test_relay_websocket_persists_conversation(client):
    with client.websocket_connect("/relay/ingest/agent_live?conversation_id=live_1") as ws:
        ws.send_json(
            {"type": "user_transcript", "user_transcription_event": {"user_transcript": "hi"}}
        )
        ws.receive_json()
        ws.send_json(
            {"type": "agent_response", "agent_response_event": {"agent_response": "hello there"}}
        )
        ws.receive_json()
        ws.send_json({"type": "end"})

    detail = client.get("/conversations/live_1").json()
    assert detail["source"] == "relay"
    assert detail["turn_count"] == 2
