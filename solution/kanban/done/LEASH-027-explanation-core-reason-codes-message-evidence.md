# LEASH-027: Explanation core: reason codes, message, evidence

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M1 — SCEN0000 offline vertical slice
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-001
**Task ID**: 001-T18
**Blocked by**: LEASH-014
**Blocks**: LEASH-032, LEASH-034, LEASH-044, LEASH-052, LEASH-121, LEASH-128
**Updated**: 2026-09-23

## Description
Turn checks into the decision payload: reason codes, a plain-language customer message, and an evidence list suitable for POST /decision. Each rule ticket supplies its own message text; this ticket builds the assembly.

## Business Value
Judges must understand what was permitted, what evidence was considered and why.

## Acceptance Criteria
- [x] Decline message names the first failing rule, then lists other failures.
- [x] Step-up message lists every warning.
- [x] Evidence lists each non-info check as 'label: actual'.
- [x] Message text never contains raw HTML or unescaped shop text.

## Technical Approach
`domain/explain.py`. Split from the rule tickets so the first vertical slice can run early.

### Dependencies
- Needs LEASH-014.
- Blocks LEASH-032.
- Blocks LEASH-034.
- Blocks LEASH-044.
- Blocks LEASH-052.
- Blocks LEASH-121.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_decline_message_names_limit`, `test_step_up_lists_all_warnings`.

## Related Files
- `solution/engine/src/leash/domain/explain.py`
- `solution/engine/tests/domain/test_explain.py`

## Out of scope
- Translations (German/French/Italian messages).

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: first failure's detail, then "Also:" with the other failures' labels.
- [x] met — criterion 2: every warn and integrity detail listed after "Please check:".
- [x] met — criterion 3: each non-info check as "label: actual", escaped and capped.
- [x] met — criterion 4: html.escape on the whole message and every evidence line; script/img/entities probed; no `<` or `>` survives.
- Fixed after review: each detail is capped (240 chars) before joining, so one huge quote can't push later warnings past the 1,000-char message cap; test added.
Check: 9 passed; mypy strict clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
