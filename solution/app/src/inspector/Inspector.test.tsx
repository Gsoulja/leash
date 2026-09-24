import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactNode } from "react";
import type { Payment, PaymentDetail as Detail } from "../api/client";
import { Inspector } from "./Inspector";

const MERCHANT = { merchant_id: "ME0022", name: "PixelHarbor", category: "electronics", country: "CH", city: "Zurich" };

function payment(extra: Partial<Payment> = {}): Payment {
  return {
    authorization_id: "AZ-1", run_id: "RUN-01", merchant: MERCHANT, sim_time: "2026-08-12T09:40:00Z",
    amount: "289.00", currency: "CHF", billing_amount_chf: "289.00",
    items: [{ item_id: "IT0017", name: "27-inch monitor", quantity: 1, unit_price: "289.00" }],
    engine_verdict: "step_up", final_state: "approved", delivery: "accepted", platform_outcome: "accepted",
    resolved_by: "customer", customer_message: null,
    ...extra,
  } as Payment;
}

function detail(extra: Partial<Detail> = {}): Detail {
  return {
    ...payment(),
    checks: [
      { key: "price", label: "Price", status: "pass", agreed: "≤ CHF 400.00 per order", actual: "CHF 289.00", detail: "Within limit.", reason_code: null },
      { key: "known", label: "Known shop", status: "fail", agreed: "Paid there before", actual: "Never paid here", detail: "Unfamiliar.", reason_code: "unfamiliar_merchant" },
    ],
    evidence: ["Price: CHF 289.00", "Returns: 30 days"],
    shop_texts: [],
    sent_to_viseca: { authorization_id: "AZ-1", decision: "step_up", reason_codes: ["unfamiliar_merchant"] } as unknown as Detail["sent_to_viseca"],
    engine_version: "leash-0.1.0", reader: { name: "regex", model_unavailable: false },
    ...extra,
  } as Detail;
}

function setup(payments: Payment[], body: Detail | null = detail()) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    calls.push(url);
    if (url.startsWith("/api/payments/")) {
      return body ? new Response(JSON.stringify(body), { status: 200 })
                  : new Response(JSON.stringify({ error: { code: "not_found", message: "no" } }), { status: 404 });
    }
    return new Response(JSON.stringify({ payments }), { status: 200 });
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return { calls, ...render(<Inspector />, { wrapper }) };
}

/** Every `.inspector { display: … }` declaration in source order, with the at-rule enclosing it. */
function inspectorDisplayRules(source: string): { media: string | null; display: string }[] {
  const css = source.replace(/\/\*[\s\S]*?\*\//g, "");  // a comment is not a rule
  const out: { media: string | null; display: string }[] = [];
  const stack: string[] = [];
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf("{", i);
    if (open === -1) break;
    const close = css.indexOf("}", i);
    if (close !== -1 && close < open) {  // leaving a block
      stack.pop();
      i = close + 1;
      continue;
    }
    const selector = css.slice(i, open).trim();
    if (selector.startsWith("@")) {  // an at-rule: remember it and step inside
      stack.push(selector);
      i = open + 1;
      continue;
    }
    const end = css.indexOf("}", open);
    const body = css.slice(open + 1, end === -1 ? undefined : end);
    const display = /(?:^|;)\s*display\s*:\s*([\w-]+)/.exec(body);
    // `.inspector` on its own, not `.inspector h2` or `.inspector .row`
    if (display && selector.split(",").some((part) => part.trim() === ".inspector")) {
      out.push({ media: stack.at(-1) ?? null, display: display[1] });
    }
    i = (end === -1 ? css.length : end) + 1;
  }
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe("Inspector", () => {
  it("selecting a row shows its checks", async () => {
    setup([payment()]);
    await userEvent.click(await screen.findByRole("button", { name: /PixelHarbor/ }));
    const table = await screen.findByRole("table", { name: "Checks" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["Price", "≤ CHF 400.00 per order", "CHF 289.00", "Passed"],
      ["Known shop", "Paid there before", "Never paid here", "Failed"],
    ]);
  });

  it("shows nothing but a prompt until a payment is selected", async () => {
    setup([payment()]);
    expect(await screen.findByText("Select a payment to see its checks.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Checks" })).toBeNull();
  });

  it("selecting a row shows the JSON sent to the API", async () => {
    setup([payment()]);
    await userEvent.click(await screen.findByRole("button", { name: /PixelHarbor/ }));
    const json = await screen.findByText(/"decision": "step_up"/);
    expect(JSON.parse(json.textContent ?? "{}")).toEqual({
      authorization_id: "AZ-1", decision: "step_up", reason_codes: ["unfamiliar_merchant"],
    });
  });

  it("says so when nothing was sent, rather than showing an empty box", async () => {
    setup([payment()], detail({ sent_to_viseca: null }));
    await userEvent.click(await screen.findByRole("button", { name: /PixelHarbor/ }));
    expect(await screen.findByText("Nothing was sent.")).toBeInTheDocument();
  });

  it("lists the engine's own verdict next to the final outcome", async () => {
    setup([payment()]);
    const table = await screen.findByRole("table", { name: "Payments in this run" });
    const [row] = within(table).getAllByRole("row").slice(1);
    expect(within(row).getAllByRole("cell").map((c) => c.textContent))
      .toEqual(["PixelHarbor · CHF 289.00", "ask", "Approved · you approved"]);
  });

  it("names the reader and whether the model was unavailable", async () => {
    setup([payment()], detail({ reader: { name: "laya", model_unavailable: true } }));
    await userEvent.click(await screen.findByRole("button", { name: /PixelHarbor/ }));
    expect(await screen.findByText("laya · model unavailable · leash-0.1.0")).toBeInTheDocument();
  });

  it("never offers a way to change anything", async () => {
    const { container } = setup([payment()]);
    await userEvent.click(await screen.findByRole("button", { name: /PixelHarbor/ }));
    await screen.findByRole("table", { name: "Checks" });
    expect(container.querySelectorAll("input, textarea, select, form")).toHaveLength(0);
  });

  it("is hidden below tablet width", () => {
    // Reading the cascade, not string-matching it: an earlier review showed that a bare `toContain`
    // still passed when the rule was wrapped in `@media print`, and when a later `display:block`
    // overrode it. So every `.inspector{…}` block is collected with the at-rule that encloses it, and
    // the *last* declaration to apply at each width is the one asserted.
    const declarations = inspectorDisplayRules(readFileSync(resolve(__dirname, "../theme.css"), "utf8"));
    const unconditional = declarations.filter((d) => d.media === null);
    expect(unconditional.length, "the panel must have an unconditional display rule").toBeGreaterThan(0);
    expect(unconditional.at(-1)?.display, "the last rule that always applies must hide it").toBe("none");

    const shown = declarations.filter((d) => d.display === "block" || d.display === "flex");
    expect(shown.length, "the panel must be shown by exactly one rule").toBe(1);
    const width = /min-width:\s*(\d+)px/.exec(shown[0].media ?? "");
    expect(width, `shown by "${shown[0].media}", which is not a min-width query`).not.toBeNull();
    expect(Number(width?.[1]), "a phone must never reach it").toBeGreaterThanOrEqual(768);
  });
});
