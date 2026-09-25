/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development every /api call goes to the contract mock (LEASH-118): `npm run mock` in another terminal.
// Point LEASH_API at the real engine API once it exists.
const api = process.env.LEASH_API ?? "http://localhost:8787";
// The permission assistant is its own process (LEASH-175): it reads the customer's words with the
// model and hands what survives validation to the policy service. Only the chat talks to it.
// Its own process on its own port (`docker compose up assistant`, or `python -m assistant.service`).
// In the compose stack the engine forwards /api/permission itself, so pointing LEASH_API at the engine
// is enough; this entry is for running the assistant on its own during development.
const assistant = process.env.LEASH_ASSISTANT_API ?? "http://localhost:8100";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/permission": { target: assistant, changeOrigin: true },
      "/api": { target: api, changeOrigin: true },
    },
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
