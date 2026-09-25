// Agent screen (LEASH-092, a conversation since LEASH-190): the customer writes one instruction, sees how the engine
// reads it as a transcript derived from the draft (rules as chips, notes and questions as the assistant's turns,
// DEC-003), answers its open questions, and only then reviews exactly what was posted to Viseca and confirms.
// Nothing is active, and nothing can be paid, before the explicit Confirm. The draft lives in the policy
// service (LEASH-123); this screen keeps only its id, so a tab switch or reload picks it up again.
// Only blocking questions hold the review back; the two optional offers ("any kind of shop", the split
// check) can stay open, as the contract's `blocking` flag says.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type HardRule, type PlatformDraft, type PolicyDraft } from "../api/client";
import { AssistantBubble, SystemChip } from "../components/chat/Bubbles";
import { ChatHeader } from "../components/chat/ChatHeader";
import { MandateBar } from "../components/chat/MandateBar";
import { SummaryCard } from "../components/chat/SummaryCard";
import { Composer } from "../components/chat/Composer";
import { Transcript, type ChatMessage, type QuestionMessage } from "../components/chat/Transcript";
import { Chip } from "../components/ui/Chip";
import { draftToMessages } from "./draftToMessages";
import { perOrderLimitOf } from "./limits";

const KEY = "leash.draft_id";

function remembered(): string | null {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}

function remember(id: string | null) {
  try { if (id) sessionStorage.setItem(KEY, id); else sessionStorage.removeItem(KEY); } catch { /* no storage */ }
}

const reason = (error: unknown) =>
  error instanceof ApiError ? error.message.replace(/^[a-z_]+: /, "") : "That didn't work. Please try again.";

// A hard rule exactly as posted, in one line: field, operator, value and its qualifiers.
export function ruleLine(r: HardRule): string {
  const value = Array.isArray(r.value) ? r.value.join(", ") : String(r.value);
  const scope = r.scope === "period" ? ` over ${r.period_days} days` : r.scope ? ` per ${r.scope}` : "";
  return `${r.field} ${r.operator} ${value}${r.currency ? ` ${r.currency}` : ""}${scope}`;
}

// The assistant never claims to search, shop or pay: it only reads the instruction and asks (DEC-033).
const GREETING: ChatMessage = { id: "greeting", kind: "assistant",
  text: "Tell me what the agent may buy. I'll show you how I read it and ask about anything unclear. Nothing is active until you confirm." };

// An open question as the assistant's turn: its options as suggested replies, free text in its own composer, and
// a refused answer shown right under it (LEASH-190).
function OpenQuestion({ q, busy, onAnswer }: { q: QuestionMessage; busy: boolean;
                                               onAnswer: (answer: string) => Promise<string | null> }) {
  const [refused, setRefused] = useState<string | null>(null);
  const send = async (answer: string) => {
    setRefused(await onAnswer(answer));
  };
  const id = `q-${q.questionId}`;
  return (
    <div role="group" aria-labelledby={id} className="question-turn">
      <AssistantBubble><span id={id}>{q.text}</span></AssistantBubble>
      <Chip tone={q.blocking ? "attention" : "neutral"}>{q.blocking ? "Needed" : "Optional"}</Chip>
      <Composer replies={(q.options ?? []).map((label) => ({ label }))} onReply={send} onSend={send} disabled={busy}
                fieldLabel="Your answer" sendLabel="Send" placeholder="Or type your answer…" />
      {refused && <p role="alert" className="bubble bubble-assistant refused">{refused}</p>}
    </div>
  );
}

