// Types mirroring the backend API contract (app/schemas/api.py).

export interface ConversationSummary {
  id: string;
  agent_id: string;
  status: string;
  started_at: string | null;
  call_duration_secs: number;
  call_successful: string;
  summary_title: string | null;
  turn_count: number;
  interruption_count: number;
  interruption_rate: number;
  llm_ttfb_p95_ms: number | null;
  sentiment_overall: string | null;
  sentiment_score: number | null;
  cost_total_usd: number;
  breached_slo: boolean;
  human_takeover: boolean;
  supervisor: string | null;
  source: string;
}

export interface Turn {
  turn_index: number;
  role: string;
  message: string | null;
  time_in_call_secs: number;
  interrupted: boolean;
  original_message: string | null;
  llm_ttfb_ms: number | null;
  llm_ttf_sentence_ms: number | null;
  llm_input_tokens: number | null;
  llm_output_tokens: number | null;
  tool_calls: unknown[] | null;
  sentiment: string | null;
  sentiment_score: number | null;
  source_medium: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  transcript_summary: string | null;
  main_language: string | null;
  environment: string;
  termination_reason: string | null;
  evaluation_criteria: Record<string, unknown> | null;
  data_collection: Record<string, unknown> | null;
  talk_ratio: number | null;
  user_turn_count: number;
  agent_turn_count: number;
  llm_ttfb_p50_ms: number | null;
  llm_ttfb_max_ms: number | null;
  llm_ttf_sentence_p95_ms: number | null;
  cost_call_usd: number;
  cost_llm_usd: number;
  cost_tts_usd: number;
  cost_asr_usd: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  ingested_at: string;
  turns: Turn[];
}

export interface ConversationPage {
  items: ConversationSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface KpiSummary {
  total_conversations: number;
  success_rate: number;
  avg_duration_secs: number;
  llm_ttfb_p50_ms: number | null;
  llm_ttfb_p95_ms: number | null;
  interruption_rate: number;
  avg_cost_usd: number;
  total_cost_usd: number;
  negative_sentiment_rate: number;
  slo_breach_rate: number;
}

export interface TimeSeriesPoint {
  bucket: string;
  conversations: number;
  success_rate: number;
  llm_ttfb_p95_ms: number | null;
  interruption_rate: number;
  avg_cost_usd: number;
}

export interface AgentStats {
  agent_id: string;
  agent_name: string | null;
  conversations: number;
  success_rate: number;
  llm_ttfb_p95_ms: number | null;
  interruption_rate: number;
  avg_cost_usd: number;
}

export interface Alert {
  id: number;
  conversation_id: string | null;
  agent_id: string | null;
  rule: string;
  severity: string;
  message: string;
  threshold: number | null;
  observed_value: number | null;
  resolved: boolean;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface SearchHit {
  conversation_id: string;
  score: number;
  snippet: string;
  role: string | null;
}

export interface ReplayTimelineItem {
  turn_index: number;
  role: string;
  message: string | null;
  at_secs: number;
  interrupted: boolean;
  original_message: string | null;
  llm_ttfb_ms: number | null;
  llm_ttf_sentence_ms: number | null;
  sentiment: string | null;
  sentiment_score: number | null;
  tool_calls: unknown[] | null;
}

export interface ReplayResponse {
  conversation_id: string;
  agent_id: string;
  duration_secs: number;
  summary: string | null;
  timeline: ReplayTimelineItem[];
}

export interface LiveFrame {
  type: string;
  conversation_id: string;
  agent_id: string;
  elapsed_secs: number;
  turn_count: number;
  interruptions: number;
  avg_ping_ms: number | null;
  vad_score: number | null;
  last_role: string | null;
  last_message: string | null;
  control: string;
  supervisor: string | null;
}
