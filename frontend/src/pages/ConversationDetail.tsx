// Conversation detail = the replay / audit view.
// Turn-by-turn timeline with interruptions, per-turn latency, sentiment, plus a
// latency waterfall and cost breakdown. Opening this page logs an audit 'view'.

import { Link, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge, SentimentBadge, SuccessBadge } from "../components/Badge";
import { PipelineBar, StageLegend } from "../components/PipelineBar";
import { duration, ms, pct, stageColor, usd } from "../components/format";
import type { ConversationDetail as Detail, Turn } from "../api/types";

const SLO_TTFB = 1500;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-row">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function CostBreakdown({ c }: { c: Detail }) {
  const total = c.cost_total_usd || 1;
  const segs = [
    { label: "Call", value: c.cost_call_usd, color: "#6c8cff" },
    { label: "LLM", value: c.cost_llm_usd, color: "#b07cf0" },
    { label: "TTS", value: c.cost_tts_usd, color: "#3fb98a" },
    { label: "ASR", value: c.cost_asr_usd, color: "#e2b340" },
  ].filter((s) => s.value > 0);
  return (
    <div className="card">
      <h3>Cost breakdown — {usd(c.cost_total_usd)}</h3>
      <div className="cost-bar">
        {segs.map((s) => (
          <div
            key={s.label}
            className="cost-seg"
            style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
            title={`${s.label}: ${usd(s.value)}`}
          />
        ))}
      </div>
      {segs.map((s) => (
        <div className="stat-row" key={s.label}>
          <span className="muted">
            <span style={{ color: s.color }}>●</span> {s.label}
          </span>
          <span>{usd(s.value)}</span>
        </div>
      ))}
      <Stat label="LLM tokens" value={`${c.llm_input_tokens} in / ${c.llm_output_tokens} out`} />
    </div>
  );
}

function LatencyWaterfall({ turns }: { turns: Turn[] }) {
  const data = turns
    .filter((t) => t.role === "agent" && t.llm_ttfb_ms !== null)
    .map((t, i) => ({ name: `#${t.turn_index}`, ttfb: t.llm_ttfb_ms as number, i }));
  if (data.length === 0) return null;
  return (
    <div className="card">
      <h3>LLM response latency per agent turn (ms)</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data}>
          <XAxis dataKey="name" tick={{ stroke: "#5b6478", fontSize: 11 }} tickLine={false} />
          <YAxis tick={{ stroke: "#5b6478", fontSize: 11 }} tickLine={false} width={44} />
          <Tooltip
            contentStyle={{
              background: "#161b27",
              border: "1px solid #232a3a",
              borderRadius: 8,
              fontSize: 12,
            }}
            cursor={{ fill: "rgba(255,255,255,0.03)" }}
          />
          <Bar dataKey="ttfb" radius={[4, 4, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.i} fill={d.ttfb > SLO_TTFB ? "#e2575a" : "#6c8cff"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="faint" style={{ marginTop: 8 }}>
        Bars in red exceed the {SLO_TTFB}ms TTFB SLO.
      </p>
    </div>
  );
}

function PipelineLatency({ c }: { c: Detail }) {
  const turns = c.turns.filter((t) => t.pipeline_stages && t.pipeline_stages.length > 0);
  if (turns.length === 0) return null;
  // Shared scale so bars are comparable across turns.
  const maxE2e = Math.max(...turns.map((t) => t.e2e_latency_ms ?? 0));
  const allStages = Array.from(
    new Set(turns.flatMap((t) => (t.pipeline_stages ?? []).map((s) => s.stage))),
  );
  return (
    <div className="card">
      <h3>True end-to-end latency (multi-vendor pipeline)</h3>
      <p className="faint" style={{ marginTop: -8 }}>
        User-stops-speaking → first audio out, across every vendor. ElevenLabs only sees the
        TTS slice; the bottleneck stage is highlighted.
      </p>
      <div className="timeline" style={{ marginTop: 12 }}>
        {turns.map((t) => (
          <div key={t.turn_index}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                marginBottom: 4,
              }}
            >
              <span className="faint">turn #{t.turn_index}</span>
              <span>
                <b>{ms(t.e2e_latency_ms)}</b>{" "}
                <span className="faint" style={{ color: stageColor(t.bottleneck_stage ?? "") }}>
                  · {t.bottleneck_stage} bound
                </span>
              </span>
            </div>
            <PipelineBar
              stages={t.pipeline_stages ?? []}
              bottleneck={t.bottleneck_stage}
              total={maxE2e}
            />
          </div>
        ))}
      </div>
      <StageLegend stages={allStages} />
    </div>
  );
}