export function Agent() {
  const client = useQueryClient();
  const [draftId, setDraftId] = useState<string | null>(remembered);
  const [posted, setPosted] = useState<PlatformDraft | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<number | null>(null);  // the active version, once confirmed
  const [busy, setBusy] = useState(false);
  const query = useQuery({ queryKey: ["draft", draftId], enabled: draftId !== null, staleTime: Infinity,
                           queryFn: () => api().draft(draftId!) });  // it changes only through this screen

  const show = (d: PolicyDraft) => client.setQueryData(["draft", d.draft_id], d);

  async function act<T>(action: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setMessage(null);
    try {
      return await action();
    } catch (error) {
      setMessage(reason(error));
      return null;
    } finally {
      setBusy(false);
    }
  }

  function startOver() {
    remember(null);
    setDraftId(null);
    setPosted(null);
    setConfirmed(null);
    setMessage(null);
  }

  if (draftId === null) {
    return (
      <div className="perm chat">
        <ChatHeader status="none" />
        <Transcript messages={[GREETING]} />
        <Composer replies={[]} onReply={() => {}} disabled={busy}
                  fieldLabel="What may the agent buy?" sendLabel="Read my instruction" placeholder="e.g. a 27-inch monitor, at most CHF 400"
                  onSend={async (instruction) => {
                    const d = await act(() => api().createDraft(instruction));
                    if (d) { show(d); remember(d.draft_id); setDraftId(d.draft_id); }
                  }} />
        <div role="status" aria-live="polite" className="small">{message}</div>
      </div>
    );
  }

  if (query.isLoading) return <p className="empty">Loading your draft…</p>;
  if (!query.data) {
    return (
      <div className="perm">
        <p className="empty">Your draft couldn't be loaded.</p>
        <button type="button" className="link" onClick={startOver}>Start a new instruction</button>
      </div>
    );
  }
  const d = query.data;
  const blocking = d.open_questions.filter((q) => q.blocking).length;

  async function answer(questionId: string, text: string): Promise<string | null> {
    setBusy(true);
    setMessage(null);
    try {
      show(await api().answerDraft(d.draft_id, questionId, text));
      return null;
    } catch (error) {
      return reason(error);  // shown under the question it belongs to
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="perm chat">
      <ChatHeader status={confirmed !== null ? "active" : "none"} />
      <MandateBar state={confirmed !== null ? "active" : "draft"} rules={d.rules.map((r) => r.text)} />
      {/* Once posted, open questions are no longer answerable here: they go to Viseca as they are. */}
      <Transcript messages={draftToMessages(d).filter((m) => !posted || m.kind !== "question")}
                  renderQuestion={(q) => <OpenQuestion q={q} busy={busy} onAnswer={(text) => answer(q.questionId, text)} />}>
        {posted && <SummaryCard posted={posted} limit={perOrderLimitOf(posted.hard_rules)} ruleLine={ruleLine} />}
        {confirmed !== null && <SystemChip tone="allowed">Permission active · version {confirmed}</SystemChip>}
      </Transcript>

      {!posted && (
        <div className="consent">
          <Composer replies={[{ label: "Review permission", primary: true, disabled: d.status !== "ready" }]} disabled={busy}
                    onReply={async () => { const p = await act(() => api().submitDraft(d.draft_id)); if (p) setPosted(p); }}
                    onSend={() => {}} field={false} />
          {d.status !== "ready" && (
            <p className="small">First answer the questions marked "Needed" ({blocking} left).</p>
          )}
        </div>
      )}

      {/* Confirm is offered only after the posted draft is shown, and only until it succeeds. */}
      {posted && confirmed === null && (
        <div className="consent replies">
          <Composer replies={[{ label: "Confirm permission", primary: true, icon: "fingerprint" }, { label: "Start over" }]}
                    disabled={busy} onSend={() => {}} field={false}
                    onReply={async (label) => {
                      if (label === "Start over") { startOver(); return; }
                      const m = await act(() => api().confirmDraft(d.draft_id));
                      if (m) {
                        setConfirmed(m.version);
                        setMessage(`Confirmed. Version ${m.version} is active for runs started from now on.`);
                        await client.invalidateQueries({ queryKey: ["mandates"] });
                      }
                    }} />
        </div>
      )}

      <div role="status" aria-live="polite" className="small">{message}</div>
      <button type="button" className="link" disabled={busy} onClick={startOver}>Start a new instruction</button>
    </div>
  );
}
