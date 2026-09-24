// Engine inspector (LEASH-097): the judges' panel beside the phone. It shows every payment of the
// selected run with the engine's verdict *and* the final outcome, and for the selected one: the checks,
// the facts read from the shop's text, and the exact JSON body sent to Viseca.
//
// It is a read-only view of the same read model the phone uses (/api/payments), so it can never show a
// state the engine has not recorded. Shop text is untrusted merchant data and is rendered as React text
// like everywhere else in the app — never as markup.
//
// Below the desktop breakpoint the panel is not mounted at all (rather than hidden with CSS): there is no
// room for it on a phone, and an invisible panel should not be fetching payment detail nobody can read.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { PATHS, api, type Check, type IntegrityAlertData, type Payment } from "../api/client";

const WIDE = "(min-width: 900px)";

function useWideScreen() {
  const [wide, setWide] = useState(() => (typeof matchMedia === "function" ? matchMedia(WIDE).matches : false));
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mql = matchMedia(WIDE);
    const onChange = () => setWide(mql.matches);
    onChange();  // the width may have changed between the first render and this effect
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return wide;
}

function read(event: Event): Record<string, unknown> | null {
  try {
    const data = (JSON.parse((event as MessageEvent).data) as { data?: unknown }).data;
    return data && typeof data === "object" ? (data as Record<string, unknown>) : null;
  } catch {
    return null;  // a malformed event never breaks the panel
  }
}

const isAlert = (d: Record<string, unknown>): d is IntegrityAlertData =>
  typeof d.kind === "string" && typeof d.detail === "string";

/**
 * Live updates follow the pattern Cockpit.tsx already uses: the stream only triggers a reload of the read
 * model, and the shared ["payments"] key means the phone and the panel refresh together.
 * `integrity.alert` is operator-only (contracts/events.md) and has no home on the customer screens.
 */
function useStream(runId: string | null) {
  const client = useQueryClient();
  const [alerts, setAlerts] = useState<IntegrityAlertData[]>([]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(PATHS.events);
    const reload = () => {
      void client.invalidateQueries({ queryKey: ["payments"] });
      void client.invalidateQueries({ queryKey: ["payment"] });
    };
    for (const type of ["payment.decided", "ask.resolved"]) source.addEventListener(type, reload);
    source.onopen = reload;  // (re)connected: whatever happened meanwhile is in the read model
    source.addEventListener("integrity.alert", (event) => {
      const data = read(event);
      if (data && isAlert(data)) setAlerts((seen) => [data, ...seen]);
    });
    return () => source.close();
  }, [client]);

  // An alert without a run belongs to no single run, so it is shown whichever run is selected.
  return alerts.filter((a) => a.run_id === null || a.run_id === runId);
}

const tone =(v: string | null) =>
  v === "approve" || v === "approved" ? "approve" : v === "decline" || v === "declined" ? "decline"
  : v === "step_up" || v === "waiting" ? "step_up" : "dim";

function PaymentRow({ payment, selected, onSelect }: { payment: Payment; selected: boolean; onSelect: (id: string) => void }) {
  return (
    <button type="button" className={`irow${selected ? " sel" : ""}`} aria-pressed={selected}
            onClick={() => onSelect(payment.authorization_id)}>
      <span className="imono">{payment.authorization_id}</span>
      <span className="iname">{payment.merchant.name}</span>
      <span className="iamt">{payment.billing_amount_chf}</span>
      {/* Both verdicts, side by side: the engine's call, and what the payment actually ended up as. */}
      <span className={`v-chip v-${tone(payment.engine_verdict)}`} data-engine>{payment.engine_verdict ?? "—"}</span>
      <span className={`v-chip v-${tone(payment.final_state)}`} data-final>{payment.final_state}</span>
    </button>
  );
}

const CHECK_TONE: Record<Check["status"], string> = {
  pass: "ok", fail: "bad", warn: "warn", info: "dim", integrity: "warn",
};

