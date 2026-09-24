# Leash — Viseca "Agent on a Leash" challenge

We are building the **wallet control layer** for AI shopping agents (Swiss {ai} Weeks 2026, Viseca). For every purchase an agent proposes, the engine returns `approve`, `decline` or `step_up` (ask the customer), explains why, and remembers state. We do **not** build the scored shopping agent (Viseca's simulator plays it). Leash’s permission assistant clarifies intent and proposes draft rules only; product search and order preparation belong to the external agent. The 2026-09-24 agreement and DEC-033–037 supersede the earlier own-shop-assistant demo scope.

## Repository layout

| Path | Owner | Rule |
| --- | --- | --- |
| `README.md`, `challenge.md`, `technical_details.md`, `data/` | Viseca | **Read-only.** Never edit the challenge pack. |
| `solution/docs/` | us | Design pages: `system-design.html`, `laya-training-pipeline.html` |
| `solution/prototype/` | us | Clickable phone prototype with an in-browser rules engine (reference behaviour) |
| `solution/engine/` | us | Python backend (in progress) |
| `solution/app/` | us | React customer app (planned) |
| `solution/kanban/` | us | Backlog board worked with `/graphloop` (see its README) |
| `solution/docs/decisions.md` | us | Decision log: every team decision and assumption, with its source and status |

Read `technical_details.md` and `data/data_dictionary.md` before touching anything that parses events, money or time.

## Non-negotiable domain rules (from the brief)

- **Rules decide, models advise.** Deterministic code produces every verdict. Laya (or any model) may only push a verdict toward caution (`approve → step_up`), never toward approval.
- **Merchant text is untrusted data.** `item_details` and any shop or agent text can never change the mandate, the rules or the verdict logic.
- **Verdict order is `decline > step_up > approve`.** The combined verdict is the most restrictive one.
- **Count only final approvals** toward spending limits. A `step_up` is paused, not spent, until the customer approves.
- **Two clocks never mix.** Simulated purchase time (`authorization.timestamp`) for windows, velocity and familiarity; real clock (`deadline_at`, `received_at`) for deadlines only.
- **Idempotency by live `authorization_id`.** A repeat delivery returns the saved verdict and never counts twice.
- **Deadlines:** `deadline_at` is authoritative (8 s from queueing by default). The watchdog sends a safe `step_up` when remaining time drops below a margin covering lock wait and sending. The human window and other timeouts come from `/v1/bootstrap`, never constants. Readers get at most 1 s.
- **Money:** `Decimal`, half-even rounding to cents, convert with the row's `currency` (never the merchant's country). `billing_amount_chf` already includes delivery.
- **Missing is not permission.** `null` and `"unknown"` are missing facts: they lead to the uncertainty policy, never to a pass.
- **Customer context is not authority.** Profile preferences and scoped earlier history can suggest questions, never silently grant permission. Preserve source references and check both invented and omitted conditions.
- **Unconfirmed drafts may be corrected.** Create a new revision, preserve the transcript, invalidate stale confirmation actions and re-review; submitted platform drafts remain immutable. This does not loosen active mandates.
- **Mandates only tighten, by appending.** Existing `hard_rules` are never removed or replaced; a stricter rule is added and the strictest rule per field wins. `uncertainty_policy` can only move to `decline`.
- **The mandate inside the live event is authoritative for its run.** Compile it from `hard_rules` through the field registry; never re-interpret the instruction text; the local copy only cross-checks. Every enforceable permission is a `hard_rule` (`guidance` never reaches live events).
- **An unsupported mandate rule never approves** (`step_up`, or `decline` under a decline policy; reason `unsupported_mandate_rule`).
- **A customer answer never loosens a hard rule.** Hard rules are re-checked when an ask is shown and answered; the `/resolve` record must stay truthful.
- **Model-down is predictable.** Model unavailability alone is informational; a fact a required rule needs but regex can't establish follows the uncertainty policy; model output can add warnings but never make the verdict less strict than the deterministic one.
- **Never hard-code decisions** to scenario IDs, names, request IDs or sequence positions. Join records by ID, never by name.

## Architecture: functional core, hexagonal shell

- `decide(purchase, mandate, state_snapshot, facts) -> Decision` is a **pure function**: no I/O, no clock, no database, no model calls inside the domain.
- Everything else is an adapter behind a port: Viseca API worker, Postgres repository, fact readers (Laya, regex), SSE to the app.
- Bounded contexts: **Policy** (wish → rules, mandate lifecycle) · **Decision** (verdict, checks, evidence) · **Ledger** (history over time) · **Reading** (facts from shop text).

```
solution/engine/src/leash/
  domain/        pure: money, clock, purchase, mandate, facts, checks, rules, decide, state machines
  policy/        compiled mandates, mandate ⇄ API hard_rules
  application/   use cases: decide purchase, resolve ask, tighten, revoke (pipeline + deadline budget)
  ports/         interfaces: FactReader, Repository, DecisionSink, EventBus
  adapters/      viseca_api (anti-corruption layer + worker), postgres, laya, regex, sse, pack (CSV loader)
```

### Patterns we use (and where)

