// The journey's own stack: a separate Compose project with its own database volume and ports, so it never
// touches the local `leash` database or any other container. Against the fake platform only, never the live API.
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const PROJECT = process.env.LEASH_E2E_PROJECT ?? "leash-e2e";
// setup and teardown run `down -v`: never on a project that could be the local stack and its `leash` database
if (!/^leash-e2e[\w-]*$/.test(PROJECT)) throw new Error(`LEASH_E2E_PROJECT must start with "leash-e2e", not "${PROJECT}"`);
const PORT = process.env.LEASH_E2E_API_PORT ?? "18080";
export const BASE_URL = `http://localhost:${PORT}`;
const COMPOSE = resolve(dirname(fileURLToPath(import.meta.url)), "../../docker-compose.yml");

const env = {
  ...process.env,
  LEASH_API_PORT: PORT,
  LEASH_WORKER_HEALTH_PORT: process.env.LEASH_E2E_WORKER_PORT ?? "18081",
  LEASH_FAKE_PORT: process.env.LEASH_E2E_FAKE_PORT ?? "19100",  // 19000 is MinIO's default
  LEASH_DB_PORT: process.env.LEASH_E2E_DB_PORT ?? "55442",
  LEASH_BASE_URL: "http://fake:9000",  // the fake inside this project, whatever the caller's environment says
  TEAM_API_KEY: "fake-team-key",
  LEASH_ASSISTANT_PORT: process.env.LEASH_E2E_ASSISTANT_PORT ?? "18100",
  // The journey proves the plumbing, not the model: a real Apertus call would need a key this run does
  // not have, and would make the test as flaky as a network. `offline` reads with the compiler instead,
  // so what this asserts is that the words reach the policy service and come back as rules — not that
  // any particular sentence was understood (LEASH-175).
  LEASH_ASSISTANT_MODEL: "offline",
};

export function compose(...args: string[]) {
  execFileSync("docker", ["compose", "-p", PROJECT, "-f", COMPOSE, "--profile", "fake", ...args],
               { env, stdio: "inherit" });
}
