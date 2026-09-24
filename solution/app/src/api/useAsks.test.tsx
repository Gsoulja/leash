import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Ask } from "./client";
import { useAsks } from "./useAsks";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  readyState = 0;
  static CLOSED = 2;
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(fn);
  }
  removeEventListener() {}
  close() {
    this.closed = true;
  }
  emit(type: string, data: unknown, id?: string) {
    const event = new MessageEvent(type, { data: JSON.stringify({ id: id ?? "0", type, at: "2026-09-23T14:00:00Z", data }), lastEventId: id ?? "" });
    for (const fn of this.listeners[type] ?? []) fn(event);
  }
}

function ask(id: string, merchant = "PixelHarbor"): Ask {
  return {
    authorization_id: id,
    payment: {
      authorization_id: id, run_id: "RUN-01", merchant: { merchant_id: "ME0022", name: merchant, category: "electronics", country: "CH" },
      sim_time: "2026-08-12T10:05:00Z", amount: "289.00", currency: "CHF", billing_amount_chf: "289.00", items: [],
      engine_verdict: "step_up", final_state: "waiting", resolved_by: null, customer_message: "Please check",
    },
    reasons: ["Same order as at 11:40."], passed: [], expires_at: "2026-09-23T14:02:00Z", can_approve: true,
    cannot_approve_reason: null,
  };
}

function setup(responses: Ask[][]) {
  const calls: string[] = [];
  let i = 0;
  const fetcher = vi.fn(async (url: string) => {
    calls.push(url);
    const asks = responses[Math.min(i++, responses.length - 1)];
    return new Response(JSON.stringify({ asks }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetcher);
  vi.stubGlobal("EventSource", FakeEventSource);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = renderHook(() => useAsks(), { wrapper });
  return { hook, calls, source: () => FakeEventSource.instances.at(-1)! };
}

beforeEach(() => {
  FakeEventSource.instances = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("useAsks", () => {
  it("loads the open asks, then applies new and resolved asks from the stream", async () => {
    const { hook, source } = setup([[ask("A")]]);
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["A"]));
    expect(source().url).toBe("/api/events");
    act(() => source().emit("ask.created", { authorization_id: "B", merchant_name: "Alpine Basket", billing_amount_chf: "20.00",
      reasons: ["Size not stated"], expires_at: "2026-09-23T14:03:00Z", can_approve: true }, "43"));
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["A", "B"]));
    act(() => source().emit("ask.resolved", { authorization_id: "A", outcome: "declined", resolved_by: "customer" }, "44"));
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["B"]));
  });

  it("does not duplicate an ask replayed on reconnect", async () => {
    const { hook, source } = setup([[ask("A")]]);
    await waitFor(() => expect(hook.result.current.asks).toHaveLength(1));
    act(() => source().emit("ask.created", { authorization_id: "A", merchant_name: "PixelHarbor", billing_amount_chf: "289.00",
      reasons: ["Same order as at 11:40."], expires_at: "2026-09-23T14:02:00Z", can_approve: false }));
    await waitFor(() => expect(hook.result.current.asks[0].can_approve).toBe(false));
    expect(hook.result.current.asks).toHaveLength(1);
  });

  it("reconnects and reloads the open asks after a drop", async () => {
    const { hook, calls, source } = setup([[ask("A")], [ask("C")]]);
    await waitFor(() => expect(hook.result.current.asks).toHaveLength(1));
    expect(hook.result.current.connected).toBe(false);
    act(() => source().onopen?.());
    expect(hook.result.current.connected).toBe(true);
    act(() => source().onerror?.());  // the browser's EventSource reconnects by itself, with Last-Event-ID
    expect(hook.result.current.connected).toBe(false);
    act(() => source().onopen?.());
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["C"]));
    expect(calls.filter((u) => u === "/api/asks").length).toBe(2);  // state reloaded from the read model
  });

  it("closes the stream when unmounted", async () => {
    const { hook, source } = setup([[]]);
    await waitFor(() => expect(hook.result.current.asks).toEqual([]));
    hook.unmount();
    expect(source().closed).toBe(true);
  });
});


function deferredSetup() {
  const pending: ((asks: Ask[]) => void)[] = [];
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => {
    pending.push((asks) => resolve(new Response(JSON.stringify({ asks }), { status: 200 })));
  })));
  vi.stubGlobal("EventSource", FakeEventSource);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const hook = renderHook(() => useAsks(), { wrapper });
  return { hook, pending, source: () => FakeEventSource.instances.at(-1)! };
}

