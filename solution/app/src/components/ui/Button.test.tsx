import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "./Button";

describe("Button", () => {
  it.each(["primary", "secondary", "destructive", "destructive-fill", "approve", "attention"] as const)(
    "the %s variant renders its label as the accessible name", (variant) => {
      render(<Button variant={variant}>Confirm permission</Button>);
      const button = screen.getByRole("button", { name: "Confirm permission" });
      expect(button).toHaveClass("btn", `btn-${variant}`);
      expect(button).toHaveAttribute("type", "button");
    });

  it("a disabled button cannot be pressed", async () => {
    const onClick = vi.fn();
    render(<Button variant="primary" disabled onClick={onClick}>Save</Button>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(onClick).not.toHaveBeenCalled();
  });

  it("marks decision buttons so they get the taller target", () => {
    render(<Button variant="approve" decision>Approve</Button>);
    expect(screen.getByRole("button", { name: "Approve" })).toHaveClass("btn-decision");
  });
});
