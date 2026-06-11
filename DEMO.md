# VoxOps — Demo & Testing Guide

A complete, copy-paste runbook for (1) verifying every feature works and (2) recording a demo video that shows all of it. Nothing here needs a paid ElevenLabs or Anthropic account — the whole system runs offline.

> **macOS / zsh assumed.** Backend runs on **:8000**, frontend dev server on **:5173**.

---

## 0. Prerequisites (one time)

```bash
# from the project root: /Users/kaushikk/Documents/Products/elevenlabs-project

# Backend deps
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # safe offline defaults

# Frontend deps
cd ../frontend
npm install
```

---

## 1. Run everything (3 terminals)

Open **three** terminal tabs/windows.

### Terminal 1 — backend
```bash
cd backend
source .venv/bin/activate
python -m app.simulator --calls 60 --days 14   # seed realistic demo data
uvicorn app.main:app --reload                   # serves http://localhost:8000
```
Leave this running. You should see:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

### Terminal 2 — frontend
```bash
cd frontend
npm run dev                                      # serves http://localhost:5173
```

### Terminal 3 — leave free
Used later for the live relay / takeover demo.

Now open **http://localhost:5173** (dashboard) and **http://localhost:8000/docs** (API).

---

## 2. Troubleshooting ("I can't run the backend")

| Symptom | Cause | Fix |
|---|---|---|
| `Failed to send telemetry event ClientStartEvent: capture() takes 1 positional argument...` | **Harmless** Chroma analytics noise. The line right after it (`Seeded N conversations`) means it worked. | Already silenced in code. If you still see it, `pip install -r requirements.txt` to refresh. |
| `Address already in use` on :8000 | A previous backend is still running | `pkill -f "uvicorn app.main:app"` then retry, or use `uvicorn app.main:app --reload --port 8001` |
| `ModuleNotFoundError: No module named 'app'` | Not inside `backend/` or venv not active | `cd backend && source .venv/bin/activate` |
| `command not found: uvicorn` | venv not activated | `source .venv/bin/activate` |
| Dashboard loads but is empty | No data seeded | `python -m app.simulator --calls 60` |
| Frontend can't reach API | Backend not running / CORS | Confirm Terminal 1 is up; `.env` `CORS_ORIGINS` includes `http://localhost:5173` |

**Quick "is the backend alive?" check:**
```bash
curl -s http://localhost:8000/health
# → {"status":"ok","version":"0.1.0","env":"development","sentiment":"offline"}
```

---

## 3. Full functional test

### 3A. Automated quality gate (~30s) — run this first
```bash
cd backend && source .venv/bin/activate
ruff check app tests scripts     # → All checks passed!
pytest -q                        # → 51 passed
cd ../frontend && npm run build  # → built, no TypeScript errors
```
These three green results are your proof the project is production-grade.

### 3B. Manual feature checklist (in the browser)

| # | Feature | Where | Verify |
|---|---|---|---|
| 1 | KPI cards | Dashboard `/` | success %, LLM TTFB p95, **E2E p95**, interruptions, cost, SLO breaches all populated |
| 2 | Trend charts | Dashboard | latency p95 area + success-rate line render |
| 3 | **Pipeline bottlenecks** ⭐ | Dashboard (scroll) | stacked stage bar + table: per-vendor p95, share of E2E, bottleneck count (usually `llm`) |
| 4 | Per-agent table | Dashboard | one row per agent |
| 5 | Conversations + filters | `/conversations` | toggle Failed / Negative / SLO breached / Live relay — list narrows |
| 6 | **Replay / Audit** ⭐ | click any call | turn timeline, per-turn **pipeline bars** (bottleneck highlighted), latency waterfall (red = breach), cost breakdown, sentiment + interruption badges |
| 7 | **Live Monitor + Takeover** ⭐ | `/live` (see §4) | live call, Take Over → Send → Hand Back |
| 8 | **Multi-vendor trace** ⭐ | terminal (see §5) | E2E goes from null → computed |
| 9 | Semantic search | `/search` | "frustrated about a double charge" returns ranked calls |
| 10 | SLO alerts | `/alerts` | list of breaches; **Resolve** removes one |
| 11 | Audit log | `/audit` | your views/replays/searches recorded |
| 12 | API docs | `:8000/docs` | all endpoints, try one live |
| 13 | HMAC security | `curl -X POST localhost:8000/webhooks/elevenlabs -d '{}'` | returns **401** (signature rejected) |

