// Live Monitor: subscribes to the relay WebSocket and shows in-flight calls in
// real time (live latency, interruptions, current turn).

import { useEffect, useRef, useState } from "react";

import { ms } from "../components/format";
import type { LiveFrame } from "../api/types";

const WS_BASE = import.meta.env.VITE_WS_BASE ?? `ws://${window.location.hostname}:8000`;

type ConnState = "connecting" | "open" | "closed";

export function LiveMonitor() {
  const [frames, setFrames] = useState<Record<string, LiveFrame>>({});
  const [state, setState] = useState<ConnState>("connecting");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    const ws = new WebSocket(`${WS_BASE}/relay/monitor`);
    wsRef.current = ws;

    ws.onopen = () => setState("open");
    ws.onclose = () => !closed && setState("closed");
    ws.onerror = () => setState("closed");
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "snapshot") {
        const map: Record<string, LiveFrame> = {};
        for (const f of msg.active as LiveFrame[]) map[f.conversation_id] = f;
        setFrames(map);
      } else if (msg.type === "frame") {
        setFrames((prev) => ({ ...prev, [msg.conversation_id]: msg as LiveFrame }));
      } else if (msg.type === "ended") {
        setFrames((prev) => {
          const next = { ...prev };
          delete next[msg.conversation_id];
          return next;
        });
      }
    };

    return () => {
      closed = true;
      ws.close();
    };
  }, []);

  const active = Object.values(frames);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Live Monitor</h1>
          <p>In-flight calls streaming through the relay, updated in real time.</p>
        </div>
        <span className="badge info">
          {state === "open" ? (
            <>
              <span className="live-dot" /> connected
            </>
          ) : (
            state
          )}
        </span>
      </div>

      {active.length === 0 ? (
        <div className="card">
          <div className="empty">
            No active calls. Start one by streaming events to
            <span className="mono"> /relay/ingest/&#123;agent_id&#125;</span>, or run the relay
            demo from the README.
          </div>
        </div>
      ) : (
        <div className="grid kpi-grid">
          {active.map((f) => (
            <div className="card" key={f.conversation_id}>
              <div className="kpi-label">
                <span className="live-dot" style={{ display: "inline-block", marginRight: 6 }} />
                {f.agent_id}
              </div>
              <div className="mono faint" style={{ margin: "6px 0" }}>
                {f.conversation_id}
              </div>
              <div className="stat-row">
                <span className="muted">Elapsed</span>
                <span>{f.elapsed_secs.toFixed(1)}s</span>
              </div>
              <div className="stat-row">
                <span className="muted">Turns</span>
                <span>{f.turn_count}</span>
              </div>
              <div className="stat-row">
                <span className="muted">Interruptions</span>
                <span>{f.interruptions}</span>
              </div>
              <div className="stat-row">
                <span className="muted">Round-trip</span>
                <span>{ms(f.avg_ping_ms)}</span>
              </div>
              <div className="stat-row">
                <span className="muted">VAD</span>
                <span>{f.vad_score !== null ? f.vad_score.toFixed(2) : "—"}</span>
              </div>
              {f.last_message && (
                <p className="faint" style={{ marginBottom: 0 }}>
                  <b>{f.last_role}:</b> {f.last_message}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
