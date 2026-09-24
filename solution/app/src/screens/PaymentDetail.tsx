// Payment detail sheet: what the customer agreed vs what this payment tried to do, check by check, with
// the shop's text marked untrusted. Everything is rendered as React text (escaped), never as HTML.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../api/client";
import { statusOf } from "./status";

const STATUS: Record<string, string> = { pass: "Passed", fail: "Failed", warn: "Check", info: "Info", integrity: "Check" };
const ENGINE: Record<string, string> = { approve: "Engine: approved", decline: "Engine: declined", step_up: "Engine: asked you" };
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
              <div>
                <div className="rname">{p.merchant.name}</div>
                <div className="rsub">{when.format(new Date(p.sim_time))}{p.merchant.city ? ` · ${p.merchant.city}` : ""}, {p.merchant.country}</div>
              </div>
              <div className="ramt">
                CHF {p.billing_amount_chf}
                {p.currency !== "CHF" && <small>{p.currency} {p.amount}</small>}
              </div>
            </div>
            <div className="counts">
              {p.engine_verdict && <span className="chip dim">{ENGINE[p.engine_verdict]}</span>}
              <span className={`chip ${statusOf(p)[1]}`}>{statusOf(p)[0]}</span>
            </div>
            {p.customer_message && <p className="message">{p.customer_message}</p>}
            {p.checks.length > 0 && (
              <table className="cmp" aria-label="What you agreed vs this payment">
                <thead>
                  <tr><th scope="col">Rule</th><th scope="col">You agreed</th><th scope="col">This payment</th><th scope="col">Status</th></tr>
                </thead>
                <tbody>
                  {p.checks.map((c) => (
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
