import { render, screen } from "@testing-library/react";
import { Chip } from "./Chip";

describe("Chip", () => {
  it.each(["allowed", "attention", "stopped", "agent", "neutral"] as const)("the %s tone keeps its words", (tone) => {
    render(<Chip tone={tone}>Over budget</Chip>);
    expect(screen.getByText("Over budget")).toHaveClass("chip", tone);
  });

  it("passes data attributes through, so callers can mark the status", () => {
    render(<Chip tone="stopped" data-status="bad">Blocked</Chip>);
    expect(screen.getByText("Blocked")).toHaveAttribute("data-status", "bad");
  });
});
