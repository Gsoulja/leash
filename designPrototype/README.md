# Handoff: Wallet Control — "Agent on the Leash" (v4, conversational)

## Overview

Wallet Control is an **extension of an existing card-issuer mobile app** that lets a cardholder delegate shopping to an AI agent without handing it their card.

- The customer **talks to the agent in a chat**. As they talk, the agent turns each answer into a visible mandate rule.
- The mandate is confirmed with Face ID.
- The agent then searches verified shops and **comes back with proposed products**: a paged carousel of up to 5 per page, each with image, merchant, link, price and rule-fit chips.
- **The customer approves every purchase.** There is no silent or automatic buying anywhere in the product.
- Every outcome is logged with the evidence that produced it.

Priorities, in order:

1. **Control.** Card credentials never reach the agent. No text from a merchant or from the agent can widen a mandate. No payment happens without explicit customer approval.
2. **Reportability and transparency.** Every decision is explainable after the fact, in plain language, with its source data.
3. **Trust through UI.** The interface *is* the security surface. If the customer can't tell what they agreed to, the system has failed.

Performance is **not** a priority. The product is **mobile-first**: design at 390×800. Desktop is out of scope.

---

## About the design files

The files in `design-files` are **design references written in HTML**: interactive prototypes that show the intended look, copy and behaviour. They are **not production code**.

They use a prototype-only format: `.dc.html` files with inline styles and a small logic class, running on `support.js`. **Do not port** `support.js`, `<x-dc>`, `<sc-for>` / `<sc-if>`, `image-slot.js` or the inline-style approach.

**Recreate the designs in the target codebase's own environment** (React Native, Swift, Kotlin, React…), using its component library, navigation and state conventions. The host-app shell in the prototype (home, card hero, transaction list, settings rows, tab bar) is **deliberately generic**. Replace it with the real app's existing components. The new surfaces are the ones specified below.

Open `Hi-Fi Prototype v4 In-App Chat.dc.html` in a browser. It is fully clickable: start from Home → "AI agent", or use the screen list on the right.

**Fidelity: high.** v4 is the single source of truth for behaviour and copy. Earlier prototype versions have been removed from this package.

---

## Critical domain rules

These rules sit where the UI promises something the mandate API doesn't model by itself. A naive implementation will break each one silently.

### 1. Every purchase requires customer approval

There is **no auto-approve path**. The decision engine never returns `approve` on its own authority for a payment:

- An attempt inside all rules → `step_up`. The customer approves in the chat and the result is recorded via `POST /v1/authorizations/{id}/resolve`.
- An attempt outside any hard rule → `decline`. It is never shown to the customer as a proposal.

**Budget** is guidance, not a hard rule (`guidance.budget_chf = 200`). It only decides whether a card is shown as "within budget" (green) or "over budget" (violet).

**Stretch / hard stop** is the hard rule: `hard_rules: amount_chf <= 215`. If the customer said "never go over", then `hard_rules: amount_chf <= 200` and the tile reads "HARD STOP AT".

The summary card and the agent-access screen **must show both numbers**. The customer must never believe they authorised 200 when the mandate allows 215.

### 2. The chat is not the authority — the confirmed mandate is

- The conversation produces a **draft**. Each rule comes from a deterministic mapping of the customer's reply (quick replies map 1:1 to fields; free text is parsed into the same fields). It is shown as an "Added to mandate" chip at the moment it is created.
- `POST /v1/mandates` creates the draft from those structured fields plus the original sentences. Only the **Face ID reply on the summary card** calls `POST /v1/mandates/{draft_id}/confirm`.
- After confirmation, **nothing said in the chat can change the mandate**, whether the customer, the agent or a merchant says it. Changing the rules means starting a new mandate in a new conversation ("+ New in chat").
- The conversational model and the decision engine are separate components. The model never holds the card token and never sees raw merchant text (see rule 5).
- Two rules are **always added by the agent itself** and cannot be removed: "You approve every purchase · Face ID" and "Seller text can't change these rules".

### 3. Approvals never modify the mandate

