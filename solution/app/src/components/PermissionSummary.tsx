import type { HardRule, Mandate } from "../api/client";

export function perOrderLimit(rules: HardRule[]): number | null {
  const limits = rules.filter((r) => r.field === "authorization.billing_amount_chf" && !r.period_days
    && (r.scope ?? "purchase") === "purchase" && (r.currency ?? "CHF") === "CHF"
    && (r.operator === "<=" || r.operator === "<") && typeof r.value === "number");
  return limits.length ? Math.min(...limits.map((r) => Number(r.value))) : null;
}

export function permissionStatus(m: Mandate): string {
  if (m.status === "revoked" && !m.revocation?.platform_confirmed) return "Revocation unconfirmed";
  return m.status === "active" ? "Permission active" : m.status === "revoked" ? "Permission revoked" : "Permission expired";
}

export function PermissionSummary({ review, expanded = false }: { review: Mandate["review"]; expanded?: boolean }) {
  if (!review) return <p className="small">The rule summary could not be loaded. Check the recorded rules below.</p>;
  return <div className="permission-boundaries">
    {([["Must follow", review.must_follow], ["May choose", review.may_choose], ["Must ask", review.must_ask]] as const).map(([title, lines]) =>
      <section key={title} className="boundary-group" aria-label={title}>
        <h2>{title}</h2>
        {lines.length ? title === "May choose" && !expanded ? <details className="context-details"><summary>Choices within these boundaries</summary>
          <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul></details> : <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>
          : <p className="small">{title === "Must ask" ? "Uncertainty is handled by the rules above." : "No additional choices specified."}</p>}
      </section>)}
  </div>;
}
