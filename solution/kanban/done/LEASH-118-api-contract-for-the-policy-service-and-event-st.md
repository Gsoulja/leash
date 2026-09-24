# LEASH-118: API contract for the policy service and event stream

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M0 — Business and contract baseline
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-005
**Task ID**: 005-T9
**Blocked by**: none
**Blocks**: LEASH-061, LEASH-090, LEASH-091, LEASH-092, LEASH-093, LEASH-123, LEASH-124, LEASH-128
**Updated**: 2026-09-23

## Description
Contract-first definition of the policy service API (drafts, clarifications, confirm, tighten, revoke, resolve, runs, read model) and the SSE event format, with example payloads and mocks the app can use before the backend exists.

## Business Value
Lets frontend and backend work in parallel against one agreed contract.

## Acceptance Criteria
- [x] OpenAPI document covers every endpoint the app uses.
- [x] SSE event types and payloads are specified with examples.
- [x] A mock server serves the examples for the app.

## Technical Approach
`solution/contracts/policy-api.yaml`, `solution/contracts/events.md`, mock via a small FastAPI app.

### Dependencies
- None.
- Blocks LEASH-061.
- Blocks LEASH-090.
- Blocks LEASH-091.
- Blocks LEASH-092.
- Blocks LEASH-093.
- Blocks LEASH-123.
- Blocks LEASH-124.
- Blocks LEASH-128.

## Testing Requirements
Write first: a test that every example payload validates against the OpenAPI schema.

## Related Files
- `solution/contracts/policy-api.yaml`
- `solution/contracts/events.md`
- `solution/engine/tests/contracts/test_examples_validate.py`

## Out of scope
- Implementation of the endpoints.

## Review log

### 2026-09-23 — independent agent review (round 1)
- [ ] not met — criterion 1: no way to express the cockpit's "not sent" state (`sent_to_viseca` not nullable, `blocked` ambiguous); no endpoint to find the current mandate/run or list mandate versions after reconnecting; no GET for a local draft.
- [x] met — criterion 2: five event types documented with examples, wire format and Last-Event-ID resume; noted weakness: `StreamEvent.data` payloads were not schema-checked.
- [x] met — criterion 3: mock serves the first success example of every operation and streams the documented events (probed on a local port).
Verdict: returned to in-progress. Fixes: `final_state` now approved/waiting/declined/timed_out/not_sent with a not-sent example and nullable `sent_to_viseca`; added GET /api/mandates, /api/mandates/{id}/versions, /api/runs, /api/policies/drafts/{id}; per-type event payload schemas (AskCreatedData … IntegrityAlertData) enforced via if/then; tests extended (78 pass).

### 2026-09-23 — independent agent review (round 2)
- [x] met — criterion 1: 20 operations cover LEASH-092/093/094/095/096/123/124, including not_sent, current mandate/run, mandate versions and draft reload.
- [x] met — criterion 2: five event types with examples; per-type data schemas enforced; wrong payloads rejected.
- [x] met — criterion 3: mock serves every operation and streams the documented events (probed on a local port).
- Minor follow-ups fixed after review: getMandate/listMandates example versions now agree; the SSE sample in the spec is a complete valid event (new test). Not addressed: the mock ignores Last-Event-ID (acceptable for a mock).
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
