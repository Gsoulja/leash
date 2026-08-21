# Agent on a Leash — Technical details

This document describes the technical material available to participants: the
synthetic data pack, the sandbox API, the event protocol, and the local usage
flow. It defines the interface to build against; it does not prescribe a
policy, model, user interface, or decision strategy, and it contains no
expected decisions or reference solution.

## What you receive

The challenge environment provides:

- A REST API for synthetic cardholder profiles, mandates, scenario runs, and
  authorization decisions.
- A versioned synthetic data pack in [`data/`](data/), including catalogues,
  historical authorizations, scenario fixtures, examples, and JSON Schemas.
- Five public scenarios, each with one cardholder, one card, a
  natural-language instruction, and an ordered sequence of purchase attempts
  with cart lines and session signals. Together they deliver 45 actionable
  decision requests. Across the scenario set, the attempts include ordinary,
  ambiguous, unsafe, and manipulated cases, so neither a scenario label nor an
  event's position in the sequence determines the right control action.
  Depending on the policy and evidence, an attempt may reasonably be approved,
  declined, or paused for human confirmation; the judging approach is described in
  [`challenge_public.md`](challenge_public.md#judging-criteria).
- Machine-readable JSON Schema contracts for the data pack, the historical
  file, and the live authorization request.
- No managed LLM is part of the sandbox contract. You may use your own model
  or provider, but your solution must not depend on organizer-hosted model
  access, network availability, or credentials that are not explicitly
  supplied by the organizers.

The sandbox is a simulation. It has no connection to real cards, accounts,
payment networks, Viseca systems, credentials, customer data, or real money.
Teams may build a web application, service, notebook, command-line worker, or
another prototype that uses only the parts of the interface useful to their
idea.

## Before the API opens

The sandbox API is live at:

```text
https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io
```

Each team receives its own **team API key on the day of the event**; keys are
never published in this repository. Until then the authenticated endpoints are
not callable — and you do not need them, because the 45 public attempts are the
same fixtures the API delivers. You can develop and replay the complete flow
offline.

There is no server to run. The sandbox implementation is private and is
operated by the organizers, so there is no command to start an API from a clone
of this repository. On the day, point `LEASH_BASE_URL` at the URL above and use
the API key you were given.

What you can do before that:

- **Compile the instructions.** The five `cardholder_instruction` values in
  `scenario_catalogue.csv` are the heart of the problem. Turning natural
  language into something you can enforce needs no API at all.
- **Study the behaviour.** `authorization_history.csv` holds 4,701 historical
  authorizations for the same cardholders, with familiarity, velocity, and
  spending context already joined.
- **Build your parser.**
  [`data/scenario_fixtures/example_authorization_request.json`](data/scenario_fixtures/example_authorization_request.json)
  is a neutral, complete `authorization.request` and shows the exact shape your
  engine must accept. It is not a scenario attempt. Validate it against
  [`data/schemas/authorization_event.schema.json`](data/schemas/authorization_event.schema.json)
  with any JSON Schema library.
- **Replay the scenarios offline.** Join `purchase_attempts.csv` to
  `purchase_attempt_items.csv` and `merchants.csv`, emit the rows in
  `replay_order`, and you have the same 45 events the API will deliver in a
  public development run. Watch the types: the CSV gives you strings, and the
  event schema wants numbers and integers. `spend_in_period_before_chf` is
  empty in the public CSV and null in the event. `delivery_by` and
  `related_authorization_*` are optional, but some public attempts populate
  them. `recent_attempt_count_10m` is the count of earlier attempts in the
  same scenario whose simulated timestamp is within the preceding ten minutes;
  the interval includes the ten-minute boundary and excludes the current
  attempt. It counts attempts regardless of their eventual decision.

`purchase_attempts.csv` is the single source of runtime attempts: all 45
events, including SCEN0000's, come from that file.
`scenario_fixtures/connection_check.json` is a read-only copy of row `AU0001`
for inspection, not a second event. A participant solution may communicate with
the documented API using any HTTP client and may use the public CSV and JSON
files directly.

## Public data pack

The full file-by-file explanation is in [`data/README.md`](data/README.md), and
field definitions, units, null values, joins, chronology, and provenance are in
[`data/data_dictionary.md`](data/data_dictionary.md).

| File | Contents | Typical use |
| --- | --- | --- |
| `customers.csv` | 20 fictional customer personas | Optional customer context |
| `accounts.csv` | 31 synthetic accounts | Join account and customer context |
| `cards.csv` | 41 synthetic cards and statuses | Card capability and lifecycle context |
| `merchants.csv` | 58 fictional merchants, MCCs, countries, and categories | Merchant context and familiarity |
| `items.csv` | 66 fictional items and CHF price ranges | Cart and item context |
| `fx_rates.csv` | Four fixed synthetic conversion rates | Convert supported currencies to CHF |
| `authorization_history.csv` | 4,701 historical authorizations | Optional behavioural or familiarity features |
| `scenario_catalogue.csv` | Scenario instructions and metadata | Select a scenario and read its raw intent |
| `scenario_authorities.csv` | One fixture identity per scenario | Connect a scenario to its synthetic customer and card |
| `purchase_attempts.csv` | 45 ordered runtime attempts | Offline scenario development |
| `purchase_attempt_items.csv` | Cart lines for the runtime attempts | Offline cart analysis |
| `scenario_fixtures/connection_check.json` | Authoring fixture behind the SCEN0000 connection check | Read the SCEN0000 attempt offline |
| `scenario_fixtures/example_authorization_request.json` | One complete `authorization.request`, schema-valid | Validate an event parser offline |
| `schemas/` | Machine-readable data and event contracts | Validate files and requests |

The simple path needs `scenario_catalogue.csv` and the authorization events
delivered by the API. The other tables are optional context. For a customer
join, use:

```text
authorization_history.card_id
  -> cards.card_id
  -> accounts.account_id
  -> customers.customer_id
```

For merchant context, join `authorization_history.merchant_id` to
`merchants.merchant_id` — on the identifier, never on `merchant_name`, because
at least one pair of merchants has deliberately similar names. Historical
`status` is an observed authorization outcome, not a fraud label or answer key.
The `initiator_type` values identify ordinary customer purchases (`human`),
synthetic agent attempts (`agent`), and merchant refunds (`merchant`). Use the
data dictionary for the exact chronology-safe meaning of derived fields.

The history is worth a moment's calibration before you model it. `status` is
the observed issuer outcome, not the desired delegated-spending decision.
`initiator_type` explicitly identifies human, agent, and merchant activity.
Other behavioural signals are graded rather than absolute: for example,
declines are more likely after several attempts in ten minutes, but velocity
alone does not determine an outcome.

All monetary values use the row currency unless the name ends in `_chf`.
Supported currencies are `CHF`, `EUR`, `GBP`, and `USD`; `billing_amount_chf`
is calculated with the fixed rates in `fx_rates.csv`. Dates use `YYYY-MM-DD`,
timestamps use UTC ISO 8601, and empty optional CSV fields represent missing
values. All identifiers are fictional and deliberately are not PANs, IBANs,
or payment credentials.

### Scenarios

The `cardholder_instruction` is raw natural-language intent. It is not a
precompiled policy and does not contain an expected action.

Each scenario is one cardholder, one card, and an ordered sequence of purchase
attempts. All 45 attempts reach a team as actionable decision requests: nothing
in this pack is removed by the platform pre-check.

| ID | Name | Events | Cardholder | Card | What it exercises |
| --- | --- | ---: | --- | --- | --- |
| `SCEN0000` | Connection check | 1 | `CU0001` | `CA0001` | One small, unambiguous purchase, to prove the decision path works end to end |
| `SCEN0001` | Household budget | 10 | `CU0001` | `CA0001` | A per-order limit and a rolling seven-day limit, delivery fees counted inside the limit, order splitting, and a basket line outside the stated purpose |
| `SCEN0002` | Requested item and order terms | 12 | `CU0006` | `CA0011` | Item attributes, return terms, substitution, an unrequested add-on, retailer type, and an unfamiliar but fully compliant seller |
| `SCEN0003` | Session integrity | 11 | `CU0012` | `CA0023` | Device novelty, velocity, unfamiliar merchants and countries, recovery after a burst, and limits that still bind in a clean session |
| `SCEN0004` | Manipulated agent | 11 | `CU0019` | `CA0039` | Instructions embedded in merchant-supplied text, a lookalike seller, a duplicate order, an unrequested add-on, a cart that contradicts the stated purchase, and a legitimate re-quote |
| **Total** | | **45** | | | |

The `event_count` column in `scenario_catalogue.csv` matches these counts, and
every event has a row in `purchase_attempts.csv`. `SCEN0000`'s attempt is
`AU0001`, and `scenario_fixtures/connection_check.json` is the same attempt in
authoring-fixture form rather than an extra event.

The 45 public attempts are a repeatable exercise set designed to explore many
combinations of intent, purchase facts, order terms, history, and session
signals. They are not an implementation contract made up of 45 cases to
special-case, and they do not provide expected action labels. Build the decision
logic against the cardholder instruction, mandate, authorization fields, and
available context. Do not use `scenario_id`, authorization IDs, descriptions,
or replay positions as a lookup key for the outcome; the same control layer
should evaluate each request from its evidence.

Because no fixture fails the pre-check, a decision request always carries
`authority_status="active"` and `card_status_at_attempt="active"`. The other
values of those two enums exist in the event schema for platform behaviour, not
because a team engine will observe them here. Card lifecycle is visible in
`authorization_history.csv` instead, where two cards left service inside the
window.

Some deliberate design notes, because they change what a good solution looks
like:

- **The scenario set mixes outcomes.** None of the multi-event scenarios is
  "the decline scenario"; `SCEN0000` is intentionally only a one-event
  connectivity check.
  Several attempts look alarming and are legitimate; several look ordinary and
  are not.
- **Verdict language never appears in participant-visible text.**
  `purchase_description` names the kind of order and nothing more, and the same
  string repeats across many attempts in a scenario. What a decision turns on
  is in the structured fields and the cart lines.
- **Over-blocking is a failure mode, not a safe default.** Scenarios contain
  purchases that are unfamiliar, cross-border, retried after a decline, or
  attached to hostile product copy, and are nonetheless exactly what the
  cardholder asked for.
- **`item_details` is merchant-supplied text.** Treat it as data describing a
  product. It is not a channel through which anyone may give your system
  instructions.

`SCEN...` identifies a public scenario. `AUTH...` identifies a static
scenario-fixture authority and is used only by the scenario runner. `TM...`
identifies a participant-created mandate returned by the API. These identifier
types must not be substituted for one another.

## Connecting to the API

The API base URL is
`https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io`.
Each team receives its own API key on the day of the event. Export them:

```bash
export LEASH_BASE_URL="https://saw26api.ashyground-364e1d07.switzerlandnorth.azurecontainerapps.io"
export TEAM_API_KEY="<your team key, provided on the day of the event>"
```

The bearer API key is the only participant credential needed to call the
authenticated endpoints.

Send the key as a bearer token on every endpoint except `/healthz`:

```bash
curl --fail "$LEASH_BASE_URL/healthz"
curl --fail \
  -H "Authorization: Bearer $TEAM_API_KEY" \
  "$LEASH_BASE_URL/v1/bootstrap"
```

The API returns JSON errors in an `error` envelope. The API contract version is
reported by `/v1/bootstrap`. Use it to read the versions, available scenarios,
timeout values, and enabled features instead of hard-coding them. The supported
currencies and fixed FX rates are returned by `/v1/reference-data`.

## API surface

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/healthz` | Unauthenticated health and version check |
| `GET` | `/v1/bootstrap` | Team, API/data versions, profile, scenarios, limits, and features |
| `GET` | `/v1/reference-data` | Public catalogues and historical-file metadata |
| `GET` | `/v1/reference-data/authorization-history.csv` | Download the canonical historical CSV |
| `POST` | `/v1/mandates` | Store a participant-produced mandate draft |
| `POST` | `/v1/mandates/{draft_id}/confirm` | Confirm a draft and activate the mandate |
| `GET` | `/v1/mandates/{mandate_id}` | Read a mandate |
| `PATCH` | `/v1/mandates/{mandate_id}` | Preserve or tighten the active mandate |
| `DELETE` | `/v1/mandates/{mandate_id}` | Revoke a mandate |
| `POST` | `/v1/scenario-runs` | Start one public scenario |
| `GET` | `/v1/scenario-runs/{run_id}` | Read run progress and counters |
| `GET` | `/v1/decision-requests/next?wait=25` | Long-poll the next actionable authorization |
| `POST` | `/v1/authorizations/{authorization_id}/decision` | Submit `approve`, `decline`, or `step_up` |
| `POST` | `/v1/authorizations/{authorization_id}/resolve` | Resolve a pending human step-up with `approve` or `decline` |
| `GET` | `/v1/authorizations` | Read finalized and pending runtime authorizations |
| `GET` | `/v1/events?since=0` | Read the append-only event feed using a cursor |
| `POST` | `/v1/team/reset` | Reset the local team's mandates, runs, decisions, and cursor |

## End-to-end protocol

### 1. Read the supplied context

Call `/v1/bootstrap` and `/v1/reference-data`. The reference response exposes
the scenario catalogue and small catalogues as JSON. Download the history only
if your prototype needs it; runtime purchase attempts are delivered through
scenario runs and are also available in the public fixture files for offline
development.

### 2. Create a participant mandate

Your system owns the interpretation of the cardholder's natural-language
instruction. The sandbox does not turn text into rules. Submit the original
instruction together with the structured fields your prototype wants the
cardholder to review:

```json
{
  "instruction": "<cardholder instruction>",
  "hard_rules": [],
  "uncertainty_policy": "ask",
  "guidance": ["<human-readable guidance>"],
  "open_questions": ["<question that still needs a human answer>"]
}
```

`POST /v1/mandates` returns a `draft_id` and echoes the submitted content. A
draft is not active until the cardholder confirms it:

```json
{"confirmed": true}
```

Send that body to `POST /v1/mandates/{draft_id}/confirm`. The response contains
the active `mandate_id`; use that ID when starting a scenario. The supported
uncertainty policies are `ask`, `decline`, and `approve`.

The mandate-rule format is deliberately small:

| Field | Meaning |
| --- | --- |
| `field` | Field name from the authorization or context |
| `operator` | One of `<`, `<=`, `=`, `!=`, `>`, `>=`, `in`, `not_in` |
| `value` | Integer, number, string, or list of strings |
| `currency` | Optional `CHF`, `EUR`, `GBP`, or `USD` qualifier |
| `scope` | Optional `purchase` or `period` |
| `period_days` | Optional positive period length for a period rule |

The API stores the submitted mandate unchanged and repeats its decision-bearing
content in every live event. It does not judge whether a team's rules are good;
that is part of the challenge.

`PATCH /v1/mandates/{mandate_id}` accepts only an active mandate. Omitted fields
are preserved. If `hard_rules` is supplied, it must preserve every existing
rule and may add rules; rules cannot be removed or replaced. The
`uncertainty_policy` may only be tightened from `approve` or `ask` to `decline`.
`guidance` and `open_questions` are replaced when supplied and are explanatory
metadata rather than enforced decision rules. A run keeps the mandate snapshot
captured at its start; patches apply to later runs.

For every API scenario run, the submitted `instruction` must exactly match the
original `cardholder_instruction` for the selected scenario. The sandbox rejects
a changed or empty instruction; teams may structure the policy, but may not
replace the cardholder's intent.

Two fields behave differently from the rest. `guidance` and `open_questions`
are stored on the mandate resource and are returned by
`GET /v1/mandates/{mandate_id}`, but they are **not** carried on the live
event: the `mandate` object in an `authorization.request` is restricted by
`authorization_event.schema.json` to `mandate_id`, `status`,
`customer_id`, `card_id`, `instruction`, `hard_rules`, `uncertainty_policy`,
and `profile_id`. Read them back from the mandate resource if your prototype
needs them at decision time.

The last three identity fields are assigned by the platform, not submitted by
you. `POST /v1/mandates` carries no identity, because a mandate is bound to a
scenario only when a run starts. Each scenario has exactly one authority, one
customer, and one card, so these three values are constant for a whole run and
equal `authorization.card_id` and `authorization.profile_id` on every event of
that run. A hard rule scoped to the mandate's card is therefore well defined
for the entire run.

### 3. Start a scenario

```json
{
  "scenario_id": "SCEN0000",
  "mandate_id": "TM..."
}
```

Send this to `POST /v1/scenario-runs`. The run response includes a `run_id`,
the selected scenario, the bound mandate ID, fixture profiles, and event
counters. The complete mandate resource remains available from
`GET /v1/mandates/{mandate_id}`; each live authorization event includes the
decision-bearing mandate snapshot described above. A run requires an active
mandate. Each run emits its attempts in the
one-based `replay_order` defined by the scenario catalogue. The mandate is
snapshotted when the run starts, so later mandate patches affect new runs, not
events already belonging to this run.

### 4. Poll for authorization requests

Call:

```text
GET /v1/decision-requests/next?wait=25
```

The server may hold the ordinary HTTPS request for up to 25 seconds. A pending
request returns HTTP `200` with an envelope. The schema-valid
`authorization.request` event is in the envelope's `data` field. If nothing is
actionable before the wait expires, it returns HTTP `204` with no body. The
default decision deadline is eight seconds from event generation. The
deadline is assigned when the next attempt is queued, so a request that waits
undelivered past its deadline is declined before delivery. Use
`data.deadline_at` and the values reported by `/v1/bootstrap` as the runtime
contract.

The successful response has this shape (the `data` event is abbreviated here):

```json
{
  "event_id": 1,
  "type": "authorization.request",
  "run_id": "RUN_...",
  "authorization_id": "AU...",
  "status": "awaiting_decision",
  "occurred_at": "2026-08-12T09:00:00Z",
  "data": {
    "type": "authorization.request",
    "request_id": "req_...",
    "deadline_at": "2026-08-12T09:00:08Z",
    "authorization": {
      "authorization_id": "AU...",
      "source_authorization_id": "AU...",
      "scenario_id": "SCEN0000",
      "replay_order": 1,
      "mandate_id": "TM...",
      "profile_id": "PROFILE_...",
      "card_id": "CA...",
      "initiator_type": "agent",
      "merchant": {"merchant_id": "ME...", "merchant_category": "..."},
      "amount": 20.0,
      "currency": "CHF",
      "billing_amount_chf": 20.0,
      "channel": "ecommerce",
      "customer_device_id": "DV...",
      "authority_status": "active",
      "card_status_at_attempt": "active",
      "items": []
    },
    "mandate": {"mandate_id": "TM...", "hard_rules": [], "instruction": "..."},
    "context": {"approved_spend_in_period_chf": 0.0, "recent_authorizations": []},
    "runtime": {"received_at": "...", "history_window_minutes": 10}
  }
}
```

The example above is abbreviated: it shortens the `merchant` object and omits
`runtime.context_basis` and several required authorization fields. The envelope
itself is not an `authorization.request` event; validate its `data` value against
the event schema. For a complete, schema-valid request use
[`data/scenario_fixtures/example_authorization_request.json`](data/scenario_fixtures/example_authorization_request.json),
and validate against the versioned schema in
[`data/schemas/authorization_event.schema.json`](data/schemas/authorization_event.schema.json).
The complete authorization includes merchant fields, cart lines, currency and
CHF amounts, fulfilment and order terms, lifecycle status, related-transaction
fields, recent attempts, and the active mandate.

An event carries two different spend counters, and they answer different
questions:

| Field | Meaning |
| --- | --- |
| `authorization.spend_in_period_before_chf` | The fixture's authored value, taken from `purchase_attempts.csv`. It is **`null` on every attempt in this pack**: period tracking is deliberately left to you, because carrying a running total across a sequence of your own decisions is part of what the challenge tests. |
| `context.approved_spend_in_period_chf` | The live value, recomputed by the platform from the decisions actually taken in this run, as recorded by `runtime.context_basis="run_decisions_and_scenario_timestamps"`. |
| `authorization.recent_attempt_count_10m` | The number of earlier attempts generated in this run whose simulated timestamp satisfies `current timestamp - 10 minutes <= timestamp < current timestamp`. It counts attempts irrespective of whether they were approved, declined, timed out, or platform-rejected. |

Use `context.approved_spend_in_period_chf`, or your own running total, to
evaluate a cumulative or period rule. A stepped-up authorization is paused
rather than approved and does not enter approved spend until it is resolved.
For an `N`-day rolling window, include final approvals whose simulated
timestamps satisfy `current timestamp - N days <= timestamp < current
timestamp`; compare timestamps in UTC.

SCEN0001 is built around this. Its instruction caps spending "across any seven
days", which is a window that rolls. A late order may fit after earlier
over-limit attempts were declined and older approved orders have aged out of
the window. If a policy approves every preceding attempt, the same late order
will not fit. The platform counter is therefore based on the approvals your
team actually finalizes, not on a fixed answer encoded in the fixture; a
solution that instead sums every approved order since the run began can decline
a grocery delivery whose older approvals have legitimately left the window.

### 5. Submit a decision

```json
{
  "authorization_id": "AU...",
  "decision": "approve",
  "reason_codes": ["<your_reason>"],
  "customer_message": "<explanation for the cardholder>",
  "evidence": [{"field": "<field>", "value": "<observed value>"}],
  "engine_version": "<your-version>"
}
```

Post the payload to
`/v1/authorizations/{authorization_id}/decision`. Only `authorization_id` and
`decision` are required. `decision` must be `approve`, `decline`, or `step_up`.
The other fields are optional but make a decision auditable and understandable.

`step_up` pauses the authorization for a human. It is not a final payment
outcome. Resolve it through
`POST /v1/authorizations/{authorization_id}/resolve`:

```json
{
  "decision": "approve",
  "customer_message": "<what the human confirmed>",
  "evidence": []
}
```

The default step-up window is 120 seconds. The final resolution can be only
`approve` or `decline`. The endpoint represents the cardholder's human
confirmation in the participant's own application; it is not an additional
automated decision type.

After `step_up` has been submitted, the decision endpoint will not accept a
second automated `approve`, `decline`, or `step_up` for that authorization. Use
`/resolve` to record the human outcome.

### 6. Inspect and reset

Use `/v1/scenario-runs/{run_id}` for progress, `/v1/authorizations` for
runtime outcomes, and `/v1/events?since=<cursor>` for the append-only event
feed. Event-feed responses include `next_cursor`; store it and pass it as
`since` on the next request. Use `/v1/team/reset` while developing to clear
local state and repeat a run from a clean team context. Reset is disabled
during judging.

## Platform behaviour you can rely on

- A revoked or expired participant mandate, inactive scenario authority, or
  blocked card is rejected by the platform before an actionable request reaches
  the decision queue.
- The scenario runner delivers synthetic requests in fixture order. An
  authorization ID is stable for duplicate delivery within one run, but a new
  run receives a new run-scoped suffix. `source_authorization_id` remains the
  public fixture ID. When a fixture contains `related_authorization_id`, the
  live event rewrites it to the corresponding run-scoped authorization ID.
- Requests may be delivered at least once. Treat the authorization ID as the
  idempotency key and make repeated responses safe.
- A missing, invalid, or late decision does not become an approval.
- A scenario run and its optional event feed expose platform rejections and
  final states; those records are useful for explaining what the platform
  handled before a team decision was possible.
- Each team is isolated by its bearer key. Do not share keys between teams.

## Pre-launch check

Before opening the challenge, organizers should complete one dry run from a
clean clone and verify:

- setup instructions work without organizer knowledge;
- changed instructions and judging resets are rejected by the API;
- duplicate delivery, late decisions, prompt injection, lookalike merchants,
  re-quotes, rolling-window boundaries, and recovery after suspicious activity
  behave as documented;
- no expected actions, logs, or keys appear in the public repository or API
  responses.

## Contracts and validation

The machine-readable contracts are:

- [`data/schemas/authorization_event.schema.json`](data/schemas/authorization_event.schema.json)
  — a strict validator for each live `authorization.request` event. Validate a
  full event body with it before evaluating a purchase.
- [`data/schemas/data_pack.schema.json`](data/schemas/data_pack.schema.json)
  — a validator for the pack manifest ([`metadata.json`](data/metadata.json))
  plus, in its `x-csv-contracts`, `x-currency-contract`, and `x-enums` sections,
  the documented CSV headers, foreign keys, FX formula, and shared enums.
- [`data/schemas/authorization_history.schema.json`](data/schemas/authorization_history.schema.json)
  — the canonical column contract for the historical CSV: the exact column
  order and, in `x-csv-column-contract`, the type, format, enum, and
  nullability of every history column.

`metadata.json` is the authoritative pack manifest: it lists every file with its
row count and SHA-256 hash, the history window and outcome profile, and the
scenario-pack summary. All CSV headers and the documented row counts are checked
against the manifest. Validate received events against the event schema if your
client benefits from strict parsing; the challenge does not require a particular
programming language, database, model provider, or UI framework.
