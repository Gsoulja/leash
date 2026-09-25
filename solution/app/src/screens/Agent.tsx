import { RunActivity } from "./RunActivity";
// Agent screen (LEASH-092, rebuilt as a conversation for LEASH-145): the customer talks to Wallet Control's
// permission assistant, sees how it reads each thing they say, answers what is unclear, and only then
// reviews exactly what was posted to Viseca and confirms. Nothing is active, and nothing can be paid,
// before the explicit Confirm. The draft lives in the policy service (LEASH-123); this screen keeps its
// id and the customer's own words, so a tab switch or reload picks the conversation up again.
//
// The transcript comes from stored revisions, including superseded ones. Current permission and
// conversation history are separate: editing rules must not erase what the customer already said.
//
// Only blocking questions hold the review back; the two optional offers ("any kind of shop", the split
// check) can stay open, as the contract's `blocking` flag says.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type HardRule, type PlatformDraft, type PolicyDraft, type Question, type Run } from "../api/client";
import { Icon, LogoMark } from "../components/icons";
import { PermissionSummary } from "../components/PermissionSummary";

const KEY = "leash.draft_id";
const TALK = "leash.talk";
const UNSURE = { ask: "ask me", decline: "decline", approve: "approve" } as const;

const GREETING =
  "I'm your Wallet Control, your permission assistant. Tell me what the shopping agent may buy with your card — " +
  "I don't search or buy anything myself, I only set the boundaries it has to stay inside.";

/** The order things happened in this tab. What is *true* comes from the draft; this only orders it.
 *  A `said` entry stores the instruction the service returned for that turn — never the words as typed,
 *  because matching typed words against the instruction is guesswork, and guessing is what kept letting
 *  a turn nobody recorded onto the screen. An `answered` entry is shown only while the draft still
 *  reports that answer, because a later turn can drop one. */
type Entry = { kind: "said"; instruction: string } | { kind: "answered"; question_id: string; answer: string };
type Talk = { log: Entry[]; history?: { text: string; reply: string }[] };

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
                                                    || (e?.kind === "answered" && typeof e.answer === "string")),
        history: Array.isArray(parsed.history) ? parsed.history.filter((e: { text?: unknown; reply?: unknown }) =>
          typeof e?.text === "string" && typeof e.reply === "string") : [] };
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
  if (r.source === "customer") return "you asked for this";
  if (r.source === "viseca") return "required by Viseca";            // not ours to disagree with
  if (r.source === "assumption") return "my assumption — say so if I have it wrong";
  return "my default — say so if you disagree";
}

function Bubble({ from, label, children }: { from: "me" | "leash"; label?: string; children: React.ReactNode }) {
  return (
    <div className={`bubble ${from}`}>
      {label && <div className="who">{label}</div>}
      {children}
    </div>
  );
}

