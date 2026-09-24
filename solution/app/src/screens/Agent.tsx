// Agent screen (LEASH-092): the customer writes one instruction, sees how the engine reads it (rules and notes,
// DEC-003), answers its open questions, and only then reviews exactly what was posted to Viseca and confirms.
// Nothing is active, and nothing can be paid, before the explicit Confirm. The draft lives in the policy
// service (LEASH-123); this screen keeps only its id, so a tab switch or reload picks it up again.
// Only blocking questions hold the review back; the two optional offers ("any kind of shop", the split
// check) can stay open, as the contract's `blocking` flag says.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type HardRule, type PlatformDraft, type PolicyDraft, type Question } from "../api/client";

const KEY = "leash.draft_id";
const UNSURE = { ask: "ask me", decline: "decline", approve: "approve" } as const;

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

function OpenQuestion({ q, busy, onAnswer }: { q: Question; busy: boolean;
                                               onAnswer: (answer: string) => Promise<string | null> }) {
  const [text, setText] = useState("");
  const [refused, setRefused] = useState<string | null>(null);
  const send = async (answer: string) => {
    setRefused(await onAnswer(answer));
  };
  const id = `q-${q.question_id}`;
  return (
    <div role="group" aria-labelledby={id} className="card question">
      <div className="sum-row">
        <p id={id} className="message">{q.text}</p>
        <span className={q.blocking ? "chip warn" : "chip dim"}>{q.blocking ? "Needed" : "Optional"}</span>
      </div>
      {q.options && q.options.length > 0 && (
        <div className="options">
          {q.options.map((o) => (
            <button key={o} type="button" className="pill light" disabled={busy} onClick={() => send(o)}>{o}</button>
          ))}
        </div>
      )}
      <label className="small" htmlFor={`${id}-a`}>Your answer</label>
      <input id={`${id}-a`} className="field" value={text} onChange={(e) => setText(e.target.value)} />
      <button type="button" className="pill" disabled={busy || !text.trim()} onClick={() => send(text.trim())}>Send</button>
      {refused && <p role="alert" className="p-blocked">{refused}</p>}
    </div>
  );
}

export function Agent() {
  const client = useQueryClient();
  const [draftId, setDraftId] = useState<string | null>(remembered);
  const [instruction, setInstruction] = useState("");
  const [posted, setPosted] = useState<PlatformDraft | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
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
    setConfirmed(false);
    setMessage(null);
  }

  if (draftId === null) {
    return (
      <div className="perm">
        <section className="card" aria-label="Your instruction">
          <label className="k" htmlFor="instruction">What may the agent buy?</label>
          <textarea id="instruction" className="field" rows={4} value={instruction}
                    onChange={(e) => setInstruction(e.target.value)} />
          <p className="small">I'll show you how I read it and ask about anything unclear. Nothing is active until you confirm.</p>
          <button type="button" className="pill" disabled={busy || !instruction.trim()}
                  onClick={async () => {
                    const d = await act(() => api().createDraft(instruction.trim()));
                    if (d) { show(d); remember(d.draft_id); setDraftId(d.draft_id); }
                  }}>
            Read my instruction
          </button>
        </section>
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

  async function answer(q: Question, text: string): Promise<string | null> {
    setBusy(true);
    setMessage(null);
    try {
      show(await api().answerDraft(d.draft_id, q.question_id, text));
      return null;
    } catch (error) {
      return reason(error);  // shown under the question it belongs to
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="perm">
      <section className="card" aria-label="How I read your instruction">
        <div className="k">Your instruction</div>
        <p className="message">{d.instruction}</p>
        <ul className="rules" aria-label="Rules as I read them">
          {d.rules.map((r) => (
            <li key={r.text}>
              <span>{r.text}</span>
              {r.decision && <span className="chip dim">{r.decision}</span>}
            </li>
          ))}
        </ul>
        <ul className="notes" aria-label="Notes">
          {d.notes.map((n) => <li key={n} className="small">{n}</li>)}
        </ul>
      </section>

      {!posted && d.open_questions.map((q) => (
        <OpenQuestion key={q.question_id} q={q} busy={busy} onAnswer={(text) => answer(q, text)} />
      ))}

      {!posted && (
        <section className="card" aria-label="Review">
          <button type="button" className="pill" disabled={busy || d.status !== "ready"}
                  onClick={async () => { const p = await act(() => api().submitDraft(d.draft_id)); if (p) setPosted(p); }}>
            Review what Viseca will receive
          </button>
          {d.status !== "ready" && (
            <p className="small">First answer the questions marked "Needed" ({blocking} left).</p>
          )}
        </section>
      )}

      {posted && (
        <section className="card" aria-label="What Viseca received" role="region">
          <div className="sum-row">
            <div className="k">What Viseca received</div>
            <span className="chip dim">{posted.platform_draft_id}</span>
          </div>
          <p className="small">This exact draft becomes your permission when you confirm. It isn't active yet.</p>
          <p className="message">{posted.instruction}</p>
          <ul className="rules exact">
            {posted.hard_rules.map((r) => <li key={ruleLine(r)}><code>{ruleLine(r)}</code></li>)}
          </ul>
          <p className="small">When unsure: {UNSURE[posted.uncertainty_policy]}.</p>
          {(posted.open_questions ?? []).length > 0 && (
            <>
              <p className="small">You left these optional questions open; they go to Viseca unanswered:</p>
              <ul className="notes" aria-label="Questions left open (sent as they are)">
                {posted.open_questions!.map((q) => <li key={q} className="small">{q}</li>)}
              </ul>
            </>
          )}
          {posted.guidance.length > 0 && (
            <ul className="notes">{posted.guidance.map((g) => <li key={g} className="small">{g}</li>)}</ul>
          )}
          {!confirmed && (
            <button type="button" className="pill" disabled={busy}
                    onClick={async () => {
                      const m = await act(() => api().confirmDraft(d.draft_id));
                      if (m) {
                        setConfirmed(true);
                        setMessage(`Confirmed. Version ${m.version} is active for runs started from now on.`);
                        await client.invalidateQueries({ queryKey: ["mandates"] });
                      }
                    }}>
              Confirm this permission
            </button>
          )}
        </section>
      )}

      <div role="status" aria-live="polite" className="small">{message}</div>
      <button type="button" className="link" disabled={busy} onClick={startOver}>Start a new instruction</button>
    </div>
  );
}
