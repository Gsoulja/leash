# LEASH-175: Serve the permission assistant

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M8 — Great demo
**Rule source**: Engineering (gap found 2026-09-25)
**Decisions**: DEC-033, DEC-034, DEC-036, DEC-044, DEC-045, DEC-047, DEC-048
**Pattern**: Hexagonal shell — the assistant is an untrusted client of the policy service, never a router inside the engine
**Parent**: LEASH-008
**Task ID**: 008-T9
**Blocked by**: LEASH-101
**Blocks**: LEASH-145, LEASH-146
**Updated**: 2026-09-25

## Description
The permission assistant has no serving path. `service.py` wires six routers and none of them is the
assistant; no module under `engine/src` imports `PermissionConversation`, `PermissionAssistant` or
`ApertusModel`; and the app's `client.ts` posts `createDraft(instruction)` — the customer's words and
nothing else — straight to `POST /api/policies/drafts`.

So the chat today talks to the deterministic compiler, which reads no German, French or Italian and
refuses most ordinary phrasing. Steps 2 to 5 of the agreed journey (the LLM proposing rules, background
clarifying intent, preferences suggesting questions, the proposal being checked) exist as a tested
library that nothing calls.

This ticket gives that library an HTTP surface and points the chat at it. It adds no authority: the
assistant stays a client of the policy service, which validates every rule against the registry and
appends it (DEC-045), and only the customer's confirmation activates anything.

## Business Value
Without it the demo's opening move — "tell Leash what you want, in your own words" — is a regex parser.
It is the single missing link between a built chat screen and a built assistant.

## Acceptance Criteria
- [x] An HTTP surface runs `PermissionConversation`: customer turns in; a draft, its open questions and
      its consent sentences out.
- [x] It builds the context bundle (LEASH-154) itself; the app never supplies background, so a client
      cannot inject one.
- [x] Validated rules are posted to `POST /api/policies/drafts` in the `rules` field (DEC-045), and the
      returned draft is what the client sees — the assistant never invents a draft of its own.
- [x] Corroboration is read from `independently_read`, never from `hard_rules` (which contains our own
      proposal echoed back).
- [x] The model being unavailable is a visible, retryable failure (`503` with the failure code), never
      silence and never an empty draft that looks like "no restrictions" — nothing is written to the
      policy service (DEC-047; edge case: endpoint timeout, malformed reply).
- [x] `APERTUS_API_KEY` is read only here; the process holds no database credential and no path to the
      decision endpoint. LEASH-101's isolation criteria still hold, with a test that proves it.
- [x] Shop names and profile text reaching the model stay inside delimited data blocks (LEASH-171 applies
      to this surface once it exists).
- [x] The app's chat calls this surface instead of `POST /api/policies/drafts` directly.
- [x] A contract file describes it, written in the same change as the code — two schema updates have
      already landed late because the contract is a separate file.
- [ ] A German instruction typed into the running app produces an enforceable rule end to end.
      **Unverified.** The service test stubs the model and hands it the finished rule; the Playwright
      journey runs `LEASH_ASSISTANT_MODEL: "offline"`, the compiler DEC-045 measured as reading no
      German. Needs a run against real Apertus. Carried to the human gate.

## Technical Approach
A separate FastAPI app (its own process and its own contract), not a router inside `leash.service`: the
engine imports nothing from `solution/assistant/` today and must keep it that way, so the dependency
points one way only. It calls the policy service over HTTP through the existing `PolicyService` port.

### Dependencies
- Needs LEASH-101 (the library and its isolation guarantees).
- Blocks LEASH-145: its last open criterion — context questions disclosing their source — is implemented
  in `conversation.py` and cannot reach the customer until this exists.
- Blocks LEASH-146: the review has nothing to review until drafts carry what the model read.

## Testing Requirements
Write first: `test_turns_become_a_draft_through_the_policy_service`,
`test_the_context_bundle_is_built_here_and_never_taken_from_the_client`,
`test_a_model_failure_is_retryable_and_does_not_write_a_clarification_draft` (DEC-047),
`test_the_surface_holds_no_database_credential_or_decision_path`,
`test_a_german_instruction_produces_an_enforceable_rule`.
Run `cd solution/engine && uv run pytest ../assistant/tests -q`, then the full engine suite.

## Related Files
- `solution/assistant/` (new HTTP surface and its tests)
- `solution/contracts/` (new contract file)
- `solution/app/src/api/client.ts`
- `solution/app/src/screens/Agent.tsx`

## Out of scope
- The review screen itself (LEASH-146).
- Omission checking (LEASH-155).
- Any change to the decision path, the rules or the checkout.
- Authenticated customer consent, which stays with LEASH-140/143 (DEC-019).

## Review log

### 2026-09-25 — independent agent review
- [x] met — 1: `service.py:176-199` runs `PermissionConversation` per request and returns draft, questions, consent_text; consent text is generated from `Rule` objects, never model prose.
- [x] met — 2: `_text()` rejects every body key but `text` with 422; the bundle is built from the process-configured card. Pinned by `test_service.py:89` and `:100`.
- [x] met — 3: rules posted in the `rules` field; the returned draft is passed through verbatim (`test_service.py:189`).
- [x] met — 4: `_derived()` reads `independently_read`; `test_agent.py:794` pins that a `hard_rules` echo is not corroboration. Caveat recorded: the fallback to `hard_rules` is silent, so a service that stopped emitting the field would re-introduce self-corroboration with no test failing.
- [x] met — 5: originally reported **not met** (503 where the criterion said "questions"). Resolved by decision, not by code: DEC-047 records the 503 as the intended behaviour, and this criterion, LEASH-101's matching criterion and the named test were corrected to match.
- [x] met — 6: `APERTUS_API_KEY` appears only in `apertus.py`; AST tests ban the decide path, postgres adapter and drivers; compose blanks `DATABASE_URL` and `TEAM_API_KEY`.
- [x] met — 7: context and catalogue go to the model JSON-encoded inside labelled data blocks in the user role; `test_apertus.py:88` proves a hostile context string stays out of the system role. Canonicalisation and per-value marking remain LEASH-171's.
- [x] met — 8: `client.ts` routes `createDraft`/`addTurn`/`chatTurn` to `/api/permission/*`; no caller posts `/api/policies/drafts` any more.
- [x] met — 9: `contracts/assistant-api.yaml` landed with the code and is checked by the same suite — served paths must equal documented paths.
- [ ] unverifiable — 10: no artifact shows German through a real model to an enforced verdict.

Outside the criteria, recorded rather than fixed here: DEC-045's value-carrying quote gate was narrowed to numeric fields; logged as DEC-048.

Checks: `uv run pytest ../assistant/tests -q` 120 passed · full engine suite 1666 passed · app `vitest run` 137 passed (13 files).

Verdict: nine of ten criteria met, criterion 10 unverifiable and carried to the human gate.
