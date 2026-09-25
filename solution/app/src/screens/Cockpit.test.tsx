import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Payment, Run, RunList, Spending } from "../api/client";
import { useSelectedRun } from "../api/useSelectedRun";
import { Cockpit } from "./Cockpit";

// The run selection is owned by App.tsx now (LEASH-097); the tests drive the real hook through this harness.
const CockpitHarness = () => <Cockpit selection={useSelectedRun()} />;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 1;
  static CLOSED = 2;
  closed = false;
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown) {
    for (const fn of this.listeners[type] ?? []) fn(new MessageEvent(type, { data: JSON.stringify({ id: "9", type, at: "", data }) }));
  }
}

function payment(id: string, final_state: Payment["final_state"], extra: Partial<Payment> = {}): Payment {
  return {
    authorization_id: id, run_id: "RUN-01", merchant: { merchant_id: "ME0001", name: `Shop ${id}`, category: "groceries", country: "CH" },
    sim_time: "2026-08-12T09:40:00Z", amount: "20.00", currency: "CHF", billing_amount_chf: "20.00",
    items: [{ item_id: "IT1", name: "Fresh produce", quantity: 1, unit_price: "20.00" }],
    // `not_sent` here is the platform refusing the purchase before it ever reached the engine: no
    // verdict, and nothing was ever delivered. A decision the platform refused is a different shape
    // (verdict + delivery "refused"), covered in status.test.ts.
    engine_verdict: final_state === "not_sent" ? null : final_state === "waiting" ? "step_up" : "approve",
    final_state,
    delivery: final_state === "not_sent" ? "pending" : "accepted",
    platform_outcome: final_state === "not_sent" ? null : "accepted",
    resolved_by: final_state === "waiting" ? null : "engine",
    customer_message: "", ...extra,
  };
}

const SPENDING: Spending = { run_id: "RUN-01", period_days: 7, limit_chf: "300.00", approved_chf: "180.00",
  accepted_chf: "180.00", awaiting_platform_chf: "0.00", remaining_chf: "120.00",
  platform_counter_chf: "180.00", mismatch: false };

function run(id: string, status: Run["status"] = "running", scenario = "SCEN0001"): Run {
  return { run_id: id, scenario_id: scenario, mandate_id: "TM-1", mandate_version: 1, status };
}

const ONE_RUN: RunList = { runs: [run("RUN-01")], current_run_id: "RUN-01" };

function setup(payments: Payment[][], spending: Spending[] = [SPENDING], runs: RunList[] = [ONE_RUN]) {
  let p = 0, s = 0, r = 0;
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    const body = url.startsWith("/api/runs") ? runs[Math.min(r++, runs.length - 1)]
      : url.startsWith("/api/payments") ? { payments: payments[Math.min(p++, payments.length - 1)] }
      : spending[Math.min(s++, spending.length - 1)];
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  vi.stubGlobal("EventSource", FakeEventSource);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  render(<CockpitHarness />, { wrapper });
  return { calls, source: () => FakeEventSource.instances.at(-1)! };
}

