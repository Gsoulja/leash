# LEASH-097: Engine inspector panel

**Status**: REVIEW
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-007
**Task ID**: 007-T8
**Blocked by**: LEASH-091
**Blocks**: LEASH-103
**Updated**: 2026-09-24

## Description
Side panel for judges: every purchase with engine and final verdict, the checks for the selected one, facts read and the JSON sent to the API.

## Business Value
Makes the reasoning visible during the demo.

## Acceptance Criteria
- [x] The panel lists every payment of the selected run with both its engine verdict and its final outcome.
- [x] Selecting a payment shows its checks (label, status, agreed, actual, detail, reason code).
- [x] The selected payment shows the facts read: the reader's name, whether the model was unavailable, and the shop's text marked untrusted.
- [x] The selected payment shows the JSON body sent to Viseca, and says so plainly when nothing was sent.
- [x] `integrity.alert` events appear in the panel (operator-only; never on the phone screens).
- [x] The panel is not mounted below the desktop breakpoint (phone width).
- [x] The panel and the phone always describe the same run.

## Technical Approach
`src/inspector/Inspector.tsx`, mounted beside `PhoneFrame` by a two-column shell in `App.tsx`.

Reference behaviour and look: `renderSide()` in `solution/prototype/index.html` and its `.side` / `.panel` / `.tbl` / `.chk` tokens.

Data comes entirely from the existing contract — `GET /api/payments?run_id=` and `GET /api/payments/{id}`
(`checks`, `shop_texts`, `sent_to_viseca`, `engine_version`, `reader`). No engine change.

Live refresh reuses the house pattern: the panel listens to `payment.decided` on the event stream and
invalidates the shared `["payments"]` query key, exactly as `Cockpit.tsx` already does. `integrity.alert`
is read off the same stream.

Width is gated with `matchMedia`, so the panel is absent rather than merely hidden below the breakpoint:
it is assertable in jsdom, and it stops the panel fetching payment detail nobody can see.

`useSelectedRun` moves out of `Cockpit.tsx` into `src/api/useSelectedRun.ts` and the selection is lifted
to `App.tsx`, so a run switched on the phone also switches the panel.

### Dependencies
- Needs LEASH-091.
- Blocks LEASH-103.

## Testing Requirements
Write first: `selecting a row shows its checks`.
Also: `the panel is absent at phone width`; `shop text renders as text, never markup`;
`an integrity alert appears in the panel`; `a payment.decided event refreshes the list`.

## Related Files
- `solution/app/src/inspector/Inspector.tsx`
- `solution/app/src/inspector/Inspector.test.tsx`
- `solution/app/src/api/useSelectedRun.ts` (lifted out of `screens/Cockpit.tsx`)
- `solution/app/src/App.tsx` (two-column shell, run selection lifted)
- `solution/app/src/screens/Cockpit.tsx` (takes the run selection as a prop)
- `solution/app/src/theme.css` (inspector tokens ported from the prototype)

## Scope amendment (2026-09-24)
The original two criteria covered less than the description, and `Related Files` named only
`Inspector.tsx` — but a side panel cannot exist without a shell in `App.tsx` and its tokens in
`theme.css`. Criteria expanded to the description's four content blocks, plus the `integrity.alert`
surface that `solution/contracts/events.md` assigns to the inspector and no other ticket owns.
Agreed with the product owner before work started.

## Out of scope
- Editing data.
- The adversarial checkout form (LEASH-103 owns it).
- Changing any engine or contract behaviour.

## Review log

