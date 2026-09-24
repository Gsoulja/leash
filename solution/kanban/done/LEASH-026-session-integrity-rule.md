# LEASH-026: Session integrity rule

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M2 — All five scenarios offline
**Rule source**: Team
**Decisions**: DEC-024
**Parent**: LEASH-001
**Task ID**: 001-T17
**Blocked by**: LEASH-014, LEASH-015
**Blocks**: LEASH-033, LEASH-128
**Updated**: 2026-09-23

## Description
Score session signals (new device, attempts in 10 min, night-time in Zurich, first-time country) and warn at two or more points.

## Business Value
Session scenario: 02:14 burst on a new device, recovery afterwards.

## Acceptance Criteria
- [x] New device alone (2 points) warns; known device, normal pace passes.
- [x] Velocity uses the event's recent-attempt count; night uses Europe/Zurich local time.
- [x] After the burst, the usual device passes again.
- [x] Scored as registry field leash.session.risk_score.v1.

## Technical Approach
`domain/rules/session.py`. Points: new device 2, ≥2 recent attempts 2 (1 attempt 1), night 1, new country 2.

### Dependencies
- Needs LEASH-014.
- Needs LEASH-015.
- Blocks LEASH-033.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_new_device_asks`, `test_known_device_recovers`.

## Related Files
- `solution/engine/src/leash/domain/rules/session.py`
- `solution/engine/tests/domain/rules/test_session.py`

## Out of scope
- Device fingerprinting beyond the given device ID.

## Review log

### 2026-09-23 — independent agent review
- [x] met — new device alone (2) warns → step_up under ask; known device at normal pace passes; missing device ID scores 2; a device or country known only from a non-approved purchase still scores.
- [x] met — velocity from the event's recent-attempt count (0/1/2+ → 0/1/2); night is Zurich 00:00–05:59, checked across both DST changes.
- [x] met — after the burst the usual device passes (also replayed on SCEN0003 pack rows: burst 3–7 points, the usual device 0).
- [x] met — scored as leash.session.risk_score.v1 via `mandate.session_risk_limit`; points match the registry text and DEC-024.
Notes: plural in "At most 1 risk points" fixed after review (`test_agreed_wording`). If the customer approves the new device's first order, DEC-015 (Proposed) makes the device known for the rest of the run.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
