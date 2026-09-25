import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    new Response(JSON.stringify(url.startsWith("/api/payments") ? { payments: [] } : { run_id: "RUN-01", period_days: null,
      limit_chf: null, approved_chf: "0.00", remaining_chf: null, platform_counter_chf: null, mismatch: false }), { status: 200 })));
});
afterEach(() => vi.unstubAllGlobals());

describe("tab bar", () => {
  it("shows the three app sections, with Home selected", () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "App sections" });
    const tabs = within(nav).getAllByRole("button");
    expect(tabs.map((t) => t.textContent)).toEqual(["Home", "Agent", "Permission"]);
    expect(within(nav).getByRole("button", { name: "Home" })).toHaveAttribute("aria-current", "page");
  });

  it("switches sections by click and by keyboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Permission" }));
    expect(screen.getByRole("button", { name: "Permission" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Home" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("heading", { name: "Permission" })).toBeInTheDocument();
    screen.getByRole("button", { name: "Agent" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Agent" })).toHaveAttribute("aria-current", "page");
  });

  it("renders inside a labelled phone frame", () => {
    render(<App />);
    expect(screen.getByRole("region", { name: "Leash app" })).toBeInTheDocument();
  });
});

describe("Home's Revoke tile (LEASH-198)", () => {
  it("opens the Permission tab with the revoke sheet showing", async () => {
    const user = userEvent.setup();
    const active = { mandate_id: "TM-1", version: 1, status: "active", instruction: "At most CHF 400.", rules: [],
      hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 400, currency: "CHF", scope: "purchase" }],
      uncertainty_policy: "ask", applies_from: "next run", revocation: null };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
      url.startsWith("/api/mandates") ? { mandates: [active], current_mandate_id: "TM-1" }
        : url.startsWith("/api/payments") ? { payments: [] } : { runs: [], current_run_id: null }), { status: 200 })));
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Revoke" }));
    expect(screen.getByRole("button", { name: "Permission" })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("dialog", { name: "Revoke permission?" })).toBeInTheDocument();
  });
});
