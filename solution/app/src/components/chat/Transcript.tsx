// The conversation, oldest first. New assistant messages are announced once through a polite live region; history
// present when the transcript mounts is not re-read. The view jumps (never animates) to the newest message.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AssistantBubble, CustomerBubble, SystemChip, TypingIndicator } from "./Bubbles";
import { RuleChip, type RuleTone } from "./RuleChip";

export type ChatMessage =
  | { id: string; kind: "assistant"; text: string }
  | { id: string; kind: "customer"; text: string }
  | { id: string; kind: "rule"; label: string; value: string; tone: RuleTone; decision?: string; group?: string }
  | { id: string; kind: "system"; text: string; tone: "allowed" | "stopped" }
  | { id: string; kind: "question"; questionId: string; text: string; blocking: boolean; options?: string[] };

export type QuestionMessage = Extract<ChatMessage, { kind: "question" }>;
type RuleMessage = Extract<ChatMessage, { kind: "rule" }>;

export function useAutoScroll(count: number) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [count]);
  return ref;
}

function useAnnouncement(messages: ChatMessage[]) {
  const seen = useRef<Set<string> | null>(null);
  const [said, setSaid] = useState<{ id: string; text: string } | null>(null);
  useEffect(() => {
    if (seen.current === null) {  // mount: everything already here is history
      seen.current = new Set(messages.map((m) => m.id));
      return;
    }
    const fresh = messages.filter((m) => !seen.current!.has(m.id));
    for (const m of fresh) seen.current.add(m.id);
    const newest = fresh.filter((m) => m.kind === "assistant" || m.kind === "question").at(-1);  // both are the assistant speaking
    if (newest && (newest.kind === "assistant" || newest.kind === "question")) setSaid({ id: newest.id, text: newest.text });
  }, [messages]);
  return said;
}

// Consecutive rule chips with the same `group` render as one labelled list, so they can be read as a set.
type Block = { key: string; group: string; rules: RuleMessage[] } | { key: string; message: ChatMessage };

function blocks(messages: ChatMessage[]): Block[] {
  const out: Block[] = [];
  for (const m of messages) {
    const last = out.at(-1);
    if (m.kind === "rule" && m.group && last && "group" in last && last.group === m.group) last.rules.push(m);
    else if (m.kind === "rule" && m.group) out.push({ key: m.id, group: m.group, rules: [m] });
    else out.push({ key: m.id, message: m });
  }
  return out;
}

const chip = (m: RuleMessage) => <RuleChip label={m.label} value={m.value} tone={m.tone} decision={m.decision} />;

export function Transcript({ messages, typing = false, renderQuestion, children }: {
  messages: ChatMessage[]; typing?: boolean; children?: ReactNode;  // children: turns that are not messages (e.g. the summary card)
  /** Questions need the screen's answer handlers, so the screen renders them. */
  renderQuestion?: (q: QuestionMessage) => ReactNode;
}) {
  const scroller = useAutoScroll(messages.length + (typing ? 1 : 0));
  const said = useAnnouncement(messages);
  return (
    <>
      <div className="transcript" role="log" aria-label="Conversation" aria-live="off" ref={scroller}>
        {blocks(messages).map((b) => "group" in b ? (
          <ul key={b.key} className="turn rule-list" aria-label={b.group}>
            {b.rules.map((m) => <li key={m.id}>{chip(m)}</li>)}
          </ul>
        ) : (
          <div key={b.key} className={`turn turn-${b.message.kind}`}>
            {b.message.kind === "assistant" && <AssistantBubble>{b.message.text}</AssistantBubble>}
            {b.message.kind === "customer" && <CustomerBubble>{b.message.text}</CustomerBubble>}
            {b.message.kind === "rule" && chip(b.message)}
            {b.message.kind === "system" && <SystemChip tone={b.message.tone}>{b.message.text}</SystemChip>}
            {b.message.kind === "question" && (renderQuestion ? renderQuestion(b.message) : <AssistantBubble>{b.message.text}</AssistantBubble>)}
          </div>
        ))}
        {children}
        {typing && <TypingIndicator />}
      </div>
      {/* keyed by message id: a new node each time, so a repeat of the same words is still announced */}
      <div className="sr-only" aria-live="polite">{said && <p key={said.id}>{said.text}</p>}</div>
    </>
  );
}
