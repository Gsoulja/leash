# LEASH-125: Browser end-to-end customer journey

**Status**: DONE
**Priority**: P0
**Type**: test
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T9
**Blocked by**: LEASH-092, LEASH-093, LEASH-094, LEASH-095, LEASH-096, LEASH-124, LEASH-123
**Blocks**: LEASH-128
**Updated**: 2026-09-23

## Description
Browser test of the whole journey: instruction → clarification → platform draft → confirm → purchase → step_up → answer → payment detail → tighten → later run keeps its snapshot → revoke.

## Business Value
Proves the customer-control requirement end to end.

## Acceptance Criteria
- [x] The journey passes against the fake Viseca API.
- [x] Reloading the page mid-journey loses no open ask.

## Technical Approach
Playwright against the app + backend + fake API.

### Dependencies
- Needs LEASH-092.
- Needs LEASH-093.
- Needs LEASH-094.
- Needs LEASH-095.
- Needs LEASH-096.
- Needs LEASH-124.
- Needs LEASH-123.
- Blocks LEASH-128.

## Testing Requirements
Run `npm run test:e2e`.

## Related Files
- `solution/app/e2e/journey.spec.ts`

## Out of scope
- Visual regression.

## Implementation note (2026-09-23)
- `solution/app/e2e/journey.spec.ts` (Playwright, Chromium, phone viewport) runs the whole journey in one test, against the built app served by the engine API, with the worker and the fake Viseca platform:
  1. instruction (SCEN0004's words) → the rules as read → answer the split question → "Review what Viseca will receive" shows the exact posted rules. Nothing is active yet (checked through `/api/mandates`) → Confirm.
  2. A run starts with that mandate (version 1). The step-up prompt opens by itself.
  3. **Reload mid-journey**: every ask waiting before the reload is still listed and offered after it, and the prompt shows the same payment.
  4. Reject the CHF 289.00 double charge ("…was not made"); confirm the CHF 391.50 order converted from USD 450.00 ("…was made"); defer the rest.
  5. Cockpit: "You declined" and "Paid · you approved" rows. The blocked CHF 520.00 order's detail shows "Engine: declined" and the shop's text as untrusted.
  6. Permission: lower the limit to CHF 300 → version 2.
  7. A later run gets version 2; the first run still reports version 1.
  8. Revoke → "Revoked. Viseca confirmed…".
- The app has no start-run control yet (LEASH-066), so the test starts runs through `POST /api/runs`, the endpoint the app would use.
- Isolation (`e2e/stack.ts`, `setup.ts`, `teardown.ts`):
  - its own Compose project `leash-e2e`, with its own database volume and ports (API 18080, worker 18081, fake 19000, db 55442);
  - `LEASH_BASE_URL` is pinned to the in-project fake;
  - started fresh (`down -v`, then `up --build --wait`) and removed afterwards;
  - it never touches the local `leash` database or other containers. `LEASH_E2E_REUSE` / `LEASH_E2E_KEEP` skip start / teardown.
- `npm run test:e2e` → `playwright test`. Vitest now only picks up `src/**/*.test.*`. The e2e files are type-checked. `test-results/` is git-ignored.
- **Bug found and fixed (StepUp, LEASH-094 code):** after the customer closed an answer's notice (OK), the prompt drew the answered payment again for one frame before moving to the next ask. After "Decide later" it drew the deferred one again. A tap in that frame landed on the next ask: in the first e2e run, "Decide later" deferred the CHF 391.50 order, and the following Confirm approved a different payment (CHF 299.00).
  - Fix: the ask on screen is now chosen during the render (the kept ask if still open, otherwise the next waiting one), so an answered or deferred ask is never drawn again. The effect only stores that choice and raises the "no longer waiting" notice.
  - Regression test in `StepUp.test.tsx`: `never shows an answered payment again, not even for a frame, after its notice is closed`. It records every value the amount node held; it failed before the fix with the stale CHF 289.00 frame.
- Checks: the journey passes 3 runs in a row (about 8 s for the test, about 30 s including the stack). 76 app unit tests pass; tsc and the build are clean. No `leash-e2e` containers or volumes are left, and the shared `solution-db-1` was untouched.

## Review log

### 2026-09-23 — independent agent review
- [x] met — criterion 1: `npm run test:e2e` passed 4 of 4 runs (about 28 s each, stack included) against the in-project fake. The stack is isolated and removed after each run, and `solution-db-1` and its volume were untouched. The journey covers every step of the description; runs are started through `POST /api/runs`, as documented (LEASH-066).
- [x] met — criterion 2: after a reload with asks open, the prompt reopens on the same payment and offers at least as many asks as the server listed before, through the real `/api/asks` restore path.
- StepUp fix judged correct: pinning, notice, arming and the in-flight race are unchanged, and all existing tests pass. A mutant that keeps the stale frame fails the new regression test.
- Minor, non-blocking:
  1. the browser side of the reload check counts asks rather than identifying them;
  2. the snapshot is asserted by version number only;
  3. there was no unit test for the "Decide later" stale frame;
  4. the shared `leash-engine:local` image tag is rebuilt, and `LEASH_E2E_PROJECT` could point at the local stack.
Follow-up after the review:
- (3) added `never shows a deferred payment again, not even for a frame, after Decide later`. It fails when the old choice of ask is restored.
- (4) `e2e/stack.ts` refuses a project name not starting with `leash-e2e`, so setup and teardown can never `down -v` the local stack.
- 77 app tests pass, tsc is clean, and the e2e passed again with no containers left.
- (1), (2) and the shared image tag are left as they are: they are beyond the criteria.
Verdict: all criteria met. Moved to done on the product owner's standing instruction for this run.
