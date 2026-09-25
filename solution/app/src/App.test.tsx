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
  it("shows the three app sections, with Cockpit selected", () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "App sections" });
    const tabs = within(nav).getAllByRole("button");
    expect(tabs.map((t) => t.textContent)).toEqual(["Cockpit", "Agent", "Permission"]);
    expect(within(nav).getByRole("button", { name: "Cockpit" })).toHaveAttribute("aria-current", "page");
  });

  it("switches sections by click and by keyboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Permission" }));
    expect(screen.getByRole("button", { name: "Permission" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Cockpit" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("heading", { name: "Permission" })).toBeInTheDocument();
    screen.getByRole("button", { name: "Agent" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: "Leash" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "App sections" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Engine inspector" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Back to Cockpit" }));
    expect(screen.getByRole("button", { name: "Cockpit" })).toHaveAttribute("aria-current", "page");
  });

  it("renders inside a labelled phone frame", () => {
    render(<App />);
    expect(screen.getByRole("region", { name: "Leash app" })).toBeInTheDocument();
  });

  it("keeps the engine inspector beside the chat on desktop", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Agent" }));
    expect(screen.getByRole("heading", { name: "Leash" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Engine inspector" })).toBeInTheDocument();
  });
});
