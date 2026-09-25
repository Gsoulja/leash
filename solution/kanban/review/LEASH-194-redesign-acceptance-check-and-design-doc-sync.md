# LEASH-194: Redesign acceptance check and design-doc sync

**Status**: REVIEW
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
- [x] `npm test` passes with at least the 113 baseline tests (none deleted; renamed ones listed in the ticket notes).
- [x] `npm run typecheck`, `npm run build` and `npm run test:e2e` pass.
- [ ] Screenshots of Cockpit, Agent (empty, clarifying, summary, active), Permission, revoke sheet, step-up and payment detail are attached and reviewed by a human against the handoff.
- [x] The handoff's "Do not ship" list is checked where it still applies: no budget without its hard stop; no chat message alters a confirmed permission.
- [x] No customer-facing copy claims Leash searches, shops or approves every purchase (DEC-033, DEC-044).
- [ ] `solution/docs/system-design.html` (and any page naming the app's design source) cites DEC-044; the published artifact is updated.
- [x] Existing tests for all screens still pass.

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

## Evidence (2026-09-25)

- **Unit suite:** `npm test` → 25 files, 212 tests passing (baseline 12 files / 113; none deleted). `npm run typecheck` clean, `npm run build` succeeds.
- **Browser journey:** `npm run test:e2e` → 1 passed (2.5 min) on a fresh isolated `leash-e2e` Compose stack, at a 390×800 viewport.
- **Tests renamed during the epic:** `theme.test.ts` "match the prototype exactly" → "match the v4 handoff tokens exactly" (LEASH-181; the prototype check was retargeted to the handoff, not deleted). One assertion changed with its ticket's copy: StepUp's "Price, Known shop: OK" became one chip per passed check (LEASH-192).
- **Accessible names renamed during the epic** (tests and e2e updated to assert the same facts): "Review what Viseca will receive" → "Review permission", "Confirm this permission" → "Confirm permission" (LEASH-191). The step-up's agent tag moved from `.agentbadge` to `.chip.agent` (LEASH-192); the e2e selector followed.
- **e2e wording fixed here:** three assertions expected the Cockpit label "Paid · you approved", which `status.ts` had already replaced with "Approved · you approved" (LEASH-130, DEC-037) before this epic. They now assert the current wording. No app behaviour changed.
- **Screenshots:** the journey now captures `redesign-1-agent-empty` … `redesign-9-revoke-sheet` (Agent empty, clarifying, summary, active; step-up; Cockpit; payment detail; Permission; revoke sheet) into `test-results/`. A copy of this run's set was handed to the product owner for review. Timing artefacts, not defects: the rule chips were caught mid fade-in, and the step-up buttons during their arm delay.
- **Defects the screenshots caught, fixed before closing** (noted in LEASH-185, 186 and 193): the Agent composer overflowed the phone's edge (grid column sizing); the Cockpit row's ellipsis hid the AGENT tag; the payment-detail header squeezed merchant, product and time.
- **Do not ship, where it still applies:** no budget is ever shown (the mandate has no guidance budget), so there is none without its hard stop; after Confirm the chat takes no input at all (new test in `Agent.test.tsx`). "Pays without Face ID", "freeze ordering" and "quarantine chips" are out of scope under DEC-044 / LEASH-170.
- **Copy:** no customer-facing string says Leash searches, shops, approves every purchase or uses Face ID (grep of `src/**/*.tsx`; only code comments mention them).
- **Docs:** `solution/docs/system-design.html` now names DEC-044 as the customer app's design source. No published artifact of that page exists under this account, so none was republished. `CLAUDE.md` still says "Reuse the prototype's design tokens" and is left for the product owner to update.

## Review log

### 2026-09-25 — independent agent review
- [x] met (after a notes fix) — criterion 1: 212 tests pass, none deleted. The reviewer found the renamed theme test ("match the prototype exactly" → "match the v4 handoff tokens exactly") missing from the notes; it is now listed.
- [x] met — criterion 2: typecheck and build pass; e2e `1 passed (2.5m)`, exit 0, on the isolated `leash-e2e` stack.
- [?] unverifiable — criterion 3: all nine screenshots exist at 390×800; a human review against the handoff has not happened yet.
- [x] met — criterion 4: the only `LimitTile` rendered is `tone="stopped"`, so no budget appears without its hard stop; after Confirm the chat has no textbox or extra buttons (tested). The other three Do-not-ship items are deferred under DEC-044 / LEASH-170.
- [x] met — criterion 5: only code comments mention search/shop/approve-every/Face ID.
- [?] partly unverifiable — criterion 6: `system-design.html` cites DEC-044 (no other page in `docs/` or `app/` names the design source). No published copy of that page exists under this account (only Customer Journey v2, the wireframes and an unrelated codebase map), so nothing was republished. A human must point to a published copy or waive this part.
- [x] met — criterion 7: the full suite is green.
The reviewer confirmed the "Paid · you approved" → "Approved · you approved" e2e change is a test fix (`status.ts:34` has said this since LEASH-130), and the `.agentbadge` → `.chip.agent` selector only follows LEASH-192's markup.
Scope note for the product owner: this ticket's Technical Approach says "edit docs only", but the screenshots caught three layout defects, which were fixed here in `theme.css` and `Cockpit.tsx` and recorded against LEASH-185, 186 and 193. They change looks, not behaviour; please accept or reject them explicitly.
Verdict: moved to review; criteria 3 and 6 (artifact) are left for the human gate.
