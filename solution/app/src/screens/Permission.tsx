// Permission screen (LEASH-096): the current permission with its version, the rules the customer confirmed
// and the ones added since, and the two ways to tighten it — a lower per-order limit and "decline instead of
// asking" (DEC-006). Raising a limit is impossible here: the input only accepts a value below the current
// one. Revoking takes a second, in-page tap, and a revocation is shown only once Viseca has confirmed it.
// Changes apply to runs started afterwards; a running run keeps its snapshot (DEC-003). A run is started here
// with the active permission (LEASH-066); the scenario is typed, never chosen from a built-in list.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ApiError, api, type HardRule, type Mandate } from "../api/client";

const BILLING = "authorization.billing_amount_chf";

function perOrderLimit(m: Mandate): number | null {
  const limits = m.hard_rules
    .filter((r: HardRule) => r.field === BILLING && (r.scope ?? "purchase") === "purchase"
      && (r.currency ?? "CHF") === "CHF"
      && (r.operator === "<=" || r.operator === "<") && typeof r.value === "number")
    .map((r) => r.value as number);
  return limits.length ? Math.min(...limits) : null;
}

const chf = (value: number) => `CHF ${value.toFixed(2)}`;

export function Permission() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["mandates"], queryFn: () => api().mandates() });
  const [limit, setLimit] = useState("");
  const [scenario, setScenario] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const revokeButton = useRef<HTMLButtonElement>(null);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const [focusNext, setFocusNext] = useState<"confirm" | "revoke" | null>(null);
  useEffect(() => {  // the tapped button disappears: focus moves to its counterpart, never to the page
    if (focusNext === "confirm") confirmButton.current?.focus();
    if (focusNext === "revoke") revokeButton.current?.focus();
    setFocusNext(null);
  }, [focusNext, confirming]);

  if (query.isLoading) return <p className="empty">Loading your permission…</p>;
  if (query.isError) return <p className="empty">Your permission couldn't be loaded.</p>;
  const all = query.data?.mandates ?? [];
  const m = all.find((x) => x.mandate_id === query.data?.current_mandate_id) ?? all[all.length - 1];
  if (!m) return <p className="empty">No permission yet.</p>;

  const current = perOrderLimit(m);
  const typed = limit.trim();
  const wanted = /^\d+(\.\d{1,2})?$/.test(typed) ? Number(typed) : NaN;  // plain digits, at most two decimals
  const valid = Number.isFinite(wanted) && wanted > 0;
  const lower = valid && (current === null || wanted < current);
  const active = m.status === "active";

  async function run<T>(action: () => Promise<T>, done: string | ((result: T) => string)) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await action();
      setMessage(typeof done === "string" ? done : done(result));
      await client.invalidateQueries({ queryKey: ["mandates"] });
      await client.invalidateQueries({ queryKey: ["runs"] });
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message.replace(/^[a-z_]+: /, "") : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const revocation = m.status === "revoked"
    ? (m.revocation?.platform_confirmed ? "Revoked. Viseca confirmed: the agent can no longer pay."
      : "Revocation not confirmed by Viseca yet.") : null;

  return (
    <div className="perm">
      <section className="card" aria-label="Your permission">
        <div className="sum-row">
          <div className="k">Your permission</div>
          <span className="chip dim">Version {m.version}</span>
        </div>
        <p className="message">{m.instruction}</p>
        <ul className="rules">
          {m.rules.map((r) => (
            <li key={r.text} className={r.tightened ? "added" : undefined}>
              <span>{r.text}</span>
              {r.tightened && <span className="chip ok">Added</span>}
            </li>
          ))}
        </ul>
        <p className="small">When unsure, the agent {m.uncertainty_policy === "decline" ? "declines" : m.uncertainty_policy === "approve" ? "approves" : "asks you"}.
          {" "}Changes apply to runs started after this change; a run already going keeps its rules.</p>
      </section>

      {active && (
        <section className="card" aria-label="Tighten">
          <label className="k" htmlFor="limit">New limit per order (CHF)</label>
          <input id="limit" className="field" inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)}
                 aria-describedby="limit-hint" />
          <p id="limit-hint" className="small">
            {current === null ? "Set a limit per order." : `A limit can only go down from ${chf(current)}.`}
          </p>
          <button type="button" className="pill" disabled={busy || !lower}
                  onClick={() => run(() => api().tighten(m.mandate_id, { add_hard_rules: [
                    { field: BILLING, operator: "<=", value: wanted, currency: "CHF", scope: "purchase" }] }),
                  `The limit is now ${chf(wanted)} per order, for runs started from now on.`)}>
            Lower the limit
          </button>
          {m.uncertainty_policy !== "decline" && (
            <button type="button" className="pill light" disabled={busy}
                    onClick={() => run(() => api().tighten(m.mandate_id, { uncertainty_policy: "decline" }),
                      "When unsure, the agent now declines.")}>
              Decline instead of asking me
            </button>
          )}
        </section>
      )}

      {active && (
        <section className="card" aria-label="Start a run">
          <label className="k" htmlFor="scenario">Scenario</label>
          <input id="scenario" className="field" value={scenario} onChange={(e) => setScenario(e.target.value)}
                 aria-describedby="scenario-hint" />
          <p id="scenario-hint" className="small">The run uses version {m.version} of this permission, even if you tighten it later.</p>
          <button type="button" className="pill" disabled={busy || !scenario.trim()}
                  onClick={() => run(() => api().startRun(scenario.trim(), m.mandate_id),
                    (started) => `Run ${started.run_id} started with version ${started.mandate_version} of your permission.`)}>
            Start a run
          </button>
        </section>
      )}

      {active && (
        <section className="card" aria-label="Revoke">
          {!confirming ? (
            <button type="button" className="pill danger" disabled={busy} ref={revokeButton}
                    onClick={() => { setConfirming(true); setFocusNext("confirm"); }}>
              Revoke permission
            </button>
          ) : (
            <>
              <p className="small">The agent will not be able to pay anything more. For payments already waiting, the app shows only what the platform confirms.</p>
              <button type="button" className="pill danger" disabled={busy} ref={confirmButton}
                      onClick={() => run(async () => {
                        const revoked = await api().revoke(m.mandate_id);
                        if (!revoked.revocation?.platform_confirmed) {
                          throw new ApiError(202, "unconfirmed", "Viseca hasn't confirmed the revocation yet; the "
                                             + "permission may still be active.");
                        }
                      }, "Revoked. Viseca confirmed: the agent can no longer pay.").finally(() => setConfirming(false))}>
                Yes, revoke
              </button>
              <button type="button" className="link" disabled={busy}
                      onClick={() => { setConfirming(false); setFocusNext("revoke"); }}>Keep it</button>
            </>
          )}
        </section>
      )}

      <div role="status" aria-live="polite" className="small">{message ?? revocation}</div>
    </div>
  );
}
