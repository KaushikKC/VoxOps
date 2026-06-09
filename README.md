# Voice Agent Observability Dashboard

> Production-grade observability for [ElevenLabs](https://elevenlabs.io) conversational voice agents — capture every turn, measure latency, interruptions, sentiment, task completion and cost per call, and replay/audit any conversation.

ElevenLabs sells its Agents platform on **"testing, monitoring, reliability."** This project is the missing operational layer every team deploying a voice agent eventually has to build: a service that sits between the agent and the user, records what actually happened on every turn, and turns it into the metrics an on-call engineer and a product owner both need.

---

## Why this exists

A voice agent that "demos well" and a voice agent that's *reliable in production* are different things. In production you need answers to:

- **Is it fast?** What's the p95 LLM time-to-first-byte and time-to-first-sentence? Where are the slow turns?
- **Is it polite / natural?** How often does the user interrupt the agent (barge-in)? What's the talk ratio?
- **Did it work?** Did the call achieve its goal (`call_successful`, evaluation criteria, data collected)?
- **How does the user feel?** Per-turn and overall sentiment trajectory.
- **What did it cost?** Exact cost per call broken into call minutes + LLM tokens + TTS + ASR, the same way ElevenLabs bills it.
- **What exactly happened?** A turn-by-turn replay/audit view for any conversation.

This dashboard answers all of the above.

## How it integrates with ElevenLabs

ElevenLabs exposes conversation data through three surfaces; this project uses all three:

| Surface | What it provides | Used for |
|---|---|---|
| **Post-call webhook** (`post_call_transcription`, HMAC-signed) | Full transcript, per-turn `conversation_turn_metrics` (LLM TTFB, time-to-first-sentence), `interrupted` flags, `charging` breakdown, `analysis` (call_successful, evaluation criteria, data collection, summary) | Authoritative per-call ingestion |
| **Real-time WebSocket events** (`user_transcript`, `agent_response`, `agent_response_correction`, `interruption`, `ping`/`pong`, `vad_score`) | Live turns, live round-trip latency, live interruptions | The live **relay** that sits between agent & user |
| **Conversation REST API** | Backfill / reconciliation of historical calls | Audit + replay |

> No paid ElevenLabs account? A built-in **conversation simulator** posts realistic webhook payloads so the entire dashboard is demoable offline.

## Architecture

```
                ┌────────────────────────── Browser (React + Vite) ──────────────────────────┐
                │  KPI dashboard · time-series · conversations list · turn-by-turn replay/audit │
                └───────────────────────────────────▲───────────────────────────────────────┘
                                                     │ REST + WS
┌──────────────┐  post_call webhook (HMAC) ┌─────────┴───────────────────────────────────────┐
│  ElevenLabs  │ ─────────────────────────▶│                   FastAPI backend                │
│   Agents     │  live WS relay  ◀────────▶│  ingestion · normalizer · metrics engine ·        │
└──────────────┘                           │  sentiment/judge · analytics · alerting · audit  │
                                           └─────────┬─────────────────────┬──────────────────┘
                                                     │                     │
                                              SQLite (SQLAlchemy)      Chroma (semantic
                                              metrics + transcripts    transcript search)
```

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, Pydantic v2, Chroma, Anthropic SDK (optional, for sentiment/judging)
- **Frontend:** React + TypeScript + Vite, Recharts
- **Infra:** Docker Compose, pytest, ruff, GitHub Actions

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.main:app --reload

# Seed demo data (no ElevenLabs account needed)
python -m app.simulator --calls 50

# Frontend
cd ../frontend
npm install
npm run dev
```

Or run everything with Docker:

```bash
docker compose up --build
```

## Documentation

- Backend API: `http://localhost:8000/docs` (auto-generated OpenAPI)
- See [`docs/`](docs/) for the data model and metric definitions.

## License

[MIT](LICENSE) © Kaushik KC
