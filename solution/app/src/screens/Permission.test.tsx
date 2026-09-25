import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Mandate } from "../api/client";
import { Permission } from "./Permission";

function mandate(extra: Partial<Mandate> = {}): Mandate {
  return {
    mandate_id: "TM-1", version: 1, status: "active",
    instruction: "Buy the 27-inch monitor I chose for CHF 400 or less. Ask me when uncertain.",
    review: { must_follow: [{ text: "At most CHF 400.00 per order, delivery included.", group: "price" as const }],
              may_choose: [], must_ask: [{ text: "Missing evidence.", group: "uncertainty" as const }] },
    rules: [{ text: "At most CHF 400.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "Only the 27-inch computer monitor", source: "customer", decision: null, tightened: false }],
    hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 400, currency: "CHF", scope: "purchase" },
                 { field: "items.item_id", operator: "in", value: ["IT0017"] }],
    uncertainty_policy: "ask", applies_from: "next run", revocation: null, ...extra,
  };
}

type Reply = { status: number; body: unknown };

function stubFetch(replies: Record<string, Reply[]>) {
  replies["GET /api/scenarios"] ??= [{ status: 200, body: { scenarios: [
    { scenario_id: "SCEN0004", scenario_name: "Manipulated shopping", cardholder_instruction: "Test", event_count: 11 },
    { scenario_id: "SCEN0001", scenario_name: "Household groceries", cardholder_instruction: "Test", event_count: 11 },
  ] } }];
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const queue = replies[`${method} ${url}`] ?? [{ status: 404, body: { error: { code: "not_found", message: "no" } } }];
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    return new Response(JSON.stringify(reply.body), { status: reply.status });
  }));
  return calls;
}

function list(m: Mandate | null): Reply {
  return { status: 200, body: { mandates: m ? [m] : [], current_mandate_id: m && m.status === "active" ? m.mandate_id : null } };
}

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

async function settle() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

afterEach(() => vi.unstubAllGlobals());

describe("Permission screen", () => {
  it("limit input rejects a higher value", async () => {
    const calls = stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    const input = await screen.findByLabelText("New limit per order (CHF)");
    fireEvent.change(input, { target: { value: "500" } });
    expect(screen.getByRole("button", { name: "Review lower limit" })).toBeDisabled();
    expect(screen.getByText(/can only go down from CHF 400.00/i)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "400" } });
    expect(screen.getByRole("button", { name: "Review lower limit" })).toBeDisabled();
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("a lower limit is appended through tighten", async () => {
    const tightened = mandate({ version: 2, rules: [...mandate().rules,
      { text: "At most CHF 350.00 per order, delivery included", source: "customer", decision: null, tightened: true }] });
    const calls = stubFetch({ "GET /api/mandates": [list(mandate()), list(tightened)],
                              "POST /api/mandates/TM-1/tighten?preview=true": [{ status: 200, body: tightened }],
                              "POST /api/mandates/TM-1/tighten": [{ status: 200, body: tightened }] });
    render(wrap(<Permission />));
    fireEvent.change(await screen.findByLabelText("New limit per order (CHF)"), { target: { value: "350" } });
    fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
    await screen.findByRole("button", { name: "Confirm permission change" });
    expect(calls.filter((c) => c.url === "/api/mandates/TM-1/tighten")).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Confirm permission change" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/mandates/TM-1/tighten", method: "POST", body: { expected_version: 1, add_hard_rules: [
      { field: "authorization.billing_amount_chf", operator: "<=", value: 350, currency: "CHF", scope: "purchase" }] } });
    await settle();
    expect(await screen.findByText("Version 2")).toBeInTheDocument();
  });

  it("shows original and appended rules and that changes apply to later runs", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ version: 2, rules: [...mandate().rules,
      { text: "At most CHF 350.00 per order, delivery included", source: "customer", decision: null, tightened: true }] }))] });
    render(wrap(<Permission />));
    expect(await screen.findByText("At most CHF 400.00 per order, delivery included")).toBeInTheDocument();
    const added = screen.getByText("At most CHF 350.00 per order, delivery included").closest("li")!;
    expect(added).toHaveTextContent("Added");
    expect(screen.getByText(/apply to runs started after this change/i)).toBeInTheDocument();
  });

  it("decline instead of asking tightens the uncertainty choice, and is gone once it applies", async () => {
    const calls = stubFetch({ "GET /api/mandates": [list(mandate()), list(mandate({ version: 2, uncertainty_policy: "decline" }))],
                              "POST /api/mandates/TM-1/tighten?preview=true": [{ status: 200, body: mandate({ version: 2, uncertainty_policy: "decline" }) }],
                              "POST /api/mandates/TM-1/tighten": [{ status: 200, body: mandate({ version: 2, uncertainty_policy: "decline" }) }] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Review declining when uncertain" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm permission change" }));
    await settle();
    await settle();
    expect(calls).toContainEqual({ url: "/api/mandates/TM-1/tighten", method: "POST", body: { uncertainty_policy: "decline", expected_version: 1 } });
    expect(screen.queryByRole("button", { name: "Review declining when uncertain" })).toBeNull();
  });

  it("revoke needs a second tap and shows the platform's confirmation", async () => {
    const revoked = mandate({ status: "revoked", revocation: { platform_confirmed: true, note: null } });
    const calls = stubFetch({ "GET /api/mandates": [list(mandate()), list(revoked)],
                              "DELETE /api/mandates/TM-1": [{ status: 200, body: revoked }] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke permission" }));
    expect(calls.filter((c) => c.method === "DELETE")).toEqual([]);  // first tap only asks
    fireEvent.click(screen.getByRole("button", { name: "Yes, revoke" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/mandates/TM-1", method: "DELETE", body: undefined });
    await settle();
    expect(await screen.findByText(/Viseca confirmed: the agent can no longer pay/i, { selector: "[role=status]" })).toBeInTheDocument();
  });

  it("a revoke Viseca did not confirm is shown as still active", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())],
                "DELETE /api/mandates/TM-1": [{ status: 502, body: { error: { code: "platform_error", message: "Viseca did not revoke it; it is still active." } } }] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke permission" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, revoke" }));
    await settle();
    expect(screen.getByRole("status")).toHaveTextContent(/still active/i);
    expect(screen.queryByText(/can no longer pay/i)).toBeNull();
  });

  it("shows only platform-confirmed revocations", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ status: "revoked", revocation: { platform_confirmed: false, note: null } }))] });
    render(wrap(<Permission />));
    expect(await screen.findByText(/not confirmed by Viseca yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/can no longer pay/i)).toBeNull();
  });

  it("without a permission it says so", async () => {
    stubFetch({ "GET /api/mandates": [list(null)] });
    render(wrap(<Permission />));
    expect(await screen.findByText(/no permission yet/i)).toBeInTheDocument();
  });

  it("accepts any amount in cents below the limit, and nothing else", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    const input = await screen.findByLabelText("New limit per order (CHF)");
    const button = () => screen.getByRole("button", { name: "Review lower limit" });
    for (const ok of ["19.99", "0.29", "1.1", "399.99", " 350 "]) {
      fireEvent.change(input, { target: { value: ok } });
      expect(button()).toBeEnabled();
    }
    for (const bad of ["0x10", "3.5e2", "350,50", "350.505", "-5", "0", "Infinity", "400.00"]) {
      fireEvent.change(input, { target: { value: bad } });
      expect(button()).toBeDisabled();
    }
  });

  it("a limit in another currency is not taken for the CHF limit", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ hard_rules: [
      { field: "authorization.billing_amount_chf", operator: "<=", value: 300, currency: "EUR", scope: "purchase" }] }))] });
    render(wrap(<Permission />));
    expect(await screen.findByText(/Set a limit per order/i)).toBeInTheDocument();
  });

  it("keeps focus in place through the revoke confirmation", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke permission" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Yes, revoke" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Revoke permission" }));
  });
  it("leaves starting the agent to the conversation (LEASH-147)", async () => {
    const calls = stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    await screen.findByRole("heading", { name: "Must follow" });
    // this screen is for reading, tightening and revoking boundaries — not for launching runs
    expect(screen.queryByRole("button", { name: "Start a run" })).toBeNull();
    expect(screen.queryByLabelText("Scenario")).toBeNull();
    expect(screen.queryByText(/Simulation controls/)).toBeNull();
    expect(calls.filter((c) => c.url === "/api/scenarios")).toEqual([]);  // and it no longer asks for them
  });
});

