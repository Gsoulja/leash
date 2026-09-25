# Decision log

Every rule the engine applies has a source. This log records the ones that are **our decisions** or **assumptions**, so a ticket can point to a decision instead of burying it in its technical approach.

| Source | Meaning |
| --- | --- |
| **Viseca** | Stated in `challenge.md` or `technical_details.md`. Not ours to change. |
| **Team** | Our product or engineering decision. We can change it; update this log first. |
| **Assumption** | Needed to build, but only Viseca can confirm. Listed for the expert Q&A (LEASH-110). |

Status: **Accepted** (build on it) · **Proposed** (default we build on until the product owner confirms) · **Open** (needs an answer).

Reviewed with the product owner on 2026-09-23. Tickets reference these IDs.

## Stack and structure

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-001 | Postgres 17 is the database. The "SQLite for the hackathon" line in the system design is stale and gets fixed in LEASH-111. | Team | Accepted |
| DEC-002 | Backend in Python 3.12 (FastAPI, asyncpg); customer app in React + TypeScript. | Team | Accepted |
| DEC-021 | The customer app **ports the prototype's screens and styles** into React components wired to the real API, rather than redesigning them. | Team | Superseded by DEC-044 |
| DEC-026 | Lightweight Definition of Ready: a ticket names its rule source, gives one example and one edge case, and has no open decision that could change it. | Team | Accepted |
| DEC-027 | Work is sequenced in vertical milestones M0–M6 (tagged on every ticket) so a thin end-to-end slice works early. | Team | Accepted |
| DEC-028 | Team size and available hours. The MVP (M0–M5) is still about 200 h. | — | **Open** |
| DEC-032 | `leash.purchase.max_count` counts **every approved purchase in the run** (new rule version `v2`), not only purchases of the requested item. Why: LEASH-034 found that under v1, adding an `items.item_id` rule narrowed what counts, so a tightened mandate could approve a purchase that "buy it once" would have stopped (pack AU0017: step_up → approve). v2 never loosens when a mandate is tightened, and gives the same results for the agreed cases, because in item mode only matching purchases are approved. Product owner chose option (a) on 2026-09-24. | Team | Accepted |
| DEC-031 | A step_up caused only by an unsupported mandate rule (DEC-005) **can be approved by the customer**. The re-check still blocks Approve when a hard rule fails (DEC-012). Product owner decided on 2026-09-24. | Team | Accepted |
| DEC-030 | Duplicates, split orders, purpose mismatches and "already bought" (DEC-023) are **never approved automatically**: `step_up` under the `ask` and `approve` policies, and still `decline` under a `decline` policy (the same rule as an injection, DEC-029). First recorded as "`step_up` whatever the policy"; changed on 2026-09-24 (option A) after the LEASH-034 review showed that version let a tightened mandate loosen a verdict (an unknown-category decline became an outside-purpose step_up). Default until the Viseca experts answer (question 7). Product owner decided on 2026-09-24. | Team (ask Viseca) | Accepted |
| DEC-029 | A definite injection in shop text (a regex match) **always leads to `step_up`**, whatever the uncertainty policy is, including `approve`. A shop trying to manipulate the agent is an integrity signal, not ordinary uncertainty. Hard rules still apply first: an order that fails one is still declined. Today it is only a warning, so under `approve` it is approved; the code has to change. Product owner chose option B on 2026-09-24. | Team | Accepted |

## Mandates and rules

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-003 | The mandate embedded in the live event is authoritative for that run. We compile it from its `hard_rules`, never from the instruction text. The local copy is only a cross-check; a mismatch raises an integrity alert and the event wins. | Viseca contract + Team | Accepted |
| DEC-004 | Every enforceable permission is a `hard_rule`. Our own fields use a versioned registry with a `leash.` prefix (e.g. `leash.merchant.prior_purchases.v1`). `guidance` holds explanation only, because it is absent from live events. | Viseca contract + Team | Accepted |
| DEC-005 | A mandate rule the engine can't evaluate (unknown field) never leads to approve: the outcome is `step_up`, or `decline` when the policy is `decline`. Reason `unsupported_mandate_rule`, plus an operational alert. | Team | Accepted |
| DEC-006 | Tightening appends stricter rules; existing rules are never removed or replaced. When a field appears more than once, the strictest rule wins. | Viseca contract | Accepted |
| DEC-013 | Singular wording ("the monitor I chose", "one item", "replace my shoes") compiles to one successful purchase with quantity 1. Shown to the customer at confirmation. | Team | Accepted |
| DEC-014 | "A shop I use regularly" = at least 3 earlier approved purchases at that merchant on this card. Shown at confirmation. | Team | Accepted |
| DEC-022 | Fulfilment wording ("for delivery") compiles to a fulfilment rule; any other fulfilment method fails it. | Viseca brief (SCEN0001 wording) | Accepted |
| DEC-023 | Outcomes: duplicates, split orders, purpose mismatches and "already bought" go to `step_up`. An unfamiliar shop under an explicit "shops I've used before" rule is declined; a lookalike name is added as evidence. | Team | Accepted |
| DEC-024 | Session risk v1: new device 2 points, 2+ attempts in 10 min 2 points (1 attempt: 1), night-time in Zurich (00–06) 1 point, first-time country 2 points. Two or more points → warning. | Team | Accepted |

