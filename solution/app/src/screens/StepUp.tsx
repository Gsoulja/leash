// Step-up prompt (LEASH-094): a full-screen ask in the 3-D Secure style. Amount, shop, why I'm asking and
// what passed, a countdown from the server's expires_at (DEC-008), and Confirm payment / Reject / Decide later.
// Answers go to POST /api/asks/{id}/answer. When a hard rule now fails (DEC-012), Approve is replaced by the
// reason and only Reject remains. When an answer loses the race against the expiry, the prompt shows what the
// platform recorded instead.
//
// A payment is never swapped under the customer's finger: the ask on screen is pinned. If it disappears (it
// timed out or was answered elsewhere), or once it is answered, a notice needs an OK before the next ask is
// shown, and a newly shown Confirm stays disabled for a moment. The countdown never disables the answers:
// this device's clock may be off, so the platform decides (a late answer gets its recorded outcome).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { deliveryNote, statusOf } from "./status";
import { ApiError, api, type Ask, type Payment } from "../api/client";

const ARM_MS = 800;
const ANSWER_TIMEOUT_MS = 15_000;
const when = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const outcomeText = (p: Payment) => `${statusOf(p)[0]}. ${deliveryNote(p)}`.trim();

type Notice = { text: string } | { lookup: string; name: string };

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function useDialogFocus(dialog: React.RefObject<HTMLDivElement | null>, active: boolean, content: string,
                        onEscape: () => void) {
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    if (!active) return;
    const opener = document.activeElement as HTMLElement | null;
    const focusable = () => [...(dialog.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? [])];
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        escape.current();
        return;
      }
      if (e.key !== "Tab" || !dialog.current) return;
      const list = focusable();
      if (!list.length) return;
      const first = list[0], last = list[list.length - 1];
      const inside = dialog.current.contains(document.activeElement) && document.activeElement !== dialog.current;
      if (e.shiftKey && (document.activeElement === first || !inside)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !inside)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);  // Escape and the focus trap work wherever focus is
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();  // back to where the customer was
    };
  }, [active, dialog]);
  useEffect(() => {  // the dialog itself takes focus, never a button: a stray key press answers nothing
    if (active) dialog.current?.focus();
  }, [active, content, dialog]);
}

