import { useQuery } from "@tanstack/react-query";
import { api, type Run } from "../api/client";
import { useCockpitData } from "./Cockpit";
import { statusOf, stageOf } from "./status";

/** Only recorded checkouts and platform outcomes; no simulated search progress. */
export function RunActivity({ initial }: { initial: Run }) {
  const query = useQuery({ queryKey: ["run", initial.run_id], queryFn: () => api().run(initial.run_id),
    initialData: initial, refetchInterval: 2000 });
  const run = query.data;
  const { payments, loading, failed } = useCockpitData(run.run_id);
  const count = (state: "approved" | "declined") => payments.filter(
    p => p.final_state === state && stageOf(p) === "accepted").length;
  const conflicts = payments.filter(p => stageOf(p) === "conflict").length;
  const outstanding = payments.filter(p => p.delivery === "pending").length;
  return <section aria-label="Shopping activity" aria-live="polite">
    <h2>{run.status === "finished" ? "Simulation complete" : run.status === "failed" ? "Simulation failed" : "Checking shop checkouts"}</h2>
    <p className="small">Run {run.run_id}</p>
    {(query.isError || failed) && <p role="alert">Activity could not be refreshed. These are the last recorded results.</p>}
    {!payments.length && <p>{loading ? "Loading checkouts…" : "No checkout recorded yet."}</p>}
    <ol>{payments.map(p => <li key={p.authorization_id}>
      <strong>{p.merchant.name}</strong> · CHF {p.billing_amount_chf} — {statusOf(p)[0]}
      <p className="small">{p.items.map(i => i.name).join(", ")}</p>
    </li>)}</ol>
    {conflicts > 0 && <p role="alert">{conflicts} platform outcome(s) differ from the local record. Review needed.</p>}
    <p>Platform accepted: {count("approved")} approvals, {count("declined")} declines.
      {outstanding > 0 && ` ${outstanding} outcome(s) still pending.`}</p>
    <p className="small">Authorization outcomes do not prove settlement, shipment or delivery.</p>
  </section>;
}
