# LEASH-194: Redesign acceptance check and design-doc sync

**Status**: BACKLOG
**Priority**: P1
**Type**: test
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: CLAUDE.md working agreement ("keep the design pages in sync with decisions"); design handoff § "Do not ship"
**Decisions**: DEC-044 (LEASH-180), DEC-033
**Parent**: LEASH-179
**Task ID**: 179-T15
**Blocked by**: LEASH-186, LEASH-187, LEASH-188, LEASH-191, LEASH-192, LEASH-193
**Blocks**: none
**Updated**: 2026-09-25

## Description
Close the epic with evidence: the full unit suite and the browser journey pass on the redesigned app, a human compares 390×800 screenshots of each redesigned surface with the handoff, and the design docs stop citing DEC-021 as the app's design source.

## Business Value
Proof that the redesign changed how things look and nothing about what they do.

## Acceptance Criteria
- [ ] `npm test` passes with at least the 113 baseline tests (none deleted; renamed ones listed in the ticket notes).
- [ ] `npm run typecheck`, `npm run build` and `npm run test:e2e` pass.
- [ ] Screenshots of Cockpit, Agent (empty, clarifying, summary, active), Permission, revoke sheet, step-up and payment detail are attached and reviewed by a human against the handoff.
- [ ] The handoff's "Do not ship" list is checked where it still applies: no budget without its hard stop; no chat message alters a confirmed permission.
- [ ] No customer-facing copy claims Leash searches, shops or approves every purchase (DEC-033, DEC-044).
- [ ] `solution/docs/system-design.html` (and any page naming the app's design source) cites DEC-044; the published artifact is updated.
- [ ] Existing tests for all screens still pass.

## Technical Approach
Run the suites; capture screenshots with the existing Playwright setup; edit docs only.

### Dependencies
- Needs LEASH-186.
- Needs LEASH-187.
- Needs LEASH-188.
- Needs LEASH-191.
- Needs LEASH-192.
- Needs LEASH-193.

## Testing Requirements
`cd solution/app && npm test && npm run typecheck && npm run build && npm run test:e2e`. Compare the test count with the 2026-09-25 baseline (12 files, 113 tests).

## Related Files
- `solution/app/e2e/journey.spec.ts`
- `solution/docs/system-design.html`, `solution/docs/decisions.md`

## Out of scope
- New features; fixing behaviour found broken (file a bug ticket under LEASH-174 instead).