## State, time and money

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-007 | Decision order: validate → dedupe → read facts outside the lock → per-card lock → rebuild snapshot → decide → save authorization, event and outbox row → commit → POST the decision immediately → mark sent. The outbox only recovers from crashes. Lock waits are bounded (`lock_timeout`). | Team | Accepted |
| DEC-008 | `deadline_at` is authoritative for automated answers. The watchdog sends a safe `step_up` when the remaining time falls below a margin that covers lock wait and sending, not at a fixed 6 s. The human window and other timeouts come from `/v1/bootstrap`; the app counts down from the server's expiry time. | Viseca contract + Team | Accepted |
| DEC-010 | Period spend = final agent approvals in this run, by simulated time. It is compared with the platform's `context.approved_spend_in_period_chf`; on a mismatch the higher value is used and an integrity alert raised. Refunds don't occur in runs. | Team | Accepted |
| DEC-011 | Familiarity counts approved **purchases** only (never refunds, cash withdrawals or declines) from the history, plus approvals in this run (DEC-015). | Viseca data dictionary + Team | Accepted |
| DEC-025 | Merchant text is bounded: readers cap input per purchase; oversized text adds a caution warning (`oversized_merchant_text`) instead of being silently cut. | Team | Accepted |

## Customer answers

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-012 | Customer confirmation resolves uncertainty but never loosens a hard rule. Hard rules are re-checked when the ask is shown and when the customer taps. If a limit now fails, Approve is replaced by an explanation and only Reject remains, so the record sent through `/resolve` stays truthful. | Team (ask Viseca how to record it) | Accepted |
| DEC-016 | No customer answer within the window → not approved. | Assumption | Proposed |
| DEC-017 | Revoking while purchases wait: the app shows only outcomes the platform confirms. | Assumption | Proposed |
| DEC-015 | A shop approved earlier in the same run counts as "used before". | Assumption | Proposed |

## Models

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-009 | Model unavailability alone is informational. If an active rule needs a fact the deterministic reader can't establish, that missing fact follows the customer's uncertainty policy. A definite regex injection match always adds caution. Merge rule: model output may add facts or warnings, never erase a deterministic warning, never turn "missing" into a pass, and the final verdict is never less strict than the deterministic one. | Team | Accepted |

## Scope

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-018 | Pitch deck: unknown whether required. Until Viseca answers, it is P1 and not part of the functional freeze. | — | **Open** (ask Viseca) |
| DEC-019 | End-user login is out of scope for the prototype. | Team | Accepted |
| DEC-020 | MVP = milestones M0–M5. After MVP (M6): Laya training and inference (LEASH-073–082), shop assistant (LEASH-100–103), engine inspector (LEASH-097). The regex reader and its fallback wrapper (LEASH-070–072) stay in the MVP. | Team | Accepted |

## Permission-control agreement — 2026-09-24

Accepted product direction from the customer discussion; these are implementation requirements, not claims that the work is complete. DEC-033 supersedes the own-shopping-assistant scope in DEC-020. Earlier numerical defaults and Viseca contract rules remain unchanged unless a separate decision explicitly changes them.

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-033 | Leash builds the permission/control layer. Its LLM clarifies and proposes rules; an external shopping agent searches and prepares orders. Viseca's simulator represents that agent in the challenge. No permission-LLM tool may activate authority, start shopping or decide payment. | Product owner, 2026-09-24 | Accepted |
| DEC-034 | Background preferences and scoped earlier history inform questions, not authority. Preserve provenance and freshness; separate customer populations and current intent from inferred habits. Profile suggestions require explicit adoption and final confirmation. | Product owner, 2026-09-24 | Accepted |
| DEC-035 | Review is derived from exact enforceable rules and uncertainty policy, with Must follow / May choose / Must ask. Unconfirmed corrections create a new local draft revision; stale review/confirm actions fail. Submitted platform drafts are immutable; active mandates retain DEC-006. Consent binds the reviewed revision. | Product owner, 2026-09-24 | Accepted |
| DEC-036 | Verify both support for proposed rules and omissions from source intent. Laya permission verification is separate from shop-text reading; evaluate a reviewed baseline, calibrate and use shadow mode before any active use. Fine-tune only when evidence justifies it. Model agreement never grants authority. | Product owner, 2026-09-24 | Accepted |
| DEC-037 | Preserve evidence from conversation and context through confirmed permission, run, actual checkout, checks and platform outcome. A local approval is not platform acceptance, and neither proves delivery. Production requires authenticated consent and a controlled payment path; the credential protocol remains open. | Product owner, 2026-09-24 | Accepted |

