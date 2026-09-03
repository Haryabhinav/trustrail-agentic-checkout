import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// BACKEND_URL differs between plain local dev (localhost) and docker-compose (service name
// "backend", resolved on the container network) — see docker-compose.yml's frontend env.
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/chat": BACKEND_URL,
      "/audit": BACKEND_URL,
      "/catalog": BACKEND_URL,
      "/.well-known": BACKEND_URL,
      "/demo": BACKEND_URL,
      "/health": BACKEND_URL,
      "/webhooks": BACKEND_URL,
    },
  },
});
