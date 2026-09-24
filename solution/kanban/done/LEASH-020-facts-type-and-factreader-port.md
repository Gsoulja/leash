# LEASH-020: Facts type and FactReader port

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: DEC-009, DEC-025
**Parent**: LEASH-001
**Task ID**: 001-T11
**Blocked by**: LEASH-012
**Blocks**: LEASH-021, LEASH-022, LEASH-023, LEASH-052, LEASH-071, LEASH-128
**Updated**: 2026-09-23

## Description
The typed result of reading shop text (sizes, return days, final sale, injection excerpt, add-on and recurring flags, confidence, reader name) and the port every reader implements.

## Business Value
Lets size, returns and shop-text rules be tested purely, and lets Laya and regex swap freely.

## Acceptance Criteria
- [x] Facts distinguishes 'not stated' from any value.
- [x] Facts records which reader produced it and whether the model was unavailable.
- [x] FactReader is a Protocol with `read(purchase, budget) -> Facts`.
- [x] Readers cap merchant text per purchase; oversized input is flagged, not silently cut.
- [x] Model unavailability is recorded as information only.

## Technical Approach
`domain/facts.py` and `ports/fact_reader.py`.

### Dependencies
- Needs LEASH-012.
- Blocks LEASH-021.
- Blocks LEASH-022.
- Blocks LEASH-023.
- Blocks LEASH-052.
- Blocks LEASH-071.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_missing_return_days_is_none_not_zero`.

## Related Files
- `solution/engine/src/leash/domain/facts.py`
- `solution/engine/src/leash/ports/fact_reader.py`
- `solution/engine/tests/domain/test_facts.py`

## Out of scope
- Any reader implementation (LEASH-071, LEASH-082).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: None means not stated; empty tuple and negative days rejected.
- [x] met — criterion 2: required `reader`, `model_unavailable` flag.
- [x] met — criterion 3: runtime-checkable `FactReader.read(purchase, budget) -> Facts` and `Budget` protocol.
- [x] met — criterion 4: shared `bounded_text` caps at 16,000 chars keeping head and tail, flags `oversized_text` → `oversized_merchant_text` caution. That each reader uses it is verified in the reader tickets (LEASH-071/082).
- [x] met — criterion 5: model unavailability only in `information`; `cautions` empty.
Check: 8 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
