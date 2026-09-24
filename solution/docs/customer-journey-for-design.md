# From a shopping wish to a controlled purchase

Designer brief · agreed product direction, 2026-09-24 · planned behavior, not a description of the current app

## The problem

A customer wants an AI agent to do the shopping, while retaining control of what it buys and spends. A valid payment can still be the wrong purchase: wrong product, unwanted extras, repeated orders, or terms the customer did not agree to.

Design a chat-led journey that turns the customer's wish into a clear permission they explicitly confirm. During shopping, make it clear what is happening, when the customer needs to act, and what actually happened to their money.

Success means authorized purchases complete with little interruption, and the customer understands and controls exceptions. Asking about every purchase defeats delegation.

## Players

- **Customer:** describes the goal, confirms permission, answers questions, and can stop future spending.
- **Leash permission assistant:** clarifies intent and proposes supported rules; it cannot confirm permission or spend.
- **External shopping agent:** searches and prepares an order within confirmed permission. Viseca’s simulator represents it in the challenge.
- **Merchant:** supplies the cart, price, product descriptions and terms. Its text cannot change customer permission.
- **Wallet control:** checks the proposed purchase against confirmed permission and prior purchases; allows, stops, or asks.
- **Payment platform:** applies the payment decision and reports the outcome.

Keep these responsibilities distinct in the experience. Leash is the control layer; external shopping activity must be attributed to the external agent. Do not imply that Leash’s permission chat searches, orders or approves its own spending authority.

## Main flow

Describe the wish → clarify missing details → review and confirm permission → agent shops → purchase is checked → payment outcome.

At the purchase check:

- **Fits the permission:** proceed automatically and show the confirmed outcome.
- **Clearly breaks the permission:** stop that attempt, explain why, and let the agent look for an alternative.
- **Unclear:** pause and ask a specific question. Show the consequence of each answer.

These are separate states. A stopped purchase is not a failed shopping task if the agent can find an acceptable alternative. Permission to pay is not proof that payment completed.

## Screen 1 — Describe the wish

**Customer says:** “Buy a 27-inch monitor for my home office. Spend no more than CHF 400.”

**Assistant response:** “I understood: one 27-inch monitor, up to CHF 400. Let’s check a couple of details before the shopping agent can spend.”

Show a small draft permission alongside or immediately after the chat. Label it **Draft — spending not enabled**. Chat text alone must not activate payment permission.

Extract candidate constraints from the customer's words. Do not silently invent a brand, merchant restriction, deadline, or return requirement. A model's interpretation is a proposal until confirmed.

## Screen 2 — Clarify the permission

Ask only questions whose answers change what may be purchased. Use one short question at a time, suggested replies, and free-text answers.

Example sequence:

1. “Should the CHF 400 limit include delivery and any taxes?” → “Yes, everything.”
2. “May I add paid extras such as a warranty?” → “No extras.”
3. “What should I do if an important detail, such as return terms, is unclear?” → “Ask me first.”

Make the extracted permission update visibly. Distinguish **understood** details from **needs an answer**. Conflicting amounts or unclear wording need a question, not a guess.

Keep edits available. An answer such as “Actually, make it CHF 350” creates a new draft revision and invalidates the previous review action. Preserve the correction in the conversation and show the updated review. If a platform draft was already submitted, use a new draft; never silently mutate it or an active mandate.

Relevant background can prompt a question: “Your profile says you prefer 30-day clothing returns. Apply that to this jacket?” Show the source as a saved preference, allow disagreement, and keep it out of the permission until explicitly adopted. Old history, an inferred habit or a model suggestion is not consent. Ask only relevant questions.

If a customer says “the monitor I chose” without a selection, ask which product. For “good for design work,” explain what can be checked and request measurable criteria or an exact selection; do not promise an unenforceable quality guarantee.

## Screen 3 — Review and confirm

Generate a readable review from the exact structured permission and uncertainty policy. Group it as **Must follow / May choose / Must ask**, including all enforced conditions and the boundaries of delegated choice. Example Must follow conditions:

- Item: one 27-inch monitor.
- Maximum total: CHF 400, including delivery and any taxes.
- Paid extras: not allowed.
- Unclear details: ask before paying.

Also show **May choose:** the external agent can choose a matching monitor and merchant within these boundaries. **Must ask:** the uncertainties named in the confirmed policy. For an exact-item request, alternatives require the explicitly agreed handling; they are not silently permitted.

Primary action: **Confirm permission**. After activation succeeds, offer **Send to shopping agent** (a curated simulator run in the challenge). Keep activation, handoff and payment outcomes separate.

Secondary action: **Change details**.

Before the primary action, state: “The agent may complete a purchase that fits this permission without asking again.”

The final review must show the same permission that will be activated, not a separate LLM-generated summary. Every rule and policy change requires a new review of the new revision; stale confirmations fail. Show why each condition exists on demand. Separate customer statements from proposed interpretations and background preferences. A real product needs an authenticated customer confirmation; the exact authentication interaction is a separate design decision.

