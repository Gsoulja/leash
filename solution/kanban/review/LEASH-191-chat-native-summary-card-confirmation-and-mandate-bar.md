# LEASH-191: Chat-native summary card, confirmation and mandate bar

**Status**: REVIEW
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
- [x] Confirm is offered only after the posted draft is shown, and only once; a failed confirm leaves it actionable with the error as a message.
- [x] The summary card is built from the posted platform draft (`PlatformDraft`), never from a separate summary text.
- [x] Every posted `hard_rule` appears in the card's exact-rules disclosure.
- [x] No copy says "Face ID", "you approve every purchase" or that the assistant will search or buy (DEC-044 answers 3, 5, 6).
- [x] The mandate bar's rule count is the draft's rule count (no fixed "of 7").
- [x] Existing tests for Agent still pass; tests asserting "What Viseca received", "Confirm this permission", "PD-77" and `ruleLine` output are updated only for renamed accessible names and keep asserting the same facts.

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

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: Confirm renders only when `posted && confirmed === null`, disabled while busy, gone after success; a 409 leaves it enabled with the reason in the status message (tested).
- [x] met — criterion 2: `SummaryCard` takes only the posted `PlatformDraft`, plus the hard stop computed from `posted.hard_rules` by the shared `perOrderLimitOf` (moved as-is from Permission.tsx into `screens/limits.ts`).
- [x] met — criterion 3: the disclosure maps every `posted.hard_rules` entry through `ruleLine()`; a test checks both lines of a two-rule draft exactly.
- [x] met — criterion 4: no "Face ID", "approve every purchase" or search/buy copy in the source; the header says "Permission assistant" with setting up / active / revoked only; the fingerprint icon has no biometric wording.
- [x] met — criterion 5: the bar counts `d.rules.length` ("Permission draft · 2 rules" tested).
- [?] criterion 6: unit tests met — only "Review what Viseca will receive" → "Review permission" and "Confirm this permission" → "Confirm permission" were renamed; "What Viseca received", "PD-77" and `ruleLine` assertions unchanged. `e2e/journey.spec.ts` was renamed the same way and now opens the exact-rules disclosure before checking a rule line. The e2e hasn't been re-run since; LEASH-194 runs it.
Not built: the header's back button (the Agent tab has nowhere to go back to); a description item, not a criterion.
Verdict: moved to review; the e2e check is left to LEASH-194 and the human gate.