function TurnBubble({ turn }: { turn: Turn }) {
  const slow = turn.llm_ttfb_ms !== null && turn.llm_ttfb_ms > SLO_TTFB;
  return (
    <div className={`turn ${turn.role}`}>
      <div className="gutter">{turn.time_in_call_secs.toFixed(1)}s</div>
      <div className="bubble">
        <div className="role">
          {turn.role}
          {turn.interrupted && <Badge kind="warning" label="interrupted" />}
          {turn.role === "user" && <SentimentBadge value={turn.sentiment} />}
        </div>
        {turn.interrupted && turn.original_message && (
          <div className="strike">{turn.original_message}</div>
        )}
        <div>{turn.message ?? <span className="faint">—</span>}</div>
        <div className="meta">
          {turn.llm_ttfb_ms !== null && (
            <span className={`lat-pill ${slow ? "slow" : ""}`}>TTFB {ms(turn.llm_ttfb_ms)}</span>
          )}
          {turn.llm_ttf_sentence_ms !== null && (
            <span className="lat-pill">sentence {ms(turn.llm_ttf_sentence_ms)}</span>
          )}
          {turn.llm_output_tokens !== null && (
            <span>{turn.llm_output_tokens} out tokens</span>
          )}
          {turn.tool_calls && turn.tool_calls.length > 0 && (
            <Badge kind="info" label={`${turn.tool_calls.length} tool call`} />
          )}
        </div>
      </div>
    </div>
  );
}

export function ConversationDetail() {
  const { id } = useParams<{ id: string }>();
  const detail = useApi(() => api.conversation(id!), [id]);
  const c = detail.data;

  if (detail.loading) return <div className="spinner">Loading conversation…</div>;
  if (detail.error || !c) return <div className="error">Failed to load: {detail.error}</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <Link to="/conversations" className="faint">
            ← Conversations
          </Link>
          <h1 style={{ marginTop: 8 }}>{c.summary_title ?? c.id}</h1>
          <p className="mono">{c.id}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <SuccessBadge value={c.call_successful} />
          <SentimentBadge value={c.sentiment_overall} />
          {c.breached_slo && <Badge kind="slo" label="SLO breached" />}
          {c.human_takeover && <Badge kind="warning" label={`human: ${c.supervisor ?? "supervisor"}`} />}
          <Badge kind="info" label={c.source} />
        </div>
      </div>

      {c.transcript_summary && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>Summary</h3>
          <p className="muted" style={{ margin: 0 }}>
            {c.transcript_summary}
          </p>
        </div>
      )}

      <div className="split" style={{ marginBottom: 16 }}>
        <div className="grid" style={{ gap: 16 }}>
          <PipelineLatency c={c} />
          <LatencyWaterfall turns={c.turns} />
          <div className="card">
            <h3>Replay timeline</h3>
            <div className="timeline">
              {c.turns.map((t) => (
                <TurnBubble key={t.turn_index} turn={t} />
              ))}
            </div>
          </div>
        </div>

        <div className="grid" style={{ gap: 16 }}>
          <div className="card">
            <h3>Call metrics</h3>
            <Stat label="Duration" value={duration(c.call_duration_secs)} />
            <Stat label="Turns" value={`${c.turn_count} (${c.agent_turn_count}A / ${c.user_turn_count}U)`} />
            <Stat label="Interruptions" value={`${c.interruption_count} (${pct(c.interruption_rate)})`} />
            <Stat label="Talk ratio (agent)" value={c.talk_ratio !== null ? pct(c.talk_ratio) : "—"} />
            <Stat label="LLM TTFB p50 / p95" value={`${ms(c.llm_ttfb_p50_ms)} / ${ms(c.llm_ttfb_p95_ms)}`} />
            {c.e2e_latency_p95_ms !== null && (
              <Stat
                label="E2E p50 / p95"
                value={`${ms(c.e2e_latency_p50_ms)} / ${ms(c.e2e_latency_p95_ms)}`}
              />
            )}
            {c.bottleneck_stage && <Stat label="Bottleneck" value={c.bottleneck_stage} />}
            <Stat label="Language" value={c.main_language ?? "—"} />
            <Stat label="Ended" value={c.termination_reason ?? "—"} />
          </div>
          <CostBreakdown c={c} />
          {c.evaluation_criteria && Object.keys(c.evaluation_criteria).length > 0 && (
            <div className="card">
              <h3>Evaluation criteria</h3>
              <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                {JSON.stringify(c.evaluation_criteria, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