it("cancelling or editing a preview sends no change; stale confirmation requires a fresh review", async () => {
  const preview = mandate({ version: 2, review: { must_follow: [{ text: "At most CHF 350.00 per order.", group: "price" as const }],
                        may_choose: [], must_ask: [{ text: "Missing evidence.", group: "uncertainty" as const }] } });
  const calls = stubFetch({ "GET /api/mandates": [list(mandate())],
    "POST /api/mandates/TM-1/tighten?preview=true": [{ status: 200, body: preview }],
    "POST /api/mandates/TM-1/tighten": [{ status: 409, body: { error: { code: "stale_version", message: "This permission changed. Review again." } } }] });
  render(wrap(<Permission />));
  const input = await screen.findByLabelText("New limit per order (CHF)");
  fireEvent.change(input, { target: { value: "350" } });
  fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
  fireEvent.click(await screen.findByRole("button", { name: "Cancel change" }));
  expect(calls.filter((c) => c.url === "/api/mandates/TM-1/tighten")).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
  await screen.findByRole("button", { name: "Confirm permission change" });
  fireEvent.change(input, { target: { value: "340" } });
  expect(screen.queryByRole("button", { name: "Confirm permission change" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirm permission change" }));
  await settle();
  expect(screen.getByRole("status")).toHaveTextContent("This permission changed. Review again.");
  expect(screen.queryByRole("button", { name: "Confirm permission change" })).toBeNull();
});

it("refreshes a stale permission before retrying a preview", async () => {
  const calls = stubFetch({ "GET /api/mandates": [list(mandate()), list(mandate({ version: 2 }))],
    "POST /api/mandates/TM-1/tighten?preview=true": [
      { status: 409, body: { error: { code: "stale_version", message: "Review the current version." } } },
      { status: 200, body: mandate({ version: 3 }) },
    ] });
  render(wrap(<Permission />));
  fireEvent.change(await screen.findByLabelText("New limit per order (CHF)"), { target: { value: "350" } });
  fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
  await screen.findByText("Version 2");
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Review lower limit" }));
  await screen.findByRole("button", { name: "Confirm permission change" });
  expect(calls.filter((c) => c.url.endsWith("?preview=true")).map((c) => (c.body as { expected_version: number }).expected_version)).toEqual([1, 2]);
  expect(calls.filter((c) => c.url === "/api/mandates/TM-1/tighten")).toEqual([]);
});
