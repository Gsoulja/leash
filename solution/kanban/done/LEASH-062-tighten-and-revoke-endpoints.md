# LEASH-062: Tighten and revoke endpoints

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M4 — Customer-control journey
**Rule source**: Engineering
**Decisions**: DEC-006
**Parent**: LEASH-005
**Task ID**: 005-T3
**Blocked by**: LEASH-061
**Blocks**: LEASH-096, LEASH-128
**Updated**: 2026-09-23

## Description
PATCH to tighten (lower limits, add rules, uncertainty to decline) and DELETE to revoke, refusing anything that loosens.

## Business Value
The customer can tighten or revoke at any time.

## Acceptance Criteria
- [x] Loosening returns 422 with an explanation.
- [x] Tighten creates a new mandate version and PATCHes the API.
- [x] Revoke calls DELETE and marks the mandate revoked locally.
- [x] PATCH sends every existing rule unchanged plus the new stricter rules.

## Technical Approach
Extends the policy API; domain checks in CompiledMandate.

### Dependencies
- Needs LEASH-061.
- Blocks LEASH-096.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_raising_limit_is_refused`.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/tests/adapters/test_tighten_revoke.py`

## Out of scope
- Loosening (requires a new mandate).

## Implementation note (2026-09-23)
- `policy_api.mandate_changes_router`, wired into the API process.
- `POST /api/mandates/{id}/tighten` (contract TightenRequest):
  - The current version is compiled from its stored hard_rules. Each new rule goes through `CompiledMandate.tighten` on its own, so a looser rule can't hide next to a stricter one. A duplicate, a rule that changes nothing, `uncertainty_policy` other than `decline`, or decline when already declining all return 422 `would_loosen`, with an explanation that loosening needs a new permission.
  - The PATCH body is every existing rule unchanged plus the new ones, checked with `hard_rules.check_append_only`.
  - Version n+1 is stored only after Viseca accepts; its rule views mark the new rules `tightened: true`.
  - It runs on one connection with the mandate row locked, so two tightenings serialise.
  - Errors: 404 `mandate_not_found`, 409 `mandate_not_active` / `platform_refused`, 502 `platform_error`, 422 `invalid_rule` / `invalid_request`.
- `DELETE /api/mandates/{id}`:
  - DELETE at Viseca, then the mandate is marked `revoked` locally. It is idempotent; an already revoked mandate is not sent to Viseca again.
  - If Viseca answers 404/409 (not active there), it is revoked here too. If Viseca is unreachable, 502 and it stays active, so the record stays truthful.
- Runs keep their snapshot (LEASH-066): a tightening is a new version and never changes a started run.
- `registry.describe_field` gives plain words for tightened rules.
- The contract documents the error responses of tighten, revoke and the run endpoints; app types regenerated (36 app tests pass).
- Tests: `tests/adapters/test_tighten_revoke.py` (7, contract-validated); 1217 pass.

## Review log

### 2026-09-23 — independent agent review, round 1
- [x] met — criterion 1: no probe loosened the mandate. Refused: a higher limit, a looser rule next to a stricter one, duplicates, "="/"in" supersets, weaker `prior_purchases`/`max_count`/`unrequested_count`, and a policy other than moving to decline.
- [x] met on the main path — criterion 2: concurrent tightenings serialise. Gap: when Viseca applied the PATCH but the reply was lost, we returned 502 and kept the old version, and every later tighten was refused.
- [x] met — criterion 3: idempotent revoke; 404/409 from Viseca still revoke here; unreachable → 502 and still active. Revoking mid-run leaves queued purchases as DEC-017 (Proposed) says.
- [x] met — criterion 4: the body is the stored rules plus the new ones, guarded by `check_append_only`.
- Findings:
  - `{"uncertainty_policy": null}` and `{"add_hard_rules": null}` were accepted as empty changes (new versions);
  - rules that change nothing in practice (e.g. `not_in ["zzz-never"]`) are accepted. They never loosen, but the note said such rules are refused.
Verdict: returned to in-progress.

### Fixes (2026-09-23)
- Explicit `null` is refused (422), like any value other than a non-empty rule list or `decline`.
- A lost PATCH reply is read back with `GET /v1/mandates/{id}`. If Viseca holds exactly the rules and policy we sent, the version is stored (200) and we stay in step; otherwise 502 and nothing is stored.
- Tests: an empty change is refused; a lost reply after the change applied is stored and a later tighten still works; a lost reply that didn't apply stores nothing.
- Note corrected: a new rule must change the mandate's effective reading (`CompiledMandate._snapshot`). One that changes nothing in practice (e.g. excluding a category that doesn't exist) is accepted as harmless: it can only make verdicts equal or stricter.
- 1241 tests pass.

### 2026-09-23 — independent agent review, round 2
- [x] met — criteria 1–4. Round-1 fixes hold:
  - null bodies are refused;
  - a lost reply that applied is stored and we stay in step; one that didn't apply stores nothing;
  - the read-back refuses more, fewer, swapped or different-policy rules and a failing GET;
  - three concurrent lost-reply tightenings serialise.
- Notes:
  - (a) PATCH applied, reply lost and the read-back GET also failing leaves us one rule behind Viseca. That is the safe direction; retrying the same rule re-syncs;
  - (b) read-back rules that aren't objects gave a 500;
  - (c) a mandate revoked between PATCH and read-back was stored as active.
- Fixed after the review: (b) and (c). Malformed read-back rules and a mandate that is no longer active both give 502 and store nothing. Tests added; 12 tighten/revoke tests pass.
Verdict: all met. Moved to done on the product owner's standing instruction for this run.
