import { render, screen } from "@testing-library/react";
import { Icon, ICONS, type IconName } from "./icons";

describe("Icon", () => {
  it("covers the icons the redesign uses", () => {
    const needed: IconName[] = ["home", "chat", "shield", "fingerprint", "flag", "chevron", "back", "send", "store", "check", "close"];
    for (const name of needed) expect(ICONS[name], name).toBeDefined();
  });

  it("draws on the handoff grid: 24px, 2px stroke, square caps", () => {
    const { container } = render(<Icon name="home" />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(svg.getAttribute("stroke-width")).toBe("2");
    expect(svg.getAttribute("stroke-linecap")).toBe("square");
    expect(container.querySelector("path")!.getAttribute("d")).toBe("M4 10.5L12 4l8 6.5V20H4z");  // lifted, not redrawn
  });

  it("is decorative unless it is given a label", () => {
    const { container } = render(<Icon name="flag" />);
    expect(container.querySelector("svg")!.getAttribute("aria-hidden")).toBe("true");
    render(<Icon name="flag" label="Flagged by the shop" />);
    expect(screen.getByRole("img", { name: "Flagged by the shop" })).toBeInTheDocument();
  });
});
