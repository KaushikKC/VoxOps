// Small formatting helpers shared across views.

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function usd(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  return `$${value.toFixed(digits)}`;
}

export function duration(secs: number | null | undefined): string {
  if (secs === null || secs === undefined) return "—";
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// Consistent colors per pipeline stage across the dashboard.
const STAGE_COLORS: Record<string, string> = {
  asr: "#3fb98a",
  endpointing: "#5b6478",
  llm: "#b07cf0",
  tts: "#6c8cff",
  transport: "#e2b340",
};

export function stageColor(stage: string): string {
  return STAGE_COLORS[stage] ?? "#8b94a7";
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}
