# LEASH-130: Platform delivery truth reconciliation

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037, DEC-038, DEC-039
**Parent**: LEASH-129
**Task ID**: 129-T1
**Blocked by**: none
**Blocks**: LEASH-128, LEASH-132, LEASH-137, LEASH-142, LEASH-143, LEASH-148, LEASH-150, LEASH-156
**Updated**: 2026-09-24

## Description
Separate the engine verdict from Viseca's accepted outcome. A decision rejected after the local commit must never remain displayed or counted as paid.

## Business Value
The customer, rolling limits and future decisions must agree with the payment platform's source of truth.

## Acceptance Criteria
- [x] Authorizations record engine verdict, delivery status and platform outcome separately.
- [x] A successful decision POST records platform acceptance atomically in the local projection.
- [x] A terminal refusal such as `deadline_passed` becomes `not_sent` or an equivalent non-approved state.
- [x] Terminally refused decisions do not count toward spend, familiarity, duplicates or purchase count.
- [x] The app distinguishes decided, submitted, accepted and not sent.
- [x] `sent_to_viseca` is never populated for a failed delivery.
- [x] A reconciliation job repairs or raises an integrity alert for local/platform disagreement.
- [x] Keep pending local approvals/reservations separate from platform-accepted spending so concurrent attempts cannot overspend while acknowledgements are outstanding; release reservations after terminal refusal.
- [x] Platform acceptance is not proof of settlement, shipment or delivery; customer wording names the actual state supplied by the contract.

## Technical Approach
Extend the authorization and outbox projections with explicit delivery states. Apply platform acknowledgements through a repository transaction, then derive ledger and UI state only from accepted outcomes.

### Dependencies
- Blocks LEASH-128.
- Blocks LEASH-132.
- Blocks LEASH-137.
- Blocks LEASH-142.
- Blocks LEASH-143.
- Blocks LEASH-148.
- Blocks LEASH-150.
- Blocks LEASH-156.

## Testing Requirements
Write failing adapter tests for accepted responses, retryable failures, terminal 4xx responses and crash-after-POST. Add ledger tests proving terminal refusals never count.

## Related Files
- `solution/engine/src/leash/adapters/viseca_api/outbox_sender.py`
- `solution/engine/src/leash/adapters/postgres/repository.py`
- `solution/engine/src/leash/adapters/postgres/unit_of_work.py`
- `solution/engine/src/leash/adapters/http/query_api.py`
- `solution/app/src/screens/status.ts`

## Out of scope
- Settlement, clearing and chargeback state beyond the challenge authorization API.

## Implementation notes

The defect was concrete: `authorizations.state` carried both what the engine decided and what the
platform accepted. A decision Viseca terminally refused (`deadline_passed`) still read `approved`, so it
counted toward spend, familiarity, duplicates and the purchase count, and the app showed it as paid.

- **Migration 0009** adds `delivery` (`pending|accepted|refused`), `platform_outcome` and `delivered_at`,
  and the `delivered` event kind. `delivery` is added with a default — a catalogue-only change in
  Postgres 11+ — so it is NOT NULL from the start without a rewrite, per `migrations/README.md`. The
  backfill reads the outbox, which already knew: closed without an error → accepted, closed with one →
  refused, still open → pending. Its downgrade is the same trap as `0006` (it narrows the kind check
  against append-only rows), and its docstring says so.
- **`domain/states.py`** gains a delivery machine (`pending → accepted | refused`, by the platform,
  once) and the `approved | declined | waiting | received → not_sent` transitions a terminal refusal
  implies. A second, different platform answer is not applied — that is a disagreement, not a state
  change.
- **`PostgresRepository.record_delivery`** is the single writer, used by both send paths. Acceptance is
  written in the same transaction as closing the outbox row, so the projection can never say "sent"
  while the authorization still reads pending (AC2). A terminal refusal also moves the purchase to
  `not_sent`, which is what makes AC4 and AC8 true rather than asserted: the snapshot, the ledger and the
  platform-spend re-check all read `state`, so a refused decision disappears from every one of them at
  once, and the spend it reserved is released.
- **AC8 reading.** `approved_chf` stays what the *engine* approved, and the limit is enforced against it:
  counting only acknowledged spend would let two concurrent purchases both pass while their
  acknowledgements were outstanding. The narrower fact is now reported beside it as `accepted_chf`, with
  `awaiting_platform_chf` for the difference. Both are in the contract with that wording.
- **AC6 was a live bug**: the outbox sets `sent_at` on a terminal failure too (to close the row), and
  `sent_to_viseca` selected on `sent_at is not null` alone — so the app showed a body the platform never
  accepted. The query now also requires `last_error is null`.
- **AC7** is `application/reconcile.py`, running every 30 s in the worker and once more when a run ends.
  It repairs only what is new information — a `pending` delivery the platform agrees with, or one the
  platform says it never took — and raises an `integrity_alert` for anything else, changing nothing. A
  platform status we do not recognise is an alert, not a pass. It can never make a purchase less
  restrictive: the only state change it can cause is toward `not_sent`.
- **AC5/AC9** are `status.ts`. `stageOf` names the four stages; the labels changed from "Paid" to
  "Approved", an approval awaiting acknowledgement reads "Approved · sending" and is not green, and a
  refused delivery reads "Not accepted by the bank". A purchase the platform never sent us (no verdict)
  still reads "Not sent" — a different thing from one whose answer was refused. `deliveryNote` spells out
  that acceptance "is not confirmation that the order shipped". A test sweeps all fifteen
  state × delivery combinations against `/paid|settled|shipped|delivered|dispatched|on its way|arriving/i`
  so no label can claim settlement.

