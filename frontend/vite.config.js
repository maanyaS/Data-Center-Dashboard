import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// /api/* is forwarded to the FastAPI backend on port 8000
export default defineConfig({
  base: "./",   // relative paths, so the build works under /Data-Center-Dashboard/ on GitHub Pages
  plugins: [react(), tailwindcss()],
  worker: { format: "es" },   // MapLibre's worker is an ES module
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
