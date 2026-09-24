# LEASH-167: Trust stage in the decision pipeline

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Pipes and filters + Strategy with fallback chain
**Parent**: LEASH-160
**Task ID**: 160-T7
**Blocked by**: LEASH-163
**Blocks**: LEASH-168, LEASH-172
**Updated**: 2026-09-24

## Description
Add a timed `trust` stage between dedupe and fact reading in `application/decide_purchase.py`. It builds `CanonicalText` for every free-text field, runs `assess()`, and passes the canonical view to the fact readers (regex, and Laya when present) through `FallbackReader` unchanged. The `TrustReport` goes to `decide()` as input, next to `Facts`. Raw text stays exactly as received in the saved purchase.

## Business Value
The filter only protects anything once every reader sees its output, inside the deadline budget.

## Acceptance Criteria
- [ ] The stage appears in `HandleResult.stages` as `trust` with its duration.
- [ ] Fact readers receive canonical text: a zero-width-split "re\u200bturns within 14 days" is read as 14 days.
- [ ] The stored purchase keeps the raw `item_details` byte for byte.
- [ ] `decide()` stays pure and receives the report as an argument (no I/O added to the domain).
- [ ] A stage failure (bug in a detector) gives a safe `step_up` with reason `trust_filter_error`, never an approval (edge case: detector raises).
- [ ] p99 stage time stays under 20 ms for a 16,000-character purchase (DEC-025 cap).

## Technical Approach
`application/decide_purchase.py`, `ports/fact_reader.py` (readers read a canonical view of the purchase), `domain/decide.py` signature. Keep the watchdog margin rules as they are.

### Dependencies
- Needs LEASH-163.
- Blocks LEASH-168.
- Blocks LEASH-172.

## Testing Requirements
Write first: `test_trust_stage_is_timed`, `test_reader_sees_canonical_text`, `test_raw_text_is_stored_unchanged`, `test_detector_error_gives_step_up`. Run `uv run pytest tests/application -x -q`, then the full suite.

## Related Files
- `solution/engine/src/leash/application/decide_purchase.py`
- `solution/engine/src/leash/ports/fact_reader.py`
- `solution/engine/src/leash/domain/decide.py`
- `solution/engine/tests/application/test_decide_purchase.py`

## Out of scope
- Mapping findings to verdicts (LEASH-168).
- Persisting the report (LEASH-172).
- Laya itself (LEASH-082).
