/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development every /api call goes to the contract mock (LEASH-118): `npm run mock` in another terminal.
// Point LEASH_API at the real engine API once it exists.
const api = process.env.LEASH_API ?? "http://localhost:8787";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: api, changeOrigin: true } } },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"], include: ["src/**/*.test.{ts,tsx}"] },
});
