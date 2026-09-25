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
import { perOrderLimit, logoState, permissionStatus } from "../components/PermissionSummary";
import type { RunSelection } from "../api/useSelectedRun";
import { Icon, LogoMark } from "../components/icons";

const zurichDay = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", day: "numeric", month: "short", year: "numeric" });
const zurichTime = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Zurich", hour: "2-digit", minute: "2-digit" });

export function useCockpitData(runId: string | null) {
  const client = useQueryClient();
  const payments = useQuery({ queryKey: ["payments", runId], refetchInterval: 2000, enabled: runId !== null,
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
      void client.invalidateQueries({ queryKey: ["mandate"] });
      void client.invalidateQueries({ queryKey: ["mandateVersions"] });
    };
    for (const type of ["payment.decided", "ask.resolved", "mandate.changed"]) source.addEventListener(type, reload);
    source.onopen = reload;  // (re)connected: whatever happened meanwhile is in the read model
    return () => source.close();
  }, [client]);

  return { payments: payments.data ?? [], spending: spending.data, spendingState: spending.status,
           loading: payments.isLoading, failed: payments.isError };
}

function SpendingCard({ spending, state, payments }: { spending?: Spending; state: string; payments: Payment[] }) {
  // Counted by verdict *and* delivery stage (LEASH-130), not by tone: a tone is how a label looks, and a
  // decline the bank accepted is not an approval, so the stage alone is not enough either.
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
          <div className="k">{period ? `Approved amount · last ${period} days` : "Approved across this simulation"}</div>
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
      <p className="small">{period ? "This rolling total is separate from the limit on each order." : "Total across orders, not a per-order budget."}</p>
      {Number(spending.awaiting_platform_chf) > 0 && <p className="small">CHF {spending.awaiting_platform_chf} of this amount is still awaiting platform confirmation.</p>}
      <div className="counts">
        {/* "approved", never "paid": the bank accepting a decision is not evidence of settlement. */}
        <span className="chip ok">{at("accepted", "approved")} approved</span>
        {at("submitted") > 0 && <span className="chip warn">{at("submitted")} sending</span>}
        <span className="chip ask">{waiting} waiting for you</span>
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
      <div className="ico" aria-hidden="true"><Icon name="merchant" size={20} /></div>
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

function RunPicker({ runs, run, onSelect, names }: { runs: Run[]; run?: Run; onSelect: (id: string) => void; names: Record<string, string> }) {
  if (!run) return null;
  return (
    <section className="card" aria-label="Selected run">
      <div className="sum-row">
        {runs.length > 1 ? (
          <select className="field" aria-label="Run" value={run.run_id} onChange={(e) => onSelect(e.target.value)}>
            {runs.map((r) => <option key={r.run_id} value={r.run_id}>{names[r.scenario_id] ?? r.scenario_id} · {r.run_id} · {RUN_STATE[r.status]}</option>)}
          </select>
        ) : <div className="k">{run.scenario_id} · {run.run_id}</div>}
        <span className={`chip ${run.status === "running" ? "ok" : "dim"}`}>{RUN_STATE[run.status]}</span>
      </div>
      {run.status === "finished" && <p className="small">Finished: no more payments will arrive in this run.</p>}
      {run.status === "failed" && <p className="small">Stopped by the platform: no more payments will arrive in this run.</p>}
    </section>
  );
}

// The run selection is owned by App.tsx, so the inspector panel beside the phone follows the same run.
export function Cockpit({ selection, onPermission, onChat }: { selection: RunSelection; onPermission?: () => void; onChat?: () => void }) {
  const { payments, spending, spendingState, loading, failed } = useCockpitData(selection.runId);
  const mandate = useQuery({ queryKey: ["mandate", selection.run?.mandate_id], enabled: !!selection.run,
    queryFn: () => api().mandate(selection.run!.mandate_id) });
  const versions = useQuery({ queryKey: ["mandateVersions", selection.run?.mandate_id], enabled: !!selection.run,
    queryFn: () => api().mandateVersions(selection.run!.mandate_id) });
  const catalogue = useQuery({ queryKey: ["scenarios"], enabled: !!selection.run, queryFn: () => api().scenarios() });
  const snapshot = versions.data?.versions?.find((v) => v.version === selection.run?.mandate_version);
  const limit = snapshot ? perOrderLimit(snapshot.hard_rules) : null;
  const waiting = payments.filter((p) => p.final_state === "waiting" && stageOf(p) === "decided");
  const [open, setOpen] = useState<string | null>(null);
  const byDay = new Map<string, Payment[]>();
  for (const p of [...payments].sort((a, b) => b.sim_time.localeCompare(a.sim_time))) {
    if (waiting.includes(p)) continue;
    const day = zurichDay.format(new Date(p.sim_time));
    byDay.set(day, [...(byDay.get(day) ?? []), p]);
  }
  if (selection.loading) return <p className="empty">Loading your runs…</p>;
  if (selection.error) return <p className="empty">Your runs couldn't be loaded.</p>;
  if (selection.runId === null) return <section className="card"><p className="empty">No runs yet. Start one from your permission.</p>
    {onChat && <button className="btn primary" onClick={onChat}>Set boundaries in chat</button>}
    {onPermission && <button className="btn ghost" onClick={onPermission}>View permission</button>}</section>;
  return (
    <>
      <section className="card cockpit-status" aria-label="Agent spending status">
        <div className="k">{catalogue.data?.scenarios?.find((s) => s.scenario_id === selection.run?.scenario_id)?.scenario_name ?? "Shopping simulation"}</div>
        <h2>{selection.run?.status === "finished" ? "Simulation finished" : selection.run?.status === "failed" ? "Simulation stopped" : "Simulation running"}</h2>
        <div className="counts"><LogoMark state={logoState(mandate.data?.status)} size={24} /><span className={`chip ${mandate.data?.status === "active" ? "ok" : "dim"}`}>
          {mandate.data?.status ? permissionStatus(mandate.data) : mandate.isError ? "Permission status unavailable" : "Checking permission…"}</span>
          <span className="chip dim">Uses version {selection.run?.mandate_version}</span></div>
        {limit !== null && <p className="order-boundary">CHF {limit.toFixed(2)} <span>per order{snapshot?.hard_rules.some((r) => r.field === "authorization.billing_amount_chf" && r.operator === "<" && r.value === limit && !r.period_days) ? " · strictly below this amount" : " maximum"}</span></p>}
        <p className="small">{mandate.data?.status === "active" ? "This permission still allows new simulations. Each checkout must pass its confirmed rules." : "The simulation status and spending permission are tracked separately."}</p>
        {onPermission && <button className="btn ghost" onClick={onPermission}>View permission and controls</button>}
      </section>
      {waiting.length > 0 && <section aria-label="Needs your decision" className="attention-section">
        <h2 className="glabel">Needs your decision · {waiting.length}</h2>
        <p className="small">Review the pending request to answer. Opening a checkout here shows its evidence.</p>
        <div className="list">{waiting.map((p) => <PaymentRow key={p.authorization_id} payment={p} onOpen={setOpen} />)}</div>
      </section>}
      <SpendingCard spending={spending} state={spendingState} payments={payments} />
      {failed && <p className="empty">Payments couldn't be loaded right now.</p>}
      {!loading && !failed && payments.length === 0 && <p className="empty">No agent payments in this run yet.</p>}
      {[...byDay].map(([day, list]) => (
        <section key={day} aria-label={day}>
          <h2 className="glabel">{day}</h2>
          <div className="list">{list.map((p) => <PaymentRow key={p.authorization_id} payment={p} onOpen={setOpen} />)}</div>
        </section>
      ))}
      <details className="card context-details simulation-picker"><summary>Simulation controls &amp; history</summary>
        <RunPicker runs={selection.runs} run={selection.run} onSelect={selection.select} names={Object.fromEntries((catalogue.data?.scenarios ?? []).map((s) => [s.scenario_id, s.scenario_name]))} />
        <p className="small">Permission {selection.run?.mandate_id} · Version {selection.run?.mandate_version}. Checkout times follow the scenario data.</p>
        {onPermission && <button className="btn ghost" onClick={onPermission}>Start another simulation</button>}
      </details>
      {open && <PaymentDetail authorizationId={open} onClose={() => setOpen(null)} />}
    </>
  );
}
