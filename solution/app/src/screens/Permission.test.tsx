import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import type { Mandate } from "../api/client";
import { Permission } from "./Permission";

function mandate(extra: Partial<Mandate> = {}): Mandate {
  return {
    mandate_id: "TM-1", version: 1, status: "active",
    instruction: "Buy the 27-inch monitor I chose for CHF 400 or less. Ask me when uncertain.",
    rules: [{ text: "At most CHF 400.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "Only the 27-inch computer monitor", source: "customer", decision: null, tightened: false }],
    hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 400, currency: "CHF", scope: "purchase" },
                 { field: "items.item_id", operator: "in", value: ["IT0017"] }],
    uncertainty_policy: "ask", applies_from: "next run", revocation: null, ...extra,
  };
}

type Reply = { status: number; body: unknown };

function stubFetch(replies: Record<string, Reply[]>) {
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
    expect(screen.getByRole("button", { name: "Lower the limit" })).toBeDisabled();
    expect(screen.getByText(/can only go down from CHF 400.00/i)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "400" } });
    expect(screen.getByRole("button", { name: "Lower the limit" })).toBeDisabled();
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("a lower limit is appended through tighten", async () => {
    const tightened = mandate({ version: 2, rules: [...mandate().rules,
      { text: "At most CHF 350.00 per order, delivery included", source: "customer", decision: null, tightened: true }] });
    const calls = stubFetch({ "GET /api/mandates": [list(mandate()), list(tightened)],
                              "POST /api/mandates/TM-1/tighten": [{ status: 200, body: tightened }] });
    render(wrap(<Permission />));
    fireEvent.change(await screen.findByLabelText("New limit per order (CHF)"), { target: { value: "350" } });
    fireEvent.click(screen.getByRole("button", { name: "Lower the limit" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/mandates/TM-1/tighten", method: "POST", body: { add_hard_rules: [
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
                              "POST /api/mandates/TM-1/tighten": [{ status: 200, body: mandate({ version: 2, uncertainty_policy: "decline" }) }] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Decline instead of asking me" }));
    await settle();
    await settle();
    expect(calls).toContainEqual({ url: "/api/mandates/TM-1/tighten", method: "POST", body: { uncertainty_policy: "decline" } });
    expect(screen.queryByRole("button", { name: "Decline instead of asking me" })).toBeNull();
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
    const button = () => screen.getByRole("button", { name: "Lower the limit" });
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
  it("starts a run with the active permission and shows the run it started", async () => {  // LEASH-066
    const run = { run_id: "RUN-1", scenario_id: "SCEN0004", mandate_id: "TM-1", mandate_version: 1, status: "running" };
    const calls = stubFetch({ "GET /api/mandates": [list(mandate())],
                              "POST /api/runs": [{ status: 201, body: run }] });
    render(wrap(<Permission />));
    fireEvent.change(await screen.findByLabelText("Scenario"), { target: { value: " SCEN0004 " } });
    fireEvent.click(screen.getByRole("button", { name: "Start a run" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/runs", method: "POST", body: { scenario_id: "SCEN0004", mandate_id: "TM-1" } });
    expect(screen.getByRole("status")).toHaveTextContent("Run RUN-1 started with version 1 of your permission.");
  });

  it("start a run needs a scenario and an active permission", async () => {
    const calls = stubFetch({ "GET /api/mandates": [list(mandate({ status: "revoked", revocation: { platform_confirmed: true, note: null } }))] });
    render(wrap(<Permission />));
    await screen.findByText(/Viseca confirmed/i);
    expect(screen.queryByRole("button", { name: "Start a run" })).toBeNull();
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("a refused run start shows the engine's reason", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())],
                "POST /api/runs": [{ status: 409, body: { error: { code: "mandate_not_active", message: "This permission is not active." } } }] });
    render(wrap(<Permission />));
    const button = await screen.findByRole("button", { name: "Start a run" });
    expect(button).toBeDisabled();  // no scenario typed yet
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "SCEN0004" } });
    fireEvent.click(button);
    await settle();
    expect(screen.getByRole("status")).toHaveTextContent("This permission is not active.");
  });
});

