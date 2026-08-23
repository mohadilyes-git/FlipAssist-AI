/// <reference types="vitest/config" />
// The front end's dev server. It passes /api/... on to FlipAssist's API and adds
// the API's key on the way: the key comes from the repo's .env, here on this
// Mac, and never reaches the browser or the page's code.
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL("..", import.meta.url)), "");
  const proxy = {
    "/api": {
      target: env.FLIP_API_URL || "http://127.0.0.1:8000",
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
      headers: { "X-API-Key": env.FLIP_API_KEY ?? "" },
    },
  };
  return {
    plugins: [react()],
    server: { host: "127.0.0.1", port: 5173, proxy },
    preview: { host: "127.0.0.1", port: 4173, proxy },
    test: { environment: "jsdom" },
  };
});
