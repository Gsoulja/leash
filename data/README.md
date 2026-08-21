# Synthetic data pack

This is the fictional data pack used by the challenge API. It contains no real
people, payment credentials, expected decisions, risk labels, or answer key.
The challenge treats an AI shopping agent as transaction provenance, not as a
separate customer, provider, or master-data entity.

## Contents

| File | Rows | Use |
| --- | ---: | --- |
| `customers.csv` | 20 | Fictional customer personas |
| `accounts.csv` | 31 | Synthetic account context and limits |
| `cards.csv` | 41 | Synthetic card capabilities and current status |
| `merchants.csv` | 58 | Merchant, MCC, country and category context |
| `items.csv` | 66 | Fictional item catalogue and CHF price ranges |
| `fx_rates.csv` | 4 | Fixed synthetic currency conversion table |
| `authorization_history.csv` | 4,701 | The single historical authorization file, with human, agent, and merchant provenance |
| `scenario_catalogue.csv` | 5 | Scenario names, cardholder instructions, and neutral control questions |
| `scenario_authorities.csv` | 5 | Fixture identity and lifecycle data for scenario replay; not participant mandates |
| `purchase_attempts.csv` | 45 | Every runtime purchase attempt in the five public scenarios |
| `purchase_attempt_items.csv` | 56 | Cart lines for those attempts |
| `scenario_fixtures/connection_check.json` | 1 | Authoring fixture for the SCEN0000 attempt |
| `scenario_fixtures/example_authorization_request.json` | 1 | One complete `authorization.request`, schema-valid |
| `schemas/` | 3 | Machine-readable data-pack and event contracts |
| `metadata.json` | 1 | Pack manifest: files, hashes, history profile, and scenario summary |

`metadata.json` is the authoritative manifest: it lists every file with its row
count and SHA-256 hash, the history window and profile, and the scenario-pack
summary, and it is validated by `schemas/data_pack.schema.json`. The event
contract in `schemas/authorization_event.schema.json` is a strict
validator for live events; `schemas/authorization_history.schema.json`
defines the history CSV column contract.

## The five public scenarios

Each scenario is one cardholder, one card, one natural-language instruction,
and an ordered sequence of purchase attempts. The scenario set deliberately
mixes attempts that a good control layer should wave through, attempts it should
stop, and attempts where the honest answer is to ask the human. `SCEN0000` is
intentionally a one-event connectivity check. **The scenario identifier tells
you nothing about the answer**, and neither does the position of an event in the
sequence.

| ID | Name | Events | Cardholder | Card | What it exercises |
| --- | --- | ---: | --- | --- | --- |
| `SCEN0000` | Connection check | 1 | `CU0001` | `CA0001` | One small, unambiguous purchase, to prove the decision path works end to end |
| `SCEN0001` | Household budget | 10 | `CU0001` | `CA0001` | A per-order limit and a rolling seven-day limit, delivery fees inside the limit, order splitting, and a basket line outside the stated purpose |
| `SCEN0002` | Requested item and order terms | 12 | `CU0006` | `CA0011` | Item attributes, return terms, substitution, an unrequested add-on, retailer type, and an unfamiliar but fully compliant seller |
| `SCEN0003` | Session integrity | 11 | `CU0012` | `CA0023` | Device novelty, velocity, unfamiliar merchants and countries, recovery after a burst, and limits that still bind in a clean session |
| `SCEN0004` | Manipulated agent | 11 | `CU0019` | `CA0039` | Instructions embedded in merchant-supplied text, a lookalike seller, a duplicate order, an unrequested add-on, a cart that contradicts the stated purchase, and a legitimate re-quote |

All 45 attempts are delivered to a team as actionable decision requests. No
attempt in this pack is removed by the platform pre-check, so
`authority_status` and `card_status_at_attempt` are `active` on every event.
`purchase_attempts.csv` is the single source of those attempts, SCEN0000
included; `scenario_fixtures/connection_check.json` is a read-only copy of row
`AU0001`, not a second event. To replay a scenario offline, emit the rows of
`purchase_attempts.csv` in `replay_order`, joined to `purchase_attempt_items.csv`
and `merchants.csv`.

These fixtures are also the runtime input used by the sandbox. Keeping one
source of truth makes offline development and the live API agree exactly.

