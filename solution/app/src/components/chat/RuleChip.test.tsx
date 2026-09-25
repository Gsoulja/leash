import { render, screen } from "@testing-library/react";
import { RuleChip } from "./RuleChip";

describe("RuleChip", () => {
  it("rule chip names its field and value in text", () => {
    const { container } = render(<RuleChip label="Hard stop" value="CHF 400.00 per order" tone="stopped" />);
    expect(screen.getByText("ADDED TO PERMISSION · HARD STOP")).toBeInTheDocument();
    expect(screen.getByText("CHF 400.00 per order")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");  // the icon only repeats the words
  });

  it("speaks of permission, never of a mandate or shopping (DEC-044)", () => {
    const { container } = render(<RuleChip label="Shops" value="Only shops you used before" tone="allowed" />);
    expect(container.textContent).not.toMatch(/mandate|shopping/i);
  });

  it("renders shop text as text, never as markup", () => {
    const { container } = render(<RuleChip label="Item" value={'<img src=x onerror="alert(1)">'} tone="neutral" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
  });
});
