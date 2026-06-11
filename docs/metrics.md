# Metric definitions

Every metric the dashboard shows, how it's computed, and which ElevenLabs field
it comes from.

## Latency

| Metric | Definition | Source |
|---|---|---|
| **LLM TTFB** | Time-to-first-byte from the LLM for an agent turn | `conversation_turn_metrics.metrics.convai_llm_service_ttfb.elapsed_time` (seconds → ms) |
| **LLM TTF sentence** | Time to the first complete sentence | `convai_llm_service_ttf_sentence.elapsed_time` |
| **TTFB p50 / p95 / max** | Percentiles across a call's agent turns | computed (`services/metrics.py`) |
| **Fleet TTFB p95** | p95 of per-call p95 values over the window | computed (`services/analytics.py`) |

Percentiles use linear interpolation. The fleet view aggregates per-call p95
values rather than raw turns to keep the rollup cheap; it is directional, not a
billing-grade percentile.

In the **live relay**, per-turn latency is synthesized as the wall-clock gap
between a user transcript and the following agent response, since real
`conversation_turn_metrics` only arrive post-call.

## Multi-vendor pipeline latency

In a real deployment a turn is a relay race across vendors. ElevenLabs only sees
its own (TTS) stage, so the *true* end-to-end number lives nowhere unless you
assemble it.

| Metric | Definition |
|---|---|
| **Stage** | One vendor's contribution to a turn: `asr` (Deepgram), `llm` (OpenAI/Anthropic), `tts` (ElevenLabs), `transport` (Twilio/Vapi) |
| **End-to-end (E2E) latency** | Sum of all stages for a turn = user-stops-speaking → first audio out |
| **Bottleneck stage** | The slowest stage in a turn; the dominant bottleneck of a call is its most frequent |
| **Stage p95** | p95 of a stage's duration across turns/calls |
| **Share of E2E** | A stage's p95 as a fraction of the summed stage p95 — where the time goes |

**How stages arrive:** the simulator emits them inline; in production your
orchestrator (the layer wiring Twilio + the LLM + ElevenLabs) reports the stages
ElevenLabs can't see via `POST /traces` (`{conversation_id, turns:[{turn_index,
stages:[{stage, vendor, duration_ms}]}]}`), which enriches the stored turns and
recomputes E2E + bottleneck. Fleet view: `GET /analytics/pipeline`.

## Interruptions (barge-in)

| Metric | Definition |
|---|---|
| **Interruption count** | Turns flagged `interrupted` (webhook) or signalled by `interruption` / `agent_response_correction` (relay) |
| **Interruption rate** | `interruptions / agent_turns` — normalized against the turns that *can* be interrupted |

A high interruption rate means users are talking over the agent — often a sign
of slow responses, over-long replies, or poor turn-taking.

## Conversation shape

| Metric | Definition |
|---|---|
| **Turn count** | Total turns; split into agent / user |
| **Talk ratio** | `agent_words / (agent_words + user_words)` — how much the agent dominated |

## Outcome & sentiment

| Metric | Definition |
|---|---|
| **Task success** | `success` / `failure` / `unknown`. ElevenLabs' `analysis.call_successful` is authoritative when present; otherwise the judge decides |
| **Sentiment (per turn)** | Lexicon score in `[-1, 1]` on user utterances |
| **Sentiment (overall)** | Tail-weighted aggregate (how the user felt at the end matters most), or Claude when configured |

## Cost (USD)

Mirrors ElevenLabs billing: **call minutes + LLM tokens + TTS + ASR**.

| Component | Source / fallback |
|---|---|
| **Call** | `charging.call_charge`; else `duration_min × COST_PER_CALL_MINUTE_USD` (default $0.08) |
| **LLM** | `charging.llm_charge`; else estimated from input/output tokens |
| **Tokens** | Recursively summed from `charging.llm_usage` |
| **Credits** | Raw `metadata.cost` retained for reconciliation |

## SLOs

Configurable in `.env`; breaches raise alerts.

| SLO | Default | Scope |
|---|---|---|
| `SLO_LLM_TTFB_P95_MS` | 1500 ms | per call |
| `SLO_INTERRUPTION_RATE_MAX` | 0.25 | per call |
| `SLO_SUCCESS_RATE_MIN` | 0.85 | fleet (rolling window) |
| task failure | — | per call (critical) |
