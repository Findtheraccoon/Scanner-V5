import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const here = path.dirname(fileURLToPath(import.meta.url));
const BACKEND = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(here, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": {
        target: BACKEND,
        changeOrigin: true,
      },
      "/ws": {
        target: BACKEND.replace(/^http/, "ws"),
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
