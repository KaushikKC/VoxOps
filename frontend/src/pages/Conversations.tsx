// Conversations: filterable, paginated list linking into the replay/audit view.

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type ConversationFilters } from "../api/client";
import { useApi } from "../hooks/useApi";
import { SentimentBadge, SuccessBadge, Badge } from "../components/Badge";
import { duration, ms, relativeTime, usd } from "../components/format";

const PAGE = 25;

export function Conversations() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<ConversationFilters>({ limit: PAGE, offset: 0 });

  const page = useApi(() => api.conversations(filters), [JSON.stringify(filters)]);

  function set(patch: Partial<ConversationFilters>) {
    setFilters((f) => ({ ...f, ...patch, offset: 0 }));
  }

  const total = page.data?.total ?? 0;
  const offset = filters.offset ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Conversations</h1>
          <p>Every call, with latency, interruptions, sentiment, outcome and cost.</p>
        </div>
      </div>

      <div className="toolbar">
        <select onChange={(e) => set({ success: e.target.value || undefined })}>
          <option value="">All outcomes</option>
          <option value="success">Completed</option>
          <option value="failure">Failed</option>
          <option value="unknown">Unknown</option>
        </select>
        <select onChange={(e) => set({ sentiment: e.target.value || undefined })}>
          <option value="">All sentiment</option>
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="negative">Negative</option>
        </select>
        <select
          onChange={(e) =>
            set({ breached_slo: e.target.value === "" ? undefined : e.target.value === "true" })
          }
        >
          <option value="">All SLO states</option>
          <option value="true">SLO breached</option>
          <option value="false">Within SLO</option>
        </select>
        <select onChange={(e) => set({ source: e.target.value || undefined })}>
          <option value="">All sources</option>
          <option value="webhook">Webhook</option>
          <option value="relay">Live relay</option>
          <option value="simulator">Simulator</option>
        </select>
      </div>

      {page.error && <div className="error">Failed to load: {page.error}</div>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Call</th>
              <th>Agent</th>
              <th>When</th>
              <th>Duration</th>
              <th>Outcome</th>
              <th>Sentiment</th>
              <th>TTFB p95</th>
              <th>Interrupts</th>
              <th>Cost</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(page.data?.items ?? []).map((c) => (
              <tr
                key={c.id}
                className="row-link"
                onClick={() => navigate(`/conversations/${c.id}`)}
              >
                <td>{c.summary_title ?? <span className="mono">{c.id}</span>}</td>
                <td className="muted">{c.agent_id}</td>
                <td className="faint">{relativeTime(c.started_at)}</td>
                <td>{duration(c.call_duration_secs)}</td>
                <td>
                  <SuccessBadge value={c.call_successful} />
                </td>
                <td>
                  <SentimentBadge value={c.sentiment_overall} />
                </td>
                <td>{ms(c.llm_ttfb_p95_ms)}</td>
                <td>{c.interruption_count}</td>
                <td>{usd(c.cost_total_usd)}</td>
                <td>{c.breached_slo && <Badge kind="slo" label="SLO" />}</td>
              </tr>
            ))}
            {page.data && page.data.items.length === 0 && (
              <tr>
                <td colSpan={10} className="empty">
                  No conversations match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <span className="faint">
          {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE, total)}`} of {total}
        </span>
        <button
          className="ghost"
          disabled={offset === 0}
          onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, offset - PAGE) }))}
        >
          Prev
        </button>
        <button
          className="ghost"
          disabled={offset + PAGE >= total}
          onClick={() => setFilters((f) => ({ ...f, offset: offset + PAGE }))}
        >
          Next
        </button>
      </div>
    </>
  );
}
