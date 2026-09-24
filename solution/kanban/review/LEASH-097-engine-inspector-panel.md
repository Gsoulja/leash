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
- [x] Selecting a payment shows its checks and JSON.
- [x] Hidden on phone width.

## Technical Approach
`src/inspector/Inspector.tsx`.

### Dependencies
- Needs LEASH-091.
- Blocks LEASH-103.

## Testing Requirements
Write first: `selecting a row shows its checks`.

## Related Files
- `solution/app/src/inspector/Inspector.tsx`

## Out of scope
- Editing data.

## Implementation notes

- `src/inspector/Inspector.tsx`: a read-only `<aside>`. It lists the run's payments with the engine's
  own verdict beside the final outcome; selecting one shows the checks table, the facts read (with the
  reader's name and whether the model was unavailable), and the exact body POSTed to Viseca. Everything
  comes from `GET /api/payments` and `GET /api/payments/{id}` — the contract already carries `checks`,
  `evidence`, `sent_to_viseca`, `engine_version` and `reader`, so no API change was needed.
- Hidden on phone width in `theme.css`: `.inspector{display:none}`, shown only from `min-width:900px`.
  A test parses the stylesheet for both halves of that rule, the way `theme.test.ts` does.
- Mounted in `App.tsx` next to `PhoneFrame` inside a new `.stage` flex row (an unmounted panel is dead
  code). `App.tsx` and `theme.css` are outside Related Files for that reason. `App.tsx` mounts it
  without a run, so it lists every payment the engine has answered; the `runId` prop narrows it to one
  run when a caller supplies one.
- `Nothing was sent.` is shown when `sent_to_viseca` is null, so an empty box never reads as "sent
  nothing meaningful".
- Out of scope held: no input, textarea, select or form exists in the panel, and a test asserts it.

### Not part of this ticket, but it blocked the check
`src/api/schema.d.ts` had drifted from `contracts/policy-api.yaml` (the `revision`/`SubmitRequest`
additions from LEASH-101), so `npm test` failed before any inspector code existed. Regenerated with
`npm run gen:api`, and `Agent.test.tsx`'s draft factory gained the now-required `revision: 1`.

Verification: `npm test` → 11 files, 96 tests passed; `npm run typecheck` → clean.

## Review log

### 2026-09-24 — independent agent review
Both criteria `met`. The reviewer probed the paths the tests do not: select A then B (the detail
follows B — the query is keyed by the selection, so nothing from A survives), empty `checks`, a 404
detail, an empty and a failing payments list. Untrusted text confirmed inert: `evidence` entries with
`<script>`/`<img onerror>`, a `reader.name` of `<em>regex</em>` and markup nested inside
`sent_to_viseca` all rendered as escaped text, `querySelectorAll("script, img, iframe, b, em")` → 0.
Out of scope held: GETs only, no mutation, no form control. Six mutations of the component killed six
tests.

It found the AC2 assertion **not load-bearing** and three defects. All four are now fixed:

- **The CSS test only caught deletion.** It string-matched the stripped stylesheet, so the panel stayed
  visible at every width and the test still passed when the rule was wrapped in `@media print`, and
  again when a later `.inspector{display:block}` overrode it. Replaced with a small walker that
  collects every `.inspector` display declaration together with the at-rule enclosing it, then asserts
  the last unconditional rule hides it and exactly one rule shows it, inside a `min-width` query of at
  least 768px. Both of the reviewer's bypasses now fail it, and so does deleting the rule.
  (`display:none` is the right mechanism: below 900px the panel is out of the accessibility tree too.)
- **The list never refreshed.** It used its own query key, and nothing invalidates it — during a live
  run the judges' list would have gone stale until a remount. It now shares the cockpit's
  `["payments", runId]` key, which the event stream already invalidates.
- **The notes claimed a run scope the caller never supplies.** `App.tsx` mounts `<Inspector />` bare.
  The note is corrected rather than the mount: listing every answered payment is what a judge wants.
- **Duplicate React keys** when two evidence lines are identical; keyed by index and text now.
- Empty `checks` rendered a header row with no body; it now says no checks were recorded.

Verification: `npm test` → 11 files / 96 tests passed; `npm run typecheck` → clean.