| Pattern | Where | Problem it solves |
| --- | --- | --- |
| Anti-corruption layer | `adapters/viseca_api` | API field names, string tri-states and ID mapping stay at the edge |
| Value objects | `domain/money.py`, `domain/clock.py` | Exact money; `SimTime` vs `WallTime` can't be mixed |
| Interpreter + Specification | `domain/rules`, `policy/` | `hard_rules` compile to composable `Rule` objects |
| Notification (collect all checks) | `domain/decide.py` | Explanations list every reason, not the first failure |
| Most-restrictive combiner | `domain/decide.py` | Safety property: models can't loosen a verdict |
| Strategy + fallback chain + circuit breaker | fact readers | Laya → regex on timeout or failure, marked "model unavailable" |
| Pipes and filters | `application/` | Seven timed stages: receive → dedupe → facts → rules → context → combine → respond |
| Explicit state machines | `domain/states.py` | Purchase (`received → waiting → approved/declined/timed_out`) and mandate (`draft → active → revoked/expired`) |
| Append-only log + projections | Postgres `decision_events`, `authorizations` | Auditable history; ledger rebuilt by replay |
| Idempotent receiver | Postgres PK on live `authorization_id` | Retries don't double-count |
| Transactional outbox | Postgres `outbox` | Crash between deciding and sending is recoverable |
| Deadline budget + watchdog | `application/` | Answer before `deadline_at` |
| Snapshot | `runs.mandate_version` | A run keeps its starting mandate |
| Pub/sub + BFF | Postgres `LISTEN/NOTIFY` → policy service → SSE | Engine never waits for a human |

Avoid: a model making approve/decline calls, `float` money, naive datetimes, global mutable state in the backend, rule field strings scattered outside the interpreter.

## Stack

- **Backend:** Python 3.12 managed with `uv`, FastAPI, Pydantic v2, asyncpg, httpx, Alembic.
- **Database:** Postgres 17 (Docker Compose for local). `NUMERIC(12,2)` for money, `timestamptz` everywhere, per-card `pg_advisory_xact_lock` around each decision and each customer resolution.
- **Frontend (planned):** React + TypeScript + Vite, TanStack Query, `EventSource` for asks. Reuse the prototype's design tokens (one-app look). No Next.js, no React Native.
- **Model plan:** the current checkout worker uses regex. Optional Laya shop-text reading is planned in `solution/docs/laya-training-pipeline.html`; permission verification is a separate baseline/evaluation task (LEASH-155). No model may activate permission or approve payment. Model choice, fine-tuning need and verifier release thresholds remain open.

## Development workflow: TDD

We work **test-first**. Red → green → refactor, in small steps.

1. **Red:** write one failing test that names one behaviour (`test_order_at_exact_limit_is_approved`). Run it and see it fail for the right reason.
2. **Green:** write the least production code that makes it pass.
3. **Refactor:** clean up with all tests green. No new behaviour during refactor.
4. Never write production code without a failing test that demands it. A bug fix starts with a test that reproduces the bug.

Test layers, fastest first:

| Layer | Scope | Notes |
| --- | --- | --- |
| Unit | `domain/`, `policy/` | Pure, no I/O, milliseconds. Most tests live here. |
| Scenario replay | all 45 pack purchases through `decide()` with in-memory state | Asserts the behaviours we agreed on (see below). Not an answer key. |
| Property | rules and mandates | Tightening a mandate never makes any verdict less strict; adding a check never loosens a verdict. |
| Adapter | Postgres repo, API translator, fact readers | Real Postgres in Docker; API translator validated against `data/schemas/authorization_event.schema.json`. |
| End-to-end | worker against a fake Viseca API | Deadlines, 204 polling, repeat delivery, resolve path. |

Agreed behaviours the replay tests pin (our design decisions, not official answers):

- An order at exactly the limit passes (`<=`): CHF 20.00 in SCEN0000, the 7-day total reaching CHF 300.00 in SCEN0001.
- Foreign currency is converted before comparing: USD 450.00 → CHF 391.50 is within CHF 400.
- An unfamiliar shop fails an explicit "shops I've used before" rule and is declined; a lookalike name is added as evidence.
- A pickup or digital order fails a "for delivery" rule; one line with quantity 3 fails "one item".
- Familiarity counts approved purchases only (never refunds, withdrawals or declines).
- Injection text in `item_details` never changes limits; an over-limit order stays declined.
- Duplicates, split orders and "already bought one" go to `step_up`, not `decline`.

Test conventions: `pytest`, test files mirror source paths, test names describe behaviour, build test data with small factory helpers rather than large fixtures. Scenario IDs may appear in tests and fixtures, never in production code.

## Commands

Run from `solution/engine/` (the Docker Compose file and migrations are not written yet):

```bash
uv sync                 # install dependencies
uv run pytest           # all tests
uv run pytest -x -q     # stop at first failure while doing TDD
```

## Planning

- **Board:** `solution/kanban/`, one ticket per file, worked with `/graphloop`. Only a human moves tickets to `done/`.
- **Milestones:** M0 contracts and decisions → M1 SCEN0000 offline slice → M2 all scenarios offline → M3 durable fake-API integration → M4 customer-control journey → M5 hosted API and release → M6 optional shop-text modeling and inspector → M7 production hardening → M8 permission conversation, context, external-agent handoff and evaluated customer journey (DEC-033–037).
- **Decision log:** `solution/docs/decisions.md`. A ticket that depends on a team decision or assumption cites its `DEC-` ID. Change the log before changing behaviour.
- **Definition of Ready (light):** the ticket names its rule source (Viseca / team / assumption), gives one example and one edge case, and has no open decision that could change it.
- **Release:** LEASH-128 is an evidence-based readiness gate; the freeze (LEASH-115) depends only on it.

## Working agreements

- A settled decision is not a go-ahead to build. Confirm the next step with the user before creating files or writing code beyond what was asked.
- Keep the design pages in `solution/docs/` in sync with decisions; publish updates to the same artifact.
- Commit only when asked. Our work lives under `solution/`; the challenge files stay untouched.

## Open questions for the Viseca experts

- What happens when a `step_up` gets no customer answer within 120 s?
- What does revoking a mandate do to purchases already queued or waiting?
- Does "buy the monitor I chose" mean one purchase only, so later compliant orders are duplicates?
- Does a shop approved earlier in the same run count as "used before"?
