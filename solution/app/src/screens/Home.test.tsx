import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import type { Mandate, Spending } from "../api/client";
import { useSelectedRun } from "../api/useSelectedRun";
import { formatChf } from "../components/ui/LimitTile";
import { DEMO_CARD, Home } from "./Home";

function mandate(extra: Partial<Mandate> = {}): Mandate {
  return {
    mandate_id: "TM-1", version: 1, status: "active", instruction: "Buy the monitor for CHF 400 or less.",
    rules: [], hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 400, currency: "CHF", scope: "purchase" }],
    uncertainty_policy: "ask", applies_from: "next run", revocation: null, ...extra,
  };
}

const SPENDING: Spending = { run_id: "RUN-01", period_days: 7, limit_chf: "300.00", approved_chf: "180.00",
  accepted_chf: "180.00", awaiting_platform_chf: "0.00", remaining_chf: "120.00", platform_counter_chf: "180.00", mismatch: false };

function setup(m: Mandate | null, onNavigate = vi.fn()) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url.startsWith("/api/runs") ? { runs: [{ run_id: "RUN-01", scenario_id: "SCEN0004", mandate_id: "TM-1", mandate_version: 1, status: "running" }], current_run_id: "RUN-01" }
      : url.startsWith("/api/payments") ? { payments: [] }
      : url.startsWith("/api/spending") ? SPENDING
      : { mandates: m ? [m] : [], current_mandate_id: m?.status === "active" ? m.mandate_id : null };
    return new Response(JSON.stringify(body), { status: 200 });
  }));
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Harness = () => <Home selection={useSelectedRun()} onNavigate={onNavigate} />;
  render(<Harness />, { wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  return { onNavigate };
}

afterEach(() => vi.unstubAllGlobals());

describe("Home (LEASH-198)", () => {
  it("greets", () => {
    setup(mandate());
    expect(screen.getByRole("heading", { level: 1, name: "Hello" })).toBeInTheDocument();
  });

  it("offers no Revoke tile without an active permission", async () => {
    setup(null);
    await screen.findByRole("button", { name: /Try your new AI shopping agent/ });
    expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull();
  });



  it("each tile names a real destination", async () => {
    const user = userEvent.setup();
    const { onNavigate } = setup(mandate());
    await screen.findByRole("button", { name: "Revoke" });  // offered once the active permission has loaded
    const tiles = within(screen.getByRole("navigation", { name: "Quick actions" })).getAllByRole("button");
    expect(tiles.map((t) => t.textContent)).toEqual(["Limits", "AI agent", "Payments", "Revoke"]);
    await user.click(screen.getByRole("button", { name: "Limits" }));
    await user.click(screen.getByRole("button", { name: "AI agent" }));
    expect(onNavigate.mock.calls).toEqual([["rules"], ["agent"]]);
    expect(screen.getByRole("button", { name: "AI agent" })).toHaveClass("tile-btn", "dark");
  });

  it("revoke tile opens the revoke sheet and is absent without an active permission", async () => {
    const user = userEvent.setup();
    const { onNavigate } = setup(mandate());
    await user.click(await screen.findByRole("button", { name: "Revoke" }));
    expect(onNavigate).toHaveBeenCalledWith("revoke");
  });



  it("the Payments tile brings the payments into view", async () => {
    const user = userEvent.setup();
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    setup(mandate());
    await user.click(await screen.findByRole("button", { name: "Payments" }));
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(scroll.mock.contexts[0]).toHaveClass("home-payments");
  });
});

describe("Home's credit card and agent banner (LEASH-199, DEC-046)", () => {
  it("home shows the credit card from the demo constant", async () => {
    setup(mandate());
    const card = screen.getByRole("region", { name: "Your credit card" });
    expect(card).toHaveTextContent("Credit card");
    expect(card).toHaveTextContent(`•••• •••• •••• ${DEMO_CARD.last4}`);
    expect(within(card).getByText("Available")).toBeInTheDocument();
    expect(within(card).getByText(`CHF ${formatChf(DEMO_CARD.available)}`)).toBeInTheDocument();
    expect(card).toHaveTextContent(DEMO_CARD.expiry);
  });

  it("the agent banner opens the chat", async () => {
    const user = userEvent.setup();
    const { onNavigate } = setup(null);
    const banner = await screen.findByRole("button", { name: /Try your new AI shopping agent/ });
    expect(banner).toHaveTextContent("Set rules together in a chat");
    await user.click(banner);
    expect(onNavigate).toHaveBeenCalledWith("agent");
  });

  it("the banner is hidden once a permission is active", async () => {
    setup(mandate());
    await screen.findByRole("button", { name: "Revoke" });  // the active permission has loaded
    expect(screen.queryByRole("button", { name: /Try your new AI shopping agent/ })).toBeNull();
  });

  it("home shows no spending card, and still no searching or matches copy", async () => {
    setup(mandate());
    await screen.findByRole("button", { name: "Revoke" });
    await screen.findByRole("region", { name: "Selected run" });
    expect(screen.queryByRole("region", { name: "Spending" })).toBeNull();
    expect(screen.queryByText(/searching|matches/i)).toBeNull();
  });
});

