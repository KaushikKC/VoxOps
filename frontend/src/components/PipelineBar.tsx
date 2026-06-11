// Stacked horizontal bar visualizing a turn's multi-vendor latency pipeline.

import { ms, stageColor } from "./format";
import type { PipelineStage } from "../api/types";

export function PipelineBar({
  stages,
  bottleneck,
  total,
}: {
  stages: PipelineStage[];
  bottleneck?: string | null;
  total?: number; // shared scale across turns; defaults to this bar's sum
}) {
  const sum = stages.reduce((acc, s) => acc + s.duration_ms, 0);
  const scale = total && total > 0 ? total : sum || 1;
  return (
    <div
      style={{ display: "flex", height: 18, borderRadius: 5, overflow: "hidden", background: "var(--bg-elevated)" }}
      title={stages.map((s) => `${s.stage} (${s.vendor}): ${ms(s.duration_ms)}`).join("  ·  ")}
    >
      {stages.map((s) => {
        const isBottleneck = s.stage === bottleneck;
        return (
          <div
            key={s.stage}
            style={{
              width: `${(s.duration_ms / scale) * 100}%`,
              background: stageColor(s.stage),
              opacity: isBottleneck || !bottleneck ? 1 : 0.55,
              boxShadow: isBottleneck ? "inset 0 0 0 2px #fff5" : undefined,
            }}
          />
        );
      })}
    </div>
  );
}

export function StageLegend({ stages }: { stages: string[] }) {
  return (
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 10 }}>
      {stages.map((stage) => (
        <span key={stage} className="faint" style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background: stageColor(stage),
              display: "inline-block",
            }}
          />
          {stage}
        </span>
      ))}
    </div>
  );
}
