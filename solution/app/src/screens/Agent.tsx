// Agent screen (LEASH-092, rebuilt as a conversation for LEASH-145): the customer talks to Leash's
// permission assistant, sees how it reads each thing they say, answers what is unclear, and only then
// reviews exactly what was posted to Viseca and confirms. Nothing is active, and nothing can be paid,
// before the explicit Confirm. The draft lives in the policy service (LEASH-123); this screen keeps its
// id and the customer's own words, so a tab switch or reload picks the conversation up again.
//
// The transcript is DERIVED, never asserted. Every message rendered is checked against what the service
// actually recorded: a turn shows only once its words are in the stored instruction, and an answer shows
// only once its question has stopped being open. Anything still in flight is labelled as in flight. That
// is what keeps the conversation from claiming work the backend never did.
//
// Only blocking questions hold the review back; the two optional offers ("any kind of shop", the split
// check) can stay open, as the contract's `blocking` flag says.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type HardRule, type PlatformDraft, type PolicyDraft, type Question } from "../api/client";

const KEY = "leash.draft_id";
const TALK = "leash.talk";
const UNSURE = { ask: "ask me", decline: "decline", approve: "approve" } as const;

const GREETING =
  "I'm Leash, your permission assistant. Tell me what the shopping agent may buy with your card — " +
  "I don't search or buy anything myself, I only set the boundaries it has to stay inside.";

/** The order things happened in this tab. What is *true* comes from the draft; this only orders it.
 *  A `said` entry stores the instruction the service returned for that turn — never the words as typed,
 *  because matching typed words against the instruction is guesswork, and guessing is what kept letting
 *  a turn nobody recorded onto the screen. An `answered` entry is shown only while the draft still
 *  reports that answer, because a later turn can drop one. */
type Entry = { kind: "said"; instruction: string } | { kind: "answered"; question_id: string; answer: string };
type Talk = { log: Entry[] };

const EMPTY: Talk = { log: [] };

function remembered(): string | null {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}

function remember(id: string | null) {
  try { if (id) sessionStorage.setItem(KEY, id); else sessionStorage.removeItem(KEY); } catch { /* no storage */ }
}

function recalled(): Talk {
  try {
    const raw = sessionStorage.getItem(TALK);
    const parsed = raw ? JSON.parse(raw) : null;
    // an older tab may hold the previous entry shape; anything unrecognised is simply not a record
    if (parsed && Array.isArray(parsed.log)) {
      return { log: parsed.log.filter((e: Entry) => (e?.kind === "said" && typeof e.instruction === "string")
                                                    || (e?.kind === "answered" && typeof e.answer === "string")) };
    }
  } catch { /* unreadable: the draft still carries the truth, the transcript just starts thinner */ }
  return EMPTY;
}

function keep(talk: Talk) {
  try { sessionStorage.setItem(TALK, JSON.stringify(talk)); } catch { /* no storage */ }
}

const reason = (error: unknown) =>
  error instanceof ApiError ? error.message.replace(/^[a-z_]+: /, "") : "That didn't work. Please try again.";

// A hard rule exactly as posted, in one line: field, operator, value and its qualifiers.
export function ruleLine(r: HardRule): string {
  const value = Array.isArray(r.value) ? r.value.join(", ") : String(r.value);
  const scope = r.scope === "period" ? ` over ${r.period_days} days` : r.scope ? ` per ${r.scope}` : "";
  return `${r.field} ${r.operator} ${value}${r.currency ? ` ${r.currency}` : ""}${scope}`;
}

/** Where a rule came from, in the customer's terms. A default is never dressed up as their instruction. */
export function ruleSource(r: { source?: string | null; decision?: string | null }): string {
  const tag = r.decision ? ` (${r.decision})` : "";
  if (r.source === "customer") return "you asked for this";
  if (r.source === "viseca") return `required by Viseca${tag}`;       // not ours to disagree with
  if (r.source === "assumption") return `my assumption${tag} — say so if I have it wrong`;
  return `my default${tag} — say so if you disagree`;
}

function Bubble({ from, label, children }: { from: "me" | "leash"; label?: string; children: React.ReactNode }) {
  return (
    <div className={`bubble ${from}`}>
      {label && <div className="who">{label}</div>}
      {children}
    </div>
  );
}

