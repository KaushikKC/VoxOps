// Semantic search across conversation transcripts.
// Driven by the global top-bar search (?q=…); also has its own input.

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { SearchHit } from "../api/types";

export function Search() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") ?? "";
  const [q, setQ] = useState(initial);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runQuery = useCallback(async (query: string) => {
    if (query.trim().length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.search(query, 15);
      setHits(res.hits);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-run whenever the ?q= param changes (e.g. from the top-bar search).
  useEffect(() => {
    const urlQ = params.get("q") ?? "";
    setQ(urlQ);
    if (urlQ.trim().length >= 2) runQuery(urlQ);
  }, [params, runQuery]);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim().length >= 2) setParams({ q: q.trim() });
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Semantic Search</h1>
          <p>Find calls by meaning — e.g. “user angry about a double charge”.</p>
        </div>
      </div>

      <form className="toolbar" onSubmit={onSubmit}>
        <input
          type="search"
          placeholder="Describe what you're looking for…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ flex: 1, minWidth: 280 }}
        />
        <button type="submit">Search</button>
      </form>

      {error && <div className="error">{error}</div>}
      {loading && <div className="spinner">Searching…</div>}

      {hits && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Conversation</th>
                <th>Relevance</th>
                <th>Snippet</th>
              </tr>
            </thead>
            <tbody>
              {hits.map((h) => (
                <tr
                  key={h.conversation_id}
                  className="row-link"
                  onClick={() => navigate(`/conversations/${h.conversation_id}`)}
                >
                  <td className="mono">{h.conversation_id}</td>
                  <td>{(h.score * 100).toFixed(0)}%</td>
                  <td className="muted">{h.snippet}</td>
                </tr>
              ))}
              {hits.length === 0 && (
                <tr>
                  <td colSpan={3} className="empty">
                    No matches. Try a different query.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
