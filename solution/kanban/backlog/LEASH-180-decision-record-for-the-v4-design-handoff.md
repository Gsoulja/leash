# LEASH-180: Decision record — adopt the v4 handoff as the design source and rule on its scope

**Status**: BACKLOG
**Priority**: P1
**Type**: docs
**Estimated Effort**: S
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` vs DEC-021 (Team, Proposed) and DEC-033 (Product owner, Accepted)
**Decisions**: DEC-021, DEC-033, DEC-004, DEC-017, DEC-019, DEC-035
**Pattern**: — (decision record)
**Parent**: LEASH-179
**Task ID**: 179-T1
**Blocked by**: none
**Blocks**: LEASH-181, LEASH-187, LEASH-191
**Gate**: DECISION — the product owner confirms switching the app's design source from `solution/prototype/index.html` (DEC-021) to the Hi-Fi v4 handoff, and rules on the eight scope questions below. Answers 3–6 change what LEASH-187 and LEASH-191 render.
**Updated**: 2026-09-25

## Description
CLAUDE.md: "Change the decision log before changing behaviour." Record DEC-044 (next free ID; re-check `decisions.md` at write time) in `solution/docs/decisions.md` and mark DEC-021 superseded. The app currently cites DEC-021, which was never accepted and ports a placeholder prototype. The handoff calls itself the single source of truth for behaviour and copy, but part of its flow predates DEC-033 and conflicts with it.

Questions the product owner must answer (each with the proposed default):

1. **Design source.** Adopt the v4 handoff's visual system (tokens, type, icons, logo, component shapes) for the customer phone app; DEC-021 → Superseded. The engine inspector keeps its own tokens. *Default: yes.*
2. **Surfaces in scope.** In: tokens, type, icons/logo, chat primitives, rule chip, summary card, mandate bar, V3 agent-access status card and tiles, V7 freeze sheet as the revoke presentation, V5 transaction-detail styling, step-up restyle. Out (DEC-033 or generic host shell): search card, product carousel and pagination, per-proposal Approve buttons, receipt card, searching/matches banner states, card hero, quick actions, Cards/Profile tabs, V6 timeline (left to LEASH-148/150). *Default: as listed.*
3. **Handoff rule 1 ("no auto-approve, every purchase is a step_up").** Not adopted: the designer brief (`customer-journey-for-design.md`, "Fits: proceed without interruption") and the engine both allow approval within permission. *Default: not adopted; UI copy must not say "you approve every purchase".*
4. **Budget vs hard stop.** Live mandates carry only `hard_rules`; `guidance` is absent from live events (DEC-004). Leash has no "stretch" concept. *Default: show the enforceable per-order limit as the red "HARD STOP AT" tile; show a green BUDGET tile only when a separate guidance budget exists, labelled as guidance, never as enforced.*
5. **"Confirm with Face ID".** DEC-019 excludes login from the prototype; the app performs no biometric check. *Default: keep the ink-filled confirm chip with the fingerprint icon but label it "Confirm permission"; never claim biometric authentication.*
6. **Assistant persona.** The handoff's header says "Shopping agent" and "Searching…". Under DEC-033 Leash's assistant clarifies permission and does not shop. *Default: header reads "Permission assistant"; status lines limited to setting up / active / revoked.*
7. **Split with LEASH-145/146.** This epic's LEASH-189–190 present today's draft flow as a chat; LEASH-145/146 add LLM clarification, revisions, context and the Must follow / May choose / Must ask review on top of these primitives. *Default: confirm the split; LEASH-145/146 reuse, not rebuild, the chat primitives.*
8. **Tab bar in chat.** The handoff hides the tab bar in chat and the freeze sheet. *Default: keep the three existing tabs visible everywhere (they are the app's navigation, not the host shell).*

## Business Value
Every later ticket in LEASH-179 cites one settled decision instead of two competing design sources, and no ticket quietly re-introduces the superseded agent-shopping surfaces.

## Acceptance Criteria
- [ ] DEC-044 exists in `solution/docs/decisions.md` with source (product owner), date and status.
- [ ] DEC-021's status reads `Superseded by DEC-044` (row kept; nothing deleted).
- [ ] Each of the eight questions above has a recorded answer or an explicitly named default with an owner.
- [ ] DEC-044 lists the handoff surfaces that are out of scope under DEC-033.

## Technical Approach
Edit `solution/docs/decisions.md` only. Quote the handoff README sections ("About the design files", "Critical domain rules" 1–2, "Screens" V3/V4/V7) as the sources.

### Dependencies
- Blocks LEASH-181.
- Blocks LEASH-187.
- Blocks LEASH-191.

## Testing Requirements
No code. Check: `grep -n "DEC-044\|DEC-021" solution/docs/decisions.md` shows the new entry and the superseded status. `cd solution/app && npm test` is unaffected (still 113 passing).

## Related Files
- `solution/docs/decisions.md`
- `designPrototype/README.md`
- `solution/docs/customer-journey-for-design.md`

## Out of scope
- Writing code or tests.
- Editing the design handoff or the challenge pack.
- Changing other DEC entries beyond cross-references.