Files beyond Related Files: `migrations/versions/0009_delivery_truth.py`, `domain/states.py`,
`application/reconcile.py`, `adapters/viseca_api/worker.py` (the reconcile loop),
`adapters/postgres/unit_of_work.py`, `contracts/policy-api.yaml` (+ its examples), `app/src/api/schema.d.ts`,
`app/src/screens/status.test.ts`, `policy/registry.py` and `tests/policy/test_registry.py` (classification
and the LOCK re-pin — the change only ever tightens: something that used to count now does not).

Verification: 20 new delivery tests, 1539 engine tests, 104 app tests, `mypy src` clean on 67 files,
`npm run typecheck` clean.

## Review log

### 2026-09-24 — independent agent review
AC1, AC2, AC3, AC5 `met`; **AC4, AC7, AC8, AC9 `not met`** — all findings fixed.

Verified by the reviewer before the failures: the full enumeration of counting paths (period spend,
familiarity baseline and within-run familiarity, duplicates, split check, purchase count, the platform
re-check, the resolve re-check, `/api/spending`, `permission_context`, replay) with only `snapshot.prior`
and `auth_history` reaching them, so the `not_sent` mechanism does cover all of them; atomicity in all
three writers with the POST inside the transaction; and that a customer answering an ask whose delivery
was refused gets a clean `409 not_waiting`, not a 500.

**AC4 — two ways a refused purchase still counted.**
- **Migration 0009's own backfill.** It set `delivery = 'refused'` and left `state = 'approved'` — the
  exact bug this revision exists to fix, reintroduced for every pre-0009 row, and unreachable by the
  reconciler because the delivery was no longer `pending`. The backfill now releases the state too, and
  `test_the_migration_reads_delivery_out_of_the_outbox` asserts the row leaves `snapshot.prior` — the
  thing the old test never looked at.
- **The reconciler poisoned an undecided row.** `AGREES["received"]` accepted a platform `"pending"`, so
  a row still being decided got `delivery = 'accepted'` for a decision that did not exist — and because
  a delivery outcome is recorded once, a later genuine `deadline_passed` was silently dropped and the
  purchase counted. `received` rows are now left alone entirely (reported as `in_flight`); taking them
  to `not_sent` would have collided with the decision the worker was about to commit.

**AC7 — the reconciler had both cases backwards.** It repaired the undecided case it should have flagged
(above) and only flagged the backfilled `refused`-but-still-counting case it should have repaired.
Releasing a refusal is now a repair, because it only ever stops something counting. It also appended a
fresh `integrity_alert` row every 30 seconds for the same unresolved disagreement; an identical open
alert is now recorded once.

**AC8 — `accepted_chf` was unwindowed while `approved_chf` was windowed**, so an accepted purchase
outside the period made `accepted_chf` exceed the total it is documented as part of, and the `max(…, 0)`
clamp reported `awaiting_platform_chf: 0.00` while 180.00 genuinely was outstanding. Both are now
measured over the same window, and both are asserted by tests — neither had one before.

**AC9 — `Cockpit.tsx` still rendered "N paid"** for exactly the accepted state, outside the sweep's
reach because the sweep only exercised `statusOf`. The chip now reads "approved", and a second test
reads the *source* of every screen for settlement wording, with negations ("…not confirmation that the
order shipped") allowed. Re-introducing "paid" fails it, verified. While fixing it: the chip counted by
tone, so a decline the bank accepted was counted as an approval and a submitted approval was summed into
"waiting"; it now counts by verdict and delivery stage.

**AC6 was met but untested** — the mutation the reviewer ran (dropping `and last_error is null`) passed
29 tests, because the test re-typed the query instead of calling the endpoint. It now goes through
`/api/payments/{id}`. That exposed a real false negative: neither `mark_sent` cleared a stale
`last_error` from an earlier retryable attempt, so a decision Viseca accepted could read as "Nothing was
sent." Both now clear it.

**Also fixed, from the reviewer's out-of-scope notes:** `delivered` events and reconciler disagreements
reached no SSE contract kind, so the app never learned of a refusal live — there is now a
`payment.delivered` stream event and a `platform_delivery_mismatch` alert kind, both documented in
`events.md`; `stageOf`/`deliveryNote` were dead code and are now used by the Cockpit and the payment
sheet; and `policy-api.yaml` still described `final_state` as "approved=Paid".

**The LOCK justification was wrong and is corrected in the re-pin note.** "Only ever tightens" is true of
spend and false of verdicts: dropping a refused purchase from `snapshot.prior` also removes it as a
*prior*, so a duplicate, split or count check it used to trigger no longer fires. The reviewer
reproduced it — an identical second order went from `possible_duplicate` (step_up under DEC-029/030) to
no check at all. That is what AC4 asks for, but it is a loosening for later purchases and is now
recorded as one.

One thing deliberately left: after a terminal refusal, a redelivery that the platform *does* accept
leaves the purchase `not_sent` for good. Staying refused under-counts spend and never over-counts, and
moving back to `approved` is the loosening the state machine exists to forbid; the reconciler raises it
once for a person instead of resolving it silently.

Verification after round 2: 26 delivery tests, 1562 engine tests, 110 app tests, `mypy src` clean on 67
files, `npm run typecheck` clean.