### 2026-09-24 — independent agent review
- [x] met — criterion 1: both verdicts rendered per row (`data-engine` / `data-final`), `null` engine verdict shown as `—`; `GET /api/payments` has no pagination, so "every payment" holds.
- [x] met — criterion 2: all six check fields rendered; `CHECK_TONE` is typed `Record<Check["status"], string>`, so tsc enforces every contract status.
- [x] met — criterion 3: reader name, an `model_unavailable` branch, and each shop text under an "untrusted" heading; empty case handled.
- [x] met — criterion 4: both branches covered by tests.
- [x] met — criterion 5: the panel is the only listener for `integrity.alert` in `src/` (verified by grep); malformed payloads are swallowed by `read()`.
- [x] met — criterion 6 (logic): `Inspector` returns null before `InspectorPanel`'s hooks run; the test asserts zero fetches at phone width. The matchMedia query matches the `.shell` breakpoint in `theme.css`.
- [ ] not met — criterion 7: `selected` outlived a `runId` change, so the open decision block kept showing a payment from the run the phone had left; the detail query key carried no run.
- Checked and clean: no assertion in `Cockpit.test.tsx` was weakened, deleted or made vacuous by the `useSelectedRun` extraction (five hunks, all swapping `<Cockpit />` for a harness that calls the real hook); no `dangerouslySetInnerHTML` or `innerHTML` anywhere in `src/`.
Verdict: returned to in-progress.

Fix: a failing test was written first (`switching the run clears a payment selected in the run left behind`), then `InspectorPanel` was given a `shownRun` guard that clears `selected` during render when `runId` changes. Integrity alerts are deliberately *not* cleared — they are filtered by run instead, so switching back re-shows an earlier run's alerts rather than discarding them.

### 2026-09-24 — independent agent review (round 2)
- [x] met — criterion 7: the reviewer traced that the new test fails against the pre-fix component (the assertions are synchronous right after the rerender, so it cannot pass by racing a refetch) and could no longer construct a sequence where the panel shows anything from a run the phone has left.
- [x] met — criteria 1–6 re-checked against the fix: no render loop (state is adjusted on the rendering component itself and the guard is false on the next pass), no lost selection in the same-run case, alerts still behave as criterion 5 requires.
- 99 tests pass; `tsc --noEmit` clean; `npm run build` clean.

Recorded as unverified, for the human gate:
- The panel's actual appearance and resize behaviour in a real browser — not judgeable from tests.
- Integrity alerts are live-stream-only: alerts raised before the panel mounts are not shown, because the contract has no backfill endpoint. Inherent to the contract, not a defect in this ticket.
- The Playwright journey (`e2e/journey.spec.ts`) was not run here — it needs the Docker stack. Its locators were read and do not collide with the panel's row names, but that is inspection, not a run.

Verdict: moved to review.

### 2026-09-24 — a second implementation, dropped in the merge

This ticket was built twice in parallel: once on `feature/LEASH-097` (the version above, which shipped)
and once in a session that did not see it. On merge the shipped one was kept, because it is better on
both points that second implementation's own reviewer had found against it:

- the panel took a `runId` prop that `App.tsx` never passed, so it listed payments across every run
  rather than the selected one — the version above lifts `useSelectedRun` out of `Cockpit` so the phone
  and the panel provably describe the same run;
- it hid the panel with CSS `display:none`, so on a phone the panel was still mounted and still fetched
  `/api/payments` — the version above does not mount it below the breakpoint at all.

Two findings from that review are worth keeping, because they apply to this implementation too and are
not covered by its own tests:

1. **Asserting CSS from a test is easy to get wrong.** A `toContain(".inspector{display:none}")` check
   passed while the panel was visible at every width — once with the rule wrapped in `@media print`, once
   with a later `display:block` overriding it. It only ever caught deletion. This implementation uses
   `matchMedia` instead, so it is not exposed to that, but any future CSS-level assertion should read the
   cascade rather than string-match it.
2. **A settlement-wording sweep must cover the inspector too.** `status.test.ts` (LEASH-130) sweeps the
   customer screens for "paid / settled / shipped / delivered"; `src/inspector/` is not in that list. The
   panel is operator-facing, so the customer-wording rule does not strictly bind it — but if it ever
   renders one of those words next to an accepted delivery, DEC-037 and LEASH-130's AC9 are the reason
   that would be wrong.

The dropped implementation's code is not retained; nothing from it is referenced anywhere.
