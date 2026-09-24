# LEASH-010: Money value object

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T1
**Blocked by**: none
**Blocks**: LEASH-012, LEASH-013, LEASH-128
**Updated**: 2026-09-23

## Description
Exact money handling: Decimal amounts, half-even rounding to cents, fixed FX conversion to CHF, Swiss display format (CHF 1'142.70).

## Business Value
The 300.00-exactly edge case and currency conversion (USD 450 → CHF 391.50) depend on it.

## Acceptance Criteria
- [x] Amounts are Decimal and round half-even to cents.
- [x] USD 450.00 converts to CHF 391.50; EUR 199.00 to CHF 189.05; GBP 219.00 to CHF 245.28.
- [x] Unsupported currency raises a clear error.
- [x] Formats 1142.7 as `CHF 1'142.70`.

## Technical Approach
Value object in `domain/money.py`. Rates from data/fx_rates.csv are constants; no I/O.

### Dependencies
- None.
- Blocks LEASH-012.
- Blocks LEASH-013.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_usd_converts_with_fixed_rate`, `test_half_even_rounding`. Run `uv run pytest tests/domain/test_money.py`.

## Related Files
- `solution/engine/src/leash/domain/money.py`
- `solution/engine/tests/domain/test_money.py`

## Out of scope
- Live FX rates.
- Currency inferred from merchant country (forbidden by the data contract).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: `money()` and `to_chf()` quantize to cents with ROUND_HALF_EVEN, float rejected; ties 0.125→0.12, 0.135→0.14, 2.675→2.68 tested; matches data_dictionary.md.
- [x] met — criterion 2: rates match data/fx_rates.csv; 450×0.87=391.50, 199×0.95=189.05, 219×1.12=245.28 asserted.
- [x] met — criterion 3: `UnsupportedCurrency` names the currency and lists supported ones; tested with JPY.
- [x] met — criterion 4: `fmt_chf(money("1142.7")) == "CHF 1'142.70"` asserted, plus larger and negative amounts.
Check: `uv run pytest tests/domain/test_money.py` — 8 passed.
Verdict: moved to review.
