# LEASH-112: Demo script

**Status**: DONE
**Priority**: P0
**Type**: docs
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-009
**Task ID**: 009-T3
**Blocked by**: LEASH-056, LEASH-094, LEASH-096
**Blocks**: LEASH-113, LEASH-114, LEASH-128
**Updated**: 2026-09-25

## Description
Script covering the three required moments: an ordinary purchase with no friction, a manipulated purchase stopped, and the human approve / reject / revoke path.

## Business Value
Exactly what the brief asks judges to see.

## Acceptance Criteria
- [ ] Script fits in 5 minutes. *(Timed plan: 5:00. The stopwatch dry run with the app on screen is a human rehearsal step; see the checklist in the script.)*
- [x] Each moment names the scenario purchase and what to point at.
- [x] Includes policy interpretation and explicit confirmation before any purchase.

## Technical Approach
`solution/demo/script.md`.

### Dependencies
- Needs LEASH-056.
- Needs LEASH-094.
- Needs LEASH-096.
- Blocks LEASH-113.
- Blocks LEASH-114.
- Blocks LEASH-128.

## Testing Requirements
Dry run with a stopwatch.

## Related Files
- `solution/demo/script.md`

## Out of scope
- Deck design.

## Notes (2026-09-23, from LEASH-066)
- Start demo runs through the policy service, `POST /api/runs` (it stores the run's mandate snapshot), not straight at the platform.

## Implementation note (2026-09-23)
- `solution/demo/script.md` uses SCEN0004 with a 5:00 timeline:
  - 0:00–1:00 the permission is read into rules and questions, one question is answered, the draft is posted and shown exactly as Viseca holds it, then explicitly confirmed; the run starts through `POST /api/runs`;
  - Moment 1: AU0035 approved with no friction;
  - Moment 2: AU0037, the shop's text claiming a CHF 900 pre-authorisation, declined on the CHF 400 limit; optionally AU0039, the lookalike PixelHarbour;
  - Moment 3: the step-up prompt, with AU0036 rejected as a duplicate and AU0038 (USD 450 → CHF 391.50) approved after the re-check; then revoke with a second tap and Viseca's confirmation.
  - Each moment names the purchase and what to point at.
- The app has no chat (LEASH-092) and no start-run control (LEASH-066 flag), so the permission steps run as terminal commands (`curl` + `jq`) next to the app.
- Automated dry run of the whole flow through the API process and worker against the fake platform (a throw-away database, dropped afterwards): every stated outcome and message matched (approved/declined states, the AU0036 and AU0039 messages, the order of asks, reject → declined, approve → approved, revoke confirmed).
- Criterion 1 is unticked. The plan is timed to 5:00, but the stopwatch rehearsal with the app on screen is a human step (rehearsal checklist at the end of the script).

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met — criterion 3: interpretation → answer → exact posted draft → explicit confirm, before the run. Every command, jq path and message was checked.
- [ ] not met — criterion 1: every purchase is decided within a second of the run's start and every ask expires 120 s later. Answering AU0038 at 3:40 would find it expired. The full-screen prompt also covered moments 1 and 2 and would not reopen by itself.
- [ ] not met — criterion 2: the labels didn't exist in the app ("Approved"/"Declined" instead of "Paid"/"Blocked"; the table caption is only an aria-label).
Verdict: returned to in-progress. Fixes:
- The timeline puts the human path right after the run starts (1:10–2:30, inside the 120 s window, with the prompt already open), then moment 1 (AU0035, **Paid**, "Engine: approved", every row **Passed**), then moment 2 (AU0037, **Blocked**, "Engine: declined", Price **Failed**), then revoke. Still 5:00.
- The checklist checks that AU0038 is answered within 120 s of the run starting.

### 2026-09-23 — independent agent review, round 2
- [x] closed from round 1: the 120 s window (AU0038 answered about 85 s after the run starts), the prompt covering the app and its reopening, the order of steps, and verbatim labels.
- [ ] not met — criterion 2: an ask arriving on the stream carries only the shop, amount, reasons and expiry. The prompt showed no "what passed", no USD amount and no items until a reload, yet the script points at them.
- [?] criterion 1: the timed plan adds up; the stopwatch rehearsal remains a human step.
Verdict: returned to in-progress. Fix in the app, not the script (real customers had the same gap): `useAsks` fetches `/api/asks` 0.3 s after an `ask.created` (debounced for bursts), so the prompt fills in what passed, the currency and the items by itself; the event journal keeps a slow reply from dropping or reviving an ask. Test in `useAsks.test.tsx`; 68 app tests pass (3/3).

### 2026-09-23 — independent agent review, round 3
- [x] met — criterion 2. A test of the real `useAsks` and `StepUp` together shows AU0036's passed line and AU0038's USD 450.00 and items filling in about 0.3 s after the stream event, with no reload. Removing the refetch makes it fail. The refetch can't drop or revive an ask (commit-before-event, journal replay; tested with a slow stale reply).
- [x] met — criterion 3.
- [?] unverifiable — criterion 1. The plan adds up to 5:00, with AU0038 answered about 85 s into the 120 s window. **Needs a human stopwatch rehearsal** (checklist at the end of the script).
Verdict: moved to review/, not done. The only open item is the human rehearsal.