export function StepUp({ asks }: { asks: Ask[] }) {
  const [later, setLater] = useState<Set<string>>(new Set());
  const [done, setDone] = useState<Set<string>>(new Set());  // answered, or announced as gone
  const [refused, setRefused] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pinned, setPinned] = useState<Ask | null>(null);
  const [armedFor, setArmedFor] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState<string | null>(null);  // our own answer, not yet replied to
  const [shownSeq, setShownSeq] = useState(0);  // bumps whenever an ask is shown again after a notice
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const dialog = useRef<HTMLDivElement>(null);

  const waiting = asks.filter((a) => !later.has(a.authorization_id) && !done.has(a.authorization_id));
  // The ask on screen stays until the customer answers it, defers it or acknowledges that it's gone. The next
  // one is chosen here, during the render, so an answered or deferred ask is never drawn again, not even for
  // one frame (a tap in that frame would land on the next ask).
  const kept = pinned && !done.has(pinned.authorization_id) && !later.has(pinned.authorization_id) ? pinned : null;
  const target = notice ? pinned : (kept ?? waiting[0] ?? null);
  const live = target ? asks.find((a) => a.authorization_id === target.authorization_id) : undefined;

  useEffect(() => {
    if (notice) return;
    if (kept && !live && inFlight !== kept.authorization_id) {
      setNotice({ text: `${kept.payment.merchant.name} is no longer waiting for your answer: it timed out or was answered elsewhere.` });
      setDone((d) => new Set(d).add(kept.authorization_id));
      return;
    }
    if (target !== pinned) setPinned(target);
  }, [notice, kept, live, inFlight, target, pinned]);

  // the freshest copy of the ask on screen; while our own answer is in flight it stays as it was
  const current = target && (live ?? (inFlight === target.authorization_id ? target : null)) || null;
  const armKey = current && !notice ? `${current.authorization_id}|${current.can_approve}|${shownSeq}` : null;
  useEffect(() => {  // answers are armed only a moment after an ask (or a changed one) is shown
    setArmedFor(null);
    if (!armKey) return;
    const timer = setTimeout(() => setArmedFor(armKey), ARM_MS);
    return () => clearTimeout(timer);
  }, [armKey]);

  const outcome = useQuery({
    queryKey: ["payment", notice && "lookup" in notice ? notice.lookup : null],
    enabled: notice !== null && "lookup" in notice, retry: false,
    queryFn: () => api().payment((notice as { lookup: string }).lookup),
  });

  const open = notice !== null || current !== null;
  const closeNotice = () => {
    setNotice(null);
    setShownSeq((n) => n + 1);
  };
  const deferCurrent = () => {
    if (notice) closeNotice();
    else if (current) setLater((s) => new Set(s).add(current.authorization_id));
  };
  useDialogFocus(dialog, open, notice ? "notice" : armKey ?? "", deferCurrent);
  if (!open) {
    const deferred = asks.filter((a) => later.has(a.authorization_id) && !done.has(a.authorization_id)).length;
    if (!deferred) return null;
    return (
      <button type="button" className="review-banner" onClick={() => setLater(new Set())}>
        {deferred} payment{deferred > 1 ? "s" : ""} waiting for your answer · Review now
      </button>
    );
  }

  if (notice) {
    const text = "text" in notice ? notice.text : notice.name + (outcome.isError
      ? "Your answer arrived too late, and I couldn't load what the platform recorded. Check the payment in your list."
      : outcome.data ? outcomeText(outcome.data) : "Checking what the platform recorded…");
    return (
      <div className="prompt" role="dialog" aria-modal="true" aria-label="Payment waiting for your answer" tabIndex={-1}
           ref={dialog}>
        <p className="p-outcome" aria-live="polite">{text}</p>
        <button type="button" className="pill" onClick={closeNotice}>OK</button>
      </div>
    );
  }

  const ask = current!;
  const p = ask.payment;
  const left = Math.max(0, Math.ceil((new Date(ask.expires_at).getTime() - now) / 1000));
  const reason = refused[ask.authorization_id] ?? (ask.can_approve ? null : ask.cannot_approve_reason
    ?? "A rule you set now blocks this payment.");
  const armed = armedFor !== null && armedFor === armKey;
  const name = `${p.merchant.name} · CHF ${p.billing_amount_chf}: `;  // every notice says which payment

  async function answer(decision: "approve" | "decline") {
    const id = ask.authorization_id;
    setBusy(true);
    setInFlight(id);
    try {
      const recorded = await Promise.race([  // a reply that never comes must not trap the customer
        api().answerAsk(id, decision),
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error("no answer")), ANSWER_TIMEOUT_MS)),
      ]);
      setDone((d) => new Set(d).add(id));
      setNotice({ text: name + outcomeText(recorded) });
    } catch (error) {
      if (error instanceof ApiError && error.code === "cannot_approve") {
        setRefused((r) => ({ ...r, [id]: error.message.replace(/^cannot_approve: /, "") }));
      } else if (error instanceof ApiError && error.code === "not_waiting") {
        setDone((d) => new Set(d).add(id));
        setNotice({ lookup: id, name });  // show what the platform recorded instead
      } else {
        setNotice({ text: name + "Your answer couldn't be sent. Please try again." });
      }
    } finally {
      setInFlight(null);
      setBusy(false);
    }
  }

  return (
    <div className="prompt" role="dialog" aria-modal="true" aria-label="Payment waiting for your answer" tabIndex={-1}
         ref={dialog}>
      <div className="p-top">
        <span>{p.sim_time ? when.format(new Date(p.sim_time)) : ""}</span>
        <span className="agentbadge">AI agent{waiting.length > 1 ? ` · 1 of ${waiting.length}` : ""}</span>
      </div>
      <div className="p-mid">
        <div className="p-amt">CHF {p.billing_amount_chf}</div>
        <div className="p-shop">{p.merchant.name}</div>
        <div className="p-card">
          {p.currency !== "CHF" ? `${p.currency} ${p.amount} · ` : ""}{p.items.map((i) => i.name).join(" + ")}
        </div>
      </div>
      <section className="why" aria-label="Why I'm asking">
        <b className="why-title">Why I'm asking</b>
        {ask.reasons.map((r) => <div key={r} className="st-warn"><span>{r}</span></div>)}
        {ask.passed.length > 0 && <div className="st-pass"><span>{ask.passed.join(", ")}: OK</span></div>}
      </section>
      <div className="p-foot">
        <p className="timer">
          {left > 0 ? `Answer within ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`
            : "The time may have run out. You can still answer; the platform decides whether it counts."}
        </p>
        <div aria-live="polite">{reason && <p className="p-blocked">{reason}</p>}</div>
        {!reason && <button type="button" className="pill" disabled={busy || !armed} onClick={() => answer("approve")}>Confirm payment</button>}
        <button type="button" className="link" disabled={busy || !armed} onClick={() => answer("decline")}>Reject</button>
        <button type="button" className="link later" disabled={busy} onClick={deferCurrent}>Decide later</button>
        {/* LEASH-146: a purchase-specific answer is not a change of permission. Saying so keeps one
            approval from reading as a standing allowance the customer never gave. */}
        <p className="small">This answer covers this payment only; your permission stays as it is.</p>
      </div>
    </div>
  );
}
