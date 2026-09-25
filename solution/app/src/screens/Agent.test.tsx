import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import type { PlatformDraft, PolicyDraft } from "../api/client";
import { Agent } from "./Agent";

const INSTRUCTION = "Buy groceries for CHF 50 or less.";

function draft(extra: Partial<PolicyDraft> = {}): PolicyDraft {
  return {
    draft_id: "LD-1", revision: 1, instruction: INSTRUCTION, status: "needs_answers",
    rules: [{ text: "At most CHF 50.00 per order, delivery included", source: "customer", decision: null, tightened: false },
            { text: "One item per order", source: "team", decision: "DEC-013", tightened: false }],
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

const SPLIT_ONLY = [{ question_id: "Q-split", blocking: false,
                      text: "If two orders at the same shop within an hour go over CHF 50.00, should I ask you?",
                      options: ["Yes, ask me", "No"] }];

const ANSWERED = [{ question_id: "Q-unsure", answer: "Decline",
                    question: "When I'm unsure about a purchase, should I ask you, decline, or approve it?" }];

const READY = draft({ status: "ready", uncertainty_policy: "decline", open_questions: SPLIT_ONLY,
                      answers: ANSWERED });

const POSTED: PlatformDraft = {
  draft_id: "LD-1", platform_draft_id: "PD-77", instruction: INSTRUCTION,
  hard_rules: [{ field: "authorization.billing_amount_chf", operator: "<=", value: 50, currency: "CHF", scope: "purchase" }],
  uncertainty_policy: "decline", guidance: [],
  open_questions: ["If two orders at the same shop within an hour go over CHF 50.00, should I ask you?"],
};

const MANDATE = {
  mandate_id: "TM-9", version: 1, status: "active", instruction: INSTRUCTION, rules: READY.rules,
  hard_rules: POSTED.hard_rules, uncertainty_policy: "decline", applies_from: "next run", revocation: null,
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

/** Say something in the composer. The first one creates the draft; later ones are turns. */
async function say(text: string) {
  const composer = screen.getByRole("region", { name: "Say something" });
  fireEvent.change(within(composer).getByRole("textbox"), { target: { value: text } });
  fireEvent.click(within(composer).getByRole("button", { name: "Send" }));
  await settle();
}

/** The assistant's answer around a policy draft (LEASH-175): the chat now goes through it, and it
 *  hands back the policy service's own draft unaltered, plus what the customer is asked to agree to. */
const assistant = (body: PolicyDraft) => ({ draft: body, consent_text: [], questions: [], status: body.status });

it("restores superseded messages, answers and earlier interpretations in conversation order", async () => {
  sessionStorage.clear();
  sessionStorage.setItem("leash.draft_id", "LD-1");
  const edited = draft({ revision: 3, instruction: "Only books.", answers: [],
    customer_turn: { text: "Only books.", replaced: true } });
  const current = { ...edited, revisions: [draft(), { ...READY, revision: 2 }, edited],
    messages: [{ text: "Where did I shop?", reply: "Your earlier shop.", revision: 2, context: {} }] };
  stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: current }] });
  const view = render(wrap(<Agent />));
  await screen.findByText("Only books.");
  const messages = () => [...screen.getByRole("log").querySelectorAll(".bubble.me .message")].map((node) => node.textContent);
  expect(messages()).toEqual([INSTRUCTION, "Decline", "Where did I shop?", "Only books."]);
  expect(screen.getByText("Your earlier shop.")).toBeInTheDocument();
  expect(screen.getByText("Earlier draft · revision 1")).toBeInTheDocument();
  view.unmount();
  render(wrap(<Agent />));
  await screen.findByText("Only books.");
  expect(messages()).toEqual([INSTRUCTION, "Decline", "Where did I shop?", "Only books."]);
  cleanup();
});

it("keeps history questions asked before creating a draft across reloads", async () => {
  sessionStorage.clear();
  stubFetch({ "POST /api/permission/drafts": [{ status: 200, body: {
    kind: "history", draft: null, reply: "Your earlier shop.", status: "ready", questions: [], consent_text: [],
  } }] });
  const view = render(wrap(<Agent />));
  await say("Where did I shop?");
  view.unmount();
  render(wrap(<Agent />));
  expect(screen.getByText("Where did I shop?")).toBeInTheDocument();
  expect(screen.getByText("Your earlier shop.")).toBeInTheDocument();
  cleanup();
});

