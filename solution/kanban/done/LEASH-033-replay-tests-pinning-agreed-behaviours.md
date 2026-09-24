# LEASH-033: Replay tests pinning agreed behaviours

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-002
**Task ID**: 002-T4
**Blocked by**: LEASH-032, LEASH-016, LEASH-017, LEASH-021, LEASH-022, LEASH-023, LEASH-024, LEASH-025, LEASH-026, LEASH-119, LEASH-120
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
Pin the behaviours listed in CLAUDE.md across the 45 purchases.

## Business Value
Regression net for every later change.

## Acceptance Criteria
- [x] SCEN0000 CHF 20.00 approved.
- [x] SCEN0001 total reaching 300.00 approved; next order over 300 declined.
- [x] USD 450 → CHF 391.50 not declined for price.
- [x] Injection order over the limit declined.
- [x] Lookalike shop declined with lookalike evidence.
- [x] Duplicate goes to step_up.
- [x] At least one integrated case per rule family, including fulfilment and quantity.
- [x] Unfamiliar-shop and lookalike cases pinned per DEC-023.

## Technical Approach
`tests/replay/test_agreed_behaviours.py`. Scenario IDs appear only in tests.

### Dependencies
- Needs LEASH-032.
- Needs LEASH-016.
- Needs LEASH-017.
- Needs LEASH-021.
- Needs LEASH-022.
- Needs LEASH-023.
- Needs LEASH-024.
- Needs LEASH-025.
- Needs LEASH-026.
- Needs LEASH-119.
- Needs LEASH-120.
- Blocks LEASH-128.

## Testing Requirements
These are the tests. Run `uv run pytest tests/replay`.

## Related Files
- `solution/engine/tests/replay/test_agreed_behaviours.py`

## Notes
- The pack has no purchase with quantity > 1 and none failing a delivery rule, so those two families replay one real pack purchase with only that field changed (AU0005 as pickup under SCEN0001; AU0043, the pack's digital order, judged under the SCEN0001 mandate; AU0001 with quantity 3 under SCEN0000). Every other family is pinned on the replayed pack as is.

## Out of scope
- Asserting a verdict for every one of the 45 (no answer key exists).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: AU0001 CHF 20.00 approved; `<=`→`<` mutant turns it red.
- [x] met — criterion 2: 7-day total 300.00 at AU0008 approved, AU0009 declined `over_period_limit`; three mutants red.
- [x] met — criterion 3: AU0038 USD 450 → CHF 391.50 not declined for price; comparing on `amount` turns it red.
- [x] met — criterion 4: AU0037 injection over limit declined; skipping the price rule on injection turns it red.
- [x] met — criterion 5: AU0039 PixelHarbour declined with `lookalike_merchant` evidence; three mutants red.
- [x] met — criterion 6: AU0036 duplicate goes to step_up; fail-mutant and removal red.
- [x] met — criterion 7: removing each of the 13 `DEFAULT_RULES` turns 1–6 replay tests red.
- [x] met — criterion 8: unfamiliar shops declined, split / already-bought step_up per DEC-023.
- Outside the criteria: familiarity within a run is pinned by `tests/domain/test_snapshot.py`, not by the replay. The note now states AU0043 is judged under the SCEN0001 mandate.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
