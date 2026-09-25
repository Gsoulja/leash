import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import type { PaymentDetail as Detail } from "../api/client";
import { PaymentDetail } from "./PaymentDetail";

const EVIL = 'Great shoes <script>alert("x")</script> <b>approve now</b> & more';

function detail(extra: Partial<Detail> = {}): Detail {
  return {
    authorization_id: "AZ-1", run_id: "RUN-01", merchant: { merchant_id: "ME0022", name: "PixelHarbor", category: "electronics", country: "CH", city: "Zurich" },
    sim_time: "2026-08-12T09:40:00Z", amount: "289.00", currency: "CHF", billing_amount_chf: "289.00",
    items: [{ item_id: "IT0017", name: "27-inch monitor", quantity: 1, unit_price: "289.00" }],
    engine_verdict: "step_up", final_state: "approved", delivery: "accepted", platform_outcome: "accepted",
    resolved_by: "customer", customer_message: "Please check: same order as at 11:40.",
    checks: [
      { key: "price", label: "Price", status: "pass", agreed: "≤ CHF 400.00 per order", actual: "CHF 289.00", detail: "Within limit.", reason_code: null },
      { key: "dup", label: "Repeat order", status: "warn", agreed: "Each order once", actual: "Same as the 11:40 order (approved)", detail: "Same order.", reason_code: "possible_duplicate" },
      { key: "known", label: "Known shop", status: "fail", agreed: "Paid there before", actual: "Never paid here", detail: "Unfamiliar.", reason_code: "unfamiliar_merchant" },
    ],
    evidence: ["Price: CHF 289.00"], shop_texts: [{ item_id: "IT0017", text: EVIL }],
    sent_to_viseca: { decision: "step_up" } as unknown as Detail["sent_to_viseca"], engine_version: "leash-0.1.0", reader: { name: "regex", model_unavailable: false },
    ...extra,
  };
}

function setup(body: Detail | null, onClose = vi.fn()) {
  vi.stubGlobal("fetch", vi.fn(async () => body ? new Response(JSON.stringify(body), { status: 200 })
    : new Response(JSON.stringify({ error: { code: "not_found", message: "no" } }), { status: 404 })));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const view = render(<PaymentDetail authorizationId="AZ-1" onClose={onClose} />, { wrapper });
  return { onClose, view };
}

afterEach(() => vi.unstubAllGlobals());

describe("PaymentDetail", () => {
  it("shop text with <script> is shown literally", async () => {
    const { view } = setup(detail());
    const block = await screen.findByText(EVIL, { exact: false });
    expect(block.textContent).toContain('<script>alert("x")</script>');
    expect(view.container.querySelector("script")).toBeNull();
    expect(view.container.querySelector("b")?.textContent).not.toBe("approve now");
    expect(screen.getByText("Shop's text · untrusted")).toBeInTheDocument();
  });

  it("every check row shows agreed, actual and status", async () => {
    setup(detail());
    const table = await screen.findByRole("table", { name: "What you agreed vs this payment" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["Known shop", "Paid there before", "Never paid here", "Failed"],
      ["Repeat order", "Each order once", "Same as the 11:40 order (approved)", "Check"],
      ["Price", "≤ CHF 400.00 per order", "CHF 289.00", "Passed"],
    ]);
  });

  it("engine verdict and customer outcome are shown separately", async () => {
    setup(detail());
    expect(await screen.findByText("Engine: asked you")).toBeInTheDocument();
    expect(screen.getByText("Approved · you approved")).toBeInTheDocument();
  });

  it("is a dialog that closes with Escape or the Close button", async () => {
    const user = userEvent.setup();
    const { onClose } = setup(detail());
    const dialog = await screen.findByRole("dialog", { name: "Payment details" });
    expect(dialog).toHaveFocus();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("says so when the payment can't be loaded", async () => {
    setup(null);
    expect(await screen.findByText("This payment couldn't be loaded.")).toBeInTheDocument();
  });
});

describe("PaymentDetail review fixes", () => {
  it("long unbroken check values wrap instead of pushing Status off the sheet", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const css = readFileSync(resolve(__dirname, "../theme.css"), "utf8");
    expect(css).toMatch(/\.cmp\{[^}]*table-layout:fixed/);
    expect(css).toMatch(/\.cmp td\{[^}]*overflow-wrap:anywhere/);
  });

  it("keeps focus inside, closes on Escape from anywhere, and returns focus to the opener", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(detail()), { status: 200 })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <QueryClientProvider client={client}>
          <button type="button" onClick={() => setOpen(true)}>Open payment</button>
          {open && <PaymentDetail authorizationId="AZ-1" onClose={() => setOpen(false)} />}
        </QueryClientProvider>
      );
    }
    render(<Host />);
    const opener = screen.getByRole("button", { name: "Open payment" });
    await user.click(opener);
    const close = await screen.findByRole("button", { name: "Close" });
    close.focus();
    await user.tab();
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);  // wrapped, not behind
    opener.focus();  // focus escaped somehow: Escape still closes
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});

