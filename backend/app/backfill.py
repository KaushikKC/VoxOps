"""Backfill real conversations from the ElevenLabs REST API.

Pulls your existing ElevenLabs conversation history and runs each call through
the same normalizer the webhook uses, so the dashboard fills with *real* data
without waiting for new live calls.

Usage::

    # key read from backend/.env (ELEVENLABS_API_KEY)
    python -m app.backfill                      # all conversations
    python -m app.backfill --limit 50           # most recent 50
    python -m app.backfill --agent-id agent_xxx # one agent only

API: https://api.elevenlabs.io/v1/convai/conversations  (header: xi-api-key)
"""

from __future__ import annotations

import argparse
import logging

import httpx

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.schemas.elevenlabs import ConversationData
from app.services import search
from app.services.alerting import evaluate_conversation_alerts
from app.services.ingest import ingest_conversation

logger = logging.getLogger("observability.backfill")

API_BASE = "https://api.elevenlabs.io"


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"xi-api-key": api_key},
        timeout=30.0,
    )


def list_conversation_ids(
    client: httpx.Client, *, agent_id: str | None = None, limit: int | None = None
) -> list[str]:
    """Page through the conversations list endpoint and collect ids (newest first)."""
    ids: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, object] = {"page_size": 100}
        if agent_id:
            params["agent_id"] = agent_id
        if cursor:
            params["cursor"] = cursor

        resp = client.get("/v1/convai/conversations", params=params)
        resp.raise_for_status()
        body = resp.json()

        for item in body.get("conversations", []):
            cid = item.get("conversation_id")
            if cid:
                ids.append(cid)
                if limit and len(ids) >= limit:
                    return ids[:limit]

        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return ids


def fetch_conversation(client: httpx.Client, conversation_id: str) -> dict:
    resp = client.get(f"/v1/convai/conversations/{conversation_id}")
    resp.raise_for_status()
    return resp.json()


def backfill(*, agent_id: str | None = None, limit: int | None = None) -> int:
    """Fetch and ingest real conversations. Returns the number ingested."""
    settings = get_settings()
    api_key = settings.elevenlabs_api_key.strip()
    if not api_key:
        raise SystemExit(
            "ELEVENLABS_API_KEY is not set. Add it to backend/.env and retry."
        )

    init_db()
    db = SessionLocal()
    ingested = 0
    try:
        with _client(api_key) as client:
            try:
                ids = list_conversation_ids(client, agent_id=agent_id, limit=limit)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    raise SystemExit("ElevenLabs rejected the API key (401). Check it.") from exc
                raise
            print(f"Found {len(ids)} conversation(s). Fetching transcripts…")

            for cid in ids:
                try:
                    detail = fetch_conversation(client, cid)
                    data = ConversationData.model_validate(detail)
                except Exception as exc:  # noqa: BLE001 - skip a bad record, keep going
                    logger.warning("Skipping %s: %s", cid, exc)
                    continue

                if not data.transcript:
                    continue  # call without a transcript (e.g. failed/empty)

                conv = ingest_conversation(db, data, source="backfill")
                evaluate_conversation_alerts(db, conv)
                db.commit()
                search.index_conversation_safe(conv.id, data)
                ingested += 1

        print(f"Backfilled {ingested} real conversation(s) into the dashboard.")
        return ingested
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill real ElevenLabs conversations.")
    parser.add_argument("--agent-id", default=None, help="restrict to one agent")
    parser.add_argument("--limit", type=int, default=None, help="most recent N conversations")
    args = parser.parse_args()
    backfill(agent_id=args.agent_id, limit=args.limit)


if __name__ == "__main__":
    main()
