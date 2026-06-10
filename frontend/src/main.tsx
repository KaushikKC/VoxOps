import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Alerts } from "./pages/Alerts";
import { Audit } from "./pages/Audit";
import { ConversationDetail } from "./pages/ConversationDetail";
import { Conversations } from "./pages/Conversations";
import { Dashboard } from "./pages/Dashboard";
import { LiveMonitor } from "./pages/LiveMonitor";
import { Search } from "./pages/Search";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: "conversations", element: <Conversations /> },
      { path: "conversations/:id", element: <ConversationDetail /> },
      { path: "live", element: <LiveMonitor /> },
      { path: "search", element: <Search /> },
      { path: "alerts", element: <Alerts /> },
      { path: "audit", element: <Audit /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
