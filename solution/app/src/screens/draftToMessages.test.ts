import type { PolicyDraft } from "../api/client";
import { draftToMessages } from "./draftToMessages";

function draft(extra: Partial<PolicyDraft> = {}): PolicyDraft {
  return {
    draft_id: "LD-1", revision: 1, instruction: "Buy a 27-inch monitor, no more than CHF 400", status: "needs_answers",
    rules: [{ text: "At most CHF 400.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "One item per order (DEC-013)", source: "team", decision: "DEC-013", tightened: false }],
    hard_rules: [], uncertainty_policy: "ask",
    notes: ["When unsure, I ask you."],
    open_questions: [
      { question_id: "Q-unsure", text: "When I'm unsure, should I ask you?", blocking: true, options: ["Ask me", "Decline"] },
      { question_id: "Q-split", text: "Should I watch for split orders?", blocking: false },
    ],
    ...extra,
  };
}

describe("draftToMessages", () => {
  it("starts with the customer's instruction", () => {
    expect(draftToMessages(draft())[0]).toEqual({ id: "instruction", kind: "customer", text: "Buy a 27-inch monitor, no more than CHF 400" });
  });

  it("every rule becomes one rule chip", () => {
    const rules = draftToMessages(draft()).filter((m) => m.kind === "rule");
    expect(rules).toEqual([
      { id: "rule-0", kind: "rule", label: "Your words", value: "At most CHF 400.00 per order, delivery included", tone: "neutral",
        decision: undefined, group: "Rules as I read them" },
      { id: "rule-1", kind: "rule", label: "Team reading", value: "One item per order (DEC-013)", tone: "neutral",
        decision: "DEC-013", group: "Rules as I read them" },
    ]);
  });

  it("open questions follow the rules and notes in order", () => {
    expect(draftToMessages(draft()).map((m) => m.id)).toEqual(
      ["instruction", "rule-0", "rule-1", "note-0", "q-Q-unsure", "q-Q-split"]);
    const q = draftToMessages(draft()).find((m) => m.id === "q-Q-unsure");
    expect(q).toEqual({ id: "q-Q-unsure", kind: "question", questionId: "Q-unsure", text: "When I'm unsure, should I ask you?",
                        blocking: true, options: ["Ask me", "Decline"] });
  });

  it("no message is produced for data the draft lacks", () => {
    const bare = draftToMessages(draft({ rules: [], notes: [], open_questions: [] }));
    expect(bare).toEqual([{ id: "instruction", kind: "customer", text: "Buy a 27-inch monitor, no more than CHF 400" }]);
  });

  it("rebuilds the same messages, with the same ids, from the same draft (a reload adds no duplicates)", () => {
    expect(draftToMessages(draft())).toEqual(draftToMessages(structuredClone(draft())));
  });

  it("never has the assistant claim to search, shop or pay (DEC-033)", () => {
    const text = JSON.stringify(draftToMessages(draft()).filter((m) => m.kind !== "customer" && m.kind !== "rule"));
    expect(text).not.toMatch(/search|shopping|I'll buy|I will buy|I paid|I'll pay/i);
  });
});
