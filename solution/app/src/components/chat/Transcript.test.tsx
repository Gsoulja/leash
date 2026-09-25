import { render, screen } from "@testing-library/react";
import { Transcript, type ChatMessage } from "./Transcript";

const live = () => document.querySelector("[aria-live=polite]")!;

describe("Transcript", () => {
  const first: ChatMessage[] = [
    { id: "a1", kind: "assistant", text: "What is the most per order?" },
    { id: "c1", kind: "customer", text: "CHF 400" },
  ];

  it("shows the messages in order, each in its own shape", () => {
    render(<Transcript messages={[...first,
      { id: "r1", kind: "rule", label: "Hard stop", value: "CHF 400.00 per order", tone: "stopped" },
      { id: "s1", kind: "system", text: "Permission active", tone: "allowed" }]} />);
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log.textContent).toMatch(/most per order\?.*CHF 400.*HARD STOP.*Permission active/);
  });

  it("does not re-announce history that was already there", () => {
    render(<Transcript messages={first} />);
    expect(live().textContent).toBe("");
  });

  it("transcript announces a new assistant message once", () => {
    const { rerender } = render(<Transcript messages={first} />);
    const next: ChatMessage[] = [...first, { id: "a2", kind: "assistant", text: "Which shops may it use?" }];
    rerender(<Transcript messages={next} />);
    expect(live().textContent).toBe("Which shops may it use?");
    rerender(<Transcript messages={[...next, { id: "c2", kind: "customer", text: "Any" }]} />);
    expect(live().textContent).toBe("Which shops may it use?");  // a customer message is not announced
    rerender(<Transcript messages={[...next, { id: "c2", kind: "customer", text: "Any" }, { id: "a3", kind: "assistant", text: "Noted." }]} />);
    expect(live().textContent).toBe("Noted.");
  });

  it("announces a repeat of the same words as a new message", () => {
    const next: ChatMessage[] = [...first, { id: "a2", kind: "assistant", text: "Anything else?" }];
    const { rerender } = render(<Transcript messages={first} />);
    rerender(<Transcript messages={next} />);
    const before = live().firstElementChild;
    rerender(<Transcript messages={[...next, { id: "a3", kind: "assistant", text: "Anything else?" }]} />);
    expect(live().textContent).toBe("Anything else?");
    expect(live().firstElementChild).not.toBe(before);  // replaced, so assistive tech hears it again
  });

  it("scrolls to the newest message", () => {
    const { rerender } = render(<Transcript messages={first} />);
    const log = screen.getByRole("log");
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 900 });
    rerender(<Transcript messages={[...first, { id: "a2", kind: "assistant", text: "Next?" }]} />);
    expect(log.scrollTop).toBe(900);
  });
});
