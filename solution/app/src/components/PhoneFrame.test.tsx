import { render, screen } from "@testing-library/react";
import { PhoneFrame } from "./PhoneFrame";

describe("PhoneFrame", () => {
  it("shows the handoff's status bar, hidden from assistive tech", () => {
    const { container } = render(<PhoneFrame><p>content</p></PhoneFrame>);
    const bar = container.querySelector(".sbar")!;
    expect(bar).toHaveAttribute("aria-hidden", "true");
    expect(bar.textContent).toBe("9:41●●● ⌁");
    expect(container.querySelector(".island")).toBeNull();
    expect(screen.getByRole("region", { name: "Leash app" })).toContainElement(screen.getByText("content"));
  });
});
