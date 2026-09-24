# LEASH-144: Demo experience overhaul

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: none
**Blocked by**: LEASH-101
**Blocks**: none
**Updated**: 2026-09-24

## Description
Turn the customer app from a policy form into a convincing agent experience: a natural conversation, visible work, clear interventions, truthful results and presenter-controlled pacing.

## Business Value
Judges must understand within seconds what the agent is doing, how Leash constrains it, when the customer intervenes and why the final outcome is trustworthy.

## Acceptance Criteria
- [ ] The customer journey reads as a conversation rather than a configuration form.
- [ ] A running agent has visible progress, activity and completion states.
- [ ] The presenter can run a deterministic scenario without typing internal identifiers.
- [ ] Customer-facing screens hide implementation jargon by default.
- [ ] A timed rehearsal passes the demo-readiness gate.

## Sub-tasks
- LEASH-145 — Build the conversational Agent journey.
- LEASH-146 — Replace the technical permission dump with a human review.
- LEASH-147 — Let the Agent launch curated shopping runs.
- LEASH-148 — Show a live run activity timeline.
- LEASH-149 — Add presenter demo controls.
- LEASH-150 — Tell the completed-run outcome story.
- LEASH-151 — Make demo reset and frontend delivery deterministic.
- LEASH-152 — Add projector and narrow-screen presentation modes.
- LEASH-153 — Pass the great-demo readiness gate.

## Technical Approach
Keep domain decisions and platform state authoritative. Build a customer-facing narrative projection and a separate presenter-only orchestration surface around the existing run, payment and event APIs.

### Dependencies
- Needs LEASH-101 for the LLM-backed shopping conversation and safe draft proposal boundary.
- The epic closes when LEASH-145 through LEASH-153 are done.

## Testing Requirements
Each leaf ticket supplies component, integration or browser evidence. LEASH-153 rehearses the complete story.

## Related Files
- `solution/app/src/App.tsx`
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/screens/Cockpit.tsx`
- `solution/prototype/index.html`

## Out of scope
- Changing the deterministic authorization rules to make the demo easier.
