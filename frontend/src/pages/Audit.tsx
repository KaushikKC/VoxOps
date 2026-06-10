// Audit log: who viewed, replayed, searched or exported transcripts.

import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge } from "../components/Badge";
import { relativeTime } from "../components/format";

const ACTION_KIND: Record<string, string> = {
  view: "info",
  replay: "info",
  search: "neutral",
  export: "warning",
};

export function Audit() {
  const log = useApi(() => api.audit(), []);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit Log</h1>
          <p>Every access to a PII-bearing transcript is recorded here.</p>
        </div>
      </div>

      {log.error && <div className="error">Failed to load: {log.error}</div>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {(log.data ?? []).map((e) => (
              <tr key={e.id}>
                <td className="faint">{relativeTime(e.created_at)}</td>
                <td>{e.actor}</td>
                <td>
                  <Badge kind={ACTION_KIND[e.action] ?? "neutral"} label={e.action} />
                </td>
                <td>
                  {e.resource_type === "conversation" && e.resource_id ? (
                    <Link className="mono" to={`/conversations/${e.resource_id}`}>
                      {e.resource_id}
                    </Link>
                  ) : (
                    <span className="muted">{e.resource_type}</span>
                  )}
                </td>
                <td className="faint mono">
                  {e.detail ? JSON.stringify(e.detail) : "—"}
                </td>
              </tr>
            ))}
            {log.data && log.data.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No audit entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