Open implementation choices: LLM, permission-verifier quality thresholds and training need, production customer authentication, external-agent identity and credential format. DEC-019 excludes login only from the prototype. Historical defaults such as DEC-013/014 must be visible interpretations in review, not falsely attributed to literal customer words; an unresolved chosen-product reference still requires clarification.

## Delivery truth, migration safety and release controls — 2026-09-24

Judgement calls made while building LEASH-130, LEASH-135, LEASH-141 and LEASH-151. Each shapes behaviour
and each could reasonably have gone the other way, so each is recorded with the alternative it was chosen
over. **Proposed**: the code builds on them now, and the product owner has not yet confirmed them.

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-038 | A terminal platform refusal is final. Once the platform refuses a decision, the purchase stays `not_sent` and counts toward nothing, even if a later redelivery of the same decision is accepted. Chosen over allowing `refused → accepted`: staying refused under-counts spend and never over-counts, and re-entering the ledger would be the loosening "mandates only tighten" forbids. The reconciler raises the disagreement once for a person rather than resolving it silently. | Team, 2026-09-24 | Proposed |
| DEC-039 | Spending limits are enforced against what the **engine** approved, not against what the platform has acknowledged. A local approval reserves its amount the moment it is decided; a terminal refusal releases it. Chosen over enforcing against accepted spend only: that matches the platform exactly but lets two concurrent purchases both pass while their acknowledgements are outstanding. `accepted_chf` and `awaiting_platform_chf` report the narrower facts beside it. | Team, 2026-09-24 | Proposed |
| DEC-040 | The append-only audit log outranks reversibility. `0006` and `0009` cannot be downgraded on a database that recorded a reclaimed claim or a delivery, because the blocking rows cannot be deleted. Chosen over relaxing the append-only trigger to make the chain reversible. Such a downgrade requires verified backup evidence — dump taken, restored elsewhere, row counts of every touched table checked, location and checker recorded. **This procedure has no named owner yet.** | Team, 2026-09-24 | Proposed |
| DEC-041 | A demo reset verifies the baseline **per card**, against `data/authorization_history.csv`. A reset leaves no runs, so per-card (the scope a run is bound to, `runs.card_id`) is the only scoped total the database can check. Per-scenario totals live in `purchase_attempts.csv`, which is not seeded. | Team, 2026-09-24 | Proposed |
| DEC-042 | The Compose service name `db` counts as a local database for the demo reset's host guard, so the containerised reset works. On a machine where DNS resolves `db` to something real, the `--yes` / `LEASH_ALLOW_DEMO_RESET` guard is the only remaining protection. Chosen over dropping `db` and requiring `--live` in Compose. Locality is otherwise resolved the way libpq resolves it: URL host, then `?host=`, then `PGHOST`, then a unix socket. | Team, 2026-09-24 | Proposed |
| DEC-043 | CI checks run on GitHub Actions. The repository has a GitHub remote and no other CI configuration, so this is the only non-speculative choice for the **checks**. It is explicitly *not* a deployment decision: LEASH-141's out-of-scope rule stands, and staged rollout, rollback and a deployment target remain open behind deployment ownership. | Team, 2026-09-24 | Proposed |

## Customer-app design source — 2026-09-25

Ruled on by the product owner at the LEASH-180 gate: all eight proposed defaults were accepted as written. Sources are quoted from the handoff `designPrototype/README.md` ("About the design files", "Critical domain rules" 1–2, "Screens" V3, V4 and V7) and weighed against DEC-033, which was logged after the handoff and outranks it.

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-044 | The Hi-Fi v4 handoff (`designPrototype/`) replaces the placeholder prototype as the **design source for the customer phone app**; DEC-021 is superseded. The handoff's own README says the files are "not production code": recreate them with the app's components and do not port `support.js`, `<x-dc>`, `image-slot.js` or inline styles. The eight scope rulings follow this table. | Product owner, 2026-09-25 | Accepted (ruling 2 amended by DEC-045) |

