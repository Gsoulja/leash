# LEASH-121: SCEN0000 offline vertical slice

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-002
**Task ID**: 002-T6
**Blocked by**: LEASH-051, LEASH-060, LEASH-117, LEASH-014, LEASH-018, LEASH-019, LEASH-027, LEASH-030, LEASH-031, LEASH-032
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
Prove the first end-to-end slice offline: the SCEN0000 event is translated, its mandate compiled from hard_rules, decided, and explained.

## Business Value
Milestone M1: working proof before the whole domain epic is finished.

## Acceptance Criteria
- [x] The SCEN0000 event built from the pack translates, compiles and decides without scenario-specific code.
- [x] The decision includes a plain-language message and evidence.
- [x] The same code path is used later by the worker.

## Technical Approach
Test builds the live-style event from the pack like technical_details.md step 3.

### Dependencies
- Needs LEASH-051.
- Needs LEASH-060.
- Needs LEASH-117.
- Needs LEASH-014.
- Needs LEASH-018.
- Needs LEASH-019.
- Needs LEASH-027.
- Needs LEASH-030.
- Needs LEASH-031.
- Needs LEASH-032.
- Blocks LEASH-128.

## Testing Requirements
Run `uv run pytest tests/replay/test_scen0000_slice.py`.

## Related Files
- `solution/engine/tests/replay/test_scen0000_slice.py`

## Out of scope
- Other scenarios (LEASH-033).

## Implementation note (2026-09-23)
- `adapters/viseca_api/translate.request_from_envelope(envelope, validate=)` turns a polled envelope into the `DecisionRequest` that `DecidePurchase` handles. It is the single entry path for the worker (LEASH-053) and for this slice.
- `application/replay.InMemoryDecisionStore` is the `DecisionStore` port without Postgres: pack history plus an in-memory ledger, idempotent by live ID.
- The slice test drives the fake platform: it confirms the SCEN0000 mandate from its `hard_rules`, starts the run, polls every event, then calls `request_from_envelope` → `DecidePurchase.handle` → `post_decision`.
- Registry lock re-pinned: `translate.py` (shared enforcement) gained the function; no meaning changed.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: no scenario IDs in `src`. Mutating the event's `hard_rules` after the run starts flips AU0001 to decline; wiping the local fixture leaves it approved. The verdict follows the event.
- [x] met — criterion 2: the sent body has a customer message ("All your rules passed.") and 5 evidence lines.
- [x] met — criterion 3: `request_from_envelope` is production code, reads the envelope as technical_details.md describes it, and runs through the real `VisecaClient` and `DecidePurchase`; only the store is in memory. Caveat: the worker (LEASH-053) must actually use it — noted on LEASH-053.
- Note: the in-memory store is keyed by card, not run, and puts its own `engine_version` in the body. Neither matters for this slice.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