async function start(first: PolicyDraft, more: Record<string, Reply[]> = {}) {
  const calls = stubFetch({ "POST /api/permission/drafts": [{ status: 200, body: assistant(first) }],
                            "GET /api/policies/drafts/LD-1": [{ status: 200, body: first }], ...more });
  render(wrap(<Agent />));
  await say(INSTRUCTION);
  await screen.findByRole("list", { name: "Rules as I read them" });
  return calls;
}

type Call = { method: string; url: string; body: unknown };
const posts = (calls: Call[], path: string) => calls.filter((c) => c.method === "POST" && c.url === path);

beforeEach(() => { try { sessionStorage.clear(); } catch { /* no storage */ } });
afterEach(() => vi.unstubAllGlobals());

describe("Agent conversation (LEASH-145)", () => {
  it("explains the purchase-count question in an older saved draft without guessing its value", async () => {
    await start(draft({ open_questions: [{ question_id: "AQ-old", blocking: true,
      text: "I drafted a rule you didn't say in those words, so it stays an unconfirmed suggestion: leash.purchase.max_count.v2. Do you want it?" }] }));
    expect(screen.getByRole("group", { name: /How many purchases should this permission allow in total/ })).toBeInTheDocument();
    expect(screen.queryByText(/leash\.purchase\.max_count/)).not.toBeInTheDocument();
  });

  it("opens with a greeting and one composer, and says what Wallet Control is not", async () => {
    stubFetch({});
    render(wrap(<Agent />));
    const greeting = screen.getByText(/I'm your Wallet Control, your permission assistant/);
    expect(greeting).toBeInTheDocument();
    expect(greeting).toHaveTextContent(/don't search or buy anything myself/);  // not the shopping agent
    expect(screen.getByLabelText("What may the agent buy?")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Send" })).toHaveLength(1);
    expect(screen.queryByRole("list", { name: "Rules as I read them" })).not.toBeInTheDocument();
  });

  it("shows the customer's words as their own message, then how Wallet Control read them", async () => {
    const calls = await start(draft());
    expect(posts(calls, "/api/permission/drafts")[0].body).toEqual({ text: INSTRUCTION });
    expect(screen.getByText(INSTRUCTION)).toBeInTheDocument();
    expect(screen.getByText(/Got it\./)).toBeInTheDocument();  // acknowledged before the boundaries
    const rules = screen.getByRole("list", { name: "Rules as I read them" });
    expect(within(rules).getByText("At most CHF 50.00 per order, delivery included")).toBeInTheDocument();
    expect(screen.getByText("When unsure, I ask you.")).toBeInTheDocument();
  });

  it("never labels its own default as something the customer asked for", async () => {
    await start(draft());
    const rules = screen.getByRole("list", { name: "Rules as I read them" });
    const mine = within(rules).getByText("One item per order").closest("li")!;
    expect(within(mine).getByText(/my default — say so if you disagree/)).toBeInTheDocument();
    expect(mine.textContent).not.toContain("DEC-013");   // our reference, not a boundary (LEASH-146)
    expect(within(mine).getByText(/say so if you disagree/)).toBeInTheDocument();  // disagreement is allowed
    const theirs = within(rules).getByText("At most CHF 50.00 per order, delivery included").closest("li")!;
    expect(within(theirs).getByText("you asked for this")).toBeInTheDocument();
  });

  it("asks one clarification at a time, and the answered one stays in the transcript", async () => {
    await start(draft(), { "POST /api/policies/drafts/LD-1/answers": [{ status: 200, body: READY }] });
    expect(screen.getByRole("group", { name: /When I'm unsure/ })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: /two orders at the same shop/ })).not.toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("group", { name: /When I'm unsure/ }))
      .getByRole("button", { name: "Decline" }));
    await settle();

    expect(screen.queryByRole("group", { name: /When I'm unsure/ })).not.toBeInTheDocument();
    expect(screen.getByText(/When I'm unsure about a purchase/)).toBeInTheDocument();  // still readable
    expect(screen.getByText("Decline")).toBeInTheDocument();                           // with its answer
    expect(screen.getByRole("group", { name: /two orders at the same shop/ })).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: /two orders/ })).getByText("Optional")).toBeInTheDocument();
  });

  it("a correction is a new turn, and the revision it replaces is visible", async () => {
    const CORRECTED = draft({ revision: 2, instruction: `${INSTRUCTION} Actually, make it CHF 30.`,
                              rules: [{ text: "At most CHF 30.00 per order, delivery included",
                                        source: "customer", decision: null, tightened: false }] });
    const calls = await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [{ status: 200, body: assistant(CORRECTED) }] });
    await say("Actually, make it CHF 30.");

    expect(posts(calls, "/api/permission/drafts/LD-1/turns")[0].body).toEqual({ text: "Actually, make it CHF 30." });
    expect(screen.getByText("revision 2")).toBeInTheDocument();
    expect(screen.getByText("replaces revision 1")).toBeInTheDocument();
    expect(screen.getByText("At most CHF 30.00 per order, delivery included")).toBeInTheDocument();
    expect(screen.getByText("Actually, make it CHF 30.")).toBeInTheDocument();
    expect(screen.getByText(INSTRUCTION)).toBeInTheDocument();  // the earlier turn is still in the transcript
  });

  it("a refused turn is reported where it happened and claims nothing", async () => {
    const calls = await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [{ status: 409, body: { error: {
      code: "already_submitted", message: "This draft is already at Viseca; start a new one to change it." } } }] });
    await say("Only for delivery.");

    expect(screen.getByRole("alert")).toHaveTextContent("already at Viseca");
    expect(screen.getByText(/what the service has now/)).toBeInTheDocument();
    // not in the transcript, because the service did not record them — only the first turn is there
    expect(document.querySelectorAll(".bubble.me")).toHaveLength(1);
    // and the words are handed back rather than lost
    const composer = screen.getByRole("region", { name: "Say something" });
    expect(within(composer).getByRole("textbox")).toHaveValue("Only for delivery.");
    expect(posts(calls, "/api/permission/drafts/LD-1/turns")).toHaveLength(1);
  });

  it("a reload rebuilds the same conversation without duplicating it", async () => {
    await start(draft(), { "GET /api/policies/drafts/LD-1": [{ status: 200, body: draft() }] });
    cleanup();  // the tab goes away; the draft id and the words the service stored do not

    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: draft() }] });
    render(wrap(<Agent />));
    await screen.findByRole("list", { name: "Rules as I read them" });
    expect(screen.getAllByText(INSTRUCTION)).toHaveLength(1);
    expect(screen.getAllByText(/I'm your Wallet Control, your permission assistant/)).toHaveLength(1);
  });

  it("does not show a remembered turn the service has no record of", async () => {
    await start(draft());
    // A turn the service never stored: the instruction it returns does not contain these words.
    stubFetch({ "POST /api/permission/drafts/LD-1/turns": [{ status: 200, body: assistant(draft()) }] });
    await say("Only for delivery.");
    expect(document.querySelectorAll(".bubble.me")).toHaveLength(1);  // the stored instruction lacks them
  });

  it("review is held back while a needed question is open, and posts nothing", async () => {
    const calls = await start(draft());
    expect(screen.queryByRole("button", { name: "Review permission" })).toBeNull();
    expect(screen.getByText("Needs your answer")).toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Send" })).toHaveLength(1);
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/submit")).toEqual([]);
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);
  });

  it("a refused free-text answer shows the reason and keeps the question", async () => {
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [{ status: 422, body: { error: {
      code: "invalid_answer", message: '"Maybe" doesn\'t answer this question: it doesn\'t say anything I can use' } } }] });
    await say("Maybe");
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("doesn't answer this question");
    expect(screen.getByRole("textbox")).toHaveValue("Maybe");
    expect(screen.getByRole("group", { name: /When I'm unsure/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review permission" })).toBeNull();
  });

  it("routes free-text history questions through the model and preserves the permission", async () => {
    const reply = "151 approved purchases. Your permission is unchanged.";
    const after = draft({ messages: [{ text: "check the history", reply, revision: 1, context: {} }] });
    const calls = await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: { ...assistant(after), kind: "history", reply } }] });
    await say("check the history");
    await screen.findByText(reply);
    expect(posts(calls, "/api/policies/drafts/LD-1/answers")).toHaveLength(0);
    expect(posts(calls, "/api/permission/drafts/LD-1/turns")[0].body).toEqual({ text: "check the history" });
    expect(screen.getByText(INSTRUCTION)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review permission" })).toBeNull();
  });

  it("review and confirm carry the revision that was reviewed, and only Confirm activates it", async () => {
    const calls = await start(READY, {
      "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
      "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: MANDATE }],
    });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    const exact = await screen.findByRole("region", { name: "What Viseca received" });
    expect(posts(calls, "/api/policies/drafts/LD-1/submit")[0].body).toEqual({ revision: 1 });
    expect(within(exact).getByText("PD-77")).toBeInTheDocument();
    expect(within(exact).getByText("authorization.billing_amount_chf <= 50 CHF per purchase")).toBeInTheDocument();
    expect(within(exact).getByText(/When unsure: decline/)).toBeInTheDocument();
    const unasked = within(exact).getByRole("group", { name: "Choices you left to me" });
    expect(within(unasked).getByText(/two orders at the same shop/)).toBeInTheDocument();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);  // nothing is active before the tap

    fireEvent.click(screen.getByRole("button", { name: "Confirm this permission" }));
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")[0].body).toEqual({ confirmed: true, revision: 1 });
    expect(screen.getByRole("status")).toHaveTextContent("Version 1 is active");
    expect(screen.queryByRole("button", { name: "Confirm this permission" })).not.toBeInTheDocument();
  });

  it("a stale tab cannot confirm a revision it never reviewed", async () => {
    const calls = await start(READY, {
      "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
      "POST /api/policies/drafts/LD-1/confirm": [{ status: 409, body: { error: {
        code: "stale_revision", message: "You reviewed revision 1; the draft is now at revision 2." } } }],
    });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    await screen.findByRole("region", { name: "What Viseca received" });
    fireEvent.click(screen.getByRole("button", { name: "Confirm this permission" }));
    await settle();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")[0].body).toEqual({ confirmed: true, revision: 1 });
    expect(screen.getByRole("alert")).toHaveTextContent("the draft is now at revision 2");
    expect(screen.getByRole("button", { name: "Confirm this permission" })).toBeInTheDocument();  // not activated
  });


  it("stops showing an answer that a later turn dropped", async () => {
    // A correction re-asks the question under a new id, so the service no longer replays the old
    // answer. A transcript that kept showing it would claim a settled point the draft does not hold.
    const CORRECTED = draft({ revision: 2, answers: [],
                              instruction: `${INSTRUCTION} Actually, make it CHF 30.`,
                              open_questions: [{ question_id: "Q-split-30", blocking: false,
                                                 text: "If two orders at the same shop within an hour go over CHF 30.00, should I ask you?",
                                                 options: ["Yes, ask me", "No"] }] });
    await start(draft(), {
      "POST /api/policies/drafts/LD-1/answers": [{ status: 200, body: READY }],
      "POST /api/permission/drafts/LD-1/turns": [{ status: 200, body: assistant(CORRECTED) }],
    });
    fireEvent.click(within(screen.getByRole("group", { name: /When I'm unsure/ }))
      .getByRole("button", { name: "Decline" }));
    await settle();
    expect(screen.getByText(/When I'm unsure about a purchase/)).toBeInTheDocument();

    await say("Actually, make it CHF 30.");
    expect(screen.queryByText(/When I'm unsure about a purchase/)).not.toBeInTheDocument();
    expect(screen.queryByText("Decline")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: /go over CHF 30.00/ })).toBeInTheDocument();
  });

  it("one recorded turn is one message, even after the same words failed to land", async () => {
    // The first attempt returns 200 with an instruction that does not contain the words, so nothing
    // was recorded. Saying them again records them once — and must render once, not twice.
    const WITH_IT = draft({ revision: 2, instruction: `${INSTRUCTION} Only for delivery.` });
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: assistant(draft()) }, { status: 200, body: assistant(WITH_IT) }] });
    await say("Only for delivery.");
    expect(document.querySelectorAll(".bubble.me")).toHaveLength(1);
    await say("Only for delivery.");
    expect(screen.getAllByText("Only for delivery.")).toHaveLength(1);
    expect(document.querySelectorAll(".bubble.me")).toHaveLength(2);  // the instruction, and this one
  });

  it("keeps the order things happened in, not the order of the payload", async () => {
    const AFTER = draft({ revision: 2, status: "ready", uncertainty_policy: "decline", answers: ANSWERED,
                          instruction: `${INSTRUCTION} Only for delivery.`, open_questions: SPLIT_ONLY });
    await start(draft(), {
      "POST /api/policies/drafts/LD-1/answers": [{ status: 200, body: READY }],
      "POST /api/permission/drafts/LD-1/turns": [{ status: 200, body: assistant(AFTER) }],
    });
    fireEvent.click(within(screen.getByRole("group", { name: /When I'm unsure/ }))
      .getByRole("button", { name: "Decline" }));
    await settle();
    await say("Only for delivery.");

    const said = [...document.querySelectorAll(".bubble .message")].map((n) => n.textContent);
    expect(said.indexOf(INSTRUCTION)).toBeLessThan(said.findIndex((s) => s?.includes("When I'm unsure")));
    expect(said.indexOf("Decline")).toBeLessThan(said.indexOf("Only for delivery."));
  });

  it("shows an answer the service reports even when this tab never saw it given", async () => {
    // Another tab, or a reload: the draft is the record, so its answers belong in the transcript.
    sessionStorage.setItem("leash.draft_id", "LD-1");
    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: READY }] });
    render(wrap(<Agent />));
    await screen.findByRole("list", { name: "Rules as I read them" });
    expect(screen.getByText(/When I'm unsure about a purchase/)).toBeInTheDocument();
    expect(screen.getByText("Decline")).toBeInTheDocument();
  });

  it("says so when the draft cannot be loaded at all", async () => {
    sessionStorage.setItem("leash.draft_id", "LD-1");
    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 404, body: { error: {
      code: "draft_not_found", message: "No draft with this ID." } } }] });
    render(wrap(<Agent />));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("couldn't load your draft");
    // the way out sits with the problem, not only in the footer
    expect(within(alert.closest(".bubble")!).getByRole("button", { name: "Start a new conversation" }))
      .toBeInTheDocument();
  });

  it("never presents a rule Viseca imposed as its own default", async () => {
    await start(draft({ rules: [
      { text: "Only shops you have paid before", source: "viseca", decision: null, tightened: false },
      { text: "One item per order", source: "assumption", decision: "DEC-013", tightened: false }] }));
    const rules = screen.getByRole("list", { name: "Rules as I read them" });
    expect(within(rules).getByText("required by Viseca")).toBeInTheDocument();
    expect(within(rules).getByText("my assumption — say so if I have it wrong")).toBeInTheDocument();
    expect(rules.textContent).not.toContain("DEC-013");
    expect(within(rules).queryByText("you asked for this")).not.toBeInTheDocument();
  });


  it("an unrecorded turn cannot hide a recorded one by matching inside it", async () => {
    // "delivery" was never recorded, but its letters appear inside the later "Only for delivery".
    // Searching anywhere would show the phantom and swallow the real turn behind it.
    const WITH_IT = draft({ revision: 2, instruction: `${INSTRUCTION} Only for delivery` });
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: assistant(draft()) },      // "delivery" changes nothing: not recorded
      { status: 200, body: assistant(WITH_IT) }] });  // "Only for delivery" is recorded
    await say("delivery");
    await say("Only for delivery");

    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine).toEqual([INSTRUCTION, "Only for delivery"]);
  });

  it("a turn that adds no boundary is answered in the chat, not turned into a revision", async () => {
    // Live transcript: typing "yes" appended those words to the draft's own instruction, burned a
    // revision, and left a question the engine could never read. The answer says what to do instead.
    const reply = "I didn't find a new boundary in that, so your draft is unchanged.";
    // The service records the exchange on the draft itself and changes nothing else about it.
    const same = draft({ messages: [{ text: "yes", reply, revision: 1, context: {} }] });
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: { ...assistant(same), reply } }] });
    await say("yes");

    expect(screen.getByText(reply)).toBeInTheDocument();
    expect(screen.queryByText("Earlier draft · revision 1")).not.toBeInTheDocument();
  });

  it("shows the conversation in the order it happened", async () => {
    // Reported live: "the chat is not well organized, all my messages are together". The draft is
    // produced by the turn above it, so an acknowledgement (DEC-059) recorded afterwards must render
    // after the interpretation it replied to — not above it, which read as the customer's messages
    // bunched together with Wallet Control answering at the end.
    const reply = "I didn't find a new boundary in that, so your draft is unchanged.";
    const same = draft({ messages: [{ text: "yes", reply, revision: 1, context: {} }] });
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: { ...assistant(same), reply } }] });
    await say("yes");

    const said = [...screen.getByRole("log").querySelectorAll(".message")].map((n) => n.textContent ?? "");
    const at = (text: string) => said.findIndex((line) => line.includes(text));
    expect(at(INSTRUCTION)).toBeGreaterThanOrEqual(0);
    expect(at("Here is the draft interpretation")).toBeGreaterThan(at(INSTRUCTION));
    expect(at("yes")).toBeGreaterThan(at("Here is the draft interpretation"));
    expect(at(reply)).toBeGreaterThan(at("yes"));
  });

  it("the same answer given twice shows twice", async () => {
    // Claimed one for one from what the draft reports, so a repeated pair is not collapsed into one.
    const TWICE = draft({ answers: [...ANSWERED, ...ANSWERED] });
    sessionStorage.setItem("leash.draft_id", "LD-1");
    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: TWICE }] });
    render(wrap(<Agent />));
    await screen.findByRole("list", { name: "Rules as I read them" });
    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine.filter((s) => s === "Decline")).toHaveLength(2);
  });


  it("a turn that landed behind a lost reply still reaches the transcript", async () => {
    // /turns commits in a transaction, so a failed reply is not proof nothing was written. The screen
    // must ask the service what it holds instead of asserting that nothing changed.
    const LANDED = draft({ revision: 2, instruction: `${INSTRUCTION} Only for delivery` });
    await start(draft(), {
      "POST /api/permission/drafts/LD-1/turns": [{ status: 500, body: { error: {
        code: "internal_error", message: "Something went wrong; nothing was confirmed twice." } } }],
      // the only GET is the refetch the failure triggers, and the service does hold the words
      "GET /api/policies/drafts/LD-1": [{ status: 200, body: LANDED }],
    });
    await say("Only for delivery");
    await settle();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine).toEqual([INSTRUCTION, "Only for delivery"]);  // read off the draft, not asserted away
  });

  it("an unrecorded turn that is a prefix of a recorded one cannot swallow it", async () => {
    const WITH_IT = draft({ revision: 2, instruction: `${INSTRUCTION} Only for delivery` });
    await start(draft(), { "POST /api/permission/drafts/LD-1/turns": [
      { status: 200, body: assistant(draft()) },      // "Only" changes nothing: not recorded
      { status: 200, body: assistant(WITH_IT) }] });  // "Only for delivery" is recorded
    await say("Only");
    await say("Only for delivery");

    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine).toEqual([INSTRUCTION, "Only for delivery"]);
  });


  it("a log left over from another conversation contributes nothing", async () => {
    // sessionStorage can outlive the draft it belongs to (a crash between the two writes in
    // startOver, a hand-edited key). An entry whose instruction the draft does not begin with is
    // not a record of this conversation, and must not be sliced into it.
    sessionStorage.setItem("leash.draft_id", "LD-1");
    sessionStorage.setItem("leash.talk", JSON.stringify({ log: [
      { kind: "said", instruction: "Buy a monitor from a shop I have used before." }] }));
    stubFetch({ "GET /api/policies/drafts/LD-1": [{ status: 200, body: draft() }] });
    render(wrap(<Agent />));
    await screen.findByRole("list", { name: "Rules as I read them" });

    const mine = [...document.querySelectorAll(".bubble.me .message")].map((n) => n.textContent);
    expect(mine).toEqual([INSTRUCTION]);  // the draft's own words, and nothing from the stale log
  });


  it("a submit refused by the service shows why and posts nothing more", async () => {
    const calls = await start(READY, { "POST /api/policies/drafts/LD-1/submit": [{ status: 409, body: { error: {
      code: "questions_open", message: "blocking questions remain" } } }] });
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("blocking questions remain");
    expect(screen.queryByRole("button", { name: "Confirm this permission" })).not.toBeInTheDocument();
    expect(posts(calls, "/api/policies/drafts/LD-1/confirm")).toEqual([]);
  });
});

