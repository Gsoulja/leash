# LEASH-101: Permission chat with evidenced drafts and revisions

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Engineering
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-008
**Task ID**: 008-T2
**Blocked by**: LEASH-065, LEASH-117, LEASH-123, LEASH-154
**Blocks**: LEASH-102, LEASH-145, LEASH-153, LEASH-156
**Updated**: 2026-09-24

## Description
Add an LLM-powered permission assistant that clarifies customer intent using relevant context and proposes an enforceable mandate draft for an external shopping agent. The assistant is an untrusted client of the policy service: it can write a candidate rule draft, but it has no authority over the control layer.

## Business Value
Deliver a natural permission conversation without allowing probabilistic model output to weaken or bypass financial controls.

## Acceptance Criteria
- [x] The LLM can converse, use the scoped context from LEASH-154 and propose candidate permission rules; unresolved product references become questions unless optional catalogue lookup resolves them for customer review.
- [x] Every proposed rule uses a versioned field from the policy registry and is validated by the policy service.
- [x] Unknown, ambiguous or unsupported model output becomes a customer clarification; it never becomes an active rule silently.
- [x] The LLM cannot confirm, activate, tighten, revoke or directly persist a mandate; only the customer-facing policy workflow can do so.
- [x] The LLM cannot evaluate an authorization, produce a final payment verdict, update counters or write to the decision log/outbox.
- [x] The assistant has no tool or network path to the control-layer decision endpoint or database credentials.
- [x] Confirmed mandates still pass through deterministic validation before the control layer can use them.
- [x] Model failure, timeout or invalid structured output falls back to a safe clarification flow.
- [x] Merchant, product and tool text is treated as untrusted data and cannot change the assistant's authority or system instructions.
- [x] The selected model, prompt version, tool calls and resulting draft are auditable without storing hidden reasoning.
- [x] A model-generated proposal can never loosen an already confirmed permission.
- [x] Each proposed rule links to customer message/answer IDs and exact source excerpts, or is explicitly an unconfirmed suggestion; profile preferences and system defaults are never labelled customer instructions.
- [x] Check the source conversation for omitted restrictions as well as validating proposed rules. Negation, corrections, quantities, currency, total-versus-per-item amounts, recurrence and uncertainty choices have explicit examples.
- [x] An unenforceable request or unresolved reference such as “the monitor I chose” blocks readiness until clarified, replaced by an enforceable condition, or explicitly left for customer review; it is never represented as a verified guarantee.
- [x] Customer corrections before activation create a new durable local draft revision, preserve the transcript and mark superseded proposals; this does not alter active mandate rules.
- [x] Each draft revision retains the LEASH-154 context bundle and its source references for evidence (moved from LEASH-154 on 2026-09-24: retention needs the draft to carry customer/account/card scope and a revision identity, which that ticket could not add — `CreateDraftRequest` takes only `instruction`, and `policy_drafts` has no scope column or revision table). `ContextBundle.as_evidence()` is the shape to store.
- [x] This layer supplies `build_context`'s inputs truthfully: `instruction` is the customer's own words only (it steers which questions are suggested, so agent or merchant text there would let untrusted text choose the questions), and each `ConfirmedPermission` carries the scope it was actually recorded for.
- [x] If a submitted platform draft changes, create a new draft through the existing API; never mutate its frozen payload. Submission and confirmation check the reviewed revision and reject stale requests.
- [x] Confirmation records the exact rules, uncertainty policy, local revision and returned mandate version. Later edits require a fresh review; the LLM cannot invoke confirmation.
- [x] Missing, conflicting or truncated relevant context raises a visible clarification; model failure cannot activate a partially checked draft.

