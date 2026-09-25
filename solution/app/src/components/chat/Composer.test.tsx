import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("suggested reply calls onReply with its label", async () => {
    const onReply = vi.fn();
    render(<Composer replies={[{ label: "Up to CHF 400" }, { label: "Ask me first", primary: true }]} onReply={onReply} onSend={() => {}} />);
    const reply = screen.getByRole("button", { name: "Ask me first" });
    expect(reply).toHaveClass("reply", "primary");
    await userEvent.setup().click(reply);
    expect(onReply).toHaveBeenCalledWith("Ask me first");
  });

  it("send is disabled when the field is empty", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer replies={[]} onReply={() => {}} onSend={onSend} />);
    const send = screen.getByRole("button", { name: "Send" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "   ");
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "only monitors{Enter}");
    expect(onSend).toHaveBeenCalledWith("only monitors");
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
  });

  it("disables everything while busy", () => {
    render(<Composer replies={[{ label: "Yes" }]} onReply={() => {}} onSend={() => {}} disabled />);
    expect(screen.getByRole("button", { name: "Yes" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
  });

  it("can offer replies without a text field, for a step that takes no free text", () => {
    render(<Composer replies={[{ label: "Confirm permission", primary: true, icon: "fingerprint" }]} onReply={() => {}} onSend={() => {}} field={false} />);
    expect(screen.queryByRole("textbox")).toBeNull();
    const confirm = screen.getByRole("button", { name: "Confirm permission" });
    expect(confirm.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
