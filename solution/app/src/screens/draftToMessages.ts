// The Agent screen's transcript, derived from the draft it already loads (LEASH-190): nothing that the draft does
// not contain, and ids taken from the draft's own content, so a reload rebuilds the same messages without
// duplicates. The draft carries no answered-question history, so none is shown (LEASH-145 adds that).
import type { PolicyDraft } from "../api/client";
import type { ChatMessage } from "../components/chat/Transcript";

const SOURCE: Record<PolicyDraft["rules"][number]["source"], string> = {
  customer: "Your words", team: "Team reading", viseca: "Viseca rule", assumption: "Assumption",
};

export const RULES_GROUP = "Rules as I read them";

export function draftToMessages(d: PolicyDraft): ChatMessage[] {
  return [
    { id: "instruction", kind: "customer", text: d.instruction },
    // The draft says where each reading comes from, not what kind of rule it is, so every chip is neutral.
    ...d.rules.map((r, i): ChatMessage => ({ id: `rule-${i}`, kind: "rule", label: SOURCE[r.source], value: r.text,
                                             tone: "neutral", decision: r.decision ?? undefined, group: RULES_GROUP })),
    ...d.notes.map((n, i): ChatMessage => ({ id: `note-${i}`, kind: "assistant", text: n })),
    ...d.open_questions.map((q): ChatMessage => ({ id: `q-${q.question_id}`, kind: "question", questionId: q.question_id,
                                                  text: q.text, blocking: q.blocking, options: q.options })),
  ];
}