it("connects supplied task, exact review, confirmation and checkout simulation", async () => {
  const task = { scenario_id: "SCEN0000", scenario_name: "Connection check", event_count: 1, cardholder_instruction: INSTRUCTION };
  const ready = { ...READY, simulation_scenario: task.scenario_id };
  const posted = { ...POSTED, review: {
    must_follow: [{ text: "At most CHF 50.00 per order.", group: "price" as const }],
    may_choose: [{ text: "Shop category.", group: "merchant" as const }],
    must_ask: [{ text: "Suspected duplicates.", group: "uncertainty" as const }] } };
  const calls = stubFetch({
    "GET /api/scenarios": [{ status: 200, body: { scenarios: [task] } }],
    "POST /api/permission/drafts": [{ status: 200, body: assistant(ready) }],
    "GET /api/policies/drafts/LD-1": [{ status: 200, body: ready }],
    "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: posted }],
    "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: MANDATE }],
    "POST /api/runs": [{ status: 201, body: { run_id: "RUN-local" } }],
  });
  const started = vi.fn();
  render(wrap(<Agent onRunStarted={started} />));
  fireEvent.click(await screen.findByRole("radio", { name: /Connection check/ }));
  await say(INSTRUCTION);
  expect(posts(calls, "/api/permission/drafts")[0].body).toEqual({ text: INSTRUCTION, scenario_id: task.scenario_id });
  expect(screen.queryByRole("button", { name: "Start shopping simulation" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
  await screen.findByRole("heading", { name: "Must follow" });
  expect(screen.getByRole("heading", { name: "May choose" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Must ask" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm this permission" }));
  fireEvent.click(await screen.findByRole("button", { name: "Start shopping" }));
  await settle();
  expect(posts(calls, "/api/runs")[0].body).toEqual({ scenario_id: task.scenario_id, mandate_id: "TM-9" });
  expect(started).toHaveBeenCalledWith("RUN-local");
});

// --- LEASH-145 AC10 ---------------------------------------------------------------------------

describe("a question that came from background (LEASH-145 AC10)", () => {
  const FROM_PROFILE = {
    question_id: "Q-returns", blocking: true,
    text: "Should a 30-day return window be required for this jacket?",
    source: { kind: "preference" as const, evidence: "prefers retailers with returns",
              file: "customers.csv", row_id: "CU0012" },
  };

  it("says it came from a recorded preference and quotes the words", async () => {
    await start(draft({ open_questions: [FROM_PROFILE] }));
    const asked = await screen.findByRole("group", { name: /30-day return window/ });
    // the customer must be able to see this was not something they said
    expect(within(asked).getByText(/from your saved preferences/i)).toBeInTheDocument();
    expect(within(asked).getByText(/prefers retailers with returns/)).toBeInTheDocument();
    expect(within(asked).getByText(/not a rule yet/i)).toBeInTheDocument();
  });

  it("claims no source for a question the customer's own words prompted", async () => {
    await start(draft({}));
    const asked = await screen.findByRole("group", { name: /unsure about a purchase/ });
    expect(within(asked).queryByText(/from your saved preferences/i)).not.toBeInTheDocument();
  });
});

// --- LEASH-174: the assistant's own wording is marked as its own -------------------------------

it("marks a question written by the model as the model's wording", async () => {
  await start(draft({ open_questions: [
    { question_id: "AQ-1", text: "Which shop did you have in mind?", blocking: true, origin: "model" },
  ] }));
  const asked = await screen.findByRole("group", { name: /Which shop did you have in mind/ });
  expect(within(asked).getByText(/my own words, not a rule/i)).toBeInTheDocument();
});

it("says nothing about wording for a question generated from a rule", async () => {
  await start(draft({}));
  const asked = await screen.findByRole("group", { name: /unsure about a purchase/ });
  expect(within(asked).queryByText(/my own words, not a rule/i)).not.toBeInTheDocument();
});

// --- LEASH-146: the review is a contract the customer can read ---------------------------------

describe("the permission review (LEASH-146)", () => {
  const REVIEW = {
    must_follow: [{ text: "At most CHF 50.00 per order, delivery included.", group: "price" as const },
                  { text: "One item per order.", group: "item" as const },
                  { text: "Only shops you have paid before.", group: "merchant" as const },
                  { text: "Another order after 1 approved purchase(s).", group: "frequency" as const }],
    may_choose: [{ text: "No explicit restriction on size; all other checks still apply.", group: "item" as const }],
    must_ask: [{ text: "Suspected duplicates, off-purpose orders, merchant instructions or integrity problems.",
                 group: "uncertainty" as const }],
  };
  const posted = { ...POSTED, review: REVIEW };

  async function review() {
    const calls = stubFetch({
      "POST /api/permission/drafts": [{ status: 200, body: assistant(READY) }],
      "GET /api/policies/drafts/LD-1": [{ status: 200, body: READY }],
      "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: posted }],
      "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: MANDATE }],
    });
    render(wrap(<Agent />));
    await say(INSTRUCTION);
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    return { card: await screen.findByRole("region", { name: "What Viseca received" }), calls };
  }

  it("reads each boundary under its own heading", async () => {
    const { card } = await review();
    const follow = within(card).getByRole("group", { name: "Must follow" });
    for (const heading of ["Item", "Price", "Shop", "How often"]) {
      expect(within(follow).getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(within(follow).getByText("One item per order.")).toBeInTheDocument();
  });

  it("keeps internal identifiers out of the review until advanced details are opened", async () => {
    const { card } = await review();
    const payload = within(card).getByText(/authorization\.billing_amount_chf/);
    const advanced = within(card).getByText("Advanced details").closest("details")!;
    expect(payload).not.toBeVisible();
    expect(within(card).getByText("PD-77")).not.toBeVisible();
    expect(card.textContent).not.toContain("DEC-013");   // decision codes belong to the notes, not the contract
    advanced.open = true;                                 // jsdom does not toggle a summary click for us
    expect(payload).toBeVisible();
  });

  it("names an optional question left open as a choice the customer made", async () => {
    const { card } = await review();
    const open = within(card).getByRole("group", { name: "Choices you left to me" });
    expect(open.textContent).toContain("two orders at the same shop");
  });

  it("says what happens next in a message from Wallet Control once confirmed", async () => {
    const { card } = await review();
    fireEvent.click(within(card).getByRole("button", { name: "Confirm this permission" }));
    const said = await screen.findByText(/Version 1 is active/);
    expect(said.closest(".bubble.leash")).not.toBeNull();
  });
});


// --- LEASH-147: the handoff to the external shopping agent -------------------------------------

describe("the handoff to the shopping agent (LEASH-147)", () => {
  const TASKS = [
    { scenario_id: "SCEN0000", scenario_name: "Connection check", cardholder_instruction: "Buy one grocery item.",
      event_count: 1, summary: "One small, unambiguous grocery purchase." },
    { scenario_id: "SCEN0004", scenario_name: "Manipulated agent", cardholder_instruction: INSTRUCTION,
      event_count: 11, recommended: true, summary: "Shop text that tries to talk the agent into an answer." },
  ];

  it("offers the demonstrations by name and by what they show, never by fixture id", async () => {
    stubFetch({ "GET /api/scenarios": [{ status: 200, body: { scenarios: TASKS } }] });
    render(wrap(<Agent />));
    const picker = await screen.findByRole("group", { name: "Choose a demonstration" });
    expect(within(picker).getByText("Manipulated agent")).toBeInTheDocument();
    expect(within(picker).getByText("Shop text that tries to talk the agent into an answer.")).toBeInTheDocument();
    expect(picker.textContent).not.toContain("SCEN");
    // the rehearsed one is ready to send, so a presenter taps once
    expect(within(picker).getByRole("radio", { name: /Manipulated agent/ })).toBeChecked();
    expect(within(picker).getByText("Recommended")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue(INSTRUCTION);
  });

  async function confirmed(runReplies: Reply[]) {
    const calls = stubFetch({
      "GET /api/scenarios": [{ status: 200, body: { scenarios: TASKS } }],
      "POST /api/permission/drafts": [{ status: 200, body: assistant({ ...READY, simulation_scenario: "SCEN0004" }) }],
      "GET /api/policies/drafts/LD-1": [{ status: 200, body: { ...READY, simulation_scenario: "SCEN0004" } }],
      "POST /api/policies/drafts/LD-1/submit": [{ status: 200, body: POSTED }],
      "POST /api/policies/drafts/LD-1/confirm": [{ status: 200, body: MANDATE }],
      "POST /api/runs": runReplies,
    });
    render(wrap(<Agent />));
    await screen.findByRole("group", { name: "Choose a demonstration" });
    await say(INSTRUCTION);
    fireEvent.click(screen.getByRole("button", { name: "Review permission" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm this permission" }));
    return calls;
  }

  it("starts exactly one run however often the action is tapped, and shows what was recorded", async () => {
    const run = { run_id: "RUN-7", scenario_id: "SCEN0004", mandate_id: "TM-9", mandate_version: 1, status: "running" };
    const calls = await confirmed([{ status: 201, body: run }]);
    const start = await screen.findByRole("button", { name: "Start shopping" });
    fireEvent.click(start);
    fireEvent.click(start);      // a double tap is one handoff, not two runs
    await settle();
    expect(posts(calls, "/api/runs")).toHaveLength(1);
    expect(posts(calls, "/api/runs")[0].body).toEqual({ scenario_id: "SCEN0004", mandate_id: "TM-9" });
    expect(await screen.findByText(/RUN-7/)).toBeInTheDocument();
    expect(screen.getByText(/running/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start shopping" })).not.toBeInTheDocument();
  });

  it("says why a refused start was refused, and leaves the action to try again", async () => {
    const calls = await confirmed([{ status: 409, body: { error: { code: "mandate_not_active", message: "This permission is not active." } } },
                                   { status: 201, body: { run_id: "RUN-8", scenario_id: "SCEN0004", mandate_id: "TM-9", mandate_version: 1, status: "running" } }]);
    fireEvent.click(await screen.findByRole("button", { name: "Start shopping" }));
    await settle();
    expect(screen.getByRole("alert")).toHaveTextContent("This permission is not active.");
    fireEvent.click(screen.getByRole("button", { name: "Start shopping" }));
    await settle();
    expect(posts(calls, "/api/runs")).toHaveLength(2);
    expect(await screen.findByText(/RUN-8/)).toBeInTheDocument();
  });

  it("offers no correction once the permission is confirmed: a change needs a fresh confirmation", async () => {
    await confirmed([{ status: 201, body: { run_id: "RUN-9", scenario_id: "SCEN0004", mandate_id: "TM-9", mandate_version: 1, status: "running" } }]);
    await screen.findByRole("button", { name: "Start shopping" });
    // the menu holds no edit action once a permission exists, so there is nothing to correct in place
    expect(screen.queryByRole("button", { name: "Edit task and review again" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();  // nothing more can be said into this draft
  });
});