function Checks({ checks }: { checks: Check[] }) {
  if (checks.length === 0) return <p className="inote">No checks ran for this payment.</p>;
  return (
    <div role="group" aria-label="Checks" className="ichecks">
      {checks.map((c) => (
        <div className="ichk" key={c.key}>
          <span className={`v-chip v-${CHECK_TONE[c.status]}`}>{c.status}</span>
          <span className="ilabel">{c.label}</span>
          <span className="idetail">
            <span className="iagreed">{c.agreed} → {c.actual}</span>
            {c.detail}
            {c.reason_code && <code className="icode">{c.reason_code}</code>}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Inspector({ runId }: { runId: string | null }) {
  // The hooks live in the panel, so at phone width nothing mounts, subscribes or fetches.
  return useWideScreen() ? <InspectorPanel runId={runId} /> : null;
}

function InspectorPanel({ runId }: { runId: string | null }) {
  const [selected, setSelected] = useState<string | null>(null);
  const alerts = useStream(runId);

  // A payment belongs to the run it was selected in. When the phone switches run the selection goes with
  // it, so the open decision block can never describe a run the rest of the panel has left.
  const [shownRun, setShownRun] = useState(runId);
  if (shownRun !== runId) {
    setShownRun(runId);
    setSelected(null);
  }

  // Same query keys as the cockpit: one fetch serves both, and one invalidation refreshes both.
  const payments = useQuery({ queryKey: ["payments", runId], enabled: runId !== null,
                              queryFn: async () => (await api().payments(runId ?? undefined)).payments });
  const chosen = useQuery({ queryKey: ["payment", selected], enabled: selected !== null,
                            queryFn: () => api().payment(selected!) });

  const list = payments.data ?? [];
  const d = chosen.data;

  return (
    <aside className="side" role="complementary" aria-label="Engine inspector">
      <section className="panel">
        <div className="ph">
          <h2>Engine inspector</h2>
          <span className="meta">{runId ?? "no run"}</span>
        </div>
        <p className="inote">
          Every payment the agent proposed in this run, with the verdict the rules produced and what the
          payment finally became. Select one to see why.
        </p>
        {payments.isError && <p className="inote">Payments couldn't be loaded.</p>}
        {!payments.isError && list.length === 0 && <p className="inote">No payments in this run yet.</p>}
        <div className="ilist">
          {list.map((p) => (
            <PaymentRow key={p.authorization_id} payment={p} selected={p.authorization_id === selected}
                        onSelect={setSelected} />
          ))}
        </div>
      </section>

      {alerts.length > 0 && (
        <section className="panel">
          <h2>Integrity alerts</h2>
          {/* Operator-only (contracts/events.md): these never appear on the customer's screens. */}
          <div role="group" aria-label="Integrity alerts" className="ichecks">
            {alerts.map((a, i) => (
              <div className="ichk" key={`${a.kind}-${i}`}>
                <span className="v-chip v-warn">alert</span>
                <span className="ilabel"><code className="icode">{a.kind}</code></span>
                <span className="idetail">{a.detail}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {selected && (
        <section className="panel">
          <div className="ph">
            <h2>Decision · {selected}</h2>
            {d && <span className="meta">{d.engine_version}</span>}
          </div>
          {chosen.isError && <p className="inote">This payment couldn't be loaded.</p>}
          {!d && !chosen.isError && <p className="inote">Loading…</p>}
          {d && (
            <>
              <div className="counts">
                <span className={`v-chip v-${tone(d.engine_verdict)}`}>engine: {d.engine_verdict ?? "—"}</span>
                <span className={`v-chip v-${tone(d.final_state)}`}>
                  final: {d.final_state}{d.resolved_by === "customer" ? " · you" : ""}
                </span>
              </div>
              <h3>Checks</h3>
              <Checks checks={d.checks} />

              <h3>Facts read</h3>
              <div role="group" aria-label="Facts read" className="ifacts">
                <p className="inote">
                  Reader: <b>{d.reader.name}</b>
                  {d.reader.model_unavailable
                    ? " — model unavailable, so the regex fallback read this text."
                    : " — available."}
                </p>
                {d.shop_texts.length === 0
                  ? <p className="inote">No shop text was read for this payment.</p>
                  : d.shop_texts.map((t) => (
                      <div className="untrusted" key={t.item_id}>
                        <b>Shop's text · untrusted</b>
                        {/* Rendered as text: merchant data can never change a verdict, or this page. */}
                        <span>{t.text}</span>
                      </div>
                    ))}
              </div>

              <h3>Sent to Viseca</h3>
              <div role="group" aria-label="Sent to Viseca">
                {d.sent_to_viseca
                  ? <pre className="json">{JSON.stringify(d.sent_to_viseca, null, 2)}</pre>
                  : <p className="inote">Nothing was sent: the engine never answered for this payment.</p>}
              </div>
            </>
          )}
        </section>
      )}
    </aside>
  );
}
