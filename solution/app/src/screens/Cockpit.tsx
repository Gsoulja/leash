// Cockpit: the agent's payments by day with their outcome, and spending against a period limit.
// Initial state comes from the read model (/api/payments, /api/spending); stream events only trigger a
// reload of it, so the screen never shows a state the engine hasn't recorded. Everything on it describes one
// selected run (LEASH-133): the current run when the screen opens, or an earlier one the customer picks. A newer
// run starting later never switches the selection by itself.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { PaymentDetail } from "./PaymentDetail";
import { stageOf, statusOf, type Stage } from "./status";
import { PATHS, api, type Payment, type Run, type Spending } from "../api/client";

const zurichDay = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", day: "numeric", month: "short", year: "numeric" });
const zurichTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", hour: "2-digit", minute: "2-digit" });

function useSelectedRun() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api().runs() });
  const [chosen, setChosen] = useState<string | null>(null);
  const list = runs.data?.runs ?? [];
  const first = runs.data?.current_run_id ?? list[0]?.run_id ?? null;
  useEffect(() => {  // pin the run shown first, so a newer run starting later doesn't take over the screen
    if (chosen === null && first !== null) setChosen(first);
  }, [chosen, first]);
  const runId = chosen ?? first;
  return { runs: list, run: list.find((r) => r.run_id === runId), runId, select: setChosen,
           loading: runs.isLoading, error: runs.isError };
}

function useCockpitData(runId: string | null) {
  const client = useQueryClient();
  const payments = useQuery({ queryKey: ["payments", runId], enabled: runId !== null,
                              queryFn: async () => (await api().payments(runId ?? undefined)).payments });
  const spending = useQuery({ queryKey: ["spending", runId], enabled: runId !== null,
                              queryFn: () => api().spending(runId ?? undefined) });

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(PATHS.events);
    const reload = () => {
      void client.invalidateQueries({ queryKey: ["runs"] });
      void client.invalidateQueries({ queryKey: ["payments"] });
      void client.invalidateQueries({ queryKey: ["spending"] });
    };
    for (const type of ["payment.decided", "ask.resolved"]) source.addEventListener(type, reload);
    source.onopen = reload;  // (re)connected: whatever happened meanwhile is in the read model
    return () => source.close();
  }, [client]);

  return { payments: payments.data ?? [], spending: spending.data, spendingState: spending.status,
           loading: payments.isLoading, failed: payments.isError };
}

