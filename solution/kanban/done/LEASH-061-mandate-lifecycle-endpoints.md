# LEASH-061: Mandate lifecycle endpoints

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-005
**Task ID**: 005-T2
**Blocked by**: LEASH-060, LEASH-050, LEASH-043, LEASH-118
**Blocks**: LEASH-062, LEASH-063, LEASH-066, LEASH-092, LEASH-128
**Updated**: 2026-09-23

## Description
Policy service endpoints: create draft, confirm (only after the customer agrees), read current mandate.

## Business Value
The customer confirms before the agent can spend.

## Acceptance Criteria
- [x] Draft is created at the Viseca API and stored locally as version 1.
- [x] Confirm calls /confirm and stores the returned mandate_id.
- [x] Confirming twice or confirming a revoked mandate fails.
- [x] Distinguishes the local policy draft from the Viseca mandate draft.
- [x] A double-clicked confirm is idempotent.

## Technical Approach
`adapters/http/policy_api.py` (FastAPI) calling the Viseca client.

### Dependencies
- Needs LEASH-060.
- Needs LEASH-050.
- Needs LEASH-043.
- Needs LEASH-118.
- Blocks LEASH-062.
- Blocks LEASH-063.
- Blocks LEASH-066.
- Blocks LEASH-092.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_confirm_requires_draft`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/tests/adapters/test_policy_api.py`

## Out of scope
- Authentication of end users.

## Implementation note (2026-09-23)
- `adapters/http/policy_api.py` provides these endpoints, following `contracts/policy-api.yaml`:
  - `POST /api/policies/drafts` compiles the instruction with the compiler and the catalogue into a local draft `LD-…`.
  - `GET /api/policies/drafts/{id}`.
  - `POST …/submit` posts to Viseca `POST /v1/mandates` and stores `platform_draft_id` plus the exact body posted.
  - `POST …/confirm` requires `{"confirmed": true}` and calls `/v1/mandates/{platform_draft_id}/confirm`. It stores the returned `mandate_id` in `mandates` and the rules in `mandate_versions` as version 1.
  - `GET /api/mandates` and `GET /api/mandates/{id}`.
- New migration `0004_policy_drafts.py` adds the local draft table, which keeps the local draft apart from the platform draft. The registry lock was re-pinned because migrations are hashed.
- How the criteria are read (flagged for the product owner):
  - A repeat confirm of the same draft, including a concurrent double click, returns the same mandate and calls Viseca's `/confirm` once. The draft row is locked for the whole confirm.
  - "Confirming twice fails" is read as: a second confirmation never reaches Viseca and never creates a second mandate. A platform refusal (4xx) returns 409 `platform_refused` and stores nothing.
  - Confirming a draft whose mandate is revoked or expired returns 409 `mandate_revoked`.
- Blocking questions: every question blocks submission except the two that only offer an extra restriction, merchant category and the split check. Those go to Viseca as `open_questions`. The answers endpoint is not part of this ticket.

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met, under an interpretation — criterion 1: the draft is local (`LD-…`), `submit` creates it at Viseca, and "version 1" is written at confirm. This follows the LEASH-118 contract (PolicyDraft → PlatformDraft → Mandate). **Flag for the product owner:** "stored locally as version 1" happens at confirm, not at draft creation.
- [ ] gap — criterion 2: if Viseca confirmed but the local write failed, or the answer was lost, every retry got `platform_refused` and the mandate active at Viseca was unknown locally.
- [x] met, under an interpretation — criterion 3: a repeat confirm returns the same mandate and never calls Viseca again; a revoked or expired mandate returns 409. **Flag for the product owner:** this reverses the literal "confirming twice fails".
- [x] met — criteria 4 and 5: 10 parallel confirms gave one Viseca confirm and one mandate.
- Minor: a non-object body got FastAPI's `{"detail"}` shape; parallel submit had no test.
Verdict: returned to in-progress.