const created = (id: string) => ({ authorization_id: id, merchant_name: "Shop", billing_amount_chf: "10.00",
  reasons: ["r"], expires_at: "2026-09-23T14:03:00Z", can_approve: true });

describe("useAsks ordering (review findings)", () => {
  it("keeps stream events that arrive while /api/asks is still loading", async () => {
    const { hook, pending, source } = deferredSetup();
    await waitFor(() => expect(pending).toHaveLength(1));
    act(() => source().emit("ask.created", created("B")));
    act(() => source().emit("ask.resolved", { authorization_id: "A", outcome: "declined", resolved_by: "customer" }));
    await act(async () => pending[0]([ask("A")]));  // a stale snapshot: A was resolved, B is new
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["B"]));
  });

  it("keeps events that arrive during a reconnect reload", async () => {
    const { hook, pending, source } = deferredSetup();
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => pending[0]([ask("A")]));
    act(() => source().onopen?.());
    act(() => source().onerror?.());
    act(() => source().onopen?.());  // reconnected: reload starts
    await waitFor(() => expect(pending).toHaveLength(2));
    act(() => source().emit("ask.created", created("C")));
    await act(async () => pending[1]([ask("A")]));
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["A", "C"]));
  });

  it("reopens a stream the browser gave up on", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { source } = deferredSetup();
      const first = source();
      act(() => {
        first.readyState = FakeEventSource.CLOSED;  // e.g. a 502 while the engine restarts
        first.onerror?.();
      });
      expect(first.closed).toBe(true);
      await act(async () => vi.advanceTimersByTime(1500));
      expect(FakeEventSource.instances.length).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("ignores events with missing fields", async () => {
    const { hook, pending, source } = deferredSetup();
    await waitFor(() => expect(pending).toHaveLength(1));
    await act(async () => pending[0]([]));
    expect(() => act(() => source().emit("ask.created", { authorization_id: "Z" }))).not.toThrow();
    expect(() => act(() => source().emit("ask.created", {}))).not.toThrow();
    expect(hook.result.current.asks).toEqual([]);
  });
});

describe("useAsks settling (review round 2)", () => {
  it("reloads again once the stream has settled, dropping an ask resolved before the stream's start point", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { hook, pending, source } = deferredSetup();
      await waitFor(() => expect(pending).toHaveLength(1));
      await act(async () => pending[0]([ask("A")]));
      act(() => source().onopen?.());  // A was resolved before the server set its start point: never streamed
      await act(async () => vi.advanceTimersByTime(2100));
      await waitFor(() => expect(pending).toHaveLength(2));
      await act(async () => pending[1]([]));
      await waitFor(() => expect(hook.result.current.asks).toEqual([]));
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("useAsks settling with a slow first load (review round 3)", () => {
  it("the settle reload is a fresh request even while the first load is still running", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { hook, pending, source } = deferredSetup();
      await waitFor(() => expect(pending).toHaveLength(1));
      act(() => source().onopen?.());
      await act(async () => vi.advanceTimersByTime(2100));
      await waitFor(() => expect(pending).toHaveLength(2));  // a new request, not joined to the slow one
      await act(async () => pending[0]([ask("A")]));          // the slow first response, now stale
      await act(async () => pending[1]([]));
      await waitFor(() => expect(hook.result.current.asks).toEqual([]));
    } finally {
      vi.useRealTimers();
    }
  });

});

describe("useAsks details", () => {
  it("fills in an ask that arrived by the stream with its full details from /api/asks", async () => {
    const full: Ask = { ...ask("B"), passed: ["Price", "Known shop"],
                   payment: { ...ask("B").payment, currency: "USD" as const, amount: "450.00", items: [
                     { item_id: "IT0017", name: "27-inch computer monitor", quantity: 1, unit_price: "450.00" }] } };
    const { hook, source } = setup([[], [full]]);
    await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
    act(() => source().emit("ask.created", { authorization_id: "B", merchant_name: "PixelHarbor", billing_amount_chf: "391.50",
      reasons: ["You already bought it."], expires_at: "2026-09-23T14:02:00Z", can_approve: true }));
    await waitFor(() => expect(hook.result.current.asks.map((a) => a.authorization_id)).toEqual(["B"]));
    await waitFor(() => expect(hook.result.current.asks[0].passed).toEqual(["Price", "Known shop"]));
    expect(hook.result.current.asks[0].payment.currency).toBe("USD");
  });
});
