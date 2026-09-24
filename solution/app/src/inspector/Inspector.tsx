// LEASH-097: the judges' side panel. Read-only, and deliberately not part of the customer's phone:
// it shows every payment the engine has answered — or one run's, when the caller names one — with the
// engine's own verdict next to the final outcome, and for
// the selected one the checks that produced it, the facts that were read, and the exact JSON sent to
// the Viseca API. Nothing here can change anything — there is no mutation and no form.
//
// It is hidden below tablet width (theme.css `.inspector`), so the phone stays the whole screen on a
// phone. Shop text arrives inside `evidence` and `sent_to_viseca`; both are rendered as React text.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Payment } from "../api/client";
import { statusOf } from "../screens/status";

const ENGINE: Record<string, string> = { approve: "approve", decline: "decline", step_up: "ask" };
const STATUS: Record<string, string> = { pass: "Passed", fail: "Failed", warn: "Check", info: "Info", integrity: "Check" };

function Rows({ payments, selected, onSelect }: { payments: Payment[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <table className="ins-list" aria-label="Payments in this run">
      <thead>
        <tr><th scope="col">Payment</th><th scope="col">Engine</th><th scope="col">Final</th></tr>
      </thead>
      <tbody>
        {payments.map((p) => (
          <tr key={p.authorization_id} aria-selected={p.authorization_id === selected}>
            <td>
              <button type="button" className="link" onClick={() => onSelect(p.authorization_id)}>
                {p.merchant.name} · CHF {p.billing_amount_chf}
              </button>
            </td>
            <td>{p.engine_verdict ? ENGINE[p.engine_verdict] : "—"}</td>
            <td>{statusOf(p)[0]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Inspector({ runId }: { runId?: string }) {
  // The same key the cockpit uses, so the event stream's `invalidateQueries(["payments"])` refreshes
  // this list too. A panel that silently stopped updating during a run would be worse than none.
  const payments = useQuery({ queryKey: ["payments", runId ?? null],
                              queryFn: async () => (await api().payments(runId)).payments });
  const [selected, setSelected] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["payment", selected], enabled: selected !== null,
                            queryFn: () => api().payment(selected as string) });
  const d = detail.data;
  return (
    <aside className="inspector" aria-label="Engine inspector">
      <h2>Engine inspector</h2>
      {payments.isError && <p className="empty">Payments couldn't be loaded.</p>}
      {payments.data && payments.data.length === 0 && <p className="empty">No payments yet.</p>}
      {payments.data && payments.data.length > 0 &&
        <Rows payments={payments.data} selected={selected} onSelect={setSelected} />}
      {selected === null && <p className="small">Select a payment to see its checks.</p>}
      {selected !== null && detail.isError && <p className="empty">This payment couldn't be loaded.</p>}
      {d && (
        <>
          {d.checks.length === 0 && <p className="small">No checks were recorded for this payment.</p>}
          {d.checks.length > 0 && (
          <table className="cmp" aria-label="Checks">
            <thead>
              <tr><th scope="col">Rule</th><th scope="col">Agreed</th><th scope="col">This payment</th><th scope="col">Status</th></tr>
            </thead>
            <tbody>
              {d.checks.map((c) => (
                <tr key={c.key}>
                  <td>{c.label}</td><td>{c.agreed}</td><td>{c.actual}</td>
                  <td className={`st st-${c.status}`}>{STATUS[c.status] ?? c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>)}
          <h3>Facts read</h3>
          <p className="small">{d.reader.name}{d.reader.model_unavailable ? " · model unavailable" : ""} · {d.engine_version}</p>
          <ul className="ins-facts">{d.evidence.map((e, i) => <li key={`${i}-${e}`}>{e}</li>)}</ul>
          <h3>Sent to Viseca</h3>
          <pre className="ins-json">{d.sent_to_viseca ? JSON.stringify(d.sent_to_viseca, null, 2) : "Nothing was sent."}</pre>
        </>
      )}
    </aside>
  );
}
