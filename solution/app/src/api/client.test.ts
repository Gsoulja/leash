import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { PATHS, api } from "./client";

const contract = readFileSync(resolve(__dirname, "../../../contracts/policy-api.yaml"), "utf8");

describe("API client", () => {
  it("only uses paths from the contract (LEASH-118)", () => {
    for (const path of Object.values(PATHS)) expect(contract).toContain(`\n  ${path}:`);
  });

  it("calls the relative /api base, which the dev server proxies to the contract mock", async () => {
    const calls: string[] = [];
    const fetcher = async (url: string) => {
      calls.push(url);
      return new Response(JSON.stringify({ data: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    await api(fetcher).payments();
    expect(calls).toEqual(["/api/payments"]);
  });

  it("starts a run with a POST of the scenario and the mandate (LEASH-066)", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    const fetcher = async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const run = { run_id: "RUN-1", scenario_id: "SCEN0004", mandate_id: "TM-1", mandate_version: 1, status: "running" };
      return new Response(JSON.stringify(run), { status: 201, headers: { "Content-Type": "application/json" } });
    };
    const run = await api(fetcher).startRun("SCEN0004", "TM-1");
    expect(run.mandate_version).toBe(1);
    expect(calls[0].url).toBe("/api/runs");
    expect(calls[0].init?.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ scenario_id: "SCEN0004", mandate_id: "TM-1" });
  });

  it("reports contract errors with their code", async () => {
    const fetcher = async () =>
      new Response(JSON.stringify({ error: { code: "not_found", message: "no" } }), { status: 404 });
    await expect(api(fetcher).payment("AZ-1")).rejects.toThrow("not_found");
  });
});
