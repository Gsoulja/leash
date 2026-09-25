# LEASH-191: Chat-native summary card, confirmation and mandate bar

**Status**: BACKLOG
**Priority**: P1
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` V4 summary card, confirm reply chip, system chip, header and mandate bar; rule 2 ("the chat is not the authority — the confirmed mandate is"); DEC-035 (confirm binds the reviewed draft)
**Decisions**: DEC-044 (LEASH-180, questions 3–6), DEC-035, DEC-019, DEC-033, DEC-003
**Parent**: LEASH-179
**Task ID**: 179-T12
**Blocked by**: LEASH-180, LEASH-183, LEASH-190
**Blocks**: LEASH-194
**Updated**: 2026-09-25

## Description
Second half of the structural change. Replace the review button, posted-draft card and confirm button below the transcript with the handoff's chat-native moment, keeping the exact same calls (`submitDraft`, then `confirmDraft`) and their gating:
- When the draft is `ready`, a suggested reply "Review permission" triggers `submitDraft` (same as today's button).
- The posted draft renders as the **summary card** in the transcript: 1.5px ink border, the hard-stop tile (and budget tile only per DEC-044), the remaining rules, the uncertainty policy, open optional questions, and a disclosure with the exact `hard_rules` lines (`ruleLine()`) and the platform draft id.
- Suggested replies: ink-filled **Confirm permission** with the fingerprint icon (no biometric claim, DEC-019) and **Start over**. Confirm calls `confirmDraft`; on success a green system chip "Permission active · version N" is posted.
- Header: back, `LogoMark` with status dot, "Permission assistant", status line; and the **mandate bar** (draft / active / revoked tint, "n rules", expandable list).

## Business Value
The consent moment, in the conversation, showing exactly what will be enforced — the handoff's central trust promise.

## Acceptance Criteria
- [ ] Confirm is offered only after the posted draft is shown, and only once; a failed confirm leaves it actionable with the error as a message.
- [ ] The summary card is built from the posted platform draft (`PlatformDraft`), never from a separate summary text.
- [ ] Every posted `hard_rule` appears in the card's exact-rules disclosure.
- [ ] No copy says "Face ID", "you approve every purchase" or that the assistant will search or buy (DEC-044 answers 3, 5, 6).
- [ ] The mandate bar's rule count is the draft's rule count (no fixed "of 7").
- [ ] Existing tests for Agent still pass; tests asserting "What Viseca received", "Confirm this permission", "PD-77" and `ruleLine` output are updated only for renamed accessible names and keep asserting the same facts.

## Technical Approach
New `SummaryCard` and `MandateBar` in `components/chat/`, rendered by `Agent.tsx` from `posted` and `d`. The `act()` wrapper, `confirmed` flag, query invalidation of `["mandates"]` and `startOver()` are unchanged. `ruleLine()` stays exported and reused.

### Dependencies
- Needs LEASH-180.
- Needs LEASH-183.
- Needs LEASH-190.
- Blocks LEASH-194.

## Testing Requirements
Red first in `src/screens/Agent.test.tsx`: `summary card lists every posted hard rule`, `confirm is not offered before the draft is posted`, `a confirmed permission posts one active system chip`. Run `cd solution/app && npm test && npm run typecheck && npm run test:e2e`.
At risk: `src/screens/Agent.test.tsx` (review region, confirm button, platform draft id, open questions list), `e2e/journey.spec.ts` ("Confirm this permission").

## Related Files
- `solution/app/src/screens/Agent.tsx`, `solution/app/src/screens/Agent.test.tsx`
- `solution/app/src/components/chat/`, `solution/app/src/components/ui/LimitTile.tsx`

## Out of scope
- Must follow / May choose / Must ask grouping, revision ids and stale-confirm handling (LEASH-146, LEASH-101).
- "Start shopping" handoff after activation (LEASH-147).
- Freeze button in the header, search progress, carousel, receipt (DEC-033 / LEASH-188).
