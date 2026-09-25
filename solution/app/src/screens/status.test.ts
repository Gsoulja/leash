// LEASH-130: the engine's verdict and the platform's acceptance are different facts, and the wording
// says only what the contract says — never that anything was settled, shipped or delivered.
import type { Payment } from "../api/client";
import { deliveryNote, stageOf, statusOf } from "./status";

function payment(extra: Partial<Payment> = {}): Payment {
  return {
    authorization_id: "AZ-1", run_id: "RUN-01",
    merchant: { merchant_id: "ME0022", name: "PixelHarbor", category: "electronics", country: "CH" },
    sim_time: "2026-08-12T09:40:00Z", amount: "289.00", currency: "CHF", billing_amount_chf: "289.00",
    items: [{ item_id: "IT0017", name: "monitor", quantity: 1, unit_price: "289.00" }],
    engine_verdict: "approve", final_state: "approved", delivery: "accepted", platform_outcome: "accepted",
    resolved_by: "engine", customer_message: "", ...extra,
  } as Payment;
}

describe("delivery and verdict are separate", () => {
  it("names all four stages the ticket distinguishes", () => {
    expect(stageOf(payment({ final_state: "waiting", delivery: "pending" }))).toBe("decided");
    expect(stageOf(payment({ delivery: "pending" }))).toBe("submitted");
    expect(stageOf(payment({ delivery: "accepted" }))).toBe("accepted");
    expect(stageOf(payment({ delivery: "refused", platform_outcome: "deadline_passed" }))).toBe("not_sent");
  });

  it("an approval the platform has not acknowledged is not shown as approved-and-done", () => {
    const [label, tone] = statusOf(payment({ delivery: "pending" }));
    expect(label).toBe("Approved · sending");
    expect(tone).not.toBe("ok");
  });

  it("a refused delivery is never shown as a payment", () => {
    const [label, tone] = statusOf(payment({ delivery: "refused", platform_outcome: "deadline_passed" }));
    expect(label).toBe("Not accepted by the bank");
    expect(tone).toBe("off");
  });

  it("a refused delivery on a declined purchase is still not a block by us", () => {
    expect(stageOf(payment({ final_state: "declined", delivery: "refused" }))).toBe("not_sent");
  });

  it("a purchase the platform never sent us reads differently from one it refused our answer for", () => {
    const never = payment({ final_state: "not_sent", engine_verdict: null, delivery: "pending",
                            platform_outcome: null, resolved_by: null });
    expect(statusOf(never)).toEqual(["Not sent", "off"]);
    const refused = payment({ final_state: "not_sent", engine_verdict: "approve", delivery: "refused",
                              platform_outcome: "deadline_passed" });
    expect(statusOf(refused)).toEqual(["Not accepted by the bank", "off"]);
  });

  it("an ask is still the customer's to answer, whatever the delivery says", () => {
    expect(statusOf(payment({ final_state: "waiting", delivery: "pending", resolved_by: null })))
      .toEqual(["Waiting for you", "warn"]);
  });

  it("no label claims the order was settled, shipped or delivered", () => {
    const states: Payment["final_state"][] = ["approved", "declined", "waiting", "timed_out", "not_sent"];
    const deliveries: Payment["delivery"][] = ["pending", "accepted", "refused"];
    const claims = /\b(paid|settled|shipped|delivered|dispatched|on its way|arriving)\b/i;
    for (const final_state of states) {
      for (const delivery of deliveries) {
        const [label] = statusOf(payment({ final_state, delivery }));
        expect(label, `${final_state}/${delivery}`).not.toMatch(claims);
      }
    }
  });

  it("the delivery note says what accepted does and does not mean", () => {
    expect(deliveryNote(payment({ delivery: "accepted" }))).toContain("not confirmation of a completed payment");
    expect(deliveryNote(payment({ delivery: "pending" }))).toContain("waiting for it to confirm");
    expect(deliveryNote(payment({ delivery: "refused", platform_outcome: "deadline_passed" })))
      .toContain("deadline_passed");
    expect(deliveryNote(payment({ final_state: "waiting", delivery: "pending" }))).toBe("");
  });
});

describe("no user-facing string claims the order was settled or shipped", () => {
  // The sweep above only exercises `statusOf`. A label somewhere else in the app is just as visible —
  // the cockpit's summary chip said "N paid" for exactly the accepted state, which the sweep could not
  // reach. This reads the source of every screen instead.
  const SETTLEMENT = /\b(paid|settled|shipped|delivered|dispatched|en route|on its way|arriving)\b/i;

  it.each([
    "Cockpit.tsx", "PaymentDetail.tsx", "StepUp.tsx", "Permission.tsx", "Agent.tsx", "status.ts",
  ])("%s", (file) => {
    const { readFileSync } = require("node:fs") as typeof import("node:fs");
    const { resolve } = require("node:path") as typeof import("node:path");
    const source = readFileSync(resolve(__dirname, file === "status.ts" ? file : file), "utf8");
    const offenders = source
      .split("\n")
      .map((line, i) => [i + 1, line] as const)
      // Comments explain the rule; only rendered text can mislead a customer. A `label:` or `agreed:`
      // in test-shaped data does not appear here because these are the components, not the tests.
      .filter(([, line]) => !line.trimStart().startsWith("//") && !line.trimStart().startsWith("*"))
      // "…is not confirmation of a completed payment" and "…so nothing was paid" are the opposite of
      // the claim being swept for, so a negation before the word in the same sentence clears the line.
      .filter(([, line]) => {
        const text = line.replace(/\/\*[\s\S]*?\*\//g, "");
        if (!SETTLEMENT.test(text)) return false;
        return !/\b(not|nothing|never|no|didn't|did not)\b[^.?!]*?\b(paid|settled|shipped|delivered|dispatched|en route|on its way|arriving)\b/i.test(text);
      })
      .map(([n, line]) => `${file}:${n}: ${line.trim()}`);
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});


it("a decline still awaiting the platform is not presented as confirmed", () => {
  const pending = payment({ final_state: "declined", delivery: "pending", engine_verdict: "decline" });
  expect(statusOf(pending)).toEqual(["Declined · sending", "warn"]);
  expect(deliveryNote(pending)).toContain("waiting for it to confirm");
  expect(deliveryNote({ ...pending, delivery: "accepted" })).toContain("confirmed the decline");
  expect(deliveryNote({ ...pending, delivery: "accepted" })).not.toContain("shipped");
});
