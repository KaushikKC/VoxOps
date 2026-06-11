// Thin typed fetch wrapper around the observability backend.

import type {
  AgentStats,
  Alert,
  AuditEntry,
  ConversationDetail,
  ConversationPage,
  KpiSummary,
  PipelineBreakdown,
  ReplayResponse,
  SearchHit,
  TimeSeriesPoint,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const res = await fetch(url.toString(), { headers: { "x-actor": "dashboard" } });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${path}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "x-actor": "dashboard", "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export interface ConversationFilters {
  agent_id?: string;
  success?: string;
  sentiment?: string;
  breached_slo?: boolean;
  source?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  summary: (params?: { agent_id?: string; days?: number }) =>
    get<KpiSummary>("/analytics/summary", params),
  timeseries: (params?: { agent_id?: string; days?: number; bucket?: string }) =>
    get<TimeSeriesPoint[]>("/analytics/timeseries", params),
  agents: (params?: { days?: number }) => get<AgentStats[]>("/analytics/agents", params),
  pipeline: (params?: { agent_id?: string; days?: number }) =>
    get<PipelineBreakdown>("/analytics/pipeline", params),

  conversations: (filters?: ConversationFilters) =>
    get<ConversationPage>("/conversations", filters as Record<string, unknown>),
  conversation: (id: string) => get<ConversationDetail>(`/conversations/${id}`),
  replay: (id: string) => get<ReplayResponse>(`/conversations/${id}/replay`),

  alerts: (params?: { resolved?: boolean; severity?: string }) =>
    get<Alert[]>("/alerts", params),
  resolveAlert: (id: number) => post<Alert>(`/alerts/${id}/resolve`),

  audit: (params?: { actor?: string; action?: string; resource_id?: string }) =>
    get<AuditEntry[]>("/audit", params),

  search: (q: string, limit = 10) =>
    get<{ query: string; hits: SearchHit[] }>("/search", { q, limit }),

  // Human-in-the-loop relay control.
  takeover: (conversationId: string, supervisor = "supervisor") =>
    post<{ control: string }>(
      `/relay/${conversationId}/takeover?supervisor=${encodeURIComponent(supervisor)}`,
    ),
  handback: (conversationId: string) => post<{ control: string }>(`/relay/${conversationId}/handback`),
  say: (conversationId: string, text: string) =>
    post<{ status: string }>(`/relay/${conversationId}/say`, { text }),
};
