# LEASH-161: Decision log entry for the trust filter

**Status**: BACKLOG
**Priority**: P1
**Type**: docs
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (proposal from the 2026-09-24 trust-filter session)
**Decisions**: DEC-009, DEC-025, DEC-029, DEC-030
**Pattern**: — (decision record)
**Parent**: LEASH-160
**Task ID**: 160-T1
**Blocked by**: none
**Blocks**: LEASH-162, LEASH-165, LEASH-169, LEASH-173
**Gate**: DECISION — the product owner answers the four open questions (price anomaly severity, scanning names, price reference outside the pack, off-platform payment under a decline policy). Each answer changes the verdict mapping in LEASH-168 and the scope of LEASH-165.
**Updated**: 2026-09-24

## Description
Record the trust filter in `solution/docs/decisions.md` as DEC-038 before any behaviour changes (CLAUDE.md: change the log before changing behaviour). The filter labels untrusted shop and agent text and never deletes it. It canonicalises the text, scans all five free-text fields (`merchant_name`, `merchant_city`, `item_name`, `item_details`, `purchase_description`), flags links and payment steering, checks the offer against the catalogue and MCC, and runs the lookalike check on a confusable skeleton. Four open questions must be answered here.

## Business Value
Every later ticket in this epic cites one settled decision instead of the brainstorm.

## Acceptance Criteria
- [ ] DEC-038 states: the filter labels, never deletes; raw text stays evidence; findings only add caution (DEC-009 merge rule unchanged).
- [ ] DEC-038 lists which reason codes are integrity signals (never auto-approve, DEC-029/030) and which are doubt signals (uncertainty policy).
- [ ] Open question answered: is a price outside the catalogue range a doubt or an integrity signal?
- [ ] Open question answered: are names scanned for instructions, or only neutralised when shown? (Example: a shop called "System Store".)
- [ ] Open question answered: what replaces `items.csv` as a price reference outside the pack?
- [ ] Open question answered: off-platform payment under a `decline` policy is `decline` (like injection).
- [ ] Status `Accepted` with the product owner as source, or the open items explicitly deferred with a named default.

## Technical Approach
Edit `decisions.md` only. Use the options and trade-offs in `chat-to-purchase-flow-v2.html` ("Open before building").

### Dependencies
- Blocks LEASH-162.
- Blocks LEASH-165.
- Blocks LEASH-169.
- Blocks LEASH-173.

## Testing Requirements
No code. Check: `grep DEC-038 solution/docs/decisions.md` shows the entry with status and source.

## Related Files
- `solution/docs/decisions.md`

## Out of scope
- Writing code or tests.
- Changing existing DEC entries other than cross-references.
