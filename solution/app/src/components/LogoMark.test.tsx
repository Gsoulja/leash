import { render, screen } from "@testing-library/react";
import { LogoMark } from "./LogoMark";

describe("LogoMark", () => {
  it.each([
    ["none", "Agent permission: none"],
    ["active", "Agent permission: active"],
    ["revoked", "Agent permission: revoked"],
  ] as const)("names the %s status in words", (status, name) => {
    render(<LogoMark status={status} />);
    expect(screen.getByRole("img", { name })).toBeInTheDocument();
  });

  it("never relies on colour alone: every status has its own accessible name", () => {
    const names = (["none", "active", "revoked"] as const).map((status) => {
      const { unmount } = render(<LogoMark status={status} />);
      const name = screen.getByRole("img").getAttribute("aria-label");
      unmount();
      return name;
    });
    expect(new Set(names).size).toBe(3);
  });

  it("lights the dot grey, green or red by status", () => {
    const dot = (status: "none" | "active" | "revoked", onDark = false) => {
      const { container, unmount } = render(<LogoMark status={status} onDark={onDark} />);
      const fill = (container.querySelector("circle") as SVGCircleElement).style.fill;
      unmount();
      return fill;
    };
    expect(dot("none")).toBe("var(--hf-muted)");
    expect(dot("active")).toBe("var(--hf-allowed)");
    expect(dot("active", true)).toBe("var(--hf-on-dark)");
    expect(dot("revoked")).toBe("var(--hf-stopped)");
  });

  it("gives each mark its own mask, so two marks on one screen don't share cut-outs", () => {
    const { container } = render(<><LogoMark status="active" /><LogoMark status="none" /></>);
    const ids = [...container.querySelectorAll("mask")].map((m) => m.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    for (const id of ids) expect(id).toMatch(/^[\w-]+$/);  // safe inside url(#…)
  });
});
