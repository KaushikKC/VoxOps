# Voice Agent Observability Dashboard

> A production-grade observability, evaluation and live-intervention layer for [ElevenLabs](https://elevenlabs.io) conversational voice agents — and, more broadly, for any **multi-vendor voice stack**. It captures every turn of every call, computes the latency / quality / cost metrics an operator actually needs, reconstructs true end-to-end latency across vendors ElevenLabs can't see, lets a human supervisor take over a live call, and makes any conversation replayable and auditable.

<p align="center">
  <em>FastAPI · SQLAlchemy · Chroma · React + TypeScript · WebSockets · Docker</em><br/>
  <em>~4,300 lines of Python · ~1,600 lines of TypeScript · 51 automated tests · 92 commits</em>
</p>

---

## Table of contents

1. [Motivation](#1-motivation)
2. [What it does](#2-what-it-does-feature-overview)
3. [How it integrates with ElevenLabs](#3-how-it-integrates-with-elevenlabs)
4. [System architecture](#4-system-architecture)
5. [Subsystem deep dives](#5-subsystem-deep-dives)
6. [Data model](#6-data-model)
7. [API reference](#7-api-reference)
8. [Frontend](#8-frontend)
9. [Getting started](#9-getting-started)
10. [Configuration](#10-configuration)
11. [Testing & CI](#11-testing--ci)
12. [Project structure](#12-project-structure)
13. [Design decisions & trade-offs](#13-design-decisions--trade-offs)
14. [Scaling to production](#14-scaling-to-production)
15. [Roadmap](#15-roadmap)
16. [License](#16-license)

---

## 1. Motivation

ElevenLabs markets its Agents platform on three words: **"testing, monitoring, reliability."** Yet the moment a team ships a voice agent to production, they discover a gap between a demo that *sounds* good and a system that is *operationally reliable*. The questions that matter in production are not "does it talk?" but:

- **Is it fast?** What is the p95 LLM time-to-first-byte? Where are the slow turns, and *which vendor* caused the delay?
- **Is it natural?** How often does the user interrupt the agent (barge-in)? Who dominates the conversation (talk ratio)?
- **Did it work?** Did the call achieve its goal? Was the required information collected?
- **How did the user feel?** What was the sentiment trajectory across the call?
- **What did it cost?** Broken down the way it is actually billed — call minutes + LLM tokens + TTS + ASR.
- **Can I intervene?** For high-stakes calls, can a human take over from the AI in real time?
- **What exactly happened?** Can I replay and audit any conversation turn by turn?

A single vendor cannot answer all of these. In a realistic deployment ElevenLabs handles **TTS**, while **Twilio/Vapi** handle telephony and **OpenAI/Anthropic** are the LLM brain — so no single provider can see the *true* end-to-end latency or attribute a bottleneck. This project is the missing operational layer that stitches the full picture together.

### The three classes of problem this solves

| Class | The gap | This project's answer |
|---|---|---|
| **Multi-vendor stack** | ElevenLabs only sees its own (TTS) slice; true end-to-end latency lives nowhere | Per-turn pipeline tracing across ASR → LLM → TTS → transport, with bottleneck attribution |
| **Deep business metrics** | "Call ended" ≠ "task succeeded" or "user satisfied" | Task-completion judging, sentiment trajectory, evaluation criteria, semantic search over transcripts |
| **Real-time human-in-the-loop** | No way to rescue a live high-stakes call | A relay that streams active calls and lets a supervisor take over, speak as the agent, and hand back |

---

## 2. What it does (feature overview)

| Capability | Summary |
|---|---|
| **HMAC-verified webhook ingestion** | Receives ElevenLabs `post_call_transcription`, verifies the signature in constant time with replay protection, idempotent on `conversation_id`. |
| **Real-time relay** | A WebSocket service that sits in the event stream between the agent and the user, tracking live latency, interruptions and VAD, broadcasting "observability frames" to dashboards. |
| **Human-in-the-loop takeover** | A supervisor can take over a live call from the AI, speak as the agent in real time, and hand back. The call is tagged `human_takeover`. |
| **Latency metrics engine** | LLM TTFB p50 / p95 / max, time-to-first-sentence, computed with linear-interpolation percentiles. |
| **Multi-vendor pipeline tracing** | Computes *true* end-to-end latency (user-stops-speaking → first audio out) across the whole stack and pinpoints the bottleneck stage per turn and across the fleet. |
| **Exact cost model** | Per-call cost broken into call minutes + LLM tokens + TTS + ASR, mirroring ElevenLabs billing, with estimation fallback. |
| **Sentiment & task-completion judging** | Deterministic offline lexicon analyzer by default; Claude when an API key is present. |
| **Semantic transcript search** | Chroma-backed "find calls where the user was angry about billing", with an offline hashing embedder. |
| **Replay / audit view** | Turn-by-turn timeline with latency waterfall, pipeline bars, interruptions, sentiment and cost breakdown. Every access is logged. |
| **SLO alerting** | Per-call and fleet-level breaches on latency, interruption rate, success rate and task failure. |
| **Audit log** | Every view / replay / search of a (PII-bearing) transcript is recorded. |
| **Offline-first** | A conversation simulator seeds realistic data; no ElevenLabs or Claude account required to run the whole thing. |

---

## 3. How it integrates with ElevenLabs

ElevenLabs exposes conversation data through three surfaces. This project consumes all three, plus a fourth channel for the data ElevenLabs cannot produce.

| Surface | What it provides | Used for |
|---|---|---|
| **Post-call webhook** (`post_call_transcription`, HMAC-signed) | Full transcript, per-turn `conversation_turn_metrics` (LLM TTFB, time-to-first-sentence), `interrupted` flags, `charging` breakdown, `analysis` (call_successful, evaluation criteria, data collection, summary) | Authoritative per-call ingestion |
| **Real-time WebSocket events** (`user_transcript`, `agent_response`, `agent_response_correction`, `interruption`, `ping`/`pong`, `vad_score`) | Live turns, live round-trip latency, live interruptions | The live **relay** that sits between agent & user |
| **Conversation REST API** | Backfill / reconciliation of historical calls | Audit + replay |
| **Orchestrator traces** (`POST /traces`, *this project*) | Per-turn stage timings from the vendors ElevenLabs can't see (ASR, LLM, transport) | True end-to-end latency + bottleneck attribution |

> **No paid account?** A built-in conversation simulator posts realistic payloads — including multi-vendor pipeline stages — so the entire dashboard is demoable offline.

---

## 4. System architecture

```
┌──────────────────────────────── Browser (React + Vite + TypeScript) ────────────────────────────────┐
│  Dashboard (KPIs · trends · pipeline bottlenecks) · Conversations · Replay/Audit · Live Monitor       │
│  (take-over controls) · Semantic Search · Alerts · Audit Log                                          │
└───────────────────────────────▲───────────────────────────────────▲──────────────────────────────────┘
                        REST /api │                                   │ WS  /relay/monitor
┌──────────────────────┐         │                                   │
│   ElevenLabs Agent    │ post_call_transcription (HMAC) ┌───────────┴───────────────────────────────────┐
│  (TTS + orchestration)│ ──────────────────────────────▶│                FastAPI backend                 │
└──────────┬────────────┘                                │                                                │
           │  live event stream (WS)                     │  Routers                Services               │
           │  user_transcript / agent_response /         │  ├─ webhooks   ───────▶ security  (HMAC verify) │
           ▼  interruption / ping / vad_score            │  ├─ relay (WS) ───────▶ relay     (live agg +   │
┌──────────────────────┐   bidirectional relay           │  │                       takeover control plane)│
│  Producer / Bridge    │◀───────────────────────────────│  ├─ traces     ───────▶ pipeline  (e2e + bottleneck)
│ (Twilio/Vapi + LLM)   │   control: take_over/hand_back/ │  ├─ conversations       ingest    (normalizer) ─┐│
└──────────────────────┘   human_message                 │  ├─ analytics           metrics   (percentiles) ││
           │                                              │  ├─ alerts              cost      (USD model)   ││
           │  POST /traces (ASR/LLM/transport timings)    │  ├─ audit               sentiment (offline/Claude)
           └─────────────────────────────────────────────│  ├─ search    ───────▶ search    (Chroma)       ││
                                                          │  └─ ...                 alerting  (SLOs) ◀───────┘│
                                                          └───────────┬──────────────────────┬───────────────┘
                                                                      │                      │
                                                            SQLite (SQLAlchemy)        Chroma (vector
                                                            agents · conversations ·   transcript search,
                                                            turns · raw_events ·        offline hashing
                                                            alerts · audit_log         embedder by default)
```

### Core architectural principle: one normalization path

Both the **post-call webhook** and the **real-time relay** terminate in a single normalizer (`services/ingest.py → ingest_conversation`). A live call's accumulated turns are converted into the *same* canonical `ConversationData` shape used by the webhook path, then persisted through the same code. This guarantees that a conversation becomes metrics *exactly one way*, regardless of how it arrived — there is a single source of truth for every computed value.

### Request lifecycle (post-call webhook)

1. **Verify** the HMAC signature (`services/security.py`).
2. **Log** the raw payload to `raw_events` (append-only — enables reprocessing after a logic change).
3. **Normalize** (`services/ingest.py`): upsert the agent; build `Conversation` + `Turn` rows; compute latency metrics, cost, sentiment and pipeline metrics. Idempotent on `conversation_id`.
4. **Evaluate** SLOs (`services/alerting.py`) and raise `Alert` rows.
5. **Index** the transcript into Chroma for semantic search (best-effort, never blocks ingestion).

---

## 5. Subsystem deep dives

### 5.1 Webhook security (HMAC)

ElevenLabs signs webhooks Stripe-style: an `ElevenLabs-Signature` header of the form `t=<unix_ts>,v0=<hex>`, where the signed message is `HMAC-SHA256(secret, "{ts}.{raw_body}")`.

- Verification is **constant-time** (`hmac.compare_digest`) to prevent timing attacks.
- Signatures older than `webhook_max_age_seconds` (default 1800s) are **rejected to prevent replay**.
- The raw body is preserved byte-for-byte for verification (parsing happens only after the signature is validated).
- Returns `401` on signature failure, `422` on an unparseable body, `200` quickly on success so ElevenLabs does not retry.

### 5.2 Normalization & idempotency

The normalizer upserts the agent, then upserts the conversation by `conversation_id`. On re-delivery (ElevenLabs retries transcription webhooks), existing turns are replaced and stale alerts cleared, so retries never double-count. Lenient Pydantic models (`extra="allow"`) mirror the ElevenLabs payload and preserve unknown fields in the raw event log rather than failing.

### 5.3 Latency metrics engine

Pure, dependency-free functions (`services/metrics.py`) so the math is trivially unit-testable:

- **LLM TTFB / TTF-sentence** extracted from `conversation_turn_metrics.metrics.convai_llm_service_ttfb` and `...ttf_sentence` (seconds → milliseconds).
- **Percentiles** computed with linear interpolation between ranks; `p50`, `p95`, `max`.
- **Interruption rate** `= interruptions / agent_turns` — normalized against the turns that *can* be interrupted.
- **Talk ratio** `= agent_words / (agent_words + user_words)` — how much the agent dominated.

### 5.4 Multi-vendor pipeline tracing *(the headline differentiator)*

A single turn is a relay race across vendors:

```
user stops speaking
   → ASR finalize        (e.g. Deepgram)
   → LLM generation TTFB (e.g. OpenAI / Anthropic)
   → TTS first audio     (ElevenLabs)
   → transport delivery  (e.g. Twilio / Vapi)
→ first audio reaches the user
```

ElevenLabs only sees the TTS stage. This subsystem (`services/pipeline.py`) models every stage:

- **Per turn:** `e2e_latency_ms = Σ stage durations`; `bottleneck_stage = argmax(duration)`.
- **Per call:** e2e p50/p95, per-stage p95, and the *dominant bottleneck* (the most frequent per-turn bottleneck).
- **Per fleet** (`GET /analytics/pipeline`): per-stage p95, each stage's **share of E2E**, and a **bottleneck distribution** (how often each stage is the culprit).

Stages arrive two ways: inline on the turn (simulator / a payload your orchestrator pre-merges), or via **`POST /traces`** — decoupled from the webhook because traces may arrive before or after the transcript. The trace endpoint matches turns by `turn_index`, attaches stages, and recomputes everything. This is the answer to *"was the slow turn the LLM thinking or ElevenLabs buffering?"*

Canonical stages and default vendor labels: `asr`→deepgram, `endpointing`→vad, `llm`→openai, `tts`→elevenlabs, `transport`→twilio.

### 5.5 Cost model

`services/cost.py` mirrors how ElevenLabs actually bills: **call minutes + LLM tokens + TTS + ASR**.

- Prefers explicit values from the `charging` object (`call_charge`, `llm_charge`) when present.
- Falls back to estimation: `call = duration_min × COST_PER_CALL_MINUTE_USD` (default $0.08), `llm` from input/output token counts.
- Token counts are summed **recursively** from `charging.llm_usage` (the structure nests categories).
- The raw credit value (`metadata.cost`) is retained for reconciliation.

### 5.6 Sentiment & task-completion judging

A two-tier design (`services/sentiment.py`) so it runs anywhere:

- **Per-turn sentiment** uses a fast, deterministic lexicon analyzer (no network, no cost) with intensifier handling and length normalization — appropriate for scoring every user utterance.
- **Conversation-level analysis** (overall sentiment + did the call achieve its task) uses **Claude** when `ANTHROPIC_API_KEY` is set, otherwise a **tail-weighted aggregate** of per-turn scores (how the user felt at the *end* is the strongest signal). ElevenLabs' own `call_successful` always wins when present. Any Claude/network failure degrades gracefully to the offline path.

### 5.7 Real-time relay

The relay (`services/relay.py`, `routers/relay.py`) sits in the event stream between agent and user:

- `WS /relay/ingest/{agent_id}` — a producer (browser client or a bridge to the ElevenLabs conversation socket) streams events. A `LiveConversation` aggregator tracks live latency from `ping_ms`, interruptions from `interruption` / `agent_response_correction`, turns from `user_transcript` / `agent_response`, and synthesizes per-turn latency from the wall-clock gap between user and agent.
- `WS /relay/monitor` — dashboards subscribe to compact live "observability frames".
- On stream end, accumulated turns are persisted through the shared normalizer (`source="relay"`).

### 5.8 Human-in-the-loop takeover

Built on the relay's control plane:

- `POST /relay/{id}/takeover?supervisor=…` flips the call to **human control** and pushes a `take_over` control message *back down the producer socket* (the bridge mutes the AI).
- `POST /relay/{id}/say` injects a supervisor message — appended as an agent turn (`source_medium="human_supervisor"`) and delivered to the user.
- `POST /relay/{id}/handback` returns control to the AI.
- The ingest WebSocket runs the **producer-read loop and a control-drain loop concurrently**, so commands are delivered without blocking event ingestion. Persisted calls are tagged `human_takeover` + `supervisor`.

### 5.9 Semantic transcript search

`services/search.py` indexes transcripts into Chroma. To keep the project runnable with zero credentials, the default embedding backend is a deterministic **hashing vectorizer** (bag-of-words, sign-hashed, L2-normalized) — no model download, no API. All Chroma interaction is wrapped so any failure degrades to a no-op rather than breaking ingestion.

### 5.10 SLO alerting

`services/alerting.py` evaluates each freshly ingested call against configurable SLOs and raises `Alert` rows:

| Rule | Default | Scope | Severity |
|---|---|---|---|
| `latency_p95` (LLM TTFB) | 1500 ms | per call | warning |
| `interruption_rate` | 0.25 | per call | warning |
| `task_failure` | — | per call | critical |
| `success_rate` | 0.85 | fleet (rolling window) | critical |

Per-call evaluation is idempotent — re-ingesting a call clears its prior alerts first.

### 5.11 Audit logging

A replay/audit dashboard handles transcripts that often contain PII, so **access itself is an auditable event**. `services/audit.py` records every `view` / `replay` / `search` / `export` with actor, resource and IP, surfaced on the Audit Log page.

---

## 6. Data model

SQLite via SQLAlchemy 2.0 (swappable for Postgres through `DATABASE_URL`). Six tables:

| Table | Purpose | Notable columns |
|---|---|---|
| `agents` | One row per ElevenLabs agent | `id`, `name`, `first_seen_at`, `last_seen_at` |
| `conversations` | One row per call, with **denormalized** computed metrics for fast filtering/aggregation | latency percentiles, `interruption_rate`, `talk_ratio`, `e2e_latency_p95_ms`, `bottleneck_stage`, `stage_latency_p95`, full cost breakdown, `sentiment_overall`, `call_successful`, `breached_slo`, `human_takeover`, `supervisor`, `source` |
| `turns` | Per-turn detail | `role`, `message`, `interrupted`, `llm_ttfb_ms`, `e2e_latency_ms`, `bottleneck_stage`, `pipeline_stages` (JSON), token counts, `sentiment`, `source_medium` |
| `raw_events` | Append-only log of webhook / relay / trace payloads | `event_type`, `source`, `payload` (JSON) — enables replay & reprocessing |
| `alerts` | SLO breaches | `rule`, `severity`, `threshold`, `observed_value`, `resolved` |
| `audit_log` | Transcript access trail | `actor`, `action`, `resource_type`, `resource_id`, `detail` |

**Why denormalize metrics onto `conversations`?** The dashboard filters and aggregates constantly; precomputing percentiles, rates and the cost breakdown at ingest time keeps reads cheap and the query layer portable. The raw event log preserves full fidelity so any metric can be recomputed later.

---

## 7. API reference

Auto-generated OpenAPI docs at `http://localhost:8000/docs`. 19 HTTP + 2 WebSocket endpoints (excluding the framework's own docs routes).

### Ingestion
| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/elevenlabs` | HMAC-verified `post_call_transcription` ingestion |
| `POST` | `/traces` | Attach multi-vendor stage timings to existing turns |

### Conversations & replay
| Method | Path | Description |
|---|---|---|
| `GET` | `/conversations` | Filterable, paginated list (agent, outcome, sentiment, SLO, source) |
| `GET` | `/conversations/{id}` | Full detail incl. turn timeline (logs an audit `view`) |
| `GET` | `/conversations/{id}/replay` | Ordered replay timeline (logs an audit `replay`) |

### Analytics
| Method | Path | Description |
|---|---|---|
| `GET` | `/analytics/summary` | Headline KPIs (success, latency, e2e, interruptions, cost, sentiment, SLO) |
| `GET` | `/analytics/timeseries` | Bucketed trend lines (day/hour) |
| `GET` | `/analytics/agents` | Per-agent performance breakdown |
| `GET` | `/analytics/pipeline` | Fleet E2E p95, per-stage p95, bottleneck distribution |

### Real-time relay & takeover
| Method | Path | Description |
|---|---|---|
| `WS` | `/relay/ingest/{agent_id}` | Producer streams live ElevenLabs events |
| `WS` | `/relay/monitor` | Dashboard subscribes to live frames |
| `GET` | `/relay/active` | Snapshot of in-flight calls |
| `POST` | `/relay/{id}/takeover` | Supervisor assumes control from the AI |
| `POST` | `/relay/{id}/say` | Send a message as the agent |
| `POST` | `/relay/{id}/handback` | Return control to the AI |

### Search, alerts, audit
| Method | Path | Description |
|---|---|---|
| `GET` | `/search` | Semantic transcript search |
| `GET` | `/alerts` · `POST /alerts/{id}/resolve` · `POST /alerts/evaluate-fleet` | SLO alerts |
| `GET` | `/audit` | Transcript access log |
| `GET` | `/health` | Liveness probe |

---

## 8. Frontend

React + TypeScript + Vite + Recharts, seven pages behind a single-page router:

| Page | What it shows |
|---|---|
| **Dashboard** | KPI cards (incl. LLM TTFB p95 and **true E2E p95**), latency & success trend charts, **pipeline bottleneck widget** (per-stage p95, share of E2E, bottleneck distribution), per-agent table |
| **Conversations** | Filterable, paginated list with outcome / sentiment / SLO / human-takeover badges |
| **Replay / Audit** | Turn-by-turn timeline, **per-turn pipeline latency bars** (vendor-colored, bottleneck highlighted), latency waterfall, interruptions, sentiment, cost breakdown |
| **Live Monitor** | Active calls over WebSocket with live metrics and **Take Over / Send / Hand Back** controls |
| **Search** | Natural-language transcript search |
| **Alerts** | Open/resolved SLO breaches with resolve action |
| **Audit Log** | Who viewed / replayed / searched which transcript |

A thin typed API client (`api/client.ts`) mirrors the backend contract; a small `useApi` hook handles loading/error state.

---

## 9. Getting started

### Local

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload                 # http://localhost:8000

# Seed realistic demo data (no ElevenLabs/Claude account needed)
python -m app.simulator --calls 50

# Frontend
cd ../frontend
npm install
npm run dev                                   # http://localhost:5173
```

### Live relay + human takeover demo

With the backend running:

```bash
cd backend && python scripts/relay_demo.py
```

Open the dashboard's **Live Monitor**, click **Take over** on the active call, type a message as the agent, then **Hand back** — the demo terminal prints the control signals it receives (`AI MUTED`, the supervisor's words, `control handed back`).

### Docker (full stack)

```bash
docker compose up --build
# dashboard → http://localhost:8080   ·   API docs → http://localhost:8000/docs
```

A `Makefile` wraps common tasks: `make install`, `make backend`, `make frontend`, `make seed`, `make test`, `make lint`, `make up`.

---

## 10. Configuration

All settings are environment variables (see `.env.example`) with offline-safe defaults — the app boots with zero external credentials.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/observability.db` | SQLAlchemy URL (swap for Postgres in prod) |
| `ELEVENLABS_WEBHOOK_SECRET` | — | Shared secret for HMAC verification |
| `ELEVENLABS_VERIFY_SIGNATURE` | `true` | Set `false` only for local testing |
| `ANTHROPIC_API_KEY` | — | Enables Claude-powered sentiment/judging |
| `SENTIMENT_MODEL` | `claude-haiku-4-5-20251001` | Model used when Claude judging is enabled |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Vector index location |
| `SLO_LLM_TTFB_P95_MS` | `1500` | Latency SLO |
| `SLO_SUCCESS_RATE_MIN` | `0.85` | Fleet success-rate SLO |
| `SLO_INTERRUPTION_RATE_MAX` | `0.25` | Interruption SLO |
| `COST_PER_CALL_MINUTE_USD` | `0.08` | Call-minute rate for the cost model |
| `CORS_ORIGINS` | localhost:5173,3000 | Allowed frontend origins |

---

## 11. Testing & CI

```bash
cd backend && pytest -q       # 51 tests
```

Coverage spans HMAC verification (valid / tampered / expired / missing secret), the metrics engine (percentiles, interruption rate, talk ratio), the cost model (explicit charges, estimation, recursive token sums), the offline sentiment analyzer, relay aggregation, the **takeover** control flow, **pipeline** math + trace enrichment + bottleneck analytics, and end-to-end API tests (webhook ingestion, idempotency, filtering, analytics, replay, relay WebSocket).

**GitHub Actions** runs two jobs on every push/PR: backend (ruff + pytest) and frontend (TypeScript typecheck + Vite build).

---

## 12. Project structure

```
backend/
  app/
    config.py            # pydantic-settings, offline-safe defaults
    database.py          # SQLAlchemy engine, session, Base
    main.py              # FastAPI app, lifespan, router registration
    models/              # agents, conversations, turns, raw_events, alerts, audit_log
    schemas/             # elevenlabs.py (inbound) · api.py (outbound)
    services/            # security, ingest, metrics, cost, pipeline, sentiment,
                         # relay, alerting, analytics, search, audit
    routers/             # webhooks, conversations, analytics, relay, traces,
                         # alerts, audit, search
    simulator.py         # offline data generator (multi-vendor stages)
  scripts/relay_demo.py  # drives the live relay + takeover demo
  tests/                 # 51 pytest tests
frontend/
  src/
    api/                 # typed client + contract types
    components/          # Layout, Badge, PipelineBar, formatters
    hooks/useApi.ts      # data-fetching hook
    pages/               # Dashboard, Conversations, ConversationDetail,
                         # LiveMonitor, Search, Alerts, Audit
docs/                    # architecture.md, metrics.md
docker-compose.yml · Makefile · .github/workflows/ci.yml
```

---

## 13. Design decisions & trade-offs

- **One normalization path.** Webhook and relay both terminate in `ingest_conversation`, so there is a single source of truth for how a conversation becomes metrics. The cost of converting live turns into the canonical shape is repaid by never maintaining two metric implementations.
- **Denormalized metrics + an append-only raw log.** Reads stay cheap (no recomputation per request) while the `raw_events` log preserves full fidelity for reprocessing. The trade-off — write amplification and potential drift — is mitigated by idempotent ingest and the ability to recompute from raw events.
- **Offline-first everywhere.** Sentiment falls back to a deterministic lexicon, search to a hashing embedder, and the simulator generates a complete dataset. The whole system runs and demos with zero credentials; external services are strict upgrades, never requirements.
- **Pipeline tracing decoupled from the webhook.** Traces arrive on their own endpoint because, in a real multi-vendor stack, stage timings come from the orchestrator on a different timeline than the ElevenLabs transcript. Matching by `turn_index` and recomputing keeps the two sources independent.
- **Graceful degradation as a rule.** Claude failures, Chroma unavailability and disconnected monitors are all caught and downgraded rather than allowed to break ingestion.
- **Pure functions for the math.** Metrics, cost and pipeline computation are dependency-free pure functions, which is why they are exhaustively unit-tested.

---

## 14. Scaling to production

The service boundaries (routers → services, denormalized reads, single normalizer) are designed so the following are localized changes:

- **Postgres** via `DATABASE_URL`; compute percentiles with a native aggregate (`percentile_cont`) instead of in Python.
- **Queue/worker** for webhook normalization to absorb bursts and decouple ingestion latency from response time.
- **Auth** in front of the API so the audit `actor` is a real identity rather than a header.
- **Real embeddings** (swap the hashing vectorizer for a hosted embedding model) for higher-quality semantic search.
- **Alert delivery** (Slack/email/webhook) on top of the existing alert store.

---

## 15. Roadmap

- **Custom LLM-as-judge rubrics** — per-agent evaluation rules ("did the agent mention the refund policy?") graded automatically by Claude on each transcript.
- **Audio playback in the replay view** — store the `post_call_audio` webhook and sync a player to the turn timeline.
- **CRM / conversion mapping** — link call IDs to closed tickets (Zendesk/HubSpot) or sales outcomes (Salesforce).
- **Alert delivery channels** and per-agent cost budgets / forecasting.
- **Frontend bundle code-splitting** and component tests.

---

## 16. License

[MIT](LICENSE) © Kaushik KC