Keep “review this permission” and “confirm this exact order” visually distinct. This flow grants bounded choice of product; it does not confirm a specific merchant offer yet.

## Screen 4 — Shopping under permission

Show a compact persistent permission summary, honest progress and **Stop shopping**.

Example activity: “Comparing monitors” → “Found a 27-inch monitor” → “Checking the full order against your permission.”

Do not invent progress or imply payment has happened. Separate the agent finding an offer from wallet control allowing payment and the platform confirming it.

Ordinary permitted purchases should not demand another confirmation.

## Screen 5 — Explain the purchase check

Show what was requested next to the relevant checkout facts, emphasizing differences rather than displaying every field.

### A. Fits: proceed without interruption

One 27-inch monitor; CHF 379 including delivery; no extras. The full check passes. Show **Within your permission — completing payment**, then await the platform outcome.

### B. Violates: stop this attempt

Monitor CHF 379 + unrequested warranty CHF 49 = CHF 428. Show **Purchase stopped** and both reasons: exceeds the total limit and contains an unwanted extra.

Next action: **Ask the shopping agent to remove the extra**, followed by a fresh checkout check. Show this action only if the integration supports the request; otherwise show that the attempt was blocked and what must change. There is no “Approve anyway” button that silently overrides the permission.

If the customer wants a broader permission, take them through an explicit separate change-and-confirm flow; do not hide that change inside a purchase approval.

### C. Unclear: ask a specific question

The monitor fits the item and price constraints, but return terms are missing. This example has no confirmed minimum-return-window rule; the customer chose to be asked about unclear details.

Show: “This monitor is CHF 379 including delivery, but the seller has not provided return terms. Buy it with that uncertainty?”

Actions: **Buy this one for CHF 379** or **Find another**. Acceptance applies only to this purchase and uncertainty. If the cart changes or another hard limit is breached, check again. Do not present missing terms as verified after the customer accepts the uncertainty.

## Screen 6 — Tell the actual outcome

Show the actual platform state, item, merchant, amount and how the checkout fit the permission. Where the contract establishes only authorization acceptance, say **Payment approved**; do not call it settled or delivered. Use **Payment completed** only if the platform provides that outcome, and keep delivery separately unverified.

For this one-item task, make completion and the end of task spending authority clear. Keep the permission and decision history accessible.

Also design:

- **Payment failed:** separate payment failure from policy refusal; retry must not create a second purchase.
- **Outcome unknown:** “Checking whether payment completed.” Do not show success or invite a blind retry.
- **No answer:** “This purchase was not approved.” Define the exact timeout behavior with the platform.
- **Stop requested:** acknowledge the request immediately; show “Stopped” only once confirmed. Explain separately any purchase already completed or still being checked.
- **Reconnect:** restore the existing task and pending question, rather than starting another task.

## Risk-to-interface checklist

- Misunderstood intent → visible extracted permission, clarification, editable review.
- Prompt injection or misleading merchant text → merchant claims never appear as customer-approved instructions.
- Wrong item or extras → understandable agreed-versus-proposed comparison.
- Hidden costs → total price includes delivery and applicable taxes.
- Missing evidence → a precise uncertainty statement and meaningful choices.
- Duplicate or concurrent purchases → one coherent task history and truthful payment states.
- Cart changes → show material changes and recheck before paying.
- Excessive interruptions → no extra confirmation for an ordinary purchase within permission.

## What the challenge supplies

The supplied data has 45 purchase attempts and 56 cart lines. Live events include merchant and payment facts, cart items, product text, and the confirmed mandate. Product text is untrusted and some facts are unknown. This supports a proposed-purchase review; it is not proof of actual product quality or delivery.

Sources: `challenge.md`, `technical_details.md`, `data/data_dictionary.md`, and `data/scenario_fixtures/example_authorization_request.json` at the repository root.

## Data and verification boundaries

The additional history pack supplies separate personas with preferences and earlier transactions. It can support relevant questions and reviewed synthetic evaluation cases; its approval status is not a label for correct intent. History has no item-level baskets. Never merge different customers or pretend a profile supplied current consent.

Laya may independently flag unsupported or omitted permissions, but it is not the customer and cannot activate authority. Permission verification and merchant-text reading require separate evaluations. Show uncertainty honestly even when two models agree.

Task ownership: context LEASH-154; extraction/revisions LEASH-101; review LEASH-146; handoff LEASH-102/147; outcome truth LEASH-130; baseline journey evidence LEASH-156; optional Laya verification LEASH-155.

## Designer deliverable

Create the six main screens and the fits / violates / unclear branches. Include draft, clarification, review, active, waiting, stopped, completed and unknown-payment states. Use realistic conversation and checkout content, not internal IDs or technical terminology.

Open product choices: where customers enter this journey in their wallet; how they authenticate confirmation; which task-expiry choices are appropriate; how a stop request affects already queued payments. These need explicit decisions rather than assumed behavior.