describe("Permission screen as AI agent access (LEASH-187)", () => {
  const PURCHASE = { field: "authorization.billing_amount_chf", operator: "<=", currency: "CHF", scope: "purchase" } as const;

  it("hard stop tile shows the strictest per-purchase limit", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ hard_rules: [{ ...PURCHASE, value: 400 }, { ...PURCHASE, value: 350 }] }))] });
    render(wrap(<Permission />));
    expect(await screen.findByRole("group", { name: "Hard stop at CHF 350.00" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /CHF 400\.00/ })).toBeNull();
  });

  it("no budget tile without a guidance budget", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    await screen.findByRole("group", { name: "Hard stop at CHF 400.00" });
    expect(screen.queryByRole("group", { name: /budget/i })).toBeNull();
    expect(screen.queryByText(/budget/i)).toBeNull();
  });

  it("without a per-purchase limit there is no hard stop tile, and the rules say so", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ hard_rules: [{ field: "items.item_id", operator: "in", value: ["IT0017"] }] }))] });
    render(wrap(<Permission />));
    expect(await screen.findByText("No limit per order")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /Hard stop at/ })).toBeNull();
  });

  it.each([
    [{ status: "active" }, "ACTIVE", "Agent permission: active", "ACTIVE"],
    [{ status: "revoked", revocation: { platform_confirmed: true } }, "REVOKED", "Agent permission: revoked", "REVOKED"],
    [{ status: "revoked", revocation: { platform_confirmed: false } }, "REVOCATION NOT CONFIRMED", "Agent permission: active", null],
    [{ status: "expired" }, "NO ACTIVE PERMISSION", "Agent permission: none", null],
  ] as const)("the status card for %j reads %s", async (extra, overline, logo, badge) => {
    stubFetch({ "GET /api/mandates": [list(mandate(extra as Partial<Mandate>))] });
    render(wrap(<Permission />));
    const card = await screen.findByRole("region", { name: "AI agent access" });
    expect(card).toHaveTextContent(overline);
    expect(screen.getByRole("img", { name: logo })).toBeInTheDocument();
    if (badge) expect(screen.getByText(badge, { selector: ".badge" })).toBeInTheDocument();
    else expect(document.querySelector(".badge")).toBeNull();  // "Revoked" only once Viseca confirmed it (DEC-017)
  });
});

describe("revoke as a bottom sheet (LEASH-188)", () => {
  async function openSheet() {
    stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission />));
    fireEvent.click(await screen.findByRole("button", { name: "Revoke permission" }));
    return screen.getByRole("dialog", { name: "Revoke permission?" });
  }

  it("opens a labelled modal sheet with the consequences", async () => {
    const sheet = await openSheet();
    expect(sheet).toHaveAttribute("aria-modal", "true");
    expect(sheet).toHaveTextContent(/can't pay anything more/i);
    expect(within(sheet).getByRole("button", { name: "Yes, revoke" })).toHaveClass("btn-decision");
    expect(within(sheet).getByRole("button", { name: "Keep it" })).toHaveClass("btn-decision");
  });

  it("revoke sheet is not dismissed by clicking the backdrop", async () => {
    const sheet = await openSheet();
    fireEvent.click(sheet.parentElement!);  // the dim
    expect(screen.getByRole("dialog", { name: "Revoke permission?" })).toBeInTheDocument();
  });

  it("Escape cancels, like Keep it", async () => {
    await openSheet();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Revoke permission" }));
  });

  it("focus returns to Revoke permission after Keep it", async () => {
    await openSheet();
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Revoke permission" }));
  });

  it("keeps Tab inside the sheet", async () => {
    const user = userEvent.setup();
    const sheet = await openSheet();
    for (let i = 0; i < 4; i++) {
      await user.tab();
      expect(sheet.contains(document.activeElement)).toBe(true);
    }
  });
});

describe("opened from Home's Revoke tile (LEASH-198)", () => {
  it("shows the revoke sheet straight away, with Yes, revoke focused", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate())] });
    render(wrap(<Permission startRevoke />));
    const sheet = await screen.findByRole("dialog", { name: "Revoke permission?" });
    expect(within(sheet).getByRole("button", { name: "Yes, revoke" })).toHaveFocus();
  });

  it("never shows the sheet for a permission that is not active", async () => {
    stubFetch({ "GET /api/mandates": [list(mandate({ status: "expired" }))] });
    render(wrap(<Permission startRevoke />));
    await screen.findByRole("region", { name: "AI agent access" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
