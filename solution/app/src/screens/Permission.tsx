// The current permission, the selected run's fixed version, and server-rendered change reviews.
// Reading, tightening and revoking boundaries only: starting the agent belongs to the conversation,
// where the customer confirmed the permission in the first place (LEASH-147).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Mandate, type Run, type TightenRequest } from "../api/client";
import { PermissionSummary, perOrderLimit, permissionStatus } from "../components/PermissionSummary";

const chf = (value: number) => `CHF ${value.toFixed(2)}`;
type Proposal = { mandate: Mandate; change: TightenRequest; title: string };

export function Permission({ selectedRun, onChat }: { selectedRun?: Run; onChat?: () => void }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["mandates"], queryFn: () => api().mandates() });
  const history = useQuery({ queryKey: ["mandateVersions", selectedRun?.mandate_id], enabled: !!selectedRun,
    queryFn: () => api().mandateVersions(selectedRun!.mandate_id) });
  const [limit, setLimit] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const revokeButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const reviewPanel = useRef<HTMLElement>(null);
  const [focusNext, setFocusNext] = useState<"confirm" | "revoke" | null>(null);
  useEffect(() => {
    if (focusNext === "confirm") confirmButton.current?.focus();
    if (focusNext === "revoke") revokeButton.current?.focus();
    setFocusNext(null);
  }, [focusNext, confirming]);
  useEffect(() => { if (proposal) { reviewPanel.current?.focus(); reviewPanel.current?.scrollIntoView?.({ block: "start" }); } }, [proposal]);

  if (query.isLoading) return <p className="empty">Loading your permission…</p>;
  if (query.isError) return <p className="empty">Your permission couldn't be loaded.</p>;
  const all = query.data?.mandates ?? [];
  const m = all.find((x) => x.mandate_id === query.data?.current_mandate_id) ?? all[all.length - 1];
  if (!m) return <section className="card"><p>No permission yet.</p>
    {onChat && <button className="pill" onClick={onChat}>Set boundaries in chat</button>}</section>;

  const current = perOrderLimit(m.hard_rules);
  const wanted = /^\d+(\.\d{1,2})?$/.test(limit.trim()) ? Number(limit.trim()) : NaN;
  const lower = Number.isFinite(wanted) && wanted > 0 && (current === null || wanted < current);
  const active = m.status === "active";
  const snapshot = history.data?.versions.find((v) => v.version === selectedRun?.mandate_version);
  const stale = !!proposal && (proposal.mandate.mandate_id !== m.mandate_id || proposal.change.expected_version !== m.version || !active);

  async function run<T>(action: () => Promise<T>, done?: string, refresh = true) {
    setBusy(true); setMessage(null);
    try {
      await action();
      if (done) setMessage(done);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message.replace(/^[a-z_]+: /, "") : "That didn't work. Please try again.");
      if (error instanceof ApiError && error.code === "stale_version") {
        setProposal(null);
        if (!refresh) await client.invalidateQueries({ queryKey: ["mandates"] });
      }
    } finally {
      if (refresh) {
        await client.invalidateQueries({ queryKey: ["mandates"] });
        await client.invalidateQueries({ queryKey: ["mandate"] });
        await client.invalidateQueries({ queryKey: ["mandateVersions"] });
        await client.invalidateQueries({ queryKey: ["runs"] });
      }
      setBusy(false);
    }
  }

  async function preview(change: TightenRequest, title: string) {
    setProposal(null);
    const versioned = { ...change, expected_version: m.version };
    await run(async () => {
      const proposed = await api().previewTighten(m.mandate_id, versioned);
      if (!proposed.review) throw new Error("Missing review");
      setProposal({ mandate: proposed, change: versioned, title });
    }, undefined, false);
  }

  const revocation = m.status === "revoked"
    ? (m.revocation?.platform_confirmed ? "Revoked. Viseca confirmed: the agent can no longer pay."
      : "Revocation not confirmed by Viseca yet.") : null;

  return <div className="perm">
    <section className="card permission-control" aria-label="Permission status">
      <div className="sum-row"><strong>{permissionStatus(m)}</strong><span className="chip dim">Version {m.version}</span></div>
      <p className="small">{active ? "These boundaries apply to new simulations. Finishing a simulation does not revoke permission." : "Check the permission status before starting another simulation."}</p>
      {active && (!confirming ? <button className="pill light revoke-control" disabled={busy} ref={revokeButton}
        onClick={() => { setConfirming(true); setFocusNext("confirm"); }}>Revoke permission</button> : <>
        <p className="small">Stop further spending under this permission? We will show whether the platform confirms the revocation.</p>
        <button className="pill danger" disabled={busy} ref={confirmButton} onClick={() => run(async () => {
          const revoked = await api().revoke(m.mandate_id);
          if (!revoked.revocation?.platform_confirmed) throw new ApiError(202, "unconfirmed", "Viseca hasn't confirmed the revocation yet; the permission may still be active.");
          setProposal(null);
        }, "Revoked. Viseca confirmed: the agent can no longer pay.").finally(() => setConfirming(false))}>Yes, revoke</button>
        <button className="link" disabled={busy} onClick={() => { setConfirming(false); setFocusNext("revoke"); }}>Keep it</button>
      </>)}
    </section>
    <div role="status" aria-live="polite" className="small">{busy ? "Checking with Leash…" : message ?? revocation}</div>

    {proposal && <section className="card change-review" aria-label="Review permission change" tabIndex={-1} ref={reviewPanel}>
      <span className="chip warn">Not confirmed</span><h2>Review permission change</h2>
      <p className="message">{proposal.title}</p>
      <p className="small">Version {proposal.change.expected_version} → {proposal.mandate.version}. Applies only to new simulations. Existing simulations keep their confirmed rules.</p>
      <PermissionSummary review={proposal.mandate.review} expanded />
      {stale && <p role="alert">This permission changed. Cancel and review it again.</p>}
      <button className="pill" disabled={busy || stale} onClick={() => run(async () => {
        await api().tighten(proposal.mandate.mandate_id, proposal.change);
        setProposal(null); setLimit("");
      }, "Permission updated. The platform accepted the change for new simulations.")}>Confirm permission change</button>
      <button className="link" disabled={busy} onClick={() => setProposal(null)}>Cancel change</button>
    </section>}

    {selectedRun && <details className="card context-details">
      <summary>This simulation uses version {selectedRun.mandate_version}</summary>
      <p className="small">{selectedRun.run_id} · Permission {selectedRun.mandate_id}. This is the fixed version used to check its checkouts.</p>
      {history.isLoading ? <p className="small">Loading the confirmed version…</p> : snapshot ? <PermissionSummary review={snapshot.review} />
        : <p className="small">The confirmed version could not be loaded.</p>}
    </details>}

    <section className="card" aria-label="Your permission">
      <h2>Your confirmed boundaries</h2>
      <PermissionSummary review={m.review} />
      {m.hard_rules.some((r) => r.field === "leash.merchant.prior_purchases.v1") && <p className="small">Shop history is checked against earlier approved purchases on the same card, including earlier purchases in the simulation.</p>}
      <details className="context-details"><summary>Original instruction and rule evidence</summary>
        <p className="message">{m.instruction}</p>
        <ul className="rules">{m.rules.map((r, i) => <li key={i} className={r.tightened ? "added" : undefined}>
          <span>{r.text}</span>{r.tightened && <span className="chip ok">Added</span>}</li>)}</ul>
        <p className="small">Permission {m.mandate_id} · Version {m.version}. Historical activity supplies evidence; it does not add permission.</p>
      </details>
    </section>

    {active && <section className="card" aria-label="Tighten">
      <h2>Change your boundaries</h2>
      <p className="small">Changes apply to runs started after this change; a run already going keeps its rules. Every change needs a fresh review.</p>
      <label className="k" htmlFor="limit">New limit per order (CHF)</label>
      <input id="limit" className="field" disabled={busy} inputMode="decimal" value={limit} onChange={(e) => { setLimit(e.target.value); setProposal(null); }} aria-describedby="limit-hint" />
      <p id="limit-hint" className="small">{current === null ? "Set a limit per order." : `A limit can only go down from ${chf(current)}.`}</p>
      <button className="pill" disabled={busy || !lower} onClick={() => preview({ add_hard_rules: [
        { field: "authorization.billing_amount_chf", operator: "<=", value: wanted, currency: "CHF", scope: "purchase" }] },
        `${current === null ? "Set" : `Lower from ${chf(current)} to`} ${chf(wanted)} per order.`)}>Review lower limit</button>
      {m.uncertainty_policy !== "decline" && <button className="pill light" disabled={busy}
        onClick={() => preview({ uncertainty_policy: "decline" }, "Decline uncertain checkouts instead of asking you.")}>Review declining when uncertain</button>}
      {onChat && <button className="link" onClick={onChat}>Discuss a new permission in chat</button>}
    </section>}

  </div>;
}
