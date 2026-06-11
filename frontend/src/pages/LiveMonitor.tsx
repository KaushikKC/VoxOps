// Live Monitor: subscribes to the relay WebSocket and shows in-flight calls in
// real time (live latency, interruptions, current turn). Supervisors can take
// over a call from the AI, send messages as the agent, and hand control back.

import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { Badge } from "../components/Badge";
import { ms } from "../components/format";
import type { LiveFrame } from "../api/types";

const WS_BASE = import.meta.env.VITE_WS_BASE ?? `ws://${window.location.hostname}:8000`;

type ConnState = "connecting" | "open" | "closed";

function LiveCard({ frame }: { frame: LiveFrame }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const human = frame.control === "human";

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!text.trim()) return;
    await act(() => api.say(frame.conversation_id, text));
    setText("");
  }

  return (
    <div className="card" style={human ? { borderColor: "var(--amber)" } : undefined}>
      <div className="kpi-label" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>
          <span className="live-dot" style={{ display: "inline-block", marginRight: 6 }} />
          {frame.agent_id}
        </span>
        {human ? (
          <Badge kind="warning" label={`HUMAN · ${frame.supervisor ?? "supervisor"}`} />
        ) : (
          <Badge kind="info" label="AI" />
        )}
      </div>
      <div className="mono faint" style={{ margin: "6px 0" }}>
        {frame.conversation_id}
      </div>

      <div className="stat-row">
        <span className="muted">Elapsed</span>
        <span>{frame.elapsed_secs.toFixed(1)}s</span>
      </div>
      <div className="stat-row">
        <span className="muted">Turns</span>
        <span>{frame.turn_count}</span>
      </div>
      <div className="stat-row">
        <span className="muted">Interruptions</span>
        <span>{frame.interruptions}</span>
      </div>
      <div className="stat-row">
        <span className="muted">Round-trip</span>
        <span>{ms(frame.avg_ping_ms)}</span>
      </div>
      <div className="stat-row">
        <span className="muted">VAD</span>
        <span>{frame.vad_score !== null ? frame.vad_score.toFixed(2) : "—"}</span>
      </div>

      {frame.last_message && (
        <p className="faint" style={{ margin: "8px 0" }}>
          <b>{frame.last_role}:</b> {frame.last_message}
        </p>
      )}

      {/* Human-in-the-loop controls */}
      {!human ? (
        <button
          disabled={busy}
          style={{ width: "100%", marginTop: 8 }}
          onClick={() => act(() => api.takeover(frame.conversation_id, "supervisor"))}
        >
          Take over
        </button>
      ) : (
        <div style={{ marginTop: 8 }}>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              type="text"
              placeholder="Speak as the agent…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              style={{ flex: 1 }}
            />
            <button disabled={busy} onClick={send}>
              Send
            </button>
          </div>
          <button
            className="ghost"
            disabled={busy}
            style={{ width: "100%", marginTop: 6 }}
            onClick={() => act(() => api.handback(frame.conversation_id))}
          >
            Hand back to AI
          </button>
        </div>
      )}
    </div>
  );
}

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
          <p>
            In-flight calls streaming through the relay. Take over any call to bridge a human
            agent in real time.
          </p>
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
            <span className="mono"> /relay/ingest/&#123;agent_id&#125;</span>, or run
            <span className="mono"> python scripts/relay_demo.py</span>.
          </div>
        </div>
      ) : (
        <div className="grid kpi-grid">
          {active.map((f) => (
            <LiveCard key={f.conversation_id} frame={f} />
          ))}
        </div>
      )}
    </>
  );
}
