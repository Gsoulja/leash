# LEASH-179: Align the customer app with the Hi-Fi v4 design handoff

**Status**: BACKLOG
**Priority**: P1
**Type**: epic
**Total Effort**: ~6–7 days (15 tickets: 7 S, 8 M)
**Milestone**: M8 — Great demo
**Rule source**: Design handoff `designPrototype/README.md` + `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html` (fidelity high, "single source of truth for behaviour and copy"), limited by DEC-033 (Leash is the permission layer, not the shopping agent) and the designer brief `solution/docs/customer-journey-for-design.md`. Conflicts with DEC-021 (Proposed, never Accepted), which ports the team's placeholder prototype `solution/prototype/index.html`.
**Decisions**: DEC-044 (to be written in LEASH-180), DEC-021, DEC-033, DEC-035, DEC-017, DEC-019, DEC-004, DEC-012
**Updated**: 2026-09-25

## Description
The customer app (`solution/app`) looks like the team's first-hour placeholder prototype: blue accent `#1463F3`, Figtree, generic cards and pills (`theme.css` line 1: "ported from solution/prototype/index.html (DEC-021)"). Four hours after that prototype, a real design handoff landed in `designPrototype/`: a dark-ink / semantic green-violet-red system (`#14151A`, `#2E7D45`, `#8A1FA8`, `#C0203A`, Inter + IBM Plex Mono), an "AI agent access" screen with a hard-stop tile, and a conversational chat with "Added to mandate" rule chips and a summary card that replaces the instruction form.

The handoff itself says it is **not production code**: do not port `support.js`, `<x-dc>`, `image-slot.js` or inline styles; recreate the designs with the real app's components; the host shell (home, card hero, transactions, settings rows, tab bar) is deliberately generic and is replaced by the real app's own screens. Only the "new surfaces" (V3 agent access, V4 chat, V5 transaction detail, V7 freeze sheet, the tokens, icons and logo) are to be recreated.

Part of the handoff is superseded by DEC-033 (logged after it): the agent searching verified shops, the search card, the paged product carousel with "Approve · CHF 189" buttons, the receipt card, and "every purchase requires approval" (rule 1). Leash's UI must not simulate the external agent's shopping, and the designer brief keeps "fits → proceed automatically". Those surfaces are out of scope for every ticket here.

**This is a presentation-layer migration of a working, tested app (baseline 2026-09-25: `npm test` → 12 files, 113 tests passing).** No ticket touches `solution/engine`, the policy API contract, `api/client.ts` call signatures, or the mandate/decision logic. Work is sequenced so that low-risk foundations (decision, tokens, type, icons, primitives) land before screen restyles, and screen restyles land before the one structural change (Agent form → chat), which is split in two so that the existing review/confirm logic is untouched while the transcript lands.

### Relation to LEASH-144 (demo experience overhaul)
LEASH-145 (conversational journey) and LEASH-146 (human-readable review) own the *behaviour* of the conversation: LLM-backed clarification (LEASH-101), draft revisions, context questions, Must follow / May choose / Must ask. This epic owns the *visual system and chat presentation* over today's API, so LEASH-145/146 can build on shared primitives instead of inventing their own. LEASH-180 asks the product owner to confirm this split; no graph edges into LEASH-144's tickets are added until then.

## Business Value
The demo is judged on whether the audience instantly sees the customer's control. The handoff's hard-stop tile, rule chips and single visual language make that legible; today's generic form and blue pills read as an admin tool.

## Sub-tasks
- [x] LEASH-180 (179-T1): Decision record — adopt the v4 handoff as the design source and rule on its scope · S · **DECISION gate**
- [x] LEASH-181 (179-T2): Handoff colour tokens behind the existing token names · M
- [ ] LEASH-182 (179-T3): Typography, amounts and focus ring from the handoff · S
- [ ] LEASH-183 (179-T4): Handoff icon set and the bracket-dot logo mark · S
- [ ] LEASH-184 (179-T5): Presentational primitives: buttons, tiles, badges and chips · M
- [ ] LEASH-185 (179-T6): Phone shell and tab bar in the handoff style · S
- [ ] LEASH-186 (179-T7): Cockpit restyle: spending card and payment list · M
- [ ] LEASH-187 (179-T8): Permission screen as "AI agent access" with the hard-stop tile · M
- [ ] LEASH-188 (179-T9): Revoke confirmation as the freeze bottom sheet · M
- [ ] LEASH-189 (179-T10): Chat primitives: bubbles, rule chip, system chip, typing, composer · M
- [ ] LEASH-190 (179-T11): Agent screen as a chat transcript over the existing draft flow · M
- [ ] LEASH-191 (179-T12): Chat-native summary card, confirmation and mandate bar · M
- [ ] LEASH-192 (179-T13): Step-up prompt in the handoff style · S
- [ ] LEASH-193 (179-T14): Payment detail in the handoff style · S
- [ ] LEASH-194 (179-T15): Redesign acceptance check and design-doc sync · S
- [ ] LEASH-198 (179-T16): Home screen from the handoff's V1 (greeting, card hero, quick actions) · M · added by DEC-045
- [ ] LEASH-199 (179-T17): Home shows the credit card and the "Try your new AI shopping agent" banner · S · added by DEC-046

Sequence (enforced by Blocked by / Blocks): T1 → T2 → T3, T4 → T5, T6 → screens (T7, T8 → T9, T13, T14) and chat (T10 → T11 → T12) → T15.

## Technical Approach
Presentation only, inside `solution/app/src`: `theme.css`, `components/`, `screens/*.tsx` markup and class names. Every leaf keeps the data flow (`useQuery` keys, `api()` calls, SSE invalidation, `sessionStorage` draft id) byte-for-byte equivalent. The engine inspector (`inspector/`, the `--page`/`--panel` token set and dark mode) is out of this epic.

### Dependencies
- Children point back here with `**Parent**: LEASH-179`.
- The epic closes when LEASH-180 through LEASH-194 are done.

## Testing Requirements
Each leaf names the existing test files it puts at risk. Every leaf keeps `cd solution/app && npm test` and `npm run typecheck` green; a test is updated (never deleted) only when an accessible name or copy change is part of the ticket, and the behavioural assertion it made is preserved. LEASH-194 runs `npm run test:e2e`.

## Related Files
- `designPrototype/README.md`, `designPrototype/Hi-Fi Prototype v4 In-App Chat.dc.html`, `designPrototype/Visual System.dc.html`, `designPrototype/Sticker Sheet.dc.html` (read-only references)
- `solution/app/src/theme.css`, `solution/app/src/theme.test.ts`
- `solution/app/src/components/`, `solution/app/src/screens/`
- `solution/docs/decisions.md`, `solution/docs/customer-journey-for-design.md`

## Out of scope
- Anything in `solution/engine` or `solution/contracts`; any API or mandate-semantics change.
- Superseded by DEC-033: agent product search, the search card, the product carousel and pagination, per-proposal "Approve · CHF" buttons, the receipt card, the "searching / N matches" banner states, and handoff rule 1 (no auto-approve).
- The handoff's generic host shell: card hero, quick actions, Cards/Profile tabs, card-settings rows.
- The freeze 4-step ordering and structured quarantine flags (engine behaviour; see LEASH-160/170 for shop-text flags).
- The V6 decision-log timeline (LEASH-148/150 own run activity and outcome stories).
- Porting `support.js`, `.dc.html`, `image-slot.js` or inline styles.

## Done when
Every sub-task is in `done/`.