`PATCH` can only preserve or tighten. Approving a proposal — including an over-budget one inside the hard stop — is a `/resolve approve` on that single authorization. The mandate is untouched, and each payment uses a single-use token scoped to that merchant and amount.

After one purchase, the mandate is **fulfilled**: the other proposals switch to "Not needed" and the agent stops searching. The mandate stays open until `valid_until` only so the customer can see it. It does not re-arm.

### 4. Freeze is enforced in our layer, in a fixed order

Revocation semantics for queued work are undefined upstream, so our layer keeps the promise:

1. Set the freeze flag in our store. It is enforced immediately, before any network call.
2. Stop the search and withdraw all open proposals (cards show "Withdrawn").
3. Resolve any pending authorization as `decline` via `/resolve`. Anything arriving later is declined with `mandate_revoked`.
4. `DELETE /v1/mandates/{mandate_id}` — last.

### 5. Quarantine emits structured flags, not a boolean

```
quarantine_flags: [
  { type: "PROMPT_INJECTION", confidence: 0.94, span: [212, 268], field: "purchase_description" }
]
```

The engine and the chat model receive **only the flag and the span**, never the text. The "SKIPPED · Sportshop24" chat bubble is rendered from the flag. `purchase_description` and `item_details` are untrusted everywhere: never concatenate them into a prompt, a rule evaluation or a notification. Any view of the raw text is fetched from a separate read-only endpoint that is not on the decision path.

---

## Screens

The phone frame is 390×800 with app background `#F4F4F2` and 18px gutters. The status bar is white on chat and sheets, otherwise `#F4F4F2`. The tab bar (Home, Cards, AI agent, Profile) shows everywhere except the chat and the freeze sheet.

Scroll containers must not squash their children. In the prototype this is a grid with `grid-auto-rows:max-content`. Use the platform equivalent (a ScrollView with non-shrinking children).

### V1 — Host home

