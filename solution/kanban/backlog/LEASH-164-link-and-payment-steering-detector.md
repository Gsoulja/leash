# LEASH-164: Link and payment-steering detector

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-038 (to be written in LEASH-161), DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: Specification
**Parent**: LEASH-160
**Task ID**: 160-T4
**Blocked by**: LEASH-163
**Blocks**: LEASH-168
**Updated**: 2026-09-24

## Description
A detector for text that tries to move the payment or the customer elsewhere: URLs and bare domains, e-mail addresses, phone numbers, IBANs, crypto addresses, and phrases such as "pay outside", "complete payment at", "wire", "gift card" or "WhatsApp us". A domain that doesn't match the merchant name adds weight. Reason codes `external_link_in_shop_text` (doubt) and `off_platform_payment` (integrity), unless DEC-038 says otherwise.

## Business Value
The schema has no URL field, so a redirect can only hide in free text, and today nothing looks for it.

## Acceptance Criteria
- [ ] "Complete payment at pay-examp1e.shop for 10% off" gives `off_platform_payment` with the excerpt.
- [ ] "Manual: example.com/manual.pdf" gives only `external_link_in_shop_text`.
- [ ] An IBAN or a Bitcoin address in `item_details` gives `off_platform_payment`.
- [ ] Sizes, prices, model numbers and dates are not read as phone numbers (edge case: "27-inch 2560x1440 144 Hz").
- [ ] No pack line raises a finding except those the test names on purpose.

## Technical Approach
`domain/trust/links.py`, registered with `assess()`. Runs on canonical text so `pay‑example[.]shop` with odd dashes or brackets is still found.

### Dependencies
- Needs LEASH-163.
- Blocks LEASH-168.

## Testing Requirements
Write first: `test_payment_link_is_off_platform`, `test_manual_link_is_only_a_link`, `test_iban_is_off_platform`, `test_screen_size_is_not_a_phone_number`. Run `uv run pytest tests/domain/trust -x -q`.

## Related Files
- `solution/engine/src/leash/domain/trust/links.py`
- `solution/engine/tests/domain/trust/test_links.py`

## Out of scope
- Fetching or resolving URLs (no network in the domain).
- Reputation lists of bad domains.