beforeEach(() => {
  FakeEventSource.instances = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("Cockpit", () => {
  it("waiting payment shows 'Waiting for you'", async () => {
    setup([[payment("B", "waiting")]]);
    const row = await screen.findByRole("button", { name: /Shop B/ });
    expect(within(row).getByText("Waiting for you")).toBeInTheDocument();
  });

  it("paid, waiting, blocked, no answer and not sent are distinct", async () => {
    setup([[
      payment("A", "approved"),
      payment("C", "approved", { engine_verdict: "step_up", resolved_by: "customer" }),
      payment("B", "waiting"),
      payment("D", "declined", { engine_verdict: "decline" }),
      payment("E", "declined", { engine_verdict: "step_up", resolved_by: "customer" }),
      payment("F", "timed_out", { engine_verdict: "step_up", resolved_by: "platform" }),
      payment("G", "not_sent", { engine_verdict: null, resolved_by: "platform" }),
    ]]);
    const label = async (id: string) => {
      const row = await screen.findByRole("button", { name: new RegExp(`Shop ${id}`) });
      const chip = row.querySelector("[data-status]")!;
      return [chip.textContent, chip.getAttribute("data-status")];
    };
    expect(await label("A")).toEqual(["Approved", "ok"]);
    expect(await label("C")).toEqual(["Approved · you approved", "ok"]);
    expect(await label("B")).toEqual(["Waiting for you", "warn"]);
    expect(await label("D")).toEqual(["Blocked", "bad"]);
    expect(await label("E")).toEqual(["You declined", "bad"]);
    expect(await label("F")).toEqual(["No answer", "dim"]);
    expect(await label("G")).toEqual(["Not sent", "off"]);  // distinct from "No answer" at a glance
  });

  it("spending bar shows the rolling window and what's left", async () => {
    setup([[payment("A", "approved")]]);
    expect(await screen.findByText("Approved amount · last 7 days")).toBeInTheDocument();
    expect(screen.getByText("CHF 180.00")).toBeInTheDocument();
    expect(screen.getByText("Left in 7 days")).toBeInTheDocument();
    expect(screen.getByText("CHF 120.00")).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Spent of the 7-day limit" });
    expect(bar).toHaveAttribute("aria-valuenow", "60");
  });

  it("without a period limit there is no bar", async () => {
    setup([[payment("A", "approved")]], [{ ...SPENDING, period_days: null, limit_chf: null, remaining_chf: null }]);
    expect(await screen.findByText("Approved across this simulation")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("groups payments by day, newest first", async () => {
    setup([[payment("A", "approved", { sim_time: "2026-08-11T09:00:00Z" }), payment("B", "approved", { sim_time: "2026-08-12T23:30:00Z" })]]);
    await screen.findByRole("button", { name: /Shop B/ });
    const days = screen.getAllByRole("heading", { level: 2 });
    expect(days.filter((d) => d.classList.contains("glabel")).map((d) => d.textContent)).toEqual(["13 Aug 2026", "11 Aug 2026"]);  // 23:30Z is the 13th in Zurich
  });

  it("initial state comes from the read model; the stream only triggers a reload", async () => {
    const { calls, source } = setup([[payment("A", "approved")], [payment("A", "approved"), payment("B", "waiting")]]);
    await screen.findByRole("button", { name: /Shop A/ });
    expect(screen.queryByRole("button", { name: /Shop B/ })).toBeNull();
    act(() => source().emit("payment.decided", { authorization_id: "B", engine_verdict: "step_up", final_state: "waiting",
      billing_amount_chf: "20.00", customer_message: "" }));
    expect(await screen.findByRole("button", { name: /Shop B/ })).toBeInTheDocument();
    expect(calls.filter((u) => u.startsWith("/api/payments")).length).toBe(2);
    expect(calls.filter((u) => u.startsWith("/api/spending")).length).toBe(2);
  });
});


describe("Cockpit review fixes", () => {
  it("does not show a made-up CHF 0.00 while spending is unknown", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.startsWith("/api/runs") ? new Response(JSON.stringify(ONE_RUN), { status: 200 })
        : url.startsWith("/api/payments") ? new Response(JSON.stringify({ payments: [] }), { status: 200 })
        : new Response(JSON.stringify({ error: { code: "down", message: "x" } }), { status: 500 })));
    vi.stubGlobal("EventSource", FakeEventSource);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CockpitHarness /></QueryClientProvider>);
    expect(await screen.findByText("Spending unavailable right now")).toBeInTheDocument();
    expect(screen.queryByText("CHF 0.00")).toBeNull();
  });

  it("the bar turns red only when nothing is left, and announces the amounts", async () => {
    setup([[payment("A", "approved")]], [{ ...SPENDING, approved_chf: "299.60", remaining_chf: "0.40" }]);
    const bar = await screen.findByRole("progressbar");
    expect(bar).not.toHaveClass("full");
    expect(bar).toHaveAttribute("aria-valuetext", "CHF 299.60 of CHF 300.00 spent, CHF 0.40 left");
  });
});


describe("Cockpit per run (LEASH-133)", () => {
  // Two runs whose payments and spending differ; the fake API answers by the run_id in the URL.
  const later = payment("L", "approved", { run_id: "RUN-02" });
  const earlierPaid = payment("E1", "approved", { run_id: "RUN-01" });
  const earlierBlocked = payment("E2", "declined", { run_id: "RUN-01", engine_verdict: "decline" });
  const BY_RUN: Record<string, { payments: Payment[]; spending: Spending }> = {
    "RUN-02": { payments: [later], spending: { ...SPENDING, run_id: "RUN-02", approved_chf: "20.00", remaining_chf: "280.00" } },
    "RUN-01": { payments: [earlierPaid, earlierBlocked], spending: { ...SPENDING, run_id: "RUN-01", approved_chf: "250.00", remaining_chf: "50.00" } },
  };
  const TWO_RUNS: RunList = { runs: [run("RUN-02", "running", "SCEN0004"), run("RUN-01", "finished")], current_run_id: "RUN-02" };

  function byRun(runs: RunList[] = [TWO_RUNS]) {
    let r = 0;
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url);
      if (url.startsWith("/api/runs")) return new Response(JSON.stringify(runs[Math.min(r++, runs.length - 1)]), { status: 200 });
      const id = new URL(url, "http://x").searchParams.get("run_id") ?? "";
      const data = BY_RUN[id];
      if (!data) return new Response(JSON.stringify({ error: { code: "no_run_id", message: url } }), { status: 400 });
      return new Response(JSON.stringify(url.startsWith("/api/payments") ? { payments: data.payments } : data.spending), { status: 200 });
    }));
    vi.stubGlobal("EventSource", FakeEventSource);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CockpitHarness /></QueryClientProvider>);
    return { calls, source: () => FakeEventSource.instances.at(-1)! };
  }

  it("loads the current run and asks for its payments and spending only", async () => {
    const { calls } = byRun();
    expect(await screen.findByRole("button", { name: /Shop L/ })).toBeInTheDocument();
    expect(screen.getByText("CHF 20.00", { selector: ".v" })).toBeInTheDocument();
    expect(calls).toContain("/api/payments?run_id=RUN-02");
    expect(calls).toContain("/api/spending?run_id=RUN-02");
    expect(calls.filter((u) => u === "/api/payments" || u === "/api/spending")).toEqual([]);
  });

  it("an earlier run can be selected, and rows, counts and spending all follow it", async () => {
    byRun();
    await screen.findByRole("button", { name: /Shop L/ });
    act(() => { fireEvent.change(screen.getByLabelText("Run"), { target: { value: "RUN-01" } }); });
    expect(await screen.findByRole("button", { name: /Shop E1/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Shop L/ })).toBeNull();
    expect(await screen.findByText("CHF 250.00", { selector: ".v" })).toBeInTheDocument();
    expect(screen.getByText("CHF 50.00")).toBeInTheDocument();
    expect(screen.getByText("1 approved")).toBeInTheDocument();  // never "paid" (LEASH-130 AC9)
    expect(screen.getByText("1 blocked")).toBeInTheDocument();
  });

  it("stream events refresh the selected run and never switch to a newer one", async () => {
    const newer: RunList = { runs: [run("RUN-03"), ...TWO_RUNS.runs], current_run_id: "RUN-03" };
    const { calls, source } = byRun([TWO_RUNS, newer]);
    await screen.findByRole("button", { name: /Shop L/ });
    act(() => { fireEvent.change(screen.getByLabelText("Run"), { target: { value: "RUN-01" } }); });
    await screen.findByRole("button", { name: /Shop E1/ });
    const before = calls.filter((u) => u === "/api/payments?run_id=RUN-01").length;
    act(() => source().emit("payment.decided", { authorization_id: "X", engine_verdict: "approve", final_state: "approved",
      billing_amount_chf: "1.00", customer_message: "" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(calls.filter((u) => u === "/api/payments?run_id=RUN-01").length).toBeGreaterThan(before);
    expect(screen.getByLabelText("Run")).toHaveValue("RUN-01");
    expect(calls.some((u) => u.includes("RUN-03") && !u.startsWith("/api/runs"))).toBe(false);
  });

  it("the first run shown stays selected when a newer run starts", async () => {
    const newer: RunList = { runs: [run("RUN-03"), ...TWO_RUNS.runs], current_run_id: "RUN-03" };
    const { source } = byRun([TWO_RUNS, newer]);
    await screen.findByRole("button", { name: /Shop L/ });
    act(() => source().emit("payment.decided", { authorization_id: "X", engine_verdict: "approve", final_state: "approved",
      billing_amount_chf: "1.00", customer_message: "" }));
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    expect(screen.getByLabelText("Run")).toHaveValue("RUN-02");
    expect(await screen.findByRole("option", { name: /RUN-03/ })).toBeInTheDocument();
  });

  it("without any run it says so and asks for nothing else", async () => {
    const { calls } = byRun([{ runs: [], current_run_id: null }]);
    expect(await screen.findByText("No runs yet. Start one from your permission.")).toBeInTheDocument();
    expect(calls.filter((u) => !u.startsWith("/api/runs"))).toEqual([]);
  });

  it("a finished run says it is finished", async () => {
    byRun();
    await screen.findByRole("button", { name: /Shop L/ });
    expect(screen.getByText("Running")).toBeInTheDocument();
    act(() => { fireEvent.change(screen.getByLabelText("Run"), { target: { value: "RUN-01" } }); });
    expect(await screen.findByText("Finished: no more payments will arrive in this run.")).toBeInTheDocument();
  });
  it("an empty run and a stopped run each say so", async () => {
    BY_RUN["RUN-09"] = { payments: [], spending: { ...SPENDING, run_id: "RUN-09", approved_chf: "0.00", remaining_chf: "300.00" } };
    byRun([{ runs: [run("RUN-09", "failed")], current_run_id: null }]);
    expect(await screen.findByText("No agent payments in this run yet.")).toBeInTheDocument();
    expect(screen.getByText("Stopped by the platform: no more payments will arrive in this run.")).toBeInTheDocument();
    delete BY_RUN["RUN-09"];
  });

  it("payments that fail to load are an error, never an empty run", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.startsWith("/api/runs") ? new Response(JSON.stringify(ONE_RUN), { status: 200 })
        : url.startsWith("/api/payments") ? new Response(JSON.stringify({ error: { code: "down", message: "x" } }), { status: 500 })
        : new Response(JSON.stringify(SPENDING), { status: 200 })));
    vi.stubGlobal("EventSource", FakeEventSource);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><CockpitHarness /></QueryClientProvider>);
    expect(await screen.findByText("Payments couldn't be loaded right now.")).toBeInTheDocument();
    expect(screen.queryByText(/No agent payments/)).toBeNull();
  });
});

