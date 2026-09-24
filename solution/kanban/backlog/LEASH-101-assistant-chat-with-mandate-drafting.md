# LEASH-101: Permission chat with evidenced drafts and revisions

**Status**: BACKLOG
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
- [ ] The LLM can converse, use the scoped context from LEASH-154 and propose candidate permission rules; unresolved product references become questions unless optional catalogue lookup resolves them for customer review.
- [ ] Every proposed rule uses a versioned field from the policy registry and is validated by the policy service.
- [ ] Unknown, ambiguous or unsupported model output becomes a customer clarification; it never becomes an active rule silently.
- [ ] The LLM cannot confirm, activate, tighten, revoke or directly persist a mandate; only the customer-facing policy workflow can do so.
- [ ] The LLM cannot evaluate an authorization, produce a final payment verdict, update counters or write to the decision log/outbox.
- [ ] The assistant has no tool or network path to the control-layer decision endpoint or database credentials.
- [ ] Confirmed mandates still pass through deterministic validation before the control layer can use them.
- [ ] Model failure, timeout or invalid structured output falls back to a safe clarification flow.
- [ ] Merchant, product and tool text is treated as untrusted data and cannot change the assistant's authority or system instructions.
- [ ] The selected model, prompt version, tool calls and resulting draft are auditable without storing hidden reasoning.
- [ ] A model-generated proposal can never loosen an already confirmed permission.
- [ ] Each proposed rule links to customer message/answer IDs and exact source excerpts, or is explicitly an unconfirmed suggestion; profile preferences and system defaults are never labelled customer instructions.
- [ ] Check the source conversation for omitted restrictions as well as validating proposed rules. Negation, corrections, quantities, currency, total-versus-per-item amounts, recurrence and uncertainty choices have explicit examples.
- [ ] An unenforceable request or unresolved reference such as “the monitor I chose” blocks readiness until clarified, replaced by an enforceable condition, or explicitly left for customer review; it is never represented as a verified guarantee.
- [ ] Customer corrections before activation create a new durable local draft revision, preserve the transcript and mark superseded proposals; this does not alter active mandate rules.
- [ ] Each draft revision retains the LEASH-154 context bundle and its source references for evidence (moved from LEASH-154 on 2026-09-24: retention needs the draft to carry customer/account/card scope and a revision identity, which that ticket could not add — `CreateDraftRequest` takes only `instruction`, and `policy_drafts` has no scope column or revision table). `ContextBundle.as_evidence()` is the shape to store.
- [ ] This layer supplies `build_context`'s inputs truthfully: `instruction` is the customer's own words only (it steers which questions are suggested, so agent or merchant text there would let untrusted text choose the questions), and each `ConfirmedPermission` carries the scope it was actually recorded for.
- [ ] If a submitted platform draft changes, create a new draft through the existing API; never mutate its frozen payload. Submission and confirmation check the reviewed revision and reject stale requests.
- [ ] Confirmation records the exact rules, uncertainty policy, local revision and returned mandate version. Later edits require a fresh review; the LLM cannot invoke confirmation.
- [ ] Missing, conflicting or truncated relevant context raises a visible clarification; model failure cannot activate a partially checked draft.

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
