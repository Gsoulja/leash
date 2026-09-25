// The strictest per-purchase CHF limit among hard rules (a tightened mandate may carry several, DEC-006). Shared by
// the Permission screen (the mandate) and the chat's summary card (the posted platform draft), so both show the same
// hard stop.
import type { HardRule } from "../api/client";

const BILLING = "authorization.billing_amount_chf";

export function perOrderLimitOf(rules: HardRule[]): number | null {
  const limits = rules
    .filter((r) => r.field === BILLING && (r.scope ?? "purchase") === "purchase"
      && (r.currency ?? "CHF") === "CHF"
      && (r.operator === "<=" || r.operator === "<") && typeof r.value === "number")
    .map((r) => r.value as number);
  return limits.length ? Math.min(...limits) : null;
}
