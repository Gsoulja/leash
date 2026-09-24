// Browser end-to-end journey (LEASH-125): the built app, served by the engine API, with the worker and the fake
// Viseca platform, in an isolated Compose project (see e2e/stack.ts). `npm run test:e2e`.
import { defineConfig, devices } from "@playwright/test";
import { BASE_URL } from "./e2e/stack";

export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  globalSetup: "./e2e/setup.ts",
  globalTeardown: "./e2e/teardown.ts",
  use: { baseURL: BASE_URL, trace: "retain-on-failure", ...devices["iPhone 13"], browserName: "chromium" },
});
