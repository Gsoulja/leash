// How a payment's outcome is labelled everywhere in the app (contract: Payment.final_state).
import type { Payment } from "../api/client";

export type Tone = "ok" | "warn" | "bad" | "dim" | "off";

export function statusOf(p: Payment): [string, Tone] {
  const byCustomer = p.resolved_by === "customer";
  switch (p.final_state) {
    case "approved": return [byCustomer ? "Paid · you approved" : "Paid", "ok"];
    case "declined": return [byCustomer ? "You declined" : "Blocked", "bad"];
    case "waiting": return ["Waiting for you", "warn"];
    case "timed_out": return ["No answer", "dim"];
    case "not_sent": return ["Not sent", "off"];
  }
}
