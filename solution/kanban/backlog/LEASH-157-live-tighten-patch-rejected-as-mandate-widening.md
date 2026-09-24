# LEASH-157: Live PATCH /v1/mandates/{id} rejects any hard_rules as mandate_widening, even unchanged or additive

**Status**: BACKLOG
**Priority**: P0
**Type**: bug
**Estimated Effort**: M
**Milestone**: M5 — Hosted API and release
**Rule source**: Found by manual verification against the hosted Viseca sandbox (2026-09-24), reusing the team key confirmed working in LEASH-057
**Decisions**: none
**Blocked by**: none
**Blocks**: LEASH-128
**Updated**: 2026-09-24

## Description
`POST /api/mandates/{mandate_id}/tighten` (`solution/engine/src/leash/adapters/http/policy_api.py`, `tighten()`) always sends the mandate's full `hard_rules` array in the `PATCH /v1/mandates/{id}` body (`hard_rules = before + [rule_to_api(r) for r in new_rules]`, then `change["hard_rules"] = hard_rules` unconditionally). Against the hosted sandbox (`https://saw26api...`), this PATCH is rejected with `409 {"code":"mandate_widening","message":"An active mandate may only preserve or add hard rules"}` in every shape tried:

- resending the array byte-identical to what `GET /v1/mandates/{id}` had just returned (including the server's own echoed `"period_days": null`),
- the same array plus one genuinely new rule,
- only a new rule, with the pre-existing one omitted.

Only a PATCH with no `hard_rules` key at all (`{"uncertainty_policy": "decline"}` alone) succeeds live. This means every real "tighten with a new hard rule" customer action — the core of `LEASH-062` — is currently refused by the live platform with `platform_refused`, even though the change is genuinely additive and spec-compliant per `technical_details.md` §8 ("If you send hard_rules, keep every existing rule unchanged. You may add rules.").

Reproduction evidence (request + response, saved verbatim) is at `solution/postman/apiCalls/`: `19`–`22` (byte-identical resend, with/without `period_days`), `23`–`26` (explicit-null resend), `27`–`32` (append-only new rule, and new-rule-alone). All five independent PATCH attempts with any `hard_rules` content returned `409 mandate_widening`; the bare `uncertainty_policy`-only PATCH at call `16` returned `200`.

## Business Value
Tightening rules mid-run is one of the three demo moments (README "What to show in your demo") and a non-negotiable domain rule ("Mandates only tighten, by appending"). If it silently fails against the real platform, the customer-control story breaks live, and `LEASH-128`'s "customer can confirm, resolve, tighten and revoke" criterion has no real evidence.

## Acceptance Criteria
- [ ] Confirm with Viseca (open question) whether `mandate_widening` on an unchanged/additive `hard_rules` PATCH is expected sandbox behaviour, a documented format requirement we're missing, or a platform bug — record the answer in `solution/docs/decisions.md`.
- [ ] Until confirmed, `tighten()` degrades safely: a tighten request that only changes `uncertainty_policy` must not send `hard_rules` at all (matches the one shape verified to work live); a tighten request that adds a hard rule must not silently apply the change locally if Viseca refuses it live — the customer must see the platform's refusal, not a false success.
- [ ] A test (adapter-layer, against a fake platform double reproducing this exact `409 mandate_widening` response for a `PATCH` containing `hard_rules`) asserts `tighten()` surfaces `platform_refused` and does **not** write a new `mandate_versions` row.
- [ ] Re-run the live reproduction once a fix or platform clarification lands, and save the new evidence next to the existing `solution/postman/apiCalls/` files.

## Technical Approach
`solution/engine/src/leash/adapters/http/policy_api.py`, `tighten()` (around the `change: dict[str, Any] = {"hard_rules": hard_rules}` line). Consider omitting `hard_rules` from the PATCH body when `new_rules` is empty (already always non-empty when only `uncertainty_policy` changes per current code — that branch needs the actual fix), and re-examine whether the hosted platform expects a different encoding for "add-only" changes (e.g. only the new rules, not the full array — contradicted by call `30` also failing, so likely not the fix; needs Viseca's answer).

### Dependencies
- Relates to LEASH-062 (built the tighten/revoke endpoints this bug affects).
- Relates to LEASH-057 (established the live connection and team key used to reproduce this).
- Blocks LEASH-128 (release-readiness gate: tighten is part of its customer-control criterion).

## Testing Requirements
Add `solution/engine/tests/adapters/test_policy_api.py::test_tighten_reports_platform_refused_when_viseca_rejects_hard_rules` (or the nearest existing test module for `tighten()`), using a fake `MandateChanges.patch_mandate` that raises `VisecaApiError(409, ..., {"code": "mandate_widening", ...})` for any call whose body includes `hard_rules`. Assert the HTTP response is `409 platform_refused` and no new mandate version is persisted.

## Related Files
- `solution/engine/src/leash/adapters/http/policy_api.py`
- `solution/engine/src/leash/adapters/viseca_api/client.py`
- `solution/postman/apiCalls/16-mandates-patch-tighten.json` (working case: no `hard_rules`)
- `solution/postman/apiCalls/19-mandates-create-draft2.json` through `32-mandates-patch-exact-echo.json` (five failing reproductions)

## Out of scope
- Changing the local (non-Viseca) tighten/append-only semantics in `domain/mandate.py` — those are correct; this is purely about what the live PATCH accepts.