it("shows the selected simulation's fixed limit separately from the current permission status", async () => {
  const selected = run("RUN-01", "finished");
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url === "/api/runs" ? { runs: [selected], current_run_id: selected.run_id }
      : url === "/api/mandates/TM-1/versions" ? { mandate_id: "TM-1", versions: [{ version: 1,
        hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 250 }], uncertainty_policy: "ask" }] }
      : url === "/api/mandates/TM-1" ? { mandate_id: "TM-1", version: 2, status: "active",
        hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 100 }] }
      : url === "/api/scenarios" ? { scenarios: [{ scenario_id: "SCEN0001", scenario_name: "Household shopping" }] }
      : url.startsWith("/api/payments") ? { payments: [payment("B", "waiting", { delivery: "pending" })] }
      : { ...SPENDING, period_days: null, limit_chf: null, remaining_chf: null };
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  vi.stubGlobal("EventSource", FakeEventSource);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><CockpitHarness /></QueryClientProvider>);
  expect(await screen.findByText("Permission active")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Simulation finished" })).toBeInTheDocument();
  expect(screen.getByText("CHF 250.00", { exact: false, selector: ".order-boundary" })).toBeInTheDocument();
  expect(screen.queryByText("CHF 100.00", { exact: false })).toBeNull();
  expect(screen.getAllByRole("button", { name: /Shop B/ })).toHaveLength(1);
  expect(within(screen.getByRole("region", { name: "Needs your decision" })).getByRole("button", { name: /Shop B/ })).toBeInTheDocument();
});
