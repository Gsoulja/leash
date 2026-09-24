import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Ask, Payment } from "../api/client";
import { StepUp } from "./StepUp";

const NOW = new Date("2026-09-23T10:00:00Z").getTime();

function payment(id: string, extra: Partial<Payment> = {}): Payment {
  return {
    authorization_id: id, run_id: "RUN-01", merchant: { merchant_id: "ME0022", name: `PixelHarbor ${id}`, category: "electronics", country: "CH" },
    sim_time: "2026-08-12T10:05:00Z", amount: "289.00", currency: "CHF", billing_amount_chf: "289.00",
    items: [{ item_id: "IT0017", name: "27-inch computer monitor", quantity: 1, unit_price: "289.00" }],
    engine_verdict: "step_up", final_state: "waiting", resolved_by: null, customer_message: "", ...extra,
  };
}

function ask(id: string, extra: Partial<Ask> = {}): Ask {
  return {
    authorization_id: id, payment: payment(id), reasons: ["Same shop and price as the order at 11:40."],
    passed: ["Price", "Known shop"], expires_at: new Date(NOW + 90_000).toISOString(), can_approve: true,
    cannot_approve_reason: null, ...extra,
  };
}

type Reply = { status: number; body: unknown };

function stubFetch(replies: Record<string, Reply[]>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const queue = replies[`${init?.method ?? "GET"} ${url}`] ?? [{ status: 200, body: {} }];
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    return new Response(JSON.stringify(reply.body), { status: reply.status });
  }));
  return calls;
}

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function settle() {
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
}

async function arm() {  // a newly shown Confirm is enabled only after a moment
  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
}

