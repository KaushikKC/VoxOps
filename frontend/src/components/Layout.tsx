// App shell: sidebar navigation + routed content area.

import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/conversations", label: "Conversations" },
  { to: "/live", label: "Live Monitor" },
  { to: "/search", label: "Search" },
  { to: "/alerts", label: "Alerts" },
  { to: "/audit", label: "Audit Log" },
];

export function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="dot" />
          Voice Agent Obs.
        </div>
        <p className="brand-sub">ElevenLabs reliability layer</p>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
