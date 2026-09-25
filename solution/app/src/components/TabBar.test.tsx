import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TabBar } from "./TabBar";

describe("TabBar", () => {
  it("shows the app's three tabs in order, with the current one marked", () => {
    render(<TabBar current="agent" onSelect={() => {}} />);
    const tabs = within(screen.getByRole("navigation", { name: "App sections" })).getAllByRole("button");
    expect(tabs.map((t) => t.textContent)).toEqual(["Home", "Agent", "Permission"]);
    expect(screen.getByRole("button", { name: "Agent" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Home" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "Permission" })).not.toHaveAttribute("aria-current");
  });

  it("selects a tab by its name", async () => {
    const onSelect = vi.fn();
    render(<TabBar current="home" onSelect={onSelect} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Permission" }));
    expect(onSelect).toHaveBeenCalledWith("rules");
  });
});
