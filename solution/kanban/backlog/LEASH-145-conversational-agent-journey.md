# LEASH-145: Conversational Agent journey

**Status**: BACKLOG
**Priority**: P0
**Type**: feature
**Estimated Effort**: L
**Milestone**: M8 — Great demo
**Rule source**: Product
**Decisions**: DEC-033, DEC-034, DEC-035, DEC-036, DEC-037
**Parent**: LEASH-144
**Task ID**: 144-T1
**Blocked by**: LEASH-101
**Blocks**: LEASH-146, LEASH-147, LEASH-148, LEASH-152, LEASH-153
**Updated**: 2026-09-24

## Description
Replace the instruction form and rule dump with a persistent, message-based conversation that guides the customer from intent to confirmed permission.

## Business Value
The product must feel like an agent that understands, clarifies and reports—not a policy administration screen.

## Acceptance Criteria
- [ ] The empty state opens with a short agent greeting and a single composer.
- [ ] Customer instructions and agent responses render as distinguishable messages in chronological order.
- [ ] The agent acknowledges the goal in plain language before showing proposed boundaries.
- [ ] Clarifications appear one at a time in the conversation with quick replies and optional free text.
- [ ] Answered questions remain visible as part of the transcript.
- [ ] Loading, retry and refusal states appear as messages at the point where they occurred.
- [ ] Reload and tab changes preserve the conversation without duplicating messages.
- [ ] The transcript never claims work that the backend has not recorded.
- [ ] Messages distinguish Leash’s permission assistant from the external shopping agent; Leash never claims to search or purchase on its own.
- [ ] Context-based questions disclose their source as a preference or observation, permit disagreement, and do not imply prior customer approval.
- [ ] Corrections show the superseded and current draft revisions; reload preserves the latest revision and cannot restore a stale confirmation action.

## Technical Approach
Model the UI as explicit conversation states derived from the policy draft, its questions and mutation results. Keep the draft ID durable, but render semantic message components rather than raw API structures.

### Dependencies
- Needs LEASH-101.
- Blocks LEASH-146.
- Blocks LEASH-147.
- Blocks LEASH-148.
- Blocks LEASH-152.
- Blocks LEASH-153.

## Testing Requirements
Include background preference accepted/rejected, an explicit current-request override, a draft correction and stale-tab review recovery.

Write component tests for the empty, compiling, clarification, error, ready and reloaded states. Add a browser test that completes a clarification without leaving the conversation.

## Related Files
- `solution/app/src/screens/Agent.tsx`
- `solution/app/src/theme.css`
- `solution/app/src/api/client.ts`

## Out of scope
- General-purpose open-domain chat.