- **Greeting:** "Hello, Maya" at 700/22.
- **Card hero:** 300×180, radius 18, dark `#1E2A38` (the host app's real card component).
- **Quick actions:** 4 × 52px tiles. "AI agent" is the only dark tile (`#14151A`) and opens the chat.
- **Agent banner** (white, radius 16, 1.5px tinted border, 40px icon tile). Its content follows the agent's state:

| State | Title | Sub | Tint |
|---|---|---|---|
| never started | Try your new AI shopping agent | Set rules together in a chat | neutral |
| setup | Finish setting up your agent | n of 7 rules agreed | neutral |
| searching | Your agent is searching | Checked n offers so far | green |
| proposals | Your agent found 8 matches | Tap to review · 2 over budget | violet |
| bought / done | *(hidden)* | | |
| frozen | Agent frozen | No spending access · tap to review | red |

- **Transactions:** a white radius-16 list. Agent-initiated rows carry an **AGENT** tag (`#EDEBF8` / `#3D3478`, 600/8.5) and a status line: `APPROVED BY YOU`, `APPROVED · OVER BUDGET` or `SKIPPED`. A purchase made in chat appears at the top immediately.

### V2 — Card settings

The host's settings list, plus a new group **AI SHOPPING**:

- **"AI agent access"** row: dark icon tile, NEW badge `#8A1FA8`, row tint `#FBF7FC`. Sub-line: "Mandate active · until Sunday" or "Set up by chatting with your agent".
- **"Decision log"** row.

### V3 — AI agent access

- **Dark status card** (`#14151A`, radius 18):
  - Overline: `NO ACTIVE MANDATE`, `1 AGENT · ON A LEASH` or `FROZEN`.
  - Headline at 700/24: "Tell your agent what you need." / "Searching for your shoes…" / "8 matches waiting" / "Bought: Nike Store · CHF 189".
  - Sub-line: "Spends through virtual card ••4417 — never your ••2291".
  - White 48px button: "Start a conversation" / "Open conversation".
- **Current mandate** (from 2 rules onward): a DRAFT / ACTIVE / REVOKED badge, then the two tiles **BUDGET** (green) and **STRETCH UP TO** / **HARD STOP AT** (violet / red), then the other rules as label/value rows, then "Agreed in chat · edit by telling your agent". A "+ New in chat" link starts a fresh conversation.
- **Links:** Decision log, Monthly report, Proposal notifications toggle.
- **"Freeze all agent spending"** (outlined red, 50px), shown only while active. Opens V7.

### V4 — Agent chat (the core surface)

**Header** (white):
- Back, then a 34px dark avatar containing the bracket logo mark. Its dot is grey in setup, `#7BC48F` when active, `#E06B7E` when frozen.
- "Shopping agent", with a live status line: "Setting up your rules" / "typing…" / "Searching…" / "On a leash · you approve every purchase" / "Frozen — no spending access".
- Outlined red **Freeze** button while active.
- **Mandate bar** (radius 12; background `#F2F1EE` for a draft, `#E6F2E8` when active, `#F9E9EB` when revoked): shield icon, title ("Mandate draft · n of 7 rules" / "Mandate active · until Sunday"), **7 progress dots** that fill as rules are added, and a chevron. Tapping it expands the full rule list.

**Message types:**

| Type | Look | Notes |
|---|---|---|
| Agent text | white bubble, radius 18/18/18/6, 400/13/1.5, max 82% | |
| User text | ink `#14151A` bubble, white, radius 18/18/6/18, right-aligned | |
| Rule chip | tinted pill, 16px icon, overline `ADDED TO MANDATE · {LABEL}` 600/9.5, value 600/12.5 | Posted the moment a rule is created. **The main trust device.** |
| System chip | centred pill 600/10.5 | "Face ID ✓ · Mandate active · virtual card ••4417 issued" (green) / "Agent frozen · proposals withdrawn · mandate revoked" (red) |
| Summary card | white, 1.5px ink border, radius 18 | Two tiles (BUDGET / STRETCH UP TO) + remaining rules + `POST /v1/mandates → draft · Face ID confirms` |
| Search card | white radius 18, status dot, 6px progress bar | "Checked n offers across 12 shops" / "Skipped n — marketplace, wrong size, or over your ceiling" / "1 page quarantined — hidden instruction found". Updates live. |
| Flag bubble | `#F9E9EB`, flag icon, `SKIPPED · SPORTSHOP24` | Plain-language reason + `PROMPT_INJECTION · 0.94 · span 212–268 · quarantined` in mono |
| Results carousel | see below | |
| Receipt | `#2E7D45` card, white | "Paid CHF 189.00 · Nike Store", approval sentence, mono source, white "View transaction" button → V5 |
| Typing | three grey dots in an agent bubble | |

**Conversation script** (each step posts its rule chip before the next question):

1. "Hi Maya. Tell me what you need — before I spend anything, we'll agree on the rules together…" → reply `Black running shoes, size 44` → **ITEM**
2. Budget question → `Up to CHF 200` / `Up to CHF 150` → **BUDGET**. The agent states: "I'll never pay anything without your approval."
3. "…a better pair a little above it — should I show it to you?" → `Show me — up to CHF 15 more` → **HARD CEILING** (violet), or `Never go above CHF x` → **HARD CEILING** (red, equal to budget)
4. "Where may I shop?" → `Official brand stores` → clarification ("do big marketplaces like Zalando count?"), then **MERCHANTS**; or `Any shop rated 4.5+` → **MERCHANTS**. When the answer is ambiguous, the agent **asks rather than guesses** and states that it takes the stricter reading.
5. "How long should I keep looking?" → **VALID UNTIL**
6. The agent adds **APPROVAL · You approve every purchase · Face ID** and **SELLER TEXT · Can't change these rules** itself.
7. Summary card → reply chips **Confirm with Face ID** (ink-filled, fingerprint icon) / **Start over**.

Numbers follow the answers everywhere: budget 150 → stretch 165; "never go above" → hard stop equals budget.

**Composer:** suggested-reply chips (38px, radius 19, 1.5px `#DCDBD5`; the Face ID chip is ink-filled), then a text field ("Message your agent…"), a mic button and a dark send button. Free text must map into the same structured fields as the chips.

**Results carousel:**
- Header: "8 matches" and `1–5 of 8` in mono.
- Horizontal scroll with snap. Cards are 232px wide, radius 16, 1.5px border (`#E2E1DC`; `#E1C4EC` over budget; `#2E7D45` once bought).
  - 136px product image, with a rank badge ("#1 · best match").
  - Name 600/13, merchant with store icon, domain link in mono `#6A1783` (↗ opens the merchant site), price 700/17 tabular.
  - Fit chips: `Within budget` / `+CHF 8 over budget` (violet) / `Official` / `EU 44` / a perk.
  - One 44px button **"Approve · CHF 189"**: green `#2E7D45` within budget, violet `#8A1FA8` over budget. After a choice it becomes a state label: `Bought ✓` / `Not needed` / `Withdrawn`.
- **Pagination:** 5 per page, with "‹ Prev", numbered 34px page dots and "Next ›" (disabled ends greyed). Hidden when there's a single page.
- Footnote: "Every purchase needs your approval. Green: within your CHF 200 budget. Violet: over budget, inside your CHF 215 hard stop. Nothing above 215 is shown."
- Ranking is best match first. **Only offers inside the hard rule are ever proposed.**

### V5 — Transaction detail

- Merchant icon, merchant and product, amount at 700/28, tags `AGENT` + `APPROVED BY YOU` (or `· OVER BUDGET`).
- "WHY THIS WENT THROUGH": a plain sentence plus a mono source line (`step_up → customer approved · POST /resolve`).
- "Full decision trail" → V6.

### V6 — Decision log

A vertical timeline (12px dots coloured by outcome, 2px connector): paid, proposals made, Sportshop24 skipped (red), mandate confirmed (budget · hard stop · until), rules agreed in conversation.

### V7 — Freeze sheet

- Bottom sheet over a 45% dim, radius 24 top, grab handle. **No tap-outside dismiss.**
- Title "Freeze agent spending?" at 700/20, `#C0203A`.
- Scope sentence: agent card ••4417 stops, your own card ••2291 keeps working.
- Red block listing the consequences.
- Buttons: 54px red **Freeze now**, then an outlined **Cancel**.
- On confirm: return to the chat (or V3 if there was no chat), post the red system chip, and mark all proposals "Withdrawn".

---

## Interactions and behaviour

- Agent messages appear one after another with a typing indicator (about 750ms between messages, 550ms after rule chips). The chat auto-scrolls to the newest message.
- Rule chips animate in with a 120ms fade/translate, and the header dot fills at the same moment.
- Navigation: push 200ms ease-out. Sheets: slide up 260ms. No celebratory motion on money screens. Respect reduced-motion.
- Notifications: when proposals arrive while the app is closed, notify ("Your agent found 8 matches") with one haptic and **no sound**. Approval always happens in-app with Face ID, never from the notification alone.
- Duplicate attempts (same basket, `related_authorization_id`) are suppressed and never shown twice.
- Network failure on approve: keep the card actionable, show a retry, and never show a receipt optimistically.
- Accessibility:
  - Decision targets ≥ 48px, all other targets ≥ 44px.
  - Text contrast ≥ 4.5:1.
  - Colour never carries meaning alone: violet cards also say "over budget".
  - Each new agent message is announced via `aria-live` / accessibility announcements.

---

## State

```
agentSession {
  phase: none | setup | search | proposals | done
  frozen: boolean                 // our layer, checked before any upstream call
  messages: Message[]
  rules: { label, value, tone, source }[]   // 7 when complete
  budget: number                  // guidance
  hardCeiling: number             // hard_rules
  validUntil: string
  mandate: { draftId?, mandateId?, status: draft|active|revoked }
  proposals: Offer[]              // only offers <= hardCeiling, ranked
  page: number                    // 5 per page
  bought: Offer | null            // fulfils the mandate
}
```

Data flow:
- `POST /v1/mandates` when the summary card is shown.
- `/confirm` on Face ID.
- Long-poll `GET /v1/decision-requests/next?wait=25` for attempts; each becomes a proposal via `step_up`.
- `/resolve` on the customer's approve or on freeze.
- `GET /v1/events?since=` feeds the log.

---

## Design tokens

**Colour**

| Token | Hex | Use |
|---|---|---|
| allowed | `#2E7D45` | within-budget approve, active, receipts |
| allowed/tint · ink | `#E6F2E8` · `#1F5C33` | budget tile, chips |
| stopped | `#C0203A` | freeze, declines, quarantine |
| stopped/tint · ink | `#F9E9EB` · `#8E1729` | flag bubble, hard-stop tile |
| your-turn | `#8A1FA8` | over-budget approve, focus ring |
| your-turn/tint · ink | `#F3E6F7` · `#6A1783` | stretch tile, approval rule chip |
| agent tag | `#EDEBF8` · `#3D3478` | AGENT label in the host feed |
| ink | `#14151A` | text, user bubbles, dark cards |
| ink/muted | `#7C7C74` | secondary text |
| line | `#DCDBD5` / `#EFEEEA` | borders / dividers |
| canvas | `#F4F4F2` | app background |
| on-dark accent | `#7BC48F` | active dot on dark |

The three hues are semantic and exclusive: green = within rules and approved, violet = needs extra attention / over budget, red = stopped.

**Type:** Inter 400/500/600/700, with IBM Plex Mono for identifiers and API sources only. Scale: 28 amount · 22 greeting · 19 screen title · 13–14 body · 12 chips · 11 overline (+7% tracking) · 9.5–10.5 mono. `tabular-nums` on every amount.

**Radius:** chips 10–19 · buttons 11–14 · cards 16–18 · sheets 24.

**Buttons:** Approve green or violet (44–52px), Primary ink, Secondary outlined ink 1.5px, Destructive outlined red / red fill. Focus: 3px `#8A1FA8` ring at 2px offset.

Full tokens, the 5×6 button matrix, the logo construction and the 20-icon set are in `Visual System.dc.html` and `Sticker Sheet.dc.html`.

**Icons:** a 24px grid, 2px stroke, square caps. SVG path data is in the `icon()` method of the v4 logic class and in `Visual System.dc.html`. Lift the paths; don't redraw them.

**Logo:** a bracket around a dot (see Visual System). The dot works as a status light: grey none, green active, red frozen.

---

## Endpoints used

| Method | Path | Where |
|---|---|---|
| GET | `/v1/bootstrap` | app start |
| POST | `/v1/mandates` | summary card shown |
| POST | `/v1/mandates/{draft_id}/confirm` | Face ID reply |
| GET | `/v1/mandates/{id}` | V3 |
| DELETE | `/v1/mandates/{id}` | freeze, step 4 only |
| GET | `/v1/decision-requests/next?wait=25` | search loop |
| POST | `/v1/authorizations/{id}/decision` | engine: `step_up` or `decline` — never a self-issued `approve` |
| POST | `/v1/authorizations/{id}/resolve` | customer approve; freeze decline |
| GET | `/v1/authorizations`, `/v1/events?since=` | log, report |

API notes: https://github.com/Swiss-ai-Weeks/viseca-2026/blob/main/technical_details.md

---

## Files

| File | Use |
|---|---|
| `Hi-Fi Prototype v4 In-App Chat.dc.html` | **Primary.** All 7 screens, the chat script, the carousel and the freeze flow |
| `Visual System.dc.html` | Logo, type, colour hex, buttons, icon SVGs |
| `Sticker Sheet.dc.html` | Component states and variants |
| `IA and Storyboards.dc.html` | Information structure and storyboards. Its "policy editor" steps are now the chat, and any "silent approve" is superseded by rule 1 |
| `support.js`, `image-slot.js` | Prototype runtime. **Do not port** |

## Implementation order

1. Tokens, icons, and the chat primitives (bubbles, rule chip, system chip).
2. The conversation → structured rules → draft → Face ID confirm loop, with both numbers shown.
3. The search loop and the proposal carousel with pagination; every approval via `/resolve`.
4. Freeze with its 4-step order.
5. Quarantine flags and the skipped bubble.
6. Host integration: banner states, AGENT tags, settings row, V3, V5, V6.

**Do not ship** any of these:
- a path that pays without Face ID approval
- a budget shown without its hard stop
- a chat message that alters a confirmed mandate
- a freeze that skips the ordering
- a quarantine chip backed only by a boolean
