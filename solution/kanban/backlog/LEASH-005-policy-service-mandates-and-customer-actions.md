# LEASH-005: Policy service (mandates and customer actions)

**Status**: BACKLOG
**Priority**: P0
**Type**: epic
**Total Effort**: ~44 h (11 tickets; ~44 h in the MVP)
**Updated**: 2026-09-23

## Description
Turns the customer's instruction into rules, manages the mandate lifecycle with the Viseca API, and relays customer answers. Acts as the app's backend.

## Business Value
Covers the brief's 'customer controls permissions' and 'human approval, rejection or revocation' requirements.

## Reference
API contract: technical_details.md sections 5, 7, 8.

## Sub-tasks
- [ ] LEASH-060 (005-T1) [M1]: Mandate to API hard_rules serializer · M
- [ ] LEASH-061 (005-T2) [M4]: Mandate lifecycle endpoints · M
- [ ] LEASH-062 (005-T3) [M4]: Tighten and revoke endpoints · M
- [ ] LEASH-063 (005-T4) [M4]: Resolve endpoint for customer answers · S
- [ ] LEASH-064 (005-T5) [M4]: SSE stream of asks and decisions · M
- [ ] LEASH-065 (005-T6) [M4]: Instruction compiler v1 · L
- [ ] LEASH-066 (005-T7) [M4]: Start a scenario run with mandate snapshot · S
- [ ] LEASH-117 (005-T8) [M1]: Hard-rule field registry · M
- [ ] LEASH-118 (005-T9) [M0]: API contract for the policy service and event stream · M
- [ ] LEASH-123 (005-T10) [M4]: Policy clarification workflow · M
- [ ] LEASH-124 (005-T11) [M4]: Read model and query API · M

## Done when
Every sub-task is in `done/`.
