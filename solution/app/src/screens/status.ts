// How a payment's outcome is labelled everywhere in the app.
//
// Two facts, never one (LEASH-130): `final_state` is what the engine decided, `delivery` is what the
// payment platform did with that decision. A purchase the platform terminally refused is not a payment,
// and an approval it has not acknowledged yet is not one either — it is submitted and waiting.
//
// The wording says only what the contract says. `delivery: "accepted"` means the platform accepted the
// authorization decision; it is not evidence that anything was settled, shipped or delivered, so no
// label here claims any of those.
import type { Payment } from "../api/client";

export type Tone = "ok" | "warn" | "bad" | "dim" | "off";

/** The four delivery stages the ticket names, for anyone who needs them without the label. */
export type Stage = "decided" | "submitted" | "accepted" | "not_sent";

export function stageOf(p: Payment): Stage {
  if (p.final_state === "not_sent" || p.delivery === "refused") return "not_sent";
  if (p.delivery === "accepted") return "accepted";
  if (p.final_state === "waiting") return "decided";  // decided, and still the customer's to answer
  return "submitted";                                  // decided and sent, no acknowledgement yet
}

export function statusOf(p: Payment): [string, Tone] {
  const byCustomer = p.resolved_by === "customer";
  if (p.delivery === "refused" && p.engine_verdict !== null) {
    // We answered; the platform would not take our answer. Not the same as a purchase the platform
    // never sent us in the first place, which has no verdict and reads "Not sent" below.
    return ["Not accepted by the bank", "off"];
  }
  switch (p.final_state) {
    case "approved":
      if (p.delivery !== "accepted") return [byCustomer ? "Approved · sending" : "Approved · sending", "warn"];
      return [byCustomer ? "Approved · you approved" : "Approved", "ok"];
    case "declined":
      return [byCustomer ? "You declined" : "Blocked", "bad"];
    case "waiting":
      return ["Waiting for you", "warn"];
    case "timed_out":
      return ["No answer", "dim"];
    case "not_sent":
      return ["Not sent", "off"];
  }
}

/** One line explaining the delivery, for a detail view. Empty when there is nothing worth saying. */
export function deliveryNote(p: Payment): string {
  switch (stageOf(p)) {
    case "submitted":
      return "Sent to the bank; waiting for it to confirm.";
    case "accepted":
      return "The bank accepted this decision. That is not confirmation that the order shipped.";
    case "not_sent":
      return p.platform_outcome
        ? `The bank did not accept this decision (${p.platform_outcome}), so nothing was paid.`
        : "The bank did not accept this decision, so nothing was paid.";
    case "decided":
      return "";
  }
}
