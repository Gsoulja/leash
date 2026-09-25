# LEASH-147: Customer handoff to the external shopping agent

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T3
**Blocked by**: LEASH-145, LEASH-146, LEASH-102
**Blocks**: LEASH-148, LEASH-149, LEASH-153, LEASH-156
**Updated**: 2026-09-24

## Description
Offer the customer a handoff from confirmed permission to the external shopping agent. For the challenge, launch a curated Viseca simulator run and label it as a demonstration; Leash does not perform shopping.

## Business Value
After confirming permission, the customer expects the agent to begin work—not to visit Permission and type an engineering fixture ID.

## Acceptance Criteria
- [x] A confirmed permission leads to a prominent “Start shopping” action in Agent.
- [x] Demo scenarios are presented by human names and one-line outcomes, never `SCEN*` identifiers.
- [x] The recommended scenario is selected by default for the rehearsed demo.
- [x] Starting creates exactly one run and immediately shows its recorded ID/state in the activity experience.
- [x] Double taps cannot start duplicate runs.
- [x] A refused start appears as an actionable conversation message.
- [x] Permission remains focused on viewing, tightening and revoking boundaries.
- [x] Start uses the handoff and confirmed revision from LEASH-102; a permission correction requires reconfirmation before launch.
- [x] The action is a customer/backend action, never a permission-LLM tool. External-agent activity is shown only when recorded; a started simulator run is not proof of real merchant integration.

## Technical Approach
Add a typed scenario catalogue endpoint or build-time catalogue, then call the existing run API from the Agent state machine. Remove the run form from Permission.

### Dependencies
- Needs LEASH-145.
- Needs LEASH-146.
- Needs LEASH-102.
- Blocks LEASH-148.
- Blocks LEASH-149.
- Blocks LEASH-153.
- Blocks LEASH-156.

## Testing Requirements
Test curated selection, one-shot start, duplicate-click protection, rejected starts and the absence of raw scenario entry in customer UI.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/screens/Permission.tsx`
- `solution/app/src/api/client.ts`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Allowing customers to upload arbitrary scenario fixtures.

## What landed (2026-09-25)

Engine:
- `service.load_scenario_notes(data_dir, recommended_theme=DEMO_THEME)` reads our copy of the supplied
  `scenario_catalogue.csv` into `{scenario_id: {summary, recommended}}`. The summary is the catalogue's own
  `short_rationale`; `recommended` matches `control_theme`, so which demonstration to open with is a
  setting (`DEMO_THEME`, default `manipulated_agent`) and not a scenario ID in the code.
- `create_api` defaults `scenario_notes` from `LEASH_DATA_DIR`, exactly as it already does for
  `scenario_cards`, so nothing new has to be wired at any call site.
- `GET /api/scenarios` (in `runs_router`) merges the notes onto the platform's rows **by ID, never by
  name**. Every field the platform owns is passed through untouched; a scenario we hold no note for keeps
  the platform's fields alone. `test_scenarios_come_from_the_connected_platform` now asserts exactly that.
- Contract: `summary` and `recommended` on the scenario item, both optional.

App:
- The scenario `<select>` is gone. `Agent` offers a radio group, "Choose a demonstration": name, the
  one-line outcome, and the checkout count. No `SCEN*` string reaches the screen — pinned by a test that
  asserts the picker's text contains no "SCEN".
- The recommended demonstration is selected on load and its task put in the composer, but only while the
  customer has said nothing yet: once they type, the composer is theirs.
- `handOff()` replaces the inline start. A `starting` ref plus the `started` state make a double tap one
  handoff; the engine's `(mandate, scenario, version)` key (LEASH-102) is the other half. The card is
  `Start shopping`, and once started it shows the run as recorded — `Run RUN-7 · running` — before the app
  switches to the cockpit.
- A refused start stays a conversation message (the existing `message` bubble, `role="alert"`) and the
  action remains, so the customer can act on it. Pinned with a 409 followed by a successful retry.
- `Permission` lost its "Simulation controls" form, the `scenario` state, the scenarios query and the
  `onRunStarted` prop (and `App.tsx` stopped passing it). It reads, tightens and revokes; nothing else.
- Styles: `.task-choices`/`.task-choice` (44px tap targets) and a blue-bordered `.card.handoff`.

Criterion 9's two halves already had cover and keep it: the start is an app → engine call, and
`test_the_chat_route_cannot_start_a_run_or_answer_a_decision` (LEASH-102) pins that the chat's own route
cannot carry `/api/runs`. The handoff card says in the customer's words that a started run is not proof of
a real merchant integration.

**One thing to check by hand.** `e2e/journey.spec.ts` step 7 started the later run through the form this
ticket removed. It now starts it through the API, like step 2, with a comment saying where the UI path is
covered instead. The Playwright journey cannot run in this environment, so that edit is **unverified** —
and the file has at least one other pre-existing staleness (`"Review what Viseca will receive"` no longer
matches the button, which is `"Review permission"`). Worth one real run of that journey before the demo.

Checks: app 157 passed, `npm run build` green, `tsc --noEmit` clean; engine suite green apart from
`test_every_module_is_classified`, which another session's new `laya` modules own.
