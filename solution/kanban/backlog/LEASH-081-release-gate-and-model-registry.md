# LEASH-081: Release gate and model registry

**Status**: BACKLOG
**Priority**: P2
**Type**: feature
**Estimated Effort**: M
**Milestone**: M6 — Differentiators (after MVP)
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-006
**Task ID**: 006-T12
**Blocked by**: LEASH-076, LEASH-078
**Blocks**: LEASH-082
**Gate**: DECISION — a human reads the gate report and decides whether the release goes to shadow mode.
**Updated**: 2026-09-23

## Description
Evaluate a candidate against the gate (pack must-pass, recall ≥ 0.95 at ≤ 1% false flags, NotInject ≤ 5%, ECE ≤ 0.05, beats regex, latency) and register passing releases.

## Business Value
No model reaches the engine unless it is better than regex.

## Acceptance Criteria
- [ ] Gate report JSON with each check pass/fail.
- [ ] Passing release stored with weights, question-bank hash, temperatures, dataset version.
- [ ] Latency: p95 ≤ 50 ms for all five questions on GPU, and the whole reader call ≤ 1 s including fallback.

## Technical Approach
`training/gate.py`, `model_releases` table.

### Dependencies
- Needs LEASH-076.
- Needs LEASH-078.
- Blocks LEASH-082.

## Testing Requirements
Run `uv run python -m training.gate <checkpoint>`.

## Related Files
- `solution/training/gate.py`

## Out of scope
- Automatic promotion.