## Technical Approach
Implement the LLM behind an `AssistantModel` port in `assistant/agent.py`. Give it read-only scoped context and a candidate-draft tool only. Catalogue reference lookup is optional (LEASH-100). Parse structured output into candidate rules, then send those candidates through the existing policy registry/compiler validation. Keep assistant credentials separate from the decision engine. Extend the existing policy service for durable revision checks and provenance; reuse registry validation and exact platform draft submission. A supported field proves enforceability, not fidelity to intent. No Laya dependency is required for this baseline.

### Dependencies
- Needs LEASH-065.
- Needs LEASH-117.
- Needs LEASH-123.
- Needs LEASH-154.
- Blocks LEASH-102.
- Blocks LEASH-145.
- Blocks LEASH-153.
- Blocks LEASH-156.

## Testing Requirements
Add regression cases for invented and omitted restrictions, profile suggestions without consent, conflicting answers, unknown selected product, stale review/confirm requests, and a submitted draft corrected before activation. Run the policy/application/API tests plus `python -m pytest solution/assistant/tests` in the configured environment.

Write first: `test_assistant_cannot_confirm_mandate`, `test_assistant_has_no_decision_tool`, `test_unknown_rule_becomes_question`, `test_prompt_injection_cannot_change_authority`, `test_model_failure_falls_back_safely`, and `test_model_cannot_loosen_confirmed_permission`. Add a contract test proving the assistant can create only a draft and that the deterministic control layer produces the final verdict independently.

