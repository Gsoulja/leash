// Chat bubbles, system chip and typing indicator (handoff V4, DEC-044). Speakers differ by alignment and by a
// visually hidden "You:" / "Permission assistant:" label, never by colour alone. Text is React text, never markup.
import type { ReactNode } from "react";
import { Icon } from "../icons";

export function AssistantBubble({ children }: { children: ReactNode }) {
  return <div className="bubble bubble-assistant"><span className="sr-only">Permission assistant: </span><span>{children}</span></div>;
}

export function CustomerBubble({ children }: { children: ReactNode }) {
  return <div className="bubble bubble-customer"><span className="sr-only">You: </span><span>{children}</span></div>;
}

export function SystemChip({ tone, children }: { tone: "allowed" | "stopped"; children: ReactNode }) {
  return (
    <div className={`system-chip ${tone}`}>
      <Icon name={tone === "allowed" ? "check" : "revoke"} />
      <span>{children}</span>
    </div>
  );
}

/** Shown only while the backend is actually working on a reply; never a timer that fakes typing. */
export function TypingIndicator() {
  return (
    <div className="typing" role="img" aria-label="Permission assistant is typing">
      <span /><span /><span />
    </div>
  );
}
