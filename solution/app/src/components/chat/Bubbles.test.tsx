import { render, screen } from "@testing-library/react";
import { AssistantBubble, CustomerBubble, SystemChip, TypingIndicator } from "./Bubbles";

describe("chat bubbles", () => {
  it("tells customer and assistant apart by more than colour", () => {
    render(<><AssistantBubble>What is the most per order?</AssistantBubble><CustomerBubble>CHF 400</CustomerBubble></>);
    const assistant = screen.getByText("What is the most per order?").closest(".bubble")!;
    const customer = screen.getByText("CHF 400").closest(".bubble")!;
    expect(assistant).toHaveTextContent(/^Permission assistant:/);
    expect(customer).toHaveTextContent(/^You:/);
    expect(assistant).toHaveClass("bubble-assistant");  // left-aligned
    expect(customer).toHaveClass("bubble-customer");    // right-aligned
  });

  it("system chips carry their words and tone", () => {
    render(<SystemChip tone="stopped">Permission revoked</SystemChip>);
    expect(screen.getByText("Permission revoked").closest(".system-chip")).toHaveClass("stopped");
  });

  it("the typing indicator says who is typing", () => {
    render(<TypingIndicator />);
    expect(screen.getByRole("img", { name: "Permission assistant is typing" })).toBeInTheDocument();
  });
});