function Clarification({ q, busy, onAnswer }: { q: Question; busy: boolean;
                                                onAnswer: (answer: string, option: boolean) => Promise<string | null> }) {
  const [refused, setRefused] = useState<string | null>(null);
  const send = async (answer: string, option = false) => {
    const error = await onAnswer(answer, option);
    setRefused(error);
  };
  const id = `q-${q.question_id}`;
  return (
    <div role="group" aria-labelledby={id} className="bubble leash question">
      <div className="question-heading">
        <div className="who">Leash</div>
        <span className={q.blocking ? "chip warn" : "chip dim"}>{q.blocking ? "Needs your answer" : "Optional"}</span>
      </div>
      <p id={id} className="message">{q.text}</p>
      {q.options && q.options.length > 0 && (
        <div className="options">
          {q.options.map((o) => (
            <button key={o} type="button" className="pill light" disabled={busy} onClick={() => send(o, true)}>{o}</button>
          ))}
        </div>
      )}
      <p className="small">Reply in the message box below.</p>
      {refused && <p role="alert" className="p-blocked">{refused}</p>}
    </div>
  );
}

export function Agent({ onRunStarted, onBack }: { onRunStarted?: (id: string) => void; onBack?: () => void } = {}) {
  const client = useQueryClient();
  const [draftId, setDraftId] = useState<string | null>(remembered);
  const [talk, setTalk] = useState<Talk>(recalled);
  const scenarios = useQuery({ queryKey: ["scenarios"], queryFn: () => api().scenarios(), retry: false });
  const [scenarioId, setScenarioId] = useState("");
  const [editing, setEditing] = useState(false);
  const [mandateId, setMandateId] = useState<string | null>(null);
  const [started, setStarted] = useState<string | null>(null);
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState<string | null>(null);  // the words in flight, shown as in flight
  const [posted, setPosted] = useState<PlatformDraft | null>(null);
  const [reviewed, setReviewed] = useState<number | null>(null);  // the revision the review was built from
  const [message, setMessage] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);  // the confirmation, kept apart from errors
  const [activity, setActivity] = useState<string | null>(null);
  const busy = activity !== null;
  const [history, setHistory] = useState<{ text: string; reply: string }[]>([]);
  const end = useRef<HTMLDivElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (editing) composerInput.current?.focus(); }, [editing]);
  const query = useQuery({ queryKey: ["draft", draftId], enabled: draftId !== null, staleTime: Infinity,
                           queryFn: () => api().draft(draftId!) });  // it changes only through this screen
  const d = query.data;
  const confirmedId = mandateId ?? d?.confirmed_mandate?.mandate_id;
  const runScenario = d?.simulation_scenario ?? scenarioId;

  // jsdom gives us the element but not the method, so the call is optional too.
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [d?.revision, d?.messages?.length, sending, message, activity]);

  const show = (next: PolicyDraft) => client.setQueryData(["draft", next.draft_id], next);

  function record(change: (t: Talk) => Talk) {
    setTalk((t) => { const next = change(t); keep(next); return next; });
  }

  async function act<T>(action: () => Promise<T>, label = "Reading your request…"): Promise<T | null> {
    setActivity(label);
    setMessage(null);
    try {
      return await action();
    } catch (error) {
      setMessage(reason(error));
      return null;
    } finally {
      setActivity(null);
    }
  }

  function startOver() {
    remember(null);
    try { sessionStorage.removeItem(TALK); } catch { /* no storage */ }
    setDraftId(null);
    setTalk(EMPTY);
    setPosted(null);
    setReviewed(null);
    setDone(null);
    setMandateId(null);
    setStarted(null);
    setEditing(false);
    setMessage(null);
    setComposer("");
    setHistory([]);
  }

  async function say(text: string) {
    setSending(text);
    setComposer("");
    const result = await act(() => api().chatTurn(text, draftId ?? undefined, scenarioId || undefined, editing));
    setSending(null);
    if (result?.kind === "history") {
      if (result.draft) show(result.draft);
      else if (result.reply) setHistory((old) => [...old, { text, reply: result.reply! }]);
      return;
    }
    const next = result?.draft;
    if (!next) {
      setComposer(text);  // the words come back, so nothing is lost if it really did not get through
      // but a turn commits in a transaction: a lost reply can follow a write that landed, so ask the
      // service what it holds rather than telling the customer on its behalf.
      if (draftId !== null) await client.refetchQueries({ queryKey: ["draft", draftId] });
      return;
    }
    await client.cancelQueries({ queryKey: ["draft", next.draft_id] });  // no late read may undo this
    record((t) => ({ log: [...t.log, { kind: "said", instruction: next.instruction }] }));
    show(next);
    setEditing(false);
    setPosted(null);
    setReviewed(null);
    if (draftId === null) { remember(next.draft_id); setDraftId(next.draft_id); }
  }

  async function answer(q: Question, text: string, option: boolean): Promise<string | null> {
    setActivity(option ? "Checking your answer…" : "Reading your answer…");
    setMessage(null);
    try {
      const fromModel = !option || q.question_id.startsWith("AQ-");
      const response = fromModel ? await api().chatTurn(text, d!.draft_id) : null;
      const next = fromModel ? response?.draft : await api().answerDraft(d!.draft_id, q.question_id, text);
      if (!next) return "The assistant returned no draft. Please retry.";
      await client.cancelQueries({ queryKey: ["draft", next.draft_id] });  // no late read may undo this
      show(next);
      if (response?.kind === "history") return null;
      record((t) => ({ log: [...t.log, ...(fromModel
        ? [{ kind: "said" as const, instruction: next.instruction }]
        : [{ kind: "answered" as const, question_id: q.question_id, answer: text }])] }));
      return null;
    } catch (error) {
      return reason(error);  // shown under the question it belongs to
    } finally {
      setActivity(null);
    }
  }

  // The transcript: local order, service truth — and the words themselves come from the service.
  //
  // Each `said` entry carries the instruction the service returned for that turn, so the message shown
  // is literally the text the service ADDED: `entry.instruction` minus what was already accounted for.
  // Nothing is matched, so a turn that was never recorded contributes nothing (it added nothing), and a
  // turn that WAS recorded cannot be hidden by one that was not. Words the service holds that this tab
  // never saw a response for — a lost reply, a reload, another tab — are read off the end.
  const unclaimed = [...(d?.answers ?? [])];
  const transcript: { who: "me" | "leash"; text: string; key: string }[] = [];
  let accounted = "";
  for (const [i, entry] of talk.log.entries()) {
    if (!d) break;
    if (entry.kind === "said") {
      if (!d.instruction.startsWith(entry.instruction)) continue;      // superseded, or never recorded
      const text = entry.instruction.slice(accounted.length).trim();
      if (!text) continue;                                             // this turn added nothing
      accounted = entry.instruction;
      transcript.push({ who: "me", text, key: `s${i}` });
    } else {
      const at = unclaimed.findIndex((a) => a.question_id === entry.question_id && a.answer === entry.answer);
      if (at < 0) continue;                                            // dropped or refused: not settled
      const [answer] = unclaimed.splice(at, 1);
      transcript.push({ who: "leash", text: answer.question, key: `q${i}` });
      transcript.push({ who: "me", text: answer.answer, key: `a${i}` });
    }
  }
  const unseen = d ? d.instruction.slice(accounted.length).trim() : "";
  if (unseen) transcript.push({ who: "me", text: unseen, key: "unseen" });
  // Answers the draft reports that this tab never saw given still belong in view.
  for (const [n, a] of unclaimed.entries()) {
    transcript.push({ who: "leash", text: a.question, key: `Q${n}` });
    transcript.push({ who: "me", text: a.answer, key: `A${n}` });
  }
  const asking = (d?.open_questions ?? []).find((q) => q.blocking) ?? (d?.open_questions ?? [])[0];
  const blocking = (d?.open_questions ?? []).filter((q) => q.blocking).length;

  return (
    <div className="perm talk">
      <header className="chat-header">
        {onBack && <button className="chat-back" type="button" aria-label="Back to Cockpit" onClick={onBack}>‹</button>}
        <div className="chat-avatar" aria-hidden="true">L<span className={confirmedId ? "active" : ""} /></div>
        <div className="chat-heading"><h1>Leash</h1><p>{activity ?? (query.isLoading ? "Loading your conversation…" : confirmedId ? "Permission confirmed" : "Let’s set your shopping boundaries")}</p></div>
        {draftId !== null && <details className="chat-menu">
          <summary aria-label="Conversation options">•••</summary>
          <div className="chat-menu-actions">
            {d && !confirmedId && !editing && <button type="button" disabled={busy} onClick={(event) => {
              event.currentTarget.closest("details")?.removeAttribute("open");
              setComposer(d.instruction); setEditing(true); setPosted(null); setReviewed(null);
            }}>Edit task and review again</button>}
            <button type="button" disabled={busy} onClick={startOver}>Start a new conversation</button>
          </div>
        </details>}
      </header>
      <div className={`mandate-bar${confirmedId ? " active" : ""}`}>
        <span aria-hidden="true">◇</span>
        <div><strong>{confirmedId ? "Permission active" : posted ? "Ready for your confirmation" : "Permission draft"}</strong>
          <span>{d ? `${d.rules.length} rules · ${blocking ? `${blocking} clarification${blocking === 1 ? "" : "s"} left` : confirmedId ? "Confirmed by you" : "You review before anything is active"}` : "Nothing is active yet"}</span></div>
        <div className="chat-steps" aria-label={confirmedId ? "Permission confirmed" : posted ? "Review prepared" : "Setting up permission"}>
          <i className={d ? "filled" : ""} /><i className={posted || confirmedId ? "filled" : ""} /><i className={confirmedId ? "filled" : ""} />
        </div>
      </div>
      <div className="chat-messages" role="log" aria-label="Conversation" aria-live="polite" aria-relevant="additions">
      <Bubble from="leash" label="Leash">
        <p className="message">{GREETING}</p>
      </Bubble>

      {draftId === null && scenarios.data?.scenarios && (
        <section className="card" aria-label="Simulation data">
          <label htmlFor="scenario">Simulate a supplied shopping task</label>
          <select id="scenario" className="field" value={scenarioId} onChange={(e) => {
            setScenarioId(e.target.value);
            setComposer(scenarios.data.scenarios.find((s) => s.scenario_id === e.target.value)?.cardholder_instruction ?? "");
          }}>
            <option value="">Choose a task</option>
            {scenarios.data.scenarios.map((s) => <option key={s.scenario_id} value={s.scenario_id}>
              {s.scenario_name} · {s.event_count} checkouts
            </option>)}
          </select>
          <p className="small">Uses the supplied customer, history and checkout data. Review the task below before sending.</p>
        </section>
      )}
      {transcript.map((line) => (
        <Bubble key={line.key} from={line.who} label={line.who === "leash" ? "Leash" : undefined}>
          <p className="message">{line.text}</p>
        </Bubble>
      ))}
      {[...history, ...(d?.messages ?? [])].map((exchange, i) => (
        <div key={`history-${i}`}>
          <Bubble from="me"><p className="message">{exchange.text}</p></Bubble>
          <Bubble from="leash" label="Leash · history checked"><p className="message">{exchange.reply}</p></Bubble>
        </div>
      ))}

      {sending !== null && (
        <Bubble from="me">
          <p className="message">{sending}</p>
          <p className="small" role="status">Sending…</p>
        </Bubble>
      )}

      {query.isLoading && <div className="chat-loading" role="status"><span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>Restoring your saved conversation…</div>}

      {query.isError && (
        <Bubble from="leash" label="Leash">
          <p role="alert" className="p-blocked">I couldn't load your draft, so I can't show you where it
            got to. Nothing becomes active without your confirmation.</p>
          <button type="button" className="link" onClick={startOver}>Start a new conversation</button>
        </Bubble>
      )}

      {d && (
        <Bubble from="leash" label="Leash">
          <p className="message">{confirmedId ? "Your confirmed permission." : "Got it. Here is the draft interpretation. Nothing is active yet."}</p>
          {d.assistant?.history_checked && <p className="small">{d.assistant.history_checked}</p>}
          <div className="sum-row">
            <span className="chip dim">revision {d.revision}</span>
            {d.revision > 1 && <span className="small">replaces revision {d.revision - 1}</span>}
          </div>
          <ul className="rules" aria-label="Rules as I read them">
            {d.rules.map((r) => (
              <li key={r.text}>
                <span className="rule-mark" aria-hidden="true">{r.source === "customer" ? "✓" : "i"}</span>
                <span><span className="rule-label">{r.source === "customer" ? "From your instruction" : "Proposed interpretation"}</span>{r.text}
                  <span className="small src">{ruleSource(r)}</span></span>
              </li>
            ))}
          </ul>
          <details className="chat-details"><summary>How this draft was checked</summary>
          {d.assistant?.model && <p className="small">Model: {d.assistant.model} · {d.assistant.status === "ready" ? "proposal checked" : "clarification needed"}</p>}
          <ul className="notes" aria-label="Notes">
            {d.notes.map((n) => <li key={n} className="small">{n}</li>)}
          </ul>
          </details>
        </Bubble>
      )}

      {d && !posted && !confirmedId && asking && (
        <Clarification key={asking.question_id} q={asking} busy={busy} onAnswer={(text, option) => answer(asking, text, option)} />
      )}

      {message && (
        <Bubble from="leash" label="Leash">
          <p role="alert" className="p-blocked">{message}</p>
          <p className="small">
            {posted
              ? "Nothing is active until you confirm."
              : "Above is what the service has now — say it again if it didn't get through."}
          </p>
        </Bubble>
      )}

      {d && d.status === "ready" && !posted && !confirmedId && (
        <section className="card" aria-label="Review">
          <button type="button" className="pill" disabled={busy || d.status !== "ready"}
                  onClick={async () => {
                    const p = await act(() => api().submitDraft(d.draft_id, d.revision), "Preparing your review…");
                    if (p) { setPosted(p); setReviewed(d.revision); }
                  }}>
            Review permission
          </button>
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
          {posted.review && ([['Must follow', posted.review.must_follow], ['May choose', posted.review.may_choose], ['Must ask', posted.review.must_ask]] as const).map(([label, lines]) => (
            <div key={label}><h2>{label}</h2><ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul></div>
          ))}
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
          {!confirmedId && done === null && (
            <button type="button" className="pill" disabled={busy}
                    onClick={async () => {
                      // the revision reviewed, not whatever the draft is now: a stale tab is refused
                      const m = await act(() => api().confirmDraft(posted.draft_id, reviewed ?? undefined), "Confirming your permission…");
                      if (m) {
                        setMandateId(m.mandate_id);
                        show({ ...d!, confirmed_mandate: m });
                        setDone(`Confirmed. Version ${m.version} is active for runs started from now on.`);
                        await client.invalidateQueries({ queryKey: ["mandates"] });
                      }
                    }}>
              Confirm this permission
            </button>
          )}
        </section>
      )}

      {confirmedId && runScenario && (
        <section className="card" aria-label="Run simulation">
          <p>Permission confirmed. The shopping simulator can now submit the supplied checkouts to Leash.</p>
          <button type="button" className="pill" disabled={busy || started !== null} onClick={async () => {
            const run = await act(() => api().startRun(runScenario, confirmedId), "Starting the local simulation…");
            if (run) {
              setStarted(run.run_id);
              await client.invalidateQueries({ queryKey: ["runs"] });
              onRunStarted?.(run.run_id);
            }
          }}>{started ? `Simulation started: ${started}` : "Start shopping simulation"}</button>
          <p className="small">Leash checks each checkout; the simulated platform records whether it accepts the decision. No real payment is made.</p>
        </section>
      )}
      <div role="status" aria-live="polite" className="small">{done ?? ""}</div>
      {activity && <div className="chat-loading" role="status"><span className="typing-dots" aria-hidden="true"><i /><i /><i /></span><span>{activity}</span></div>}
      <div ref={end} />
      </div>
      {!posted && !confirmedId && (
        <section className="composer" aria-label="Say something">
          <label className="k" htmlFor="composer">
            {editing ? "Correct your task — a fresh review is required" : draftId === null ? "What may the agent buy?" : asking ? "Reply to Leash" : "Anything to add or change?"}
          </label>
          <div className="composer-input"><textarea id="composer" ref={composerInput} className="field" rows={2} placeholder={asking && !editing ? "Your answer or question…" : "Message Leash…"} aria-describedby={asking && !editing ? `q-${asking.question_id}` : undefined} value={composer}
                    onChange={(e) => setComposer(e.target.value)} />
          <button type="button" className="pill" disabled={busy || sending !== null || !composer.trim()}
                  onClick={() => say(composer.trim())} aria-label="Send"><span aria-hidden="true">↑</span></button></div>
        </section>
      )}
    </div>
  );
}