---

## 4. ⭐ Live Monitor + Human Takeover (the headline feature)

With the backend running, in **Terminal 3**:
```bash
cd backend && source .venv/bin/activate
python scripts/relay_demo.py --speed 0.5 --conversation-id demo_call
```
`--speed 0.5` slows playback so you have ~40s to interact.

In the browser, open **http://localhost:5173/live** and:

1. Watch the call tick live — turns, interruptions, round-trip ping, VAD score.
2. Click **Take over** → the card turns amber ("HUMAN · supervisor") and **Terminal 3 prints `⛔ AI MUTED — supervisor took over`**.
3. Type a message in the box → **Send** → Terminal 3 prints `🗣 supervisor says: …`.
4. Click **Hand back to AI** → Terminal 3 prints `✅ control handed back to the AI`.
5. After it ends, open `/conversations` → the call shows a **`human`** badge and `source = relay`.

> This is the single most impressive shot. Record the browser and Terminal 3 **side by side** so viewers see the control signals propagate.

---

## 5. ⭐ Multi-vendor pipeline trace (the ElevenLabs blind spot)

This proves the core thesis: ElevenLabs alone can't see true end-to-end latency.

> Requires `ELEVENLABS_VERIFY_SIGNATURE=false` in `backend/.env` for these unsigned curl calls. (It's already the default in `.env.example`.)

```bash
# 1. Ingest a call WITHOUT vendor stages — the "ElevenLabs-only" view
curl -s -X POST localhost:8000/webhooks/elevenlabs \
  -H 'content-type: application/json' \
  -d '{"type":"post_call_transcription","data":{"agent_id":"a_demo","conversation_id":"mv_demo","transcript":[{"role":"user","message":"hi","time_in_call_secs":1},{"role":"agent","message":"hello","time_in_call_secs":3}],"metadata":{"call_duration_secs":8}}}' >/dev/null

# 2. True end-to-end latency is unknown
curl -s localhost:8000/conversations/mv_demo \
  | python3 -c "import sys,json;print('E2E latency:',json.load(sys.stdin)['e2e_latency_p95_ms'])"
# → E2E latency: None

# 3. The orchestrator reports the stages ElevenLabs can't see
curl -s -X POST localhost:8000/traces -H 'content-type: application/json' \
  -d '{"conversation_id":"mv_demo","turns":[{"turn_index":1,"stages":[{"stage":"asr","vendor":"deepgram","duration_ms":110},{"stage":"llm","vendor":"anthropic","duration_ms":1400},{"stage":"tts","vendor":"elevenlabs","duration_ms":300},{"stage":"transport","vendor":"twilio","duration_ms":60}]}]}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('Now TRUE E2E:',d['e2e_latency_p95_ms'],'ms | bottleneck:',d['bottleneck_stage'])"
# → Now TRUE E2E: 1870.0 ms | bottleneck: llm
```
Then open `mv_demo` in the replay view to see the per-turn stage bars.

---

## 6. 🎬 Demo video storyboard (~5–6 min)

Record these scenes in order. The *italic* line is a suggested voiceover.

| Scene | Time | Show | Say |
|---|---|---|---|
| 0. Title | 0:10 | README top — **VoxOps** | "Observability and live intervention for ElevenLabs voice agents — and any multi-vendor voice stack." |
| 1. The problem | 0:20 | README Motivation + architecture diagram | "ElevenLabs only sees its TTS slice. In production you also have Twilio, OpenAI, Deepgram. Nobody sees the whole picture — this builds it." |
| 2. Dashboard | 0:40 | `/` — pan the KPI cards + charts | "Fleet health at a glance: success rate, LLM TTFB p95, true end-to-end latency, interruptions, cost, SLO breaches." |
| 3. Pipeline bottlenecks ⭐ | 0:30 | scroll to the pipeline widget | "The differentiator: true end-to-end latency split by vendor, and which stage is the bottleneck — usually the LLM, not ElevenLabs." |
| 4. Conversations + filters | 0:30 | `/conversations`, toggle Failed / Negative / SLO breached | "Every call, filterable by outcome, sentiment, SLO breach, or source." |
| 5. Replay / Audit ⭐ | 0:50 | open a call; scroll timeline, point at pipeline bars + waterfall + cost | "Turn by turn: the latency pipeline per turn with the bottleneck highlighted, interruptions, sentiment, and exact cost split — call, LLM, TTS, ASR." |
| 6. Live takeover ⭐⭐ | 1:00 | **split screen**: `/live` + Terminal 3. Take over → type → hand back | "A live call. The supervisor takes over — watch the AI get muted in the terminal — I speak as the agent, then hand back. Real-time human-in-the-loop." |
| 7. Multi-vendor trace | 0:30 | run the §5 curl commands | "ElevenLabs alone shows no end-to-end number. The orchestrator posts the missing stages, and now we have true E2E and the bottleneck." |
| 8. Search + Alerts + Audit | 0:30 | `/search`, `/alerts` (resolve one), `/audit` | "Semantic search over transcripts, SLO alerting, and a full audit trail — every transcript view is logged." |
| 9. Quality | 0:25 | terminal `pytest -q` (51 passed) + `:8000/docs` | "51 tests, typed API, auto-generated OpenAPI. Built production-grade." |
| 10. Close | 0:10 | dashboard | "VoxOps — the operational layer every voice-agent team ends up needing." |

**Two must-have shots:** Scene 5 (replay with pipeline bars) and Scene 6 (split-screen live takeover).

**60-second teaser version:** Scenes 3 + 5 + 6 only.

---

## 7. Recording tips

- **Tool (macOS):** QuickTime → *File ▸ New Screen Recording* (free), **Loom** (easy narration + webcam bubble), or **OBS** (most control). For a portfolio piece, Loom or OBS.
- **Before recording:**
  - Reseed fresh, clean numbers: `python -m app.simulator --calls 60 --seed 7`
  - Browser zoom ~110–125%, terminal font ~16–18pt so text is legible on small players.
  - Hide bookmarks bar + notifications; full-screen the browser.
  - Pre-arrange the **split screen** (browser left, Terminal 3 right) for Scene 6.
- **Takeover scene:** use `--speed 0.5` so you have time to take over, type, and hand back.
- **Length:** aim for 5–6 min full, plus a 60s teaser for LinkedIn/X.
- **Export:** 1080p. Keep the full version for the README, a short clip for social.

---

## 8. Command cheat sheet

```bash
# ---- run ----
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload   # backend :8000
cd frontend && npm run dev                                                 # frontend :5173

# ---- data ----
python -m app.simulator --calls 60 --days 14 --seed 7   # seed demo data
python scripts/relay_demo.py --speed 0.5                # drive a live call (for /live)

# ---- test ----
ruff check app tests scripts        # lint
pytest -q                           # 51 tests
cd frontend && npm run build        # typecheck + build

# ---- health ----
curl -s localhost:8000/health
pkill -f "uvicorn app.main:app"     # stop a stuck backend

# ---- docker (alternative) ----
docker compose up --build           # dashboard :8080, API :8000
```

---

## 9. Reset to a clean slate

```bash
cd backend
pkill -f "uvicorn app.main:app" 2>/dev/null
rm -rf data                         # wipe SQLite DB + Chroma index
source .venv/bin/activate
python -m app.simulator --calls 60 --seed 7
uvicorn app.main:app --reload
```
