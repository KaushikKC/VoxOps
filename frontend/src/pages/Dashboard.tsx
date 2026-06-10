// Dashboard: headline KPIs, trend charts and per-agent breakdown.

import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ms, pct, usd } from "../components/format";

const AXIS = { stroke: "#5b6478", fontSize: 11 };
const GRID = "#232a3a";

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function Dashboard() {
  const [days, setDays] = useState(14);
  const summary = useApi(() => api.summary({ days }), [days]);
  const series = useApi(() => api.timeseries({ days, bucket: "day" }), [days]);
  const agents = useApi(() => api.agents({ days }), [days]);

  const s = summary.data;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Fleet Overview</h1>
          <p>Reliability, quality and cost across your ElevenLabs voice agents.</p>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {summary.error && <div className="error">Failed to load: {summary.error}</div>}

      <div className="grid kpi-grid" style={{ marginBottom: 16 }}>
        <Kpi label="Conversations" value={s ? String(s.total_conversations) : "—"} />
        <Kpi
          label="Task Success"
          value={s ? pct(s.success_rate) : "—"}
          sub="call completed its goal"
        />
        <Kpi
          label="LLM TTFB p95"
          value={s ? ms(s.llm_ttfb_p95_ms) : "—"}
          sub={s ? `p50 ${ms(s.llm_ttfb_p50_ms)}` : undefined}
        />
        <Kpi
          label="Interruption Rate"
          value={s ? pct(s.interruption_rate) : "—"}
          sub="user barge-in / agent turn"
        />
        <Kpi
          label="Avg Cost / Call"
          value={s ? usd(s.avg_cost_usd) : "—"}
          sub={s ? `${usd(s.total_cost_usd, 2)} total` : undefined}
        />
        <Kpi
          label="SLO Breaches"
          value={s ? pct(s.slo_breach_rate) : "—"}
          sub={s ? `${pct(s.negative_sentiment_rate)} negative sentiment` : undefined}
        />
      </div>

      <div className="grid charts-grid" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>Latency p95 (ms) over time</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={series.data ?? []}>
              <defs>
                <linearGradient id="lat" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6c8cff" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#6c8cff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="bucket" tick={AXIS} tickLine={false} />
              <YAxis tick={AXIS} tickLine={false} width={44} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area
                type="monotone"
                dataKey="llm_ttfb_p95_ms"
                stroke="#6c8cff"
                fill="url(#lat)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3>Task success rate over time</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={series.data ?? []}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="bucket" tick={AXIS} tickLine={false} />
              <YAxis tick={AXIS} tickLine={false} width={44} domain={[0, 1]} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => pct(v)} />
              <Line
                type="monotone"
                dataKey="success_rate"
                stroke="#3fb98a"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h3>Per-agent performance</h3>
        <div className="split">
          <table className="table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Calls</th>
                <th>Success</th>
                <th>TTFB p95</th>
                <th>Interrupts</th>
                <th>Avg cost</th>
              </tr>
            </thead>
            <tbody>
              {(agents.data ?? []).map((a) => (
                <tr key={a.agent_id}>
                  <td>{a.agent_name ?? a.agent_id}</td>
                  <td>{a.conversations}</td>
                  <td>{pct(a.success_rate)}</td>
                  <td>{ms(a.llm_ttfb_p95_ms)}</td>
                  <td>{pct(a.interruption_rate)}</td>
                  <td>{usd(a.avg_cost_usd)}</td>
                </tr>
              ))}
              {agents.data && agents.data.length === 0 && (
                <tr>
                  <td colSpan={6} className="faint">
                    No data yet — seed with the simulator.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div>
            <h3 style={{ fontSize: 13 }}>Calls by agent</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={agents.data ?? []} layout="vertical">
                <XAxis type="number" tick={AXIS} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="agent_id"
                  tick={AXIS}
                  tickLine={false}
                  width={90}
                />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                <Bar dataKey="conversations" fill="#6c8cff" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </>
  );
}

const tooltipStyle = {
  background: "#161b27",
  border: "1px solid #232a3a",
  borderRadius: 8,
  color: "#e6e9f0",
  fontSize: 12,
};
