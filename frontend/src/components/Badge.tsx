// Reusable status/sentiment badge.

export function Badge({ kind, label }: { kind: string; label?: string }) {
  const text = label ?? kind;
  return <span className={`badge ${kind}`}>{text}</span>;
}

export function SuccessBadge({ value }: { value: string }) {
  const label = value === "success" ? "Completed" : value === "failure" ? "Failed" : "Unknown";
  return <Badge kind={value} label={label} />;
}

export function SentimentBadge({ value }: { value: string | null }) {
  if (!value) return <span className="faint">—</span>;
  return <Badge kind={value} />;
}