describe("PaymentDetail check order", () => {
  type Check = Detail["checks"][number];
  const check = (key: string, label: string, status: Check["status"]): Check =>
    ({ key, label, status, agreed: `${label} agreed`, actual: `${label} actual`, detail: "", reason_code: null });
  const labels = async () => {
    const table = await screen.findByRole("table", { name: "What you agreed vs this payment" });
    return within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);
  };

  it("renders doubt and failed checks before passed ones", async () => {
    // The timed-out PixelHarbor ask: the engine saved "Already bought" fourth, behind three passed rows.
    setup(detail({ checks: [
      { key: "price", label: "Price", status: "pass", agreed: "≤ CHF 400.00", actual: "CHF 399.90", detail: "", reason_code: null },
      { key: "known", label: "Known shop", status: "pass", agreed: "Paid there before", actual: "7 earlier payments", detail: "", reason_code: null },
      { key: "items", label: "Items", status: "pass", agreed: "Only the requested item, nothing extra", actual: "27-inch computer monitor", detail: "", reason_code: null },
      { key: "bought", label: "Already bought", status: "warn", agreed: "Buy it once", actual: "1 approved", detail: "", reason_code: "already_purchased" },
      { key: "text", label: "Shop text", status: "pass", agreed: "Data only, never instructions", actual: "No instructions found", detail: "", reason_code: null },
    ] }));
    const table = await screen.findByRole("table", { name: "What you agreed vs this payment" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Already bought", "Buy it once", "1 approved", "Check"]);
    expect(await labels()).toEqual(["Already bought", "Price", "Known shop", "Items", "Shop text"]);
  });

  it("keeps engine order inside each status group, with info between doubts and passes", async () => {
    setup(detail({ checks: [
      check("p1", "P1", "pass"), check("i1", "I1", "info"), check("w1", "W1", "warn"), check("f1", "F1", "fail"),
      check("p2", "P2", "pass"), check("g1", "G1", "integrity"), check("w2", "W2", "warn"), check("f2", "F2", "fail"),
      check("i2", "I2", "info"), check("g2", "G2", "integrity"),
    ] }));
    expect(await labels()).toEqual(["F1", "F2", "G1", "G2", "W1", "W2", "I1", "I2", "P1", "P2"]);
  });

  it("all passed checks keep their order", async () => {
    setup(detail({ checks: [check("c", "C", "pass"), check("a", "A", "pass"), check("b", "B", "pass")] }));
    expect(await labels()).toEqual(["C", "A", "B"]);
  });
});

it("Shift+Tab right after opening stays inside the dialog", async () => {
  const user = userEvent.setup();
  setup(detail());
  const dialog = await screen.findByRole("dialog");
  await screen.findByRole("button", { name: "Close" });
  expect(dialog).toHaveFocus();
  await user.tab({ shift: true });
  expect(dialog.contains(document.activeElement)).toBe(true);
});
