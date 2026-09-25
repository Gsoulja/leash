import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import type { PlatformDraft, PolicyDraft } from "../api/client";
import { Agent } from "./Agent";

const INSTRUCTION = "Buy groceries for CHF 50 or less.";

function draft(extra: Partial<PolicyDraft> = {}): PolicyDraft {
  return {
    draft_id: "LD-1", revision: 1, instruction: INSTRUCTION, status: "needs_answers",
    rules: [{ text: "At most CHF 50.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "One item per order (DEC-013)", source: "team", decision: "DEC-013", tightened: false }],
    hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 50, currency: "CHF", scope: "purchase" }],
    uncertainty_policy: "ask",
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

const READY = draft({ status: "ready", uncertainty_policy: "decline", open_questions: [
  { question_id: "Q-split", text: "If two orders at the same shop within an hour go over CHF 50.00, should I ask you?",
    blocking: false, options: ["Yes, ask me", "No"] }] });

const POSTED: PlatformDraft = {
  draft_id: "LD-1", platform_draft_id: "PD-77", instruction: INSTRUCTION,
  hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 50, currency: "CHF", scope: "purchase" }],
  uncertainty_policy: "decline", guidance: [],
  open_questions: ["If two orders at the same shop within an hour go over CHF 50.00, should I ask you?"],
};

type Reply = { status: number; body: unknown };

function stubFetch(replies: Record<string, Reply[]>) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const queue = replies[`${method} ${url}`] ?? [{ status: 404, body: { error: { code: "not_found", message: "no" } } }];
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
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

async function start(first: PolicyDraft) {
  const calls = stubFetch({ "POST /api/policies/drafts": [{ status: 201, body: first }] });
  render(wrap(<Agent />));
  fireEvent.change(screen.getByLabelText("What may the agent buy?"), { target: { value: INSTRUCTION } });
  fireEvent.click(screen.getByRole("button", { name: "Read my instruction" }));
  await screen.findByRole("list", { name: "Rules as I read them" });
  return calls;
}

type Call = { method: string; url: string; body: unknown };
const posts = (calls: Call[], path: string) =>
  calls.filter((c) => c.method === "POST" && c.url === path);

beforeEach(() => { try { sessionStorage.clear(); } catch { /* no storage */ } });
afterEach(() => vi.unstubAllGlobals());

