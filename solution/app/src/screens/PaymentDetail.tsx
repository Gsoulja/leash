// Payment detail sheet: what the customer agreed vs what this payment tried to do, check by check, with
// the shop's text marked untrusted. Everything is rendered as React text (escaped), never as HTML.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../api/client";
import { deliveryNote, statusOf, type Tone } from "./status";
import { Icon } from "../components/icons";
import { Chip, type ChipTone } from "../components/ui/Chip";

const STATUS: Record<string, string> = { pass: "Passed", fail: "Failed", warn: "Check", info: "Info", integrity: "Check" };
// What stopped the payment reads first: failed and doubtful rows, then info, then passed ones.
const RANK: Record<string, number> = { fail: 0, integrity: 1, warn: 2, info: 3, pass: 4 };
const ENGINE: Record<string, string> = { approve: "Engine: approved", decline: "Engine: declined", step_up: "Engine: asked you" };
const HUE: Record<Tone, ChipTone> = { ok: "allowed", warn: "attention", bad: "stopped", dim: "neutral", off: "neutral" };

// The mono source line of the "Why" section: the recorded facts in order, as the API names them (handoff V5).
function source(p: { engine_verdict: string | null; final_state: string; resolved_by: string | null; delivery: string | null }) {
  const parts = [p.engine_verdict ?? "no engine verdict", p.resolved_by ? `${p.final_state} by ${p.resolved_by}` : p.final_state];
  if (p.delivery) parts.push(`platform ${p.delivery}`);
  return parts.join(" → ");
}

const when = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function PaymentDetail({ authorizationId, onClose }: { authorizationId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ["payment", authorizationId], queryFn: () => api().payment(authorizationId) });
  const dialog = useRef<HTMLDivElement>(null);

  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close.current();
        return;
      }
      if (e.key !== "Tab" || !dialog.current) return;
      const focusable = [...dialog.current.querySelectorAll<HTMLElement>("button, [href], [tabindex]:not([tabindex='-1'])")];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      // Focus on the dialog itself (as on open) counts as outside the list, so both directions wrap.
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
      opener?.focus?.();  // back to the row that opened the sheet
    };
  }, []);

  const p = query.data;
  return (
    <div className="scrim" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Payment details" tabIndex={-1} ref={dialog}
           onClick={(e) => e.stopPropagation()}>
        {query.isError && <p>This payment couldn't be loaded.</p>}
        {!p && !query.isError && <p>Loading…</p>}
        {p && (
          <>
            <div className="sheet-head">
              <div className="ico" aria-hidden="true"><Icon name="store" /></div>
              <div>
                <div className="rname">{p.merchant.name}</div>
                {p.items[0] && <div className="rsub">{p.items.map((i) => i.name).join(" + ")}</div>}
                <div className="rsub">{when.format(new Date(p.sim_time))}{p.merchant.city ? ` · ${p.merchant.city}` : ""}, {p.merchant.country}</div>
              </div>
              <div className="ramt">
                CHF {p.billing_amount_chf}
                {p.currency !== "CHF" && <small>{p.currency} {p.amount}</small>}
              </div>
            </div>
            <div className="counts">
              <Chip tone="agent">AGENT</Chip>
              <Chip tone={HUE[statusOf(p)[1]]}>{statusOf(p)[0]}</Chip>
              {p.engine_verdict && <Chip tone="neutral">{ENGINE[p.engine_verdict]}</Chip>}
            </div>
            <section className="why-card" aria-label="Why">
              <div className="overline">Why</div>
              {p.customer_message && <p className="message">{p.customer_message}</p>}
              {deliveryNote(p) && <p className="small">{deliveryNote(p)}</p>}
              <p className="source">{source(p)}</p>
            </section>
            {p.checks.length > 0 && (
              <table className="cmp" aria-label="What you agreed vs this payment">
                <thead>
                  <tr><th scope="col">Rule</th><th scope="col">You agreed</th><th scope="col">This payment</th><th scope="col">Status</th></tr>
                </thead>
                <tbody>
                  {[...p.checks].sort((a, b) => (RANK[a.status] ?? 3) - (RANK[b.status] ?? 3)).map((c) => (
                    <tr key={c.key}>
                      <td>{c.label}</td><td>{c.agreed}</td><td>{c.actual}</td>
                      <td className={`st st-${c.status}`}>{STATUS[c.status] ?? c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {p.shop_texts.map((t) => (
              <div className="untrusted" key={t.item_id}>
                <b>Shop's text · untrusted</b>
                <span>{t.text}</span>
              </div>
            ))}
            <button type="button" className="link" onClick={onClose}>Close</button>
          </>
        )}
      </div>
    </div>
  );
}