## Related Files
- `solution/assistant/agent.py`
- `solution/assistant/tests/test_agent.py`
- `solution/engine/src/leash/policy/compiler.py`
- `solution/engine/src/leash/domain/`
- `solution/contracts/policy-api.yaml`
- `solution/engine/src/leash/application/clarify.py`
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/tests/application/test_clarify.py`
- `solution/engine/tests/adapters/test_policy_api.py`
- `solution/engine/migrations/`

## Out of scope
- Shopping search, recommendations or order execution.
- Removing or widening restrictions on an active mandate.
- Trip planning.
- Generated product images.
- Giving the LLM any authority in authorization decisions or control-layer state.
- Exposing chain-of-thought or relying on it as decision evidence.

## Review log

### 2026-09-24 — independent agent review (round 1)
11 of 20 met. Verified the central safety claim structurally and could not find a hole: `agent.py`
imports only `leash.domain.mandate`, `leash.policy.registry` and `leash.policy.compiler` (all pure);
`PermissionAssistant` can emit only a frozen `Proposal`. The LOCK re-pin was verified by
reproduction — removing migration 0007 returned all 13 fingerprints to their previous values.

Real defects found, all since **fixed**:
- **Provenance was a bare substring test.** Reproduced: the customer says "Spend at most CHF 50 per
  order", the model returns `billing_amount_chf <= 500` quoting `says="50"` — accepted as traced,
  `status="ready"`, no question. Model output could pose as the customer's words and inflate a
  limit. Fixed: excerpts now match on token boundaries, and the rule's own value must be evidenced
  in the quoted words (`_value_is_evidenced`). Item IDs are exempt — they come from a recorded
  catalogue lookup, not the customer's typing.
- **An invented item ID passed for a resolved one.** `IT9999999` short-circuited the catalogue on
  `startswith("IT")`, recorded no tool call, and reached `status="ready"`. Fixed: an item ID must
  exist in the catalogue.
- **The retention column was unreachable.** `create_draft` rejected any body but `{"instruction"}`,
  so `body.get("context")` was dead code and every revision stored `{}`. Fixed and tested end to
  end, including that a correction keeps the background it was drafted against.
- **`truncated` was a key no bundle produced.** `ContextBundle` capped entries silently. Fixed in
  `permission_context.py`: the bundle now reports truncation and `as_evidence()` carries it.
- **A malformed revision silently skipped the staleness check** (`"1"` or `1.0` read as absent).
  Fixed: a stated revision that is not a whole number ≥ 1 is a 422.
- **The migration backfill returned schema-invalid drafts.** `PolicyDraft` now requires `revision`,
  but pre-0007 rows had no such key inside their stored JSON. Fixed: the backfill stamps them.
- **AC13 had no "corrections" example**, and the cross-check compared only field and period, never
  value or operator. Both fixed.

### Still open — the assistant has no caller
ACs 1, 2 and 17 are unticked for one reason: nothing imports `assistant.agent` except its own tests.
There is no producer for its `context` argument, no path from a proposed rule to the policy
service's validation, and nothing constructs a `ConfirmedPermission`. The component and the engine
half are both tested, but they share no test and are not joined.

Wiring them needs a decision this ticket cannot make on its own: **which model, reached how**.
CLAUDE.md records model choice as still open, and no LLM is configured in this environment. The
assistant is deliberately built behind an `AssistantModel` port so that decision can be made later
without touching the safety logic.

Verification at this point: 1457 engine tests, 38 assistant tests, `mypy` clean on 66 files.

### 2026-09-24 — round 2: the assistant now has a caller

`solution/assistant/conversation.py` joins the three halves that round 1 found unconnected. It is a
separate module from `agent.py` on purpose: `agent.py` has a structural test pinning its exact import
set, and widening that allowlist to reach `permission_context` would have weakened the ticket's
strongest safety check. `conversation.py` carries the same structural test of its own.

- `customer_words()` is the only producer of `build_context`'s `instruction`, and it filters by
  speaker, so agent or merchant text cannot choose the suggested questions (AC17). No customer words
  at all is a `ValueError`, never an empty bundle.
- `scoped_permissions()` turns stored confirmations into background, each keeping the scope it was
  actually recorded for; a record that does not name a customer, or names another dataset, is dropped
  rather than widened (AC17).
- `PermissionConversation.clarify()` builds the bundle, hands it to the model as data, then sends the
  customer's own words and that bundle to the policy service (`POST /api/policies/drafts`). A
  candidate the deterministic compiler did not itself derive from the same words becomes an
  unconfirmed suggestion, never a rule (AC2); the policy service's own blocking questions are merged
  into the clarification.

### 2026-09-24 — independent agent review (round 2)

AC2 `met`, AC17 `met`, AC1 **`not met`** — all three now fixed and re-tested.

- **AC1 gap (fixed).** `clarify` passed `catalogue=self._catalogue or ()`, which turned an absent
  catalogue into an empty tuple. `agent._resolve_item` branches on `catalogue is None` to ask "which
  exact product do you mean?", so the `()` sentinel skipped that branch and reached
  `().search(...)` — `AttributeError` instead of a question, for any `items.item_id` candidate.
  Reproduced by the reviewer, now passed straight through and pinned by
  `test_without_a_catalogue_a_product_reference_is_asked_not_crashed` (verified failing before the fix).
- **AC17 was right but untested.** The reviewer's mutation — widening every stored confirmation to the
  whole customer — left all 53 tests green. Three tests added: a record naming a card keeps that card
  and does not cover another, an account-scoped record does cover its cards, and an unreadable
  `confirmed_at` is dropped (it used to crash `build_context` with `'str' object has no attribute 'at'`).
- **One false negative fixed.** `_values` compared a set-operator value written as a bare string
  against the compiler's one-element tuple and found them different, so `item_category in "electronics"`
  became a needless question. The engine reads both identically; it now compares as a set either way.

Verified by the reviewer against the **real** endpoint, not the stub: a `PolicyService` implemented
with `TestClient` and real Postgres returned 201 and a `hard_rules` shape `_derived` reads correctly
(integer values, `currency: "CHF"`, `scope: "purchase"`), and `draft_revisions.context` came back with
the conversation's card scope — no API change needed. Mutation testing: ignoring the policy service
fails 2 tests, dropping the speaker filter fails 3, forwarding non-blocking questions fails 1.

Verification after round 2: 58 assistant tests, 1474 engine tests, `mypy` clean.
