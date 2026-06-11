# Architecture

## Overview

The system is a thin, reliable observability layer that sits beside an ElevenLabs
conversational agent. It ingests conversation data from three ElevenLabs
surfaces, normalizes everything into a single store, computes operational
metrics, and serves them to a React dashboard.

```
                         ┌──────────────────────────────────────────────┐
                         │                React + Vite                   │
                         │  Dashboard · Conversations · Replay/Audit ·   │
                         │  Live Monitor · Search · Alerts · Audit log   │
                         └───────────────▲───────────────▲──────────────┘
                                REST /api │               │ WS /relay/monitor
        ┌──────────────────────────────────────────────────────────────────┐
        │                          FastAPI backend                          │
        │                                                                   │
        │   routers/                services/                               │
        │   ├─ webhooks   ─────────▶ security (HMAC)                        │
        │   ├─ relay (WS) ─────────▶ relay (live aggregation)              │
        │   ├─ conversations        ingest (normalizer) ──┐                │
        │   ├─ analytics            metrics ──────────────┤                │
        │   ├─ alerts               cost ─────────────────┤                │
        │   ├─ audit                sentiment (offline/Claude)             │
        │   └─ search ─────────────▶ search (Chroma)      │                │
        │                            alerting ◀───────────┘                │
        └───────────────┬───────────────────────────────┬─────────────────┘
                        │                               │
                  SQLite (SQLAlchemy)             Chroma (transcripts)
```

## Data flow

### 1. Post-call webhook (authoritative)

`POST /webhooks/elevenlabs` receives the `post_call_transcription` event.

1. **Verify** the HMAC signature (`services/security.py`) — `t=<ts>,v0=<hmac>`
   over `{ts}.{body}`, constant-time, replay-protected.
2. **Log** the raw payload to `raw_events` (append-only, enables reprocessing).
3. **Normalize** (`services/ingest.py`): upsert the agent, build `Conversation`
   + `Turn` rows, and compute metrics, cost and sentiment. Idempotent on
   `conversation_id` (ElevenLabs retries transcription webhooks).
4. **Evaluate** SLOs (`services/alerting.py`) and raise `Alert` rows.
5. **Index** the transcript into Chroma for semantic search.

### 2. Real-time relay (live)

The relay sits in the event stream between the agent and the user.

- `WS /relay/ingest/{agent_id}` accepts ElevenLabs client/server events. Each
  event updates a `LiveConversation` aggregator (live latency from `ping_ms`,
  interruptions from `interruption` / `agent_response_correction`, turns from
  `user_transcript` / `agent_response`).
- `WS /relay/monitor` lets dashboards subscribe to live "observability frames".
- On stream end, the accumulated turns are converted to the **same**
  `ConversationData` shape used by the webhook path and persisted through the
  normalizer — so live calls land in the dashboard identically.

**Human-in-the-loop takeover.** Each live call has a control queue. A supervisor
calls `POST /relay/{id}/takeover`, which flips the call's control state to
`human` and pushes a `take_over` control message *back down the producer socket*
(the bridge mutes the AI). `POST /relay/{id}/say` injects a supervisor message —
appended as an agent turn (`source_medium="human_supervisor"`) and pushed to the
producer to deliver to the user. `POST /relay/{id}/handback` returns control to
the AI. The persisted conversation is tagged `human_takeover` + `supervisor`.
The ingest WS runs the producer-read loop and the control-drain loop
concurrently so commands are delivered without blocking event ingestion.

### 3. Multi-vendor trace enrichment

`POST /traces` lets the orchestrator (the layer wiring Twilio/Vapi + OpenAI/
Anthropic + ElevenLabs) report the per-turn stage timings ElevenLabs can't see.
Decoupled from the webhook on purpose — traces may arrive before or after the
transcript — it matches turns by `turn_index`, attaches stages, and recomputes
true end-to-end latency + the bottleneck stage (`services/pipeline.py`). The
simulator emits these stages inline so the feature is demoable offline.

### 4. REST backfill (reconciliation)

The conversation detail and replay endpoints serve the stored, normalized data;
the raw event log allows re-running the normalizer after a metric-logic change.

## Storage model

| Table | Purpose |
|---|---|
| `agents` | One row per ElevenLabs agent |
| `conversations` | One row per call with **denormalized** computed metrics for fast filtering/aggregation |
| `turns` | Per-turn message, latency, interruption, tokens, sentiment |
| `raw_events` | Append-only raw webhook/relay payloads |
| `alerts` | SLO breaches (per-call + fleet) |
| `audit_log` | Every access to a PII-bearing transcript |

## Design choices

- **Denormalized metrics on `conversations`.** The dashboard filters and
  aggregates constantly; precomputing percentiles/rates at ingest keeps reads
  cheap and the query layer portable across SQLite/Postgres.
- **Offline-first.** Sentiment falls back to a deterministic lexicon and search
  to a hashing embedder, so the whole stack runs with zero credentials. Claude
  is used for analysis only when `ANTHROPIC_API_KEY` is set.
- **One normalization path.** Webhook and relay both terminate in
  `ingest_conversation`, so there is a single source of truth for how a
  conversation becomes metrics.
- **Idempotent ingest.** Re-delivered webhooks update in place and clear stale
  alerts, so retries never double-count.

## Scaling notes

For production scale, swap SQLite for Postgres (`DATABASE_URL`), move webhook
normalization onto a queue/worker, and compute percentiles with a native
aggregate (`percentile_cont`) instead of in Python. The service boundaries
(routers → services) already isolate these changes.
