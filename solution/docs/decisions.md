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
| DEC-021 | The customer app **ports the prototype's screens and styles** into React components wired to the real API, rather than redesigning them. | Team | Proposed |
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

## Questions for the Viseca experts (LEASH-110)

1. No answer within the human window: what does the platform record? (DEC-016)
2. Revoking while purchases are queued or waiting? (DEC-017)
3. Does singular wording mean exactly one purchase? (DEC-013)
4. Do approvals earlier in the run count as familiar? (DEC-015)
5. How should "customer wanted to approve, but a limit now blocks it" be recorded? (DEC-012)
6. Is a pitch deck part of the submission? (DEC-018)
7. Should duplicates, split orders and "already bought" go to step_up even when the customer's policy is approve? We never approve them automatically, and decline them under a decline policy. (DEC-030)