1. **Design source.** Adopt the handoff's visual system (tokens, type, icons, logo, component shapes) for the customer phone app. The engine inspector keeps its own tokens.
2. **Surfaces in scope.** In: tokens, type, icons and logo, chat primitives, rule chip, summary card, mandate bar, V3 agent-access status card and tiles, V7 freeze sheet as the revoke presentation, V5 transaction-detail styling, step-up restyle. **Out, superseded by DEC-033:** agent product search and the search card, the product carousel and pagination, per-proposal "Approve · CHF" buttons, the receipt card, the "searching / N matches" banner states, and handoff rule 1 (see 3). **Out, generic host shell:** card hero, quick actions, Cards/Profile tabs. **Out, owned elsewhere:** the V6 decision-log timeline (LEASH-148/150).
3. **Handoff rule 1 ("Every purchase requires customer approval").** Not adopted. The designer brief (`customer-journey-for-design.md`, "Fits: proceed without interruption") and the engine both approve within permission. UI copy must never say the customer approves every purchase.
4. **Budget vs hard stop.** Live mandates carry only `hard_rules` (DEC-004); Leash has no "stretch" concept. The enforceable per-order limit is the red "HARD STOP AT" tile. A green BUDGET tile appears only when a separate guidance budget exists, labelled as guidance, never as enforced.
5. **"Confirm with Face ID".** DEC-019 excludes login from the prototype and the app performs no biometric check. Keep the ink-filled confirm chip with the fingerprint icon, labelled "Confirm permission"; never claim biometric authentication.
6. **Assistant persona.** Under DEC-033 Leash's assistant clarifies permission and does not shop. The chat header reads "Permission assistant"; status lines are limited to setting up / active / revoked (no "Shopping agent", no "Searching…").
7. **Split with LEASH-145/146.** LEASH-189–190 present today's draft flow as a chat. LEASH-145/146 add LLM clarification, revisions, context and the Must follow / May choose / Must ask review (DEC-035) on top, reusing these chat primitives rather than rebuilding them.
8. **Tab bar.** The app's three tabs stay visible everywhere, including chat and the freeze sheet. They are the app's navigation, not the handoff's host shell.

**Amendment, 2026-09-25 (after the LEASH-179 build).** The product owner asked for the handoff's V1 Home instead of the restyled Cockpit.

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-045 | Amends DEC-044 ruling 2: the first tab becomes **Home**, following the handoff's V1 layout (replacing the "Cockpit" name; the spending card and payment list stay below). Adopted parts: a greeting, a dark card hero and four quick-action tiles. The card hero shows only facts Leash has (the agent's permission status, the per-order hard stop, what is left in the period): no card number, balance or expiry is invented, and nothing imitates an issuer's real card. Each tile opens a real Leash destination (no dead buttons): the handoff's "Lock card" and "Settings" have no Leash equivalent and become "Revoke" and "Payments". The greeting has no customer name, since the prototype has no login (DEC-019). Still out: the agent banner (not chosen), the Cards/Profile tabs, and the banner's searching/matches states (DEC-033). Tabs stay Home · Agent · Permission (ruling 8). | Product owner, 2026-09-25 | Accepted (card and banner amended by DEC-046) |

| ID | Decision | Source | Status |
| --- | --- | --- | --- |
| DEC-046 | Amends DEC-045 on Home. (1) The dark card becomes the handoff's **credit card** ("Credit card", masked number, available amount, expiry) with **static demo values**. These are invented for the demo: no API or pack field supplies a card number or balance. They live in one constant in `Home.tsx` and never feed a decision. The agent's permission status leaves the card; it stays on the Permission tab. (2) The spending card ("Agent spent" with its counts) is removed from Home. In its place is the handoff's agent banner in its "never started" state, "Try your new AI shopping agent · Set rules together in a chat", which opens the chat. It is shown only while no permission is active, and hidden once one is. The banner names the external shopping agent, whose rules the chat sets; Leash itself still never claims to search or shop (DEC-033). | Product owner, 2026-09-25 | Accepted |

## Questions for the Viseca experts (LEASH-110)

1. No answer within the human window: what does the platform record? (DEC-016)
2. Revoking while purchases are queued or waiting? (DEC-017)
3. Does singular wording mean exactly one purchase? (DEC-013)
4. Do approvals earlier in the run count as familiar? (DEC-015)
5. How should "customer wanted to approve, but a limit now blocks it" be recorded? (DEC-012)
6. Is a pitch deck part of the submission? (DEC-018)
7. Should duplicates, split orders and "already bought" go to step_up even when the customer's policy is approve? We never approve them automatically, and decline them under a decline policy. (DEC-030)
8. If the platform dequeues a decision request and the delivery of that response fails, is the request redelivered? `technical_details.md` does not say, and it decides whether a client may safely retry `GET /v1/decision-requests/next`. Ours retries once on a transport error. (DEC-038)
9. When the platform terminally refuses a decision (for example `deadline_passed`), does it ever accept a later redelivery of the same decision? We treat a refusal as final either way. (DEC-038)
