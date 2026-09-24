# LEASH-093: Cockpit: agent payments and spending bar

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T4
**Blocked by**: LEASH-091, LEASH-118
**Blocks**: LEASH-095, LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Payments grouped by day with status chips and a spending bar for period limits.

## Business Value
At-a-glance control, like the one app's cockpit.

## Acceptance Criteria
- [x] Paid, waiting, blocked, no answer and not sent are distinct.
- [x] Spending bar shows the rolling window and what's left.
- [x] Initial state comes from the read model; the stream only updates it.

## Technical Approach
`src/screens/Cockpit.tsx`.

### Dependencies
- Needs LEASH-091.
- Needs LEASH-118.
- Blocks LEASH-095.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `waiting payment shows 'Waiting for you'`.

## Related Files
- `solution/app/src/screens/Cockpit.tsx`

## Notes
- Wired into the app's Cockpit tab. Stream events (`payment.decided`, `ask.resolved`, reconnects) only trigger a reload of /api/payments and /api/spending.
- Chip text uses the accessible `-text` colour tokens; the grey "other" chip is 5.39:1.

## Out of scope
- Non-agent card transactions.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: labels match the contract and the prototype for every final_state × resolved_by; paid/waiting/blocked differ in colour. Caveat: No answer and Not sent shared the grey chip (as in the prototype).
- [x] met — criterion 2: 7-day label, what's left, over-limit full bar, no-period case, zero spend. Outside the wording: a failed/loading /api/spending showed a made-up CHF 0.00; rounding turned the bar red at 99.5%; the mismatch flag isn't shown.
- [x] met — criterion 3: only read-model data; payment.decided / ask.resolved / reconnect trigger reloads; close on unmount; works without EventSource. End to end against the contract mock in headless Chromium (Zurich times, 78% bar).
Fixed after review: an unknown spending state says "Loading spending…" / "Spending unavailable right now" instead of CHF 0.00; the bar is red only when nothing is left; the bar announces the CHF amounts (`aria-valuetext`); "Not sent" has its own outline chip, distinct from "No answer". The mismatch flag is deliberately not shown to the customer (events.md: integrity alerts belong in the inspector, LEASH-097). 27 app tests pass; typecheck clean.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
