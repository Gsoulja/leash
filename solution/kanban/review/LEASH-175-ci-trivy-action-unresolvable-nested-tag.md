# LEASH-175: CI image-scan job fails to resolve a nested action tag

**Status**: REVIEW
**Priority**: P0
**Type**: bug
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (observed in a GitHub Actions run on 2026-09-24)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T1
**Blocked by**: none
**Blocks**: LEASH-141
**Updated**: 2026-09-25

## Description
The `image` job in `.github/workflows/ci.yml` fails before Trivy ever runs:

```
Error: Unable to resolve action `aquasecurity/setup-trivy@v0.2.1`, unable to find version `v0.2.1`
```

`ci.yml:136` pins `aquasecurity/trivy-action` to commit `915b19bbe73b92a6cf82a1bc12b087c9a19a5fe2` (labelled `v0.28.0`). That commit's own `action.yaml` calls a *nested* action, `aquasecurity/setup-trivy@v0.2.1`, by a floating tag rather than a commit SHA. Upstream (`aquasecurity/setup-trivy`) has since deleted that tag — `git ls-remote --tags` on that repository today shows only `v0.2.6`, `v0.3.0`, `v0.3.1` — so the reference now 404s. Our pin never moved; the ground under it did.

This is the same class of problem LEASH-141 pinned every top-level action against, but it applies one level deeper: pinning `trivy-action` to a SHA does not protect against *that action's own* unpinned nested reference changing meaning upstream.

**Confirmed fix:** the current `trivy-action` release (`v0.36.0`, commit `ed142fd0673e97e23eac54620cfb913e5ce36c25`) already pins its nested `setup-trivy` call by SHA (`3fb12ec12f41e471780db15c232d5dd185dcb514` = `v0.2.6`), specifically to close this failure mode. Bumping our pin to that commit fixes the immediate break and removes the class of risk going forward.

## Business Value
The `image` job feeds the container-scanning gate, which `release` requires (LEASH-141, AC3). While this is broken, no build can pass CI, so nothing can be verified as safe to release.

## Acceptance Criteria
- [x] `.github/workflows/ci.yml` pins `aquasecurity/trivy-action` to `ed142fd0673e97e23eac54620cfb913e5ce36c25` (`v0.36.0`), with the version in a trailing comment per the existing convention.
- [ ] A real GitHub Actions run reaches and completes the Trivy scan step in the `image` job (fails only on scan findings, never on action resolution).
- [x] `test_supply_chain.py`'s action-pinning tests still pass with the updated SHA.

## Technical Approach
One-line pin bump in `.github/workflows/ci.yml`. No change to `domain/`, `application/` or any pure code — this is CI/supply-chain wiring only (`adapters`-adjacent, outside the hexagon).

### Dependencies
- Blocks LEASH-141 (this failure prevents the real green CI run its AC5–AC7 call for).

## Testing Requirements
`uv run pytest solution/engine/tests/test_supply_chain.py -x -q` locally, then push and confirm in the Actions run that the `image` job's Trivy step executes (not just that the job is queued).

## Related Files
- `.github/workflows/ci.yml`

## Out of scope
- Re-auditing every other action's nested dependencies for the same floating-tag pattern (worth a follow-up ticket if this recurs, but not needed to close this one).

## Review log

### 2026-09-25 — independent agent review
- [x] met — criterion 1: `ci.yml:136` pins `trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0`; `git ls-remote` confirms `refs/tags/v0.36.0^{}` peels to that commit, its `action.yaml` still defines `image-ref`, `severity`, `exit-code`, `ignore-unfixed`, and pins `setup-trivy@3fb12ec… # v0.2.6` by SHA.
- [?] unverifiable — criterion 2: the change is not pushed, so no Actions run exists. Evidence needed: a run URL where the `image` job's "container scan" step executes and completes.
- [x] met — criterion 3: `uv run pytest tests/test_supply_chain.py -q` → 23 passed.
Verdict: moved to review; criterion 2 is left for the human gate (needs a push and a CI run).
