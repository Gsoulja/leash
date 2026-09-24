# LEASH-066: Start a scenario run with mandate snapshot

**Status**: REVIEW
**Priority**: P0
**Type**: feature
**Estimated Effort**: S
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-005
**Task ID**: 005-T7
**Blocked by**: LEASH-061
**Blocks**: LEASH-128
**Updated**: 2026-09-24

## Description
Start a run at the API and store which mandate version it uses.

## Business Value
A run keeps the mandate it started with.

## Acceptance Criteria
- [x] Run stored with mandate_version.
- [x] Tightening after start doesn't change that run's snapshot.
- [x] Used by the end-to-end test, the app and the demo. *(End-to-end: done. App: a "Start a run" card on the Permission screen (2026-09-24). Demo: LEASH-112 starts runs through `POST /api/runs`.)*

## Technical Approach
Policy API route + repository.

### Dependencies
- Needs LEASH-061.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_run_keeps_starting_version`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/tests/adapters/test_runs.py`
- `solution/app/src/screens/Permission.tsx` (start-run card, added 2026-09-24 on the product owner's go-ahead to finish the MVP)
- `solution/app/src/screens/Permission.test.tsx`

## Out of scope
- Choosing scenarios automatically.

## Implementation note (2026-09-23)
- `policy_api.runs_router`, wired into the API process, provides the contract's `POST /api/runs`, `GET /api/runs` and `GET /api/runs/{run_id}`.
- Start:
  - The mandate must be known locally (404 `mandate_not_found`) and active (409 `mandate_not_active`).
  - The run is started at Viseca, then stored through the same `repository.ensure_run` the worker uses. The stored `mandate_version` is the local version with the platform snapshot's exact rules; if they differ, the platform's snapshot becomes a new version (authoritative, DEC-003) and an `INTEGRITY:` line is logged.
  - The card comes from the snapshot, or from the scenario's first pack purchase.
- Status and counters come from the platform (completed → finished; stopped/failed/cancelled/expired → failed). `current_run_id` is the newest run still running.
- Criterion 2: a later version (a tightening) never changes a stored run's `mandate_version`, so `StoredMandates` keeps giving that run its starting rules (tested).
- Criterion 3:
  - **End-to-end:** `tests/e2e/test_full_run.py::test_a_run_started_through_the_policy_api_is_decided_with_its_stored_snapshot` goes draft → submit → confirm → `POST /api/runs` → the worker decides every SCEN0004 purchase against that stored run.
  - **App:** its client gets a typed `startRun` (tested; 36 app tests). No ticket gives the app a start-run control yet, so the UI can't use it.
  - **Demo:** not built yet.
  - Both are flagged as open for the product owner.
- Tests: `tests/adapters/test_runs.py` (4, contract-validated) and the e2e test; 1200 pass.

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met — criterion 1: the run is stored with its version (contract-validated). A different platform snapshot becomes v2 plus an INTEGRITY line; concurrent starts create one v2. Caveat: a partial snapshot (no rules or policy) was stored as an empty v2, so re-checks for that run would see no rules.
- [x] met — criterion 2: nothing updates `runs` or `mandate_versions`; a later platform change only affects new runs.
- [ ] not met — criterion 3: end-to-end met. The app only has the client call, no UI; the demo isn't built. The box was ticked without evidence.
- Also found:
  - the worker storing the run first wins, which is fine;
  - with no snapshot, a later event with a different mandate was ignored silently;
  - the contract lacked the run endpoints' error responses.
Verdict: returned to in-progress.

### Fixes (2026-09-23)
- A platform snapshot is checked through the registry serializer before it counts. An unreadable or partial one is never stored: the version the customer confirmed is used and an INTEGRITY line is logged (test).
- `ensure_run` compares a later event's mandate with the run's stored snapshot and logs INTEGRITY when they differ. It never changes the stored one (test).
- The contract documents the errors of `POST /api/runs` and `GET /api/runs/{run_id}`; app types regenerated.
- Criterion 3 is unticked. Its app half needs a start-run control, which no ticket includes yet, so the product owner must place it; its demo half belongs to LEASH-112, which now notes to start runs through `POST /api/runs`.
- 1241 tests pass; registry re-pinned.

### 2026-09-23 — independent agent review, round 2
- [x] met — criterion 1: partial or unreadable snapshots are never stored. The confirmed version is used and INTEGRITY is logged; concurrent starts are consistent.
- [x] met — criterion 2: nothing changes a stored run's version; a later event with a different mandate is flagged only.
- [ ] not met, correctly unticked — criterion 3. The end-to-end part is met. The note on the app (client call only, no start-run control in any ticket) and the demo (LEASH-112, not built; noted there) is accurate.
- Worth knowing:
  - a platform snapshot with `hard_rules: []` is stored as an empty version (authoritative per DEC-003, INTEGRITY logged);
  - two concurrent first sightings can miss one INTEGRITY flag, but the snapshot never changes.
Verdict: stays in progress. **Needs the product owner:** place a start-run control in the app (no ticket has one) and confirm LEASH-112 covers the demo. Everything the engine side of this ticket owns is done.

### Fixes (2026-09-24) — app start-run control
- The product owner asked to finish the MVP, which settles the flag: the app gets a start-run control.
- Permission screen, new "Start a run" card, shown only for an active permission:
  - the customer types the scenario ID (no built-in scenario list; the platform decides which scenarios exist);
  - it calls the existing `startRun` client (`POST /api/runs`) with the active mandate;
  - it shows "Run <id> started with version <n> of your permission." or the engine's refusal message.
- Tests first (`Permission.test.tsx`): starts a run with the active permission; no control for a revoked permission; a refused start shows the engine's reason. 80 app tests pass, `tsc` clean.
- Checked against the running local stack through the Vite proxy: SCEN0000 started (RUN-ad5cbfe971, version 1); an unknown scenario returned the platform's `unknown_scenario` refusal.

### 2026-09-24 — independent agent review, round 3
- [x] met — criterion 1: accepted in round 2; unchanged this round.
- [x] met — criterion 2: accepted in round 2; the app also tells the customer the run keeps its version.
- [x] met — criterion 3: the Permission card calls `startRun` (`POST /api/runs`, matching the contract), shows the run and version or the engine's refusal, and holds no scenario IDs in production code. Mutations turn tests red (dropping `.trim()`; showing the card for a revoked permission). 80 app tests, `tsc` clean. Demo half: `demo/script.md` starts runs through `/api/runs`.
- [?] unverifiable by the reviewer — the live-stack run in the fix log (the reviewer was told not to start runs).
Verdict: all met; moved to review. The demo half rests on LEASH-112, which is still in review.

### Follow-up (2026-09-24, found during LEASH-133)
- The card's hint ("The run uses version 2 of this permission…") broke the browser journey's loose `getByText("Version 2")` check; the check is now exact. The journey now starts its later run through this card, and passes.
