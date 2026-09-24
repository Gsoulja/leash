# LEASH-101: AI shop chat with safe mandate drafting

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-008
**Task ID**: 008-T2
**Blocked by**: LEASH-100, LEASH-065
**Blocks**: LEASH-102, LEASH-145, LEASH-153
**Updated**: 2026-09-24

## Description
Add an LLM-powered shopping assistant that can converse, search the catalogue, explain choices and propose a mandate draft. The assistant is an untrusted client of the policy service: it can write a candidate rule draft, but it has no authority over the control layer.

## Business Value
Deliver a natural chat and shopping experience without allowing probabilistic model output to weaken or bypass financial controls.

## Acceptance Criteria
- [ ] The LLM can converse, search approved catalogue data and propose candidate permission rules.
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

## Technical Approach
Implement the LLM behind an `AssistantModel` port in `assistant/agent.py`. Give it an allow-listed catalogue-search tool and a policy-draft tool only. Parse structured output into candidate rules, then send those candidates through the existing policy registry/compiler validation. Keep the assistant process and credentials separate from the decision engine.

### Dependencies
- Needs LEASH-100.
- Needs LEASH-065.
- Blocks LEASH-102.
- Blocks LEASH-145.
- Blocks LEASH-153.

## Testing Requirements
Write first: `test_assistant_cannot_confirm_mandate`, `test_assistant_has_no_decision_tool`, `test_unknown_rule_becomes_question`, `test_prompt_injection_cannot_change_authority`, `test_model_failure_falls_back_safely`, and `test_model_cannot_loosen_confirmed_permission`. Add a contract test proving the assistant can create only a draft and that the deterministic control layer produces the final verdict independently.

## Related Files
- `solution/assistant/agent.py`
- `solution/assistant/tests/test_agent.py`
- `solution/engine/src/leash/policy/compiler.py`
- `solution/engine/src/leash/domain/`
- `solution/contracts/policy-api.yaml`

## Out of scope
- Trip planning.
- Generated product images.
- Giving the LLM any authority in authorization decisions or control-layer state.
- Exposing chain-of-thought or relying on it as decision evidence.