describe("Step-up prompt", () => {
  it("reject calls resolve with decline", async () => {
    const calls = stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 200, body: payment("AZ-1", { final_state: "declined" }) }] });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/asks/AZ-1/answer", method: "POST", body: { decision: "decline" } });
  });

  it("confirm calls resolve with approve", async () => {
    const calls = stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 200, body: payment("AZ-1", { final_state: "approved" }) }] });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/asks/AZ-1/answer", method: "POST", body: { decision: "approve" } });
  });

  it("opens when an ask arrives and shows amount, shop, why and what passed", () => {
    stubFetch({});
    const { rerender } = render(wrap(<StepUp asks={[]} />));
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(wrap(<StepUp asks={[ask("AZ-1")]} />));
    const dialog = screen.getByRole("dialog", { name: "Payment waiting for your answer" });
    expect(dialog).toHaveTextContent("CHF 289.00");
    expect(dialog).toHaveTextContent("PixelHarbor AZ-1");
    expect(dialog).toHaveTextContent("Same shop and price as the order at 11:40.");
    expect(dialog).toHaveTextContent("Price, Known shop: OK");
  });

  it("counts down from the server's expires_at", async () => {
    stubFetch({});
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    expect(screen.getByText(/Answer within 1:30/)).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(screen.getByText(/Answer within 1:25/)).toBeInTheDocument();
  });

  it("at zero it says so but lets the platform decide, since this device's clock may be off", async () => {
    stubFetch({});
    render(wrap(<StepUp asks={[ask("AZ-1", { expires_at: new Date(NOW + 2_000).toISOString() })]} />));
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    expect(screen.getByText(/time may have run out/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeEnabled();
  });

  it("a device clock running ahead never hides the answers of a live ask", async () => {
    const calls = stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 200, body: payment("AZ-1", { final_state: "approved" }) }] });
    vi.setSystemTime(NOW + 120_000);  // two minutes ahead of the server
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    expect(calls).toContainEqual({ url: "/api/asks/AZ-1/answer", method: "POST", body: { decision: "approve" } });
  });

  it("queues several asks, one at a time, never switching under the customer's finger", async () => {
    stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 200, body: payment("AZ-1", { final_state: "declined" }) }] });
    render(wrap(<StepUp asks={[ask("AZ-1"), ask("AZ-2")]} />));
    expect(screen.getByRole("dialog")).toHaveTextContent("1 of 2");
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-1");
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await settle();
    // the answer is confirmed first; the next payment only appears after OK
    expect(screen.getByRole("dialog")).toHaveTextContent(/not made/i);
    expect(screen.queryByRole("button", { name: "Confirm payment" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-2");
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeDisabled();  // armed after a moment
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeEnabled();
  });

  it("an ask resolved elsewhere while shown is announced, not swapped for the next one", () => {
    stubFetch({});
    const { rerender } = render(wrap(<StepUp asks={[ask("AZ-1"), ask("AZ-2")]} />));
    rerender(wrap(<StepUp asks={[ask("AZ-2")]} />));  // AZ-1 timed out or was answered elsewhere
    expect(screen.getByRole("dialog")).toHaveTextContent(/PixelHarbor AZ-1 is no longer waiting/i);
    expect(screen.queryByRole("button", { name: "Confirm payment" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-2");
  });

  it("an outcome that can't be loaded says so", async () => {
    stubFetch({
      "POST /api/asks/AZ-1/answer": [{ status: 409, body: { error: { code: "not_waiting", message: "expired" } } }],
      "GET /api/payments/AZ-1": [{ status: 500, body: { error: { code: "internal_error", message: "x" } } }],
    });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent(/couldn't load what the platform recorded/i);
  });

  it("Escape means decide later, focus stays inside, and returns when the prompt closes", () => {
    stubFetch({});
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    const buttons = [...dialog.querySelectorAll("button")].filter((b) => !b.disabled);
    buttons[buttons.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(buttons[0]);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it("an answer racing the expiry shows what the platform recorded", async () => {
    stubFetch({
      "POST /api/asks/AZ-1/answer": [{ status: 409, body: { error: { code: "not_waiting", message: "expired" } } }],
      "GET /api/payments/AZ-1": [{ status: 200, body: { ...payment("AZ-1", { final_state: "timed_out" }), checks: [], evidence: [],
        shop_texts: [], sent_to_viseca: null, engine_version: "", reader: { name: "regex", model_unavailable: false } } }],
    });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent(/not made: the time to answer ran out/i);
  });

  it("when a hard rule now fails, only Reject remains, with the reason", () => {
    stubFetch({});
    render(wrap(<StepUp asks={[ask("AZ-1", { can_approve: false, cannot_approve_reason: "Your 7-day limit was reached." })]} />));
    expect(screen.queryByRole("button", { name: "Confirm payment" })).toBeNull();
    expect(screen.getByText("Your 7-day limit was reached.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("a refused approval switches to Reject only", async () => {
    stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 422, body: { error: { code: "cannot_approve", message: "Your 7-day limit was reached while this payment waited." } } }] });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    expect(screen.queryByRole("button", { name: "Confirm payment" })).toBeNull();
    expect(screen.getByText("Your 7-day limit was reached while this payment waited.")).toBeInTheDocument();
  });

  it("decide later hides the ask until the next one arrives", () => {
    stubFetch({});
    const { rerender } = render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    fireEvent.click(screen.getByRole("button", { name: "Decide later" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    rerender(wrap(<StepUp asks={[ask("AZ-1"), ask("AZ-2")]} />));
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-2");
  });

  it("the customer's own answer in flight is never reported as answered elsewhere, and its outcome names it", async () => {
    let release: (r: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => (init?.method === "POST"
      ? new Promise<Response>((r) => { release = r; }) : Promise.resolve(new Response("{}", { status: 200 })))));
    const { rerender } = render(wrap(<StepUp asks={[ask("AZ-1"), ask("AZ-2")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    rerender(wrap(<StepUp asks={[ask("AZ-2")]} />));  // the stream reports AZ-1 resolved before our reply
    expect(screen.getByRole("dialog")).not.toHaveTextContent(/no longer waiting/i);
    await act(async () => { release(new Response(JSON.stringify(payment("AZ-1", { final_state: "approved" })), { status: 200 })); });
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent(/PixelHarbor AZ-1.*The payment was made/);
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-2");
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeDisabled();  // armed afresh
  });

  it("a failed answer names its payment and the next Confirm is armed afresh", async () => {
    stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 503, body: { error: { code: "busy", message: "busy" } } }] });
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await settle();
    expect(screen.getByRole("dialog")).toHaveTextContent(/PixelHarbor AZ-1.*couldn't be sent/);
    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    await settle();
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeDisabled();
  });

  it("deferred asks can be reviewed again", async () => {
    stubFetch({});
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    fireEvent.click(screen.getByRole("button", { name: "Decide later" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /1 payment waiting.*review now/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("PixelHarbor AZ-1");
  });

  it("a newly shown ask can't be answered by a stray key press", async () => {
    stubFetch({});
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    expect(document.activeElement).toBe(screen.getByRole("dialog"));  // focus on the dialog, not a button
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    await arm();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("a Confirm that comes back when a rule passes again is armed afresh", async () => {
    stubFetch({});
    const { rerender } = render(wrap(<StepUp asks={[ask("AZ-1", { can_approve: false, cannot_approve_reason: "Limit." })]} />));
    await arm();
    rerender(wrap(<StepUp asks={[ask("AZ-1")]} />));
    expect(screen.getByRole("button", { name: "Confirm payment" })).toBeDisabled();
  });

  it("an answer that never returns ends in a named notice instead of a stuck prompt", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => (init?.method === "POST"
      ? new Promise<Response>(() => {}) : Promise.resolve(new Response("{}", { status: 200 })))));
    render(wrap(<StepUp asks={[ask("AZ-1")]} />));
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Confirm payment" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(16_000); });
    expect(screen.getByRole("dialog")).toHaveTextContent(/PixelHarbor AZ-1.*couldn't be sent/);
  });
});

describe("Step-up prompt, switching asks", () => {
  // Every amount the prompt showed during `action`, including frames replaced right away: React reuses the
  // text node, so a replaced value shows up as a mutation record's old value.
  function shownAmounts(action: () => void): string[] {
    const observer = new MutationObserver(() => {});
    observer.observe(document.body, { subtree: true, characterData: true, characterDataOldValue: true });
    action();  // fireEvent flushes every render and effect it causes before returning
    const records = observer.takeRecords();
    observer.disconnect();
    const inAmount = (n: Node) => !!n.parentElement?.closest(".p-amt");
    return [...records.filter((r) => inAmount(r.target)).map((r) => r.oldValue ?? ""),
            document.querySelector(".p-amt")?.textContent ?? ""];
  }

  it("never shows an answered payment again, not even for a frame, after its notice is closed", async () => {
    stubFetch({ "POST /api/asks/AZ-1/answer": [{ status: 200, body: payment("AZ-1", { final_state: "declined" }) }] });
    const next = ask("AZ-2", { payment: payment("AZ-2", { billing_amount_chf: "391.50" }) });
    render(wrap(<StepUp asks={[ask("AZ-1"), next]} />));  // AZ-1 stays listed until its resolution arrives
    await arm();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await settle();
    const seen = shownAmounts(() => fireEvent.click(screen.getByRole("button", { name: "OK" })));
    expect(seen.join(" ")).not.toMatch(/289\.00/);
    expect(screen.getByText("CHF 391.50")).toBeInTheDocument();
  });

  it("never shows a deferred payment again, not even for a frame, after Decide later", async () => {
    stubFetch({});
    const deferred = ask("AZ-1", { payment: payment("AZ-1", { billing_amount_chf: "289.00" }) });
    const next = ask("AZ-2", { payment: payment("AZ-2", { billing_amount_chf: "391.50" }) });
    render(wrap(<StepUp asks={[deferred, next]} />));
    await arm();
    const seen = shownAmounts(() => fireEvent.click(screen.getByRole("button", { name: "Decide later" })));
    expect(seen.slice(1).join(" ")).not.toMatch(/289\.00/);  // seen[0] is the frame before the tap
    expect(screen.getByText("CHF 391.50")).toBeInTheDocument();
  });
});
