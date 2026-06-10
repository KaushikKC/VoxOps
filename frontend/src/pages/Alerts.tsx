// Alerts: SLO breaches with severity, with resolve action.

import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge } from "../components/Badge";
import { relativeTime } from "../components/format";

export function Alerts() {
  const [showResolved, setShowResolved] = useState(false);
  const alerts = useApi(
    () => api.alerts(showResolved ? {} : { resolved: false }),
    [showResolved],
  );

  async function resolve(id: number) {
    await api.resolveAlert(id);
    alerts.reload();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alerts</h1>
          <p>SLO breaches raised on latency, interruptions and task failure.</p>
        </div>
        <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
          />
          Show resolved
        </label>
      </div>

      {alerts.error && <div className="error">Failed to load: {alerts.error}</div>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Rule</th>
              <th>Message</th>
              <th>When</th>
              <th>Call</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(alerts.data ?? []).map((a) => (
              <tr key={a.id}>
                <td>
                  <Badge kind={a.severity} />
                </td>
                <td className="mono">{a.rule}</td>
                <td className="muted">{a.message}</td>
                <td className="faint">{relativeTime(a.created_at)}</td>
                <td>
                  {a.conversation_id ? (
                    <Link className="mono" to={`/conversations/${a.conversation_id}`}>
                      view
                    </Link>
                  ) : (
                    <span className="faint">fleet</span>
                  )}
                </td>
                <td>
                  {!a.resolved && (
                    <button className="ghost" onClick={() => resolve(a.id)}>
                      Resolve
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {alerts.data && alerts.data.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  No {showResolved ? "" : "open "}alerts. 🎉
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