### Fixes (2026-09-23)
- New table `policy_confirm_attempts` in migration 0004. Each attempt, and the `mandate_id` Viseca returns, is written on a separate connection, so the record survives a rollback. The local write runs in a savepoint.
- A failed local write returns 500 `local_write_failed` naming the mandate. The retry finishes the local write without asking Viseca again.
- A lost answer (timeout after Viseca confirmed) returns 502. The retry then gets 409 `confirm_outcome_unknown` ("may already be active at Viseca"), plus an INTEGRITY log, never a silent `platform_refused`.
- The draft row is locked `for no key update`, so the attempt insert's foreign-key check can't deadlock with it.
- A non-object body gets the contract Error shape.
- New tests cover parallel submits (one platform draft), the recovered failed write, the lost answer and the error shape.

### 2026-09-23 — independent agent review, round 2
- Round-1 gaps closed: failed local write recovered, lost answer reported, error shape, parallel submits.
- [ ] not met — criterion 2 (and 5 beyond two clicks): the confirm held one pool connection while `note_attempt` waited for a second from the same pool, so 4 or more confirms at once deadlocked. A crash between Viseca answering and the attempt row recording it lost the mandate_id; the response was then a plain-text 500 and every retry called Viseca again.
- False alarm: after a definite refusal, the next retry reported `confirm_outcome_unknown`.
Verdict: returned to in-progress.

### Fixes (2026-09-23), round 2
- No connection or lock is held during the Viseca call. The side table is gone; `policy_drafts` gets `confirm_started_at` and `confirmed_mandate_id`, each written in its own short transaction:
  - claim the call (a compare-and-set on `confirm_started_at`);
  - call Viseca with no connection held;
  - save `confirmed_mandate_id` (a one-column update);
  - write the mandate rows and link the draft.
- A second click waits up to 15 s for the first, then gets 409 `confirm_in_progress`.
- A claim older than 15 s (a crashed process), or one marked unanswered after a timeout, means the outcome is unknown. The retry calls Viseca: a new answer is stored, and a refusal gives 409 `confirm_outcome_unknown` plus an INTEGRITY log.
- A definite refusal clears the claim, so it is never reported as unknown later.
- Any unexpected error gets the contract Error shape (500 `internal_error`).
- New tests:
  - 12 parallel confirms on 4 drafts: no deadlock, 4 Viseca confirms, one mandate per draft;
  - a refused confirm stays refused;
  - an unexpected error has the contract shape.
- Residual, by design: if the process dies after Viseca answered but before `confirmed_mandate_id` is saved (a one-row update), the id can't be recovered locally. Viseca has no lookup by draft. The retry reports `confirm_outcome_unknown` for an operator; it can call Viseca again only if Viseca accepts a repeat confirm.

### 2026-09-23 — independent agent review, round 3
- [x] met — criterion 1: read as agreed; version 1 is written at confirm. **Flag for the product owner.**
- [x] met — criterion 2. The only loss is the stated, reported crash window (Viseca has no lookup by draft).
- [x] met — criterion 3: read as agreed; a repeat confirm returns the same mandate and a revoked mandate returns 409. **Flag for the product owner.**
- [x] met — criteria 4 and 5: 24 parallel confirms on 8 drafts (pool of 4, and also forced to 1) all succeed, one Viseca confirm per draft; no nested connections. Refusals are never reported as unknown, and every error uses the contract shape.
- Note from the review: a Viseca call longer than the 15 s claim window let a second click call Viseca too, and the writes after the call did not check the claim.
Verdict: all met.

### Follow-up hardening (2026-09-23), from the round-3 note
- The Viseca call is cut at 80% of the claim window, so a claim can't be taken over while its call runs; a cut call is marked unanswered.
- The claim returns a token, and the writes after the call (clear on refusal, unanswered marker) apply only while this request still holds it.
- `confirmed_mandate_id` is never overwritten.
- A click that waited on another request's call never calls Viseca itself; if that call ended without an answer, it reports `confirm_outcome_unknown`.
- Test `test_a_viseca_call_slower_than_the_claim_window_is_cut_and_never_answered_twice`; 18 policy tests pass.
Moved to done on the product owner's standing instruction for this run.
