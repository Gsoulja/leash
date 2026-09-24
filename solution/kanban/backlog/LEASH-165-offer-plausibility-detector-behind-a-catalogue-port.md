# LEASH-165: Offer plausibility detector behind a catalogue port

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Port and adapter (hexagonal) + Specification
**Parent**: LEASH-160
**Task ID**: 160-T5
**Blocked by**: LEASH-161, LEASH-163, LEASH-100
**Blocks**: LEASH-168
**Updated**: 2026-09-24

## Description
A detector that checks the offer makes sense. The unit price is compared with the catalogue's `unit_price_min_chf`–`unit_price_max_chf` after conversion to CHF (too cheap is a classic scam sign). The item category is checked against the merchant category and MCC, and an unknown `merchant_id` is flagged. The catalogue is read through a new `PriceReference` port; the pack adapter reuses `adapters/pack/catalogue.py`. Reason codes: `price_anomaly`, `category_mismatch`, `unknown_merchant`.

## Business Value
Scam offers often look right in text and wrong in numbers; the pack already carries the ranges and nothing uses them.

## Acceptance Criteria
- [ ] A 27-inch monitor at CHF 40 when the catalogue minimum is higher gives `price_anomaly` with both numbers in the evidence.
- [ ] A price inside the range gives nothing (edge case: exactly at the min or max is inside).
- [ ] A foreign-currency price is converted with the row's `currency` before comparing (never the merchant's country).
- [ ] An item whose `item_id` isn't in the reference gives no price finding: missing reference is not evidence either way.
- [ ] Groceries at an electronics MCC gives `category_mismatch`; cosmetics at a supermarket does not (data dictionary: merchant category isn't item category).
- [ ] The detector's severity follows DEC-038's answer on price anomalies.

## Technical Approach
Port in `ports/price_reference.py`; pack adapter in `adapters/pack/`; detector `domain/trust/plausibility.py` receives a snapshot of the reference, so the domain stays pure. Money uses `Decimal` and `to_chf` from `domain/money.py`.

### Dependencies
- Needs LEASH-161.
- Needs LEASH-163.
- Needs LEASH-100.
- Blocks LEASH-168.

## Testing Requirements
Write first: `test_price_below_catalogue_min_is_anomaly`, `test_price_at_catalogue_max_is_fine`, `test_usd_price_converted_before_comparing`, `test_unknown_item_gives_no_price_finding`. Run `uv run pytest tests/domain/trust tests/adapters -x -q`.

## Related Files
- `solution/engine/src/leash/ports/price_reference.py`
- `solution/engine/src/leash/adapters/pack/catalogue.py`
- `solution/engine/src/leash/domain/trust/plausibility.py`
- `solution/engine/tests/domain/trust/test_plausibility.py`

## Out of scope
- A production price feed.
- Using catalogue prices as the purchase price (the checkout stays authoritative).
- Hard-coding thresholds to scenario IDs.
