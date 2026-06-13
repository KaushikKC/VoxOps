// App shell: sidebar navigation + a global top bar (with search) + routed content.

import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/conversations", label: "Conversations" },
  { to: "/live", label: "Live Monitor" },
  { to: "/alerts", label: "Alerts" },
  { to: "/audit", label: "Audit Log" },
];

function TopBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  return (
    <header className="topbar">
      <form
        className="topbar-search"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim().length >= 2) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
        }}
      >
        <span className="topbar-search-icon">⌕</span>
        <input
          type="search"
          placeholder="Search transcripts by meaning — e.g. “user angry about a refund”"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </form>
      <div className="topbar-meta">
        <span className="badge info">ElevenLabs · live</span>
      </div>
    </header>
  );
}

export function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="dot" />
          VoxOps
        </div>
        <p className="brand-sub">ElevenLabs agent observability</p>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="content">
        <TopBar />
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