describe("Agent screen", () => {
  it("confirm is disabled while questions are open", async () => {
    const calls = await start(draft());
    const review = screen.getByRole("button", { name: "Review permission" });
    expect(review).toBeDisabled();
    expect(screen.getByText(/answer the questions marked/i)).toBeInTheDocument();
    fireEvent.click(review);
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/submit")).toEqual([]);
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);
  });

  it("renders the rules and notes from the draft", async () => {
    const calls = await start(draft());
    expect(posts(calls, "/api/policies/drafts")[0].body).toEqual({ instruction: INSTRUCTION });
    const rules = screen.getByRole("list", { name: "Rules as I read them" });
    expect(within(rules).getByText("At most CHF 50.00 per order, delivery included")).toBeInTheDocument();
    expect(within(rules).getByText("One item per order (DEC-013)")).toBeInTheDocument();
    expect(within(rules).getByText("DEC-013")).toBeInTheDocument();  // a team reading names its decision
    expect(screen.getByText("When unsure, I ask you.")).toBeInTheDocument();
    expect(screen.getByText(INSTRUCTION)).toBeInTheDocument();
  });

  it("marks optional questions and lets them stay open", async () => {
    await start(draft());
    const optional = screen.getByRole("group", { name: /two orders at the same shop/ });
    expect(within(optional).getByText("Optional")).toBeInTheDocument();
    const blocking = screen.getByRole("group", { name: /When I'm unsure/ });
    expect(within(blocking).getByText("Needed")).toBeInTheDocument();
  });

  it("an option answer is sent and the new draft is shown", async () => {
    await start(draft());
    const calls = stubFetch({ "POST /api/policies/drafts/LD-1/answers": [{ status: 200, body: READY }] });
    const group = screen.getByRole("group", { name: /When I'm unsure/ });
    fireEvent.click(within(group).getByRole("button", { name: "Decline" }));
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/answers")[0].body)
      .toEqual({ answers: [{ question_id: "Q-unsure", answer: "Decline" }] });
    expect(screen.queryByRole("group", { name: /When I'm unsure/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review permission" })).toBeEnabled();
  });

  it("a refused free-text answer shows the reason and keeps the question", async () => {
    await start(draft());
    stubFetch({ "POST /api/policies/drafts/LD-1/answers": [{ status: 422, body: { error: {
      code: "invalid_answer", message: "\"Maybe\" doesn't answer this question: it doesn't say anything I can use" } } }] });
    const group = screen.getByRole("group", { name: /When I'm unsure/ });
    fireEvent.change(within(group).getByLabelText("Your answer"), { target: { value: "Maybe" } });
    fireEvent.click(within(group).getByRole("button", { name: "Send" }));
    await settle();
    expect(within(group).getByRole("alert")).toHaveTextContent("doesn't answer this question");
    expect(screen.getByRole("group", { name: /When I'm unsure/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review permission" })).toBeDisabled();
  });

  it("the confirm step shows the exact platform draft, and only Confirm activates it", async () => {
    await start(READY);
    const calls = stubFetch({
      "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
      "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: {
        mandate_id: "TM-9", version: 1, status: "active", instruction: INSTRUCTION, rules: READY.rules,
        hard_rules: POSTED.hard_rules, uncertainty_policy: "decline", applies_from: "next run", revocation: null } }],
    });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    const exact = await screen.findByRole("region", { name: "What Viseca received" });
    expect(within(exact).getByText("PD-77")).toBeInTheDocument();
    expect(within(exact).getByText("authorization.billing_amount_chf <= 50 CHF per purchase")).toBeInTheDocument();
    expect(within(exact).getByText(/When unsure: decline/)).toBeInTheDocument();
    expect(within(exact).getByText(INSTRUCTION)).toBeInTheDocument();  // the posted copy, not the local one
    const unasked = within(exact).getByRole("list", { name: "Questions left open (sent as they are)" });
    expect(within(unasked).getByText(/two orders at the same shop/)).toBeInTheDocument();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);  // nothing is active before the tap

    fireEvent.click(screen.getByRole("button", { name: "Confirm permission" }));
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")[0].body).toEqual({ confirmed: true });
    expect(screen.getByRole("status")).toHaveTextContent("Confirmed. Version 1 is active for runs started from now on.");
    expect(screen.queryByRole("button", { name: "Confirm permission" })).not.toBeInTheDocument();
  });

  it("a submit refused by the service shows why and posts nothing more", async () => {
    await start(READY);
    const calls = stubFetch({ "POST /api/policies/drafts/LD-1/submit": [{ status: 409, body: { error: {
      code: "questions_open", message: "blocking questions remain" } } }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    await settle();
    expect(screen.getByRole("status")).toHaveTextContent("blocking questions remain");
    expect(screen.queryByRole("button", { name: "Confirm permission" })).not.toBeInTheDocument();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);
  });
});

describe("Agent screen as a conversation (LEASH-190)", () => {
  it("greets without claiming to search, shop or pay (DEC-033)", () => {
    stubFetch({});
    render(wrap(<Agent />));
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(log).toHaveTextContent(/Nothing is active until you confirm/);
    expect(log.textContent).not.toMatch(/search|shopping|I'll buy|I'll pay/i);
  });

  it("shows the instruction as the customer's turn and each rule as a chip", async () => {
    await start(draft());
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(within(log).getByText(INSTRUCTION).closest(".bubble")).toHaveClass("bubble-customer");
    const rules = within(log).getByRole("list", { name: "Rules as I read them" });
    expect(within(rules).getAllByRole("listitem")).toHaveLength(2);
    expect(within(rules).getAllByText(/^ADDED TO PERMISSION · /)).toHaveLength(2);
  });

  it("a reload with a stored draft rebuilds the same transcript, without duplicates", async () => {
    sessionStorage.setItem("leash.draft_id", "LD-1");
    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: draft() }] });
    render(wrap(<Agent />));
    const rules = await screen.findByRole("list", { name: "Rules as I read them" });
    expect(within(rules).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getAllByText(INSTRUCTION)).toHaveLength(1);
    expect(screen.getAllByRole("group", { name: /When I'm unsure/ })).toHaveLength(1);
  });
});

describe("the consent moment in the chat (LEASH-191)", () => {
  const TWO_RULES: PlatformDraft = { ...POSTED, hard_rules: [
    ...POSTED.hard_rules, { field: "items.quantity", operator: "<=", value: 1, scope: "purchase" }] };
  const ACTIVE = { mandate_id: "TM-9", version: 3, status: "active", instruction: INSTRUCTION, rules: READY.rules,
                   hard_rules: POSTED.hard_rules, uncertainty_policy: "decline", applies_from: "next run", revocation: null };

  it("confirm is not offered before the draft is posted", async () => {
    await start(READY);
    stubFetch({});
    expect(screen.getByRole("button", { name: "Review permission" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Confirm permission" })).toBeNull();
    expect(screen.queryByRole("region", { name: "What Viseca received" })).toBeNull();
  });

  it("summary card lists every posted hard rule", async () => {
    await start(READY);
    stubFetch({ "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: TWO_RULES }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    const card = await screen.findByRole("region", { name: "What Viseca received" });
    expect(within(screen.getByRole("log", { name: "Conversation" })).getByRole("region", { name: "What Viseca received" })).toBe(card);
    const exact = within(card).getByRole("list", { name: "Exact rules sent to Viseca" });
    expect(within(exact).getAllByRole("listitem").map((li) => li.textContent)).toEqual(
      ["authorization.billing_amount_chf <= 50 CHF per purchase", "items.quantity <= 1 per purchase"]);
    expect(within(card).getByRole("group", { name: "Hard stop at CHF 50.00" })).toBeInTheDocument();
    expect(card.textContent).not.toMatch(/Face ID|approve every purchase|search|I'll buy/i);
  });

  it("a confirmed permission posts one active system chip", async () => {
    await start(READY);
    stubFetch({ "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
                "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: ACTIVE }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm permission" }));
    await settle();
    expect(screen.getAllByText("Permission active · version 3")).toHaveLength(1);
    expect(screen.getByText("Permission active · version 3").closest(".system-chip")).toHaveClass("allowed");
    expect(screen.queryByRole("button", { name: "Confirm permission" })).toBeNull();
    expect(screen.getByRole("img", { name: "Agent permission: active" })).toBeInTheDocument();
  });

  it("a failed confirm stays actionable and says why", async () => {
    await start(READY);
    stubFetch({ "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
                "POST /api/policies/drafts/LD-1/confirm": [{ status: 409, body: { error: { code: "stale", message: "draft changed" } } }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm permission" }));
    await settle();
    expect(screen.getByRole("status")).toHaveTextContent("draft changed");
    expect(screen.getByRole("button", { name: "Confirm permission" })).toBeEnabled();
  });

  it("the header names the assistant and the bar counts the draft's rules", async () => {
    await start(READY);
    expect(screen.getByRole("banner", { name: "Permission assistant" })).toHaveTextContent("Setting up your permission");
    expect(screen.getByRole("img", { name: "Agent permission: none" })).toBeInTheDocument();
    const bar = screen.getByRole("button", { name: /Permission draft · 2 rules/ });
    expect(bar).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(bar);
    expect(bar).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list", { name: "Rules in this permission" })).toBeInTheDocument();
  });
});

describe("the handoff's Do not ship list (LEASH-194)", () => {
  it("no chat message can alter a confirmed permission: after Confirm the chat takes no input", async () => {
    await start(READY);
    stubFetch({ "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
                "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: {
                  mandate_id: "TM-9", version: 1, status: "active", instruction: INSTRUCTION, rules: READY.rules,
                  hard_rules: POSTED.hard_rules, uncertainty_policy: "decline", applies_from: "next run", revocation: null } }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm permission" }));
    await settle();
    expect(screen.getByText("Permission active · version 1")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons.filter((t) => !/^(Permission active · 1 rule|Permission active · \d+ rules|Start a new instruction)/.test(t ?? ""))).toEqual([]);
  });
});