function questionText(text: string): string {
  // Older saved questions contain no proposed value, so ask for the count instead of guessing one.
  return text === "I drafted a rule you didn't say in those words, so it stays an unconfirmed suggestion: leash.purchase.max_count.v2. Do you want it?"
    ? "How many purchases should this permission allow in total? This suggestion is not confirmed yet."
    : text;
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
        <div className="who">Wallet Control agent</div>
        <span className={q.blocking ? "chip ask" : "chip dim"}>{q.blocking ? "Needs your answer" : "Optional"}</span>
      </div>
      <p id={id} className="message">{questionText(q.text)}</p>
      {q.origin === "model" && (
        // DEC-045, LEASH-174: this sentence is the assistant's own prose, not generated from a rule or
        // a registry field. Unlabelled it reads like one of Wallet Control's deterministic questions, and the
        // customer cannot tell which of the two they are answering.
        <p className="small from-background">
          <span className="chip dim">In my own words</span>{" "}
          my own words, not a rule — your answer is what could become one.
        </p>
      )}
      {q.source && (
        // Background suggests questions; it never grants authority (DEC-034). Unattributed, this
        // question reads as something the customer already agreed to, so it says whose idea it was,
        // quotes the recorded words rather than paraphrasing them, and invites disagreement.
        <p className="small from-background">
          <span className="chip dim">
            {q.source.kind === "history" ? "From what I've seen you buy" : "From your saved preferences"}
          </span>{" "}
          “{q.source.evidence}” — not a rule yet, and not something you told me. Say so if it should
          not apply here.
        </p>
      )}
      {q.options && q.options.length > 0 && (
        <div className="options">
          {q.options.map((o) => (
            <button key={o} type="button" className="btn secondary sm" disabled={busy} onClick={() => send(o, true)}>{o}</button>
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
  const [started, setStarted] = useState<Run | null>(null);  // the run as the engine recorded it
  const starting = useRef(false);  // a second tap while the first is in flight is the same handoff
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState<string | null>(null);  // the words in flight, shown as in flight
  const [posted, setPosted] = useState<PlatformDraft | null>(null);
  const [reviewed, setReviewed] = useState<number | null>(null);  // the revision the review was built from
  const [message, setMessage] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);  // the confirmation, kept apart from errors
  const [activity, setActivity] = useState<string | null>(null);
  const busy = activity !== null;
  const end = useRef<HTMLDivElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (editing) composerInput.current?.focus(); }, [editing]);
  const query = useQuery({ queryKey: ["draft", draftId], enabled: draftId !== null, staleTime: Infinity,
                           queryFn: () => api().draft(draftId!) });  // it changes only through this screen
  const d = query.data;
  const confirmedId = mandateId ?? d?.confirmed_mandate?.mandate_id;
  const runScenario = d?.simulation_scenario ?? scenarioId;
  const previousRuns = useQuery({ queryKey: ["runs"], enabled: !!confirmedId,
    queryFn: () => api().runs(), retry: false });
  const currentRun = started ?? previousRuns.data?.runs?.find(r => r.mandate_id === confirmedId && r.scenario_id === runScenario);

  // The rehearsed demonstration is chosen for the presenter, once, and only while nothing has been said
  // yet: a customer who has started typing owns the composer (LEASH-147).
  const offered = scenarios.data?.scenarios;
  useEffect(() => {
    const pick = offered?.find((s) => s.recommended);
    if (draftId === null && pick && !scenarioId && !composer.trim()) {
      setScenarioId(pick.scenario_id);
      setComposer(pick.cardholder_instruction);
    }
  }, [offered, draftId, scenarioId, composer]);

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
    setScenarioId("");
    setTalk(EMPTY);
    setPosted(null);
    setReviewed(null);
    setDone(null);
    setMandateId(null);
    setStarted(null);
    setEditing(false);
    setMessage(null);
    setComposer("");
  }

  /** Hand the task to the external shopping agent: one run, whatever the customer's fingers do.
   *
   *  The engine keys a start on (permission, scenario, version) and returns the existing run for a
   *  retry (LEASH-102), so a double tap cannot mint two sets of counters. This guard is the local half:
   *  without it the second tap still asks, and a refused start would read as two failures. */
  async function handOff() {
    if (starting.current || currentRun || !confirmedId) return;
    starting.current = true;
    try {
      const run = await act(() => api().startRun(runScenario, confirmedId), "Handing the task over…");
      if (run) {
        setStarted(run);
        await client.invalidateQueries({ queryKey: ["runs"] });
        onRunStarted?.(run.run_id);
      }
    } finally {
      starting.current = false;
    }
  }

  async function say(text: string) {
    setSending(text);
    setComposer("");
    const result = await act(() => api().chatTurn(text, draftId ?? undefined, scenarioId || undefined, editing,
                                               editing || posted || confirmedId ? undefined : asking?.question_id));
    setSending(null);
    // A reply answers what they said; it is not a new boundary, so it must not become a revision or
    // reset a review. Both a history answer and "that changed nothing" are this shape — the latter is
    // what a customer gets for typing "yes" when they meant to confirm. The draft the service returns
    // already carries the exchange in `messages`, so only a reply without a draft is kept locally.
    if (result?.kind === "history" || result?.reply) {
      if (result.draft) show(result.draft);
      else if (result.reply) record((t) => ({ ...t, history: [...(t.history ?? []), { text, reply: result.reply! }] }));
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
    record((t) => ({ ...t, log: [...t.log, { kind: "said", instruction: next.instruction }] }));
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
      const response = fromModel ? await api().chatTurn(text, d!.draft_id, undefined, false, q.question_id) : null;
      // Nothing changed: say so under the question rather than recording an answer that was not one.
      if (response?.reply && response.kind !== "history") return response.reply;
      const next = fromModel ? response?.draft : await api().answerDraft(d!.draft_id, q.question_id, text);
      if (!next) return "The assistant returned no draft. Please retry.";
      await client.cancelQueries({ queryKey: ["draft", next.draft_id] });  // no late read may undo this
      show(next);
      if (response?.kind === "history") return null;
      record((t) => ({ ...t, log: [...t.log, ...(fromModel
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
  const transcript: { who: "me" | "leash"; text: string; key: string; snapshot?: PolicyDraft }[] = [];
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
  // Older services can still use the local ordering above. The audit is authoritative when present:
  // a superseded answer stays in history even though it no longer contributes to today's permission.
  if (d?.revisions?.length) {
    transcript.length = 0;
    let previous: PolicyDraft | undefined;
    for (const revision of d.revisions) {
      const prefix = previous?.instruction ?? "";
      const text = revision.customer_turn?.text ?? (revision.instruction.startsWith(prefix)
        ? revision.instruction.slice(prefix.length).trim() : revision.instruction);
      if (text) transcript.push({ who: "me", text, key: `r${revision.revision}-turn` });
      const remaining = [...(previous?.answers ?? [])];
      for (const [i, answer] of (revision.answers ?? []).entries()) {
        const at = remaining.findIndex((a) => a.question_id === answer.question_id && a.answer === answer.answer);
        if (at >= 0) { remaining.splice(at, 1); continue; }
        transcript.push({ who: "leash", text: answer.question, key: `r${revision.revision}-q${i}` });
        transcript.push({ who: "me", text: answer.answer, key: `r${revision.revision}-a${i}` });
      }
      if (revision.revision < d.revision) transcript.push({ who: "leash", text: "", snapshot: revision,
        key: `r${revision.revision}-interpretation` });
      for (const [i, exchange] of (d.messages ?? []).entries()) {
        if (exchange.revision !== revision.revision) continue;
        transcript.push({ who: "me", text: exchange.text, key: `history-${i}-me` });
        transcript.push({ who: "leash", text: exchange.reply, key: `history-${i}-reply` });
      }
      previous = revision;
    }
  }
  const asking = (d?.open_questions ?? []).find((q) => q.blocking) ?? (d?.open_questions ?? [])[0];
  const blocking = (d?.open_questions ?? []).filter((q) => q.blocking).length;
  const mandateInstruction = posted?.instruction ?? d?.mandate_instruction ?? d?.instruction
    ?? offered?.find(s => s.scenario_id === scenarioId)?.cardholder_instruction;

  return (
    <div className="perm talk">
      <header className="chat-header">
        {onBack && <button className="chat-back" type="button" aria-label="Back to Cockpit" onClick={onBack}><Icon name="back" /></button>}
        <div className="chat-avatar" aria-hidden="true"><LogoMark state={confirmedId ? "active" : "idle"} size={24} onDark /></div>
        <div className="chat-heading"><h1>Wallet Control agent</h1><p>{activity ?? (query.isLoading ? "Loading your conversation…" : confirmedId ? "Permission confirmed" : "Let’s set your shopping boundaries")}</p></div>
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
        <Icon name="leash" />
        <div><strong>{confirmedId ? "Permission active" : posted ? "Ready for your confirmation" : "Permission draft"}</strong>
          <span>{d ? `${d.rules.length} rules · ${blocking ? `${blocking} clarification${blocking === 1 ? "" : "s"} left` : confirmedId ? "Confirmed by you" : "You review before anything is active"}` : "Nothing is active yet"}</span></div>
        <div className="chat-steps" aria-label={confirmedId ? "Permission confirmed" : posted ? "Review prepared" : "Setting up permission"}>
          <i className={d ? "filled" : ""} /><i className={posted || confirmedId ? "filled" : ""} /><i className={confirmedId ? "filled" : ""} />
        </div>
      </div>
      {mandateInstruction && <section className="card" aria-label="Mandate instruction">
        <details className="chat-details" open><summary>Mandate instruction</summary>
          <p className="small">{mandateInstruction}</p>
          <p className="small">{confirmedId ? "Confirmed task" : "Task to review"} · Your answers refine the rules below.</p>
        </details>
      </section>}
      <div className="chat-messages" role="log" aria-label="Conversation" aria-live="polite" aria-relevant="additions">
      <Bubble from="leash" label="Wallet Control agent">
        <p className="message">{GREETING}</p>
      </Bubble>

      {draftId === null && scenarios.data?.scenarios && (
        <section className="card" aria-label="Simulation data">
          {/* By name and by what each one shows — a customer never picks a fixture ID (LEASH-147). The
              recommended demonstration is already chosen and its task already in the composer, so the
              rehearsed path is one tap. */}
          <div role="group" aria-label="Choose a demonstration" className="task-choices">
            {scenarios.data.scenarios.map((s) => (
              <label key={s.scenario_id} className={`task-choice${scenarioId === s.scenario_id ? " chosen" : ""}`}>
                <input type="radio" name="scenario" value={s.scenario_id} checked={scenarioId === s.scenario_id}
                       onChange={() => { setScenarioId(s.scenario_id); setComposer(s.cardholder_instruction); }} />
                <span>
                  <span className="task-name">{s.scenario_name}
                    {s.recommended && <span className="chip dim">Recommended</span>}</span>
                  {s.summary && <span className="small">{s.summary}</span>}
                  <span className="small">{s.event_count} checkout{s.event_count === 1 ? "" : "s"}</span>
                </span>
              </label>
            ))}
          </div>
          <p className="small">Uses the supplied customer, history and checkout data. Review the task below before sending.</p>
        </section>
      )}
      {transcript.map((line) => (
        <Bubble key={line.key} from={line.who} label={line.who === "leash" ? "Wallet Control agent" : undefined}>
          {line.snapshot ? <details className="chat-details">
            <summary>Earlier draft · revision {line.snapshot.revision}</summary>
            <p className="small">Replaced by a later draft. These are historical rules.</p>
            <ul>{line.snapshot.rules.map((rule, i) => <li key={i}>{rule.text}</li>)}</ul>
            {(line.snapshot.open_questions.find((q) => q.blocking) ?? line.snapshot.open_questions[0])?.text &&
              <p className="message">{questionText((line.snapshot.open_questions.find((q) => q.blocking) ?? line.snapshot.open_questions[0]).text)}</p>}
          </details> : <p className="message">{line.who === "leash" ? questionText(line.text) : line.text}</p>}
        </Bubble>
      ))}
      {query.isLoading && <div className="chat-loading" role="status"><span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>Restoring your saved conversation…</div>}

      {query.isError && (
        <Bubble from="leash" label="Wallet Control agent">
          <p role="alert" className="p-blocked">I couldn't load your draft, so I can't show you where it
            got to. Nothing becomes active without your confirmation.</p>
          <button type="button" className="btn ghost" onClick={startOver}>Start a new conversation</button>
        </Bubble>
      )}

      {d && (
        <Bubble from="leash" label="Wallet Control agent">
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

      {/* Anything said after the interpretation belongs after it. The draft is produced by the turn
          above, so rendering the exchanges and the in-flight message here is what puts the
          conversation in the order it happened — before this, every acknowledgement (DEC-059) and
          history answer appeared above the draft it replied to, which read as the customer's messages
          bunched together with Wallet Control answering at the end. Earlier revisions stay interleaved inside
          `transcript`; this is the current one, which is always the latest thing to have happened. */}
      {(talk.history ?? []).map((exchange, i) => (
        <div key={`preface-${i}`}>
          <Bubble from="me"><p className="message">{exchange.text}</p></Bubble>
          <Bubble from="leash" label="Wallet Control agent · history checked"><p className="message">{exchange.reply}</p></Bubble>
        </div>
      ))}
      {(!d?.revisions?.length ? d?.messages ?? [] : []).map((exchange, i) => (
        <div key={`history-${i}`}>
          <Bubble from="me"><p className="message">{exchange.text}</p></Bubble>
          <Bubble from="leash" label="Wallet Control agent · history checked"><p className="message">{exchange.reply}</p></Bubble>
        </div>
      ))}

      {sending !== null && (
        <Bubble from="me">
          <p className="message">{sending}</p>
          <p className="small" role="status">Sending…</p>
        </Bubble>
      )}


      {d && !posted && !confirmedId && asking && (
        <Clarification key={asking.question_id} q={asking} busy={busy} onAnswer={(text, option) => answer(asking, text, option)} />
      )}

      {message && (
        <Bubble from="leash" label="Wallet Control agent">
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
          <button type="button" className="btn primary" disabled={busy || d.status !== "ready"}
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
          </div>
          <p className="small">This exact draft becomes your permission when you confirm. It isn't active yet.</p>
          <p className="message">{posted.instruction}</p>
          {/* The boundaries, under their headings, generated by the engine from the rules Viseca holds
              (LEASH-146). Identifiers, decision codes and the raw payload are one disclosure away: what
              the customer agrees to has to be readable without learning our vocabulary first. */}
          <PermissionSummary review={posted.review} expanded />
          <p className="small">When unsure: {UNSURE[posted.uncertainty_policy]}.</p>
          {(posted.open_questions ?? []).length > 0 && (
            <section role="group" aria-label="Choices you left to me">
              <h2>Choices you left to me</h2>
              <p className="small">You left these optional questions open, so nothing narrows the
                boundaries above on their account. I ask you when a purchase turns on one of them:</p>
              <ul className="notes">
                {posted.open_questions!.map((q) => <li key={q} className="small">{q}</li>)}
              </ul>
            </section>
          )}
          {posted.guidance.length > 0 && (
            <ul className="notes">{posted.guidance.map((g) => <li key={g} className="small">{g}</li>)}</ul>
          )}
          <details className="chat-details">
            <summary>Advanced details</summary>
            <p className="small">The exact payload Viseca holds, for technical verification. Every line
              above is generated from these rules.</p>
            <div className="sum-row"><div className="k">Draft at Viseca</div>
              <span className="chip dim">{posted.platform_draft_id}</span></div>
            <ul className="rules exact">
              {posted.hard_rules.map((r) => <li key={ruleLine(r)}><code>{ruleLine(r)}</code></li>)}
            </ul>
            <p className="small">Uncertainty policy: <code>{posted.uncertainty_policy}</code>.</p>
          </details>
          {!confirmedId && done === null && (
            <button type="button" className="btn primary" disabled={busy}
                    onClick={async () => {
                      // the revision reviewed, not whatever the draft is now: a stale tab is refused
                      if (reviewed === null) return;
                      const m = await act(() => api().confirmDraft(posted.draft_id, reviewed), "Confirming your permission…");
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
        <section className="card handoff" aria-label="Start shopping">
          <p>Permission confirmed. The shopping agent can start, inside these boundaries.</p>
          {currentRun
            ? <RunActivity initial={currentRun} />
            : <>
                {previousRuns.isError && <p role="alert">Could not check earlier runs. <button type="button" onClick={() => previousRuns.refetch()}>Retry</button></p>}
                <button type="button" className="btn primary" disabled={busy || previousRuns.isPending || previousRuns.isError} onClick={() => handOff()}>Start shopping</button>
                <p className="small">Wallet Control checks each checkout; the simulated platform records whether it accepts
                  the decision. A started run is not proof of a real merchant integration, and no real payment is made.</p>
              </>}
        </section>
      )}
      {done && !currentRun && (
        <Bubble from="leash" label="Wallet Control agent">
          <p className="message" role="status">{done}</p>
          <p className="small">Nothing is bought yet. When the shopping agent checks out, I check it
            against these boundaries and ask you about anything they don't settle.</p>
        </Bubble>
      )}
      {activity && <div className="chat-loading" role="status"><span className="typing-dots" aria-hidden="true"><i /><i /><i /></span><span>{activity}</span></div>}
      <div ref={end} />
      </div>
      {(
        <section className="composer" aria-label="Say something">
          <label className="k" htmlFor="composer">
            {editing ? "Correct your task — a fresh review is required" : draftId === null ? "What may the agent buy?" : asking ? "Reply to Wallet Control" : "Anything to add or change?"}
          </label>
          <div className="composer-input"><textarea id="composer" ref={composerInput} className="field" rows={2} placeholder="Ask a question, answer, or change your task…" aria-describedby={asking && !editing && !posted && !confirmedId ? `q-${asking.question_id}` : undefined} value={composer}
                    onChange={(e) => setComposer(e.target.value)} />
          <button type="button" className="btn primary" disabled={busy || sending !== null || !composer.trim()}
                  onClick={() => say(composer.trim())} aria-label="Send"><Icon name="send" /></button></div>
        </section>
      )}
    </div>
  );
}
