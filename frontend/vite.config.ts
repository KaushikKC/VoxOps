import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base is configurable via VITE_API_BASE (defaults to the local backend).
// In dev we also proxy /api and /ws to the backend for a same-origin experience.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
        rewrite: (path) => path.replace(/^\/ws/, ""),
      },
    },
  },
});
