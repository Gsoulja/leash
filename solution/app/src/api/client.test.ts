import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ASSISTANT_PATHS, PATHS, api } from "./client";

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

describe("the permission assistant (LEASH-175)", () => {
  const assistantContract = readFileSync(resolve(__dirname, "../../../contracts/assistant-api.yaml"), "utf8");

  it("only uses paths from its own contract", () => {
    for (const path of Object.values(ASSISTANT_PATHS)) expect(assistantContract).toContain(`\n  ${path}:`);
  });

  it("sends the first words to the assistant, not straight to the policy service", async () => {
    const calls: { url: string; body: unknown }[] = [];
    const fetcher = async (url: string, init?: RequestInit) => {
      calls.push({ url, body: JSON.parse(String(init?.body ?? "null")) });
      return new Response(JSON.stringify({ draft: { draft_id: "LD-1", instruction: "höchstens CHF 50" },
                                           consent_text: ["At most CHF 50.00 per order, delivery included."],
                                           questions: [], status: "needs_answers" }),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const draft = await api(fetcher).createDraft("höchstens CHF 50");
    expect(calls).toEqual([{ url: "/api/permission/drafts", body: { text: "höchstens CHF 50" } }]);
    expect(draft?.draft_id).toBe("LD-1");  // history-only messages need not create a draft
  });

  it("adds a later turn to the same draft through the assistant", async () => {
    const calls: string[] = [];
    const fetcher = async (url: string) => {
      calls.push(url);
      return new Response(JSON.stringify({ draft: { draft_id: "LD-1" }, consent_text: [], questions: [],
                                           status: "ready" }),
                          { status: 200, headers: { "Content-Type": "application/json" } });
    };
    await api(fetcher).addTurn("LD-1", "nur Lieferung");
    expect(calls).toEqual(["/api/permission/drafts/LD-1/turns"]);
  });
});
