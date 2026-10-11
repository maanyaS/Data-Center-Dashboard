import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// /api/* is forwarded to the FastAPI backend on port 8000
export default defineConfig({
  base: "./",   // relative asset paths, so the build works at any URL path
  plugins: [react(), tailwindcss()],
  worker: { format: "es" },   // MapLibre's worker is an ES module
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
