// LEASH-145: the failed-turn refetch raced against the retry that succeeds. Kept in its own file
// because holding a reply open leaves a pending fetch that breaks whatever test renders next.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import type { PolicyDraft } from "../api/client";
import { Agent } from "./Agent";

const INSTRUCTION = "Buy groceries for CHF 50 or less.";

function draft(extra: Partial<PolicyDraft> = {}): PolicyDraft {
  return {
    draft_id: "LD-1", revision: 1, instruction: INSTRUCTION, status: "needs_answers",
    rules: [{ text: "At most CHF 50.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "One item per order (DEC-013)", source: "team", decision: "DEC-013", tightened: false }],
    hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 50, currency: "CHF", scope: "purchase" }],
    uncertainty_policy: "ask",
    answers: [],
    notes: ["At most CHF 50.00 per order, delivery included.", "When unsure, I ask you."],
    open_questions: [
      { question_id: "Q-unsure", text: "When I'm unsure about a purchase, should I ask you, decline, or approve it?",
        blocking: true, options: ["Ask me", "Decline", "Approve"] },
      { question_id: "Q-split", text: "If two orders at the same shop within an hour go over CHF 50.00, should I ask you?",
        blocking: false, options: ["Yes, ask me", "No"] },
    ],
    ...extra,
  };
}






type Reply = { status: number; body: unknown; hold?: Promise<void> };

function stubFetch(replies: Record<string, Reply[]>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const queue = replies[`${method} ${url}`] ?? [{ status: 404, body: { error: { code: "not_found", message: "no" } } }];
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    if (reply.hold) await reply.hold;  // a read that lands late, after a later write already returned
    return new Response(JSON.stringify(reply.body), { status: reply.status });
  }));
  return calls;
}

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

async function settle() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}

/** Say something in the composer. The first one creates the draft; later ones are turns. */
async function say(text: string) {
  const composer = screen.getByRole("region", { name: "Say something" });
  fireEvent.change(within(composer).getByRole("textbox"), { target: { value: text } });
  fireEvent.click(within(composer).getByRole("button", { name: "Send" }));
  await settle();
}

/** The assistant's answer around a policy draft (LEASH-175): the chat goes through it now. */
const assistant = (body: PolicyDraft) => ({ draft: body, consent_text: [], questions: [], status: body.status });

async function start(first: PolicyDraft, more: Record<string, Reply[]> = {}) {
  const calls = stubFetch({ "POST /api/permission/drafts": [{ status: 200, body: assistant(first) }],
                            "GET /api/policies/drafts/LD-1": [{ status: 200, body: first }], ...more });
  render(wrap(<Agent />));
  await say(INSTRUCTION);
  await screen.findByRole("list", { name: "Rules as I read them" });
  return calls;
}

beforeEach(() => { try { sessionStorage.clear(); } catch { /* no storage */ } });
afterEach(() => vi.unstubAllGlobals());

describe("Agent conversation — a slow read against a fast write", () => {
  it("shows typing only while a request is pending and restores input after failure", async () => {
    let release!: () => void;
    const held = new Promise<void>((r) => { release = r; });
    stubFetch({ "POST /api/permission/drafts": [{ status: 503, hold: held,
      body: { error: { code: "model_unavailable", message: "Please retry." } } }] });
    render(wrap(<Agent />));
    await say(INSTRUCTION);
    expect(screen.getAllByRole("status").some((s) => s.textContent === "Reading your request…")).toBe(true);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.queryByRole("list", { name: "Rules as I read them" })).not.toBeInTheDocument();
    release();
    await settle();
    expect(screen.queryByText("Reading your request…")).not.toBeInTheDocument();
    expect(screen.getByLabelText("What may the agent buy?")).toHaveValue(INSTRUCTION);
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("a slow read cannot undo a turn the service recorded after it", async () => {
    // The refetch a failed turn triggers is still in flight when the retry succeeds. If that stale
    // read wins, the recorded turn stops matching and vanishes with no error at all — the same
    // transcript-versus-backend divergence, mirrored.
    let release!: () => void;
    const held = new Promise<void>((r) => { release = r; });
    const LANDED = draft({ revision: 2, instruction: `${INSTRUCTION} Only for delivery` });
    await start(draft(), {
      "POST /api/permission/drafts/LD-1/turns": [
        { status: 500, body: { error: { code: "internal_error", message: "Something went wrong." } } },
        { status: 200, body: assistant(LANDED) }],
      // the first read is the stale one the failure started, held open; later reads answer normally
      "GET /api/policies/drafts/LD-1": [{ status: 200, body: draft(), hold: held },
                                        { status: 200, body: LANDED }],
    });
    const turn = say("Only for delivery");        // fails, starts the refetch
    await settle();
    await say("Only for delivery");               // the retry lands while that read is still open
    release();
    await turn;
    await settle();
    await settle();

    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine).toEqual([INSTRUCTION, "Only for delivery"]);
  });
});