Several attempts are designed so that a plausible-looking shortcut gets them
wrong in *both* directions. Some purchases look alarming and are legitimate;
others look ordinary and are not. A solution that only ever blocks, or only
ever approves, performs poorly on every scenario.

## What the history is and is not

`authorization_history.csv` is the single chronology-safe historical file. It
joins customer, account, card, and merchant context so that a team can build
familiarity, velocity, or behavioural features without assembling its own
joins. There is no second raw transaction CSV to reconcile with it, and runtime
context is assembled by the API at replay time.

The 4,701 rows run from `2025-09-01` to `2026-07-31` and are simulated from
persona-level behaviour: each of the 20 personas has its own category mix,
preferred merchants, channel mix, hours, travel pattern, spending scale, and
degree of shopping-agent adoption. Rows per persona range from 201 to 282, and
agent adoption from 2 rows to 41.

Two properties are worth stating explicitly, because they determine what kind
of model is worth building:

- **The observed `status` is not an answer key and not a fraud label.** It is
  the outcome an authorization system produced at the time, driven by several
  interacting factors — amount relative to the cardholder's own norm, merchant
  familiarity, attempt velocity, hour of day, cross-border use, account limits,
  and card lifecycle — with a stochastic component on top.
- **Provenance is explicit and behavioural signals are graded.**
  `initiator_type` directly identifies human, agent, and merchant activity.
  Card lifecycle fields can also explain some issuer declines. Other signals
  are probabilistic: for example, declines are more likely after several recent
  attempts, but velocity alone does not determine an outcome.

Of the 4,701 rows, 259 are declined (5.5%), spread unevenly across personas
rather than by quota. 453 rows are agent initiated (9.6%), of which 416 were
approved and 37 declined. Declined agent rows are ordinary history and are not
labelled as fraud.

## Provenance model

The historical file uses one source-of-truth field, `initiator_type`:

- `human` means an ordinary cardholder purchase;
- `agent` means a synthetic AI shopping-agent purchase attempt;
- `merchant` means a refund event.

An agent row still carries its observed `status`, so approved and declined
agent attempts are directly usable without joining to an agent catalogue or a
separate historical mandate table. Agent rows occur only on the channels an
agent can actually use (`ecommerce` and `recurring`), and they share devices,
merchants, and calendar days with the same cardholder's own purchases.

Use `card_id -> cards.card_id`, then
`cards.account_id -> accounts.account_id -> customers.customer_id` to reach
customer context. Use `merchant_id -> merchants.merchant_id` for merchant
context. The `scenario_authorities.csv` rows connect fixture profiles to their
customer and card and supply scenario lifecycle metadata. They are not the
participant mandate and contain no cardholder instruction.

## API relationship

The API reads this directory at startup. It serves the small catalogues from
`GET /v1/reference-data`, the canonical history from
`GET /v1/reference-data/authorization-history.csv`, and runtime attempts as
nested JSON through scenario runs. The runtime authorization contains
`initiator_type="agent"` and one active participant `mandate` object containing
the cardholder's instruction and structured rules. The scenario fixture
authority is used only to select the profile and provide lifecycle signals.

## Two kinds of authority, one policy

Only one of these is a participant policy:

| Identifier | Source | Meaning | Contains the cardholder instruction? |
| --- | --- | --- | --- |
| `SCEN...` | `scenario_catalogue.csv` | Public challenge scenario and its raw `cardholder_instruction` | Yes, as raw intent only |
| `AUTH...` | `scenario_authorities.csv` | Static customer/card identity and lifecycle signals used to replay a scenario | No |
| `TM...` | `POST /v1/mandates` | Participant-created, confirmed live mandate containing the structured rules | Yes |

The runtime joins these concepts without joining their IDs: the selected
`SCEN...` determines which fixture profile and `AUTH...` authority produce the
next purchase, while the participant's confirmed `TM...` mandate controls the
decision. A live event therefore has `authorization.profile_id`,
`authorization.initiator_type="agent"`, and `authorization.mandate_id="TM..."`;
the static `AUTH...` key is only an input link for the scenario runner.

All records are deterministic synthetic fixtures. Monetary values are not real
transactions, and identifiers such as `CA0001` are deliberately not payment-
card numbers.