function SpendingCard({ spending, state, payments }: { spending?: Spending; state: string; payments: Payment[] }) {
  // Counted by verdict *and* delivery stage (LEASH-130), not by tone: a decision the bank has not
  // acknowledged yet shares the "warn" tone with a genuine ask, and summing those would tell the
  // customer they have orders to answer that they do not. A decline the bank accepted is not an
  // approval either, so the stage alone is not enough.
  const at = (stage: Stage, state?: Payment["final_state"]) =>
    payments.filter((p) => stageOf(p) === stage && (state === undefined || p.final_state === state)).length;
  const waiting = payments.filter((p) => p.final_state === "waiting").length;
  if (!spending) {  // never a made-up amount
    return (
      <section className="card" aria-label="Spending">
        <div className="k">{state === "error" ? "Spending unavailable right now" : "Loading spending…"}</div>
      </section>
    );
  }
  const blocked = payments.filter((p) => statusOf(p)[1] === "bad").length;
  const period = spending?.period_days ?? null;
  const limit = spending?.limit_chf ? Number(spending.limit_chf) : null;
  const spent = spending ? Number(spending.approved_chf) : 0;
  const pct = period && limit ? Math.min(100, Math.round((spent / limit) * 100)) : null;
  const full = spending.remaining_chf !== null && Number(spending.remaining_chf) <= 0;
  return (
    <section className="card" aria-label="Spending">
      <div className="sum-row">
        <div>
          <div className="k">{period ? `Agent spent · last ${period} days` : "Agent spent"}</div>
          <div className="v">CHF {spending.approved_chf}</div>
        </div>
        {period && spending.remaining_chf && (
          <div>
            <div className="k right">Left in {period} days</div>
            <div className="v2">CHF {spending.remaining_chf}</div>
          </div>
        )}
      </div>
      {pct !== null && (
        <div className={`bar${full ? " full" : ""}`} role="progressbar" aria-label={`Spent of the ${period}-day limit`}
             aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
             aria-valuetext={`CHF ${spending.approved_chf} of CHF ${spending.limit_chf} spent, CHF ${spending.remaining_chf} left`}>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="counts">
        {/* "approved", never "paid": the bank accepting a decision is not evidence of settlement. */}
        <span className="chip ok">{at("accepted", "approved")} approved</span>
        {at("submitted") > 0 && <span className="chip warn">{at("submitted")} sending</span>}
        <span className="chip warn">{waiting} waiting for you</span>
        <span className="chip bad">{blocked} blocked</span>
        {at("not_sent") > 0 && <span className="chip dim">{at("not_sent")} not accepted</span>}
      </div>
    </section>
  );
}

function PaymentRow({ payment, onOpen }: { payment: Payment; onOpen: (id: string) => void }) {
  const [label, tone] = statusOf(payment);
  const first = payment.items[0]?.name ?? "";
  const more = payment.items.length > 1 ? ` +${payment.items.length - 1}` : "";
  return (
    <button type="button" className="row" onClick={() => onOpen(payment.authorization_id)}>
      <div className="ico" aria-hidden="true" />
      <div className="rmain">
        <div className="rname">{payment.merchant.name}</div>
        <div className="rsub">{zurichTime.format(new Date(payment.sim_time))} · via agent · {first}{more}</div>
      </div>
      <div className="ramt">
        CHF {payment.billing_amount_chf}
        {payment.currency !== "CHF" && <small>{payment.currency} {payment.amount}</small>}
        <span className={`chip ${tone}`} data-status={tone}>{label}</span>
      </div>
    </button>
  );
}

const RUN_STATE: Record<Run["status"], string> = { running: "Running", finished: "Finished", failed: "Stopped" };

function RunPicker({ runs, run, onSelect }: { runs: Run[]; run?: Run; onSelect: (id: string) => void }) {
  if (!run) return null;
  return (
    <section className="card" aria-label="Selected run">
      <div className="sum-row">
        {runs.length > 1 ? (
          <select className="field" aria-label="Run" value={run.run_id} onChange={(e) => onSelect(e.target.value)}>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.scenario_id} · {r.run_id} · {RUN_STATE[r.status]}</option>)}
          </select>
        ) : <div className="k">{run.scenario_id} · {run.run_id}</div>}
        <span className={`chip ${run.status === "running" ? "ok" : "dim"}`}>{RUN_STATE[run.status]}</span>
      </div>
      {run.status === "finished" && <p className="small">Finished: no more payments will arrive in this run.</p>}
      {run.status === "failed" && <p className="small">Stopped by the platform: no more payments will arrive in this run.</p>}
    </section>
  );
}

export function Cockpit() {
  const selection = useSelectedRun();
  const { payments, spending, spendingState, loading, failed } = useCockpitData(selection.runId);
  const [open, setOpen] = useState<string | null>(null);
  const byDay = new Map<string, Payment[]>();
  for (const p of [...payments].sort((a, b) => b.sim_time.localeCompare(a.sim_time))) {
    const day = zurichDay.format(new Date(p.sim_time));
    byDay.set(day, [...(byDay.get(day) ?? []), p]);
  }
  if (selection.loading) return <p className="empty">Loading your runs…</p>;
  if (selection.error) return <p className="empty">Your runs couldn't be loaded.</p>;
  if (selection.runId === null) return <p className="empty">No runs yet. Start one from your permission.</p>;
  return (
    <>
      <RunPicker runs={selection.runs} run={selection.run} onSelect={selection.select} />
      <SpendingCard spending={spending} state={spendingState} payments={payments} />
      {failed && <p className="empty">Payments couldn't be loaded right now.</p>}
      {!loading && !failed && payments.length === 0 && <p className="empty">No agent payments in this run yet.</p>}
      {[...byDay].map(([day, list]) => (
        <section key={day} aria-label={day}>
          <h2 className="glabel">{day}</h2>
          <div className="list">{list.map((p) => <PaymentRow key={p.authorization_id} payment={p} onOpen={setOpen} />)}</div>
        </section>
      ))}
      {open && <PaymentDetail authorizationId={open} onClose={() => setOpen(null)} />}
    </>
  );
}
