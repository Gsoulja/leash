# LEASH-094: Step-up prompt

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: DEC-012
**Parent**: LEASH-007
**Task ID**: 007-T5
**Blocked by**: LEASH-091, LEASH-063
**Blocks**: LEASH-112, LEASH-125, LEASH-128
**Updated**: 2026-09-23

## Description
Full-screen ask in the 3-D Secure style: amount, shop, why I'm asking, what passed, countdown, Confirm payment / Reject / Decide later.

## Business Value
The human approval and rejection path in the demo.

## Acceptance Criteria
- [x] Opens when an ask arrives.
- [x] Countdown from the ask's expiry.
- [x] Answers call the resolve endpoint; multiple asks queue.
- [x] Countdown uses the server's expires_at.
- [x] Answer racing expiry shows the platform outcome.
- [x] When a hard rule now fails, Approve is replaced by an explanation and only Reject remains.

## Technical Approach
`src/screens/StepUp.tsx`.

### Dependencies
- Needs LEASH-091.
- Needs LEASH-063.
- Blocks LEASH-112.
- Blocks LEASH-125.
- Blocks LEASH-128.

## Testing Requirements
Write first: `reject calls resolve with decline`.

## Related Files
- `solution/app/src/screens/StepUp.tsx`

## Out of scope
- Biometric confirmation.

## Implementation note (2026-09-23)
- `app/src/screens/StepUp.tsx` is a full-screen dialog (styles ported from the prototype, using the app's accessible colour tokens). It shows:
  - date, "AI agent · 1 of N";
  - amount, shop and items;
  - "Why I'm asking" (the ask's reasons) and what passed;
  - a countdown;
  - Confirm payment / Reject / Decide later.
- It is mounted in `App.tsx` on `useAsks()` (read model plus event stream), so it opens when an ask arrives, and several asks queue, oldest first.
- The countdown runs from the server's `expires_at` (real clock, DEC-008), ticking every second. At zero it stops offering answers and says the payment won't be made unless the platform says otherwise.
- Answers go to `POST /api/asks/{id}/answer` (new `answerAsk` in the API client).
  - 409 `not_waiting` (a race with the expiry): the prompt loads the payment and shows what the platform recorded (approved, declined, timed out or not sent).
  - 422 `cannot_approve`: Approve is replaced by the reason.
  - `can_approve: false` on the ask: the reason is shown from the start and only Reject remains (DEC-012).
- "Decide later" hides that ask; a new ask opens the prompt again.
- `useAsks` no longer assumes `EventSource` exists (as Cockpit already did).
- Tests: `StepUp.test.tsx` (10, including the requested `reject calls resolve with decline`); 46 app tests pass; `tsc` clean.

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met as worded — criteria 1, 2, 4, 5 and 6.
- [ ] safety defect under criterion 3 (multiple asks queue): the shown ask was recomputed each render. If it was resolved elsewhere, or right after an answer, the next payment appeared in its place with Confirm enabled at once, so a quick tap could approve a different payment.
- Also:
  - a device clock running ahead hid the answers of a live ask;
  - a failed outcome lookup after a 409 loaded forever;
  - no focus trap, no Escape, no focus return, and some messages not announced.
- Checked fine: escaping (React text only), a double tap sends one POST, network errors, and AA contrast of the new styles.
Verdict: returned to in-progress. Fixes:
- The ask on screen is pinned. If it disappears, a notice ("… is no longer waiting …") needs an OK before the next ask. After an answer, the recorded outcome needs an OK. A newly shown Confirm is disabled for 0.8 s.
- The countdown never disables the answers: at zero it says the time may have run out and the platform decides (a late answer shows the recorded outcome).
- A failed outcome lookup says so.
- Focus trap (enabled buttons), Escape = Decide later, focus returns to where the customer was, `aria-live` on outcome and blocked-reason messages.
- 14 StepUp tests (50 app tests), `tsc` clean.

### 2026-09-23 — independent agent review, round 2
- [x] met — criteria 1, 2, 4, 5 and 6; all round-1 fixes confirmed.
- [ ] not met — criterion 3:
  - (N2/N1) the stream could report the customer's own in-flight answer as "answered elsewhere". The reply's notice didn't name its payment and the next ask's Confirm could appear already armed, so a "try again" could approve another payment;
  - (N3) a deferred ask could never be reopened.
- Also:
  - (N5) first focus on Reject, so a keypress could decline an unread payment;
  - (N6) focus not moved to the next ask;
  - (N7) a Confirm reappearing after `can_approve` turned true again was not re-armed.
Verdict: returned to in-progress. Fixes:
- The ask whose answer is in flight stays on screen and is never reported as gone.
- Every notice names its payment (shop · amount).
- Arming is keyed to the ask, its `can_approve` and every return from a notice, and covers Reject as well as Confirm.
- The dialog itself takes focus whenever its content changes, never a button.
- A "N payment(s) waiting · Review now" banner reopens deferred asks.
- 19 StepUp tests; 63 app tests at the time, 66 after the LEASH-096 follow-ups.

### 2026-09-23 — independent agent review, round 3
- [x] met — criteria 1–6. All round-2 fixes confirmed with probes and a headless-Chromium geometry check:
  - an in-flight answer is never reported as gone; notices name the payment; the next ask stays disarmed for 0.8 s;
  - the review banner works (its tap can't reach an armed Confirm);
  - first focus is on the dialog, and Reject is armed like Confirm;
  - focus follows content changes; a returning Confirm re-arms.
- No path found where a tap or key press acts on a payment other than the one on screen.
- Minor, fixed afterwards: an answer request that never settles kept the prompt busy. It now times out after 15 s into the named "couldn't be sent" notice (test). 67 app tests pass.
- Minor, not fixed: after Escape during an in-flight answer, a "no longer waiting" notice for another ask can be replaced by the answer's outcome. It never leads to a wrong answer.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
