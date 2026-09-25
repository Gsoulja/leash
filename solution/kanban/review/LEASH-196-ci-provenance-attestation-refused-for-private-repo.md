# LEASH-196: Release job fails to store build provenance on a private repository

**Status**: REVIEW
**Priority**: P0
**Type**: bug
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (observed in GitHub Actions run 36078406126 on 2026-09-25, commit `424f514`)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T6
**Blocked by**: none
**Blocks**: LEASH-141
**Updated**: 2026-09-25

## Description
With LEASH-175 fixed, the `release` job gets as far as provenance and fails there:

```
Error: Failed to persist attestation: Feature not available for user-owned private repositories.
To enable this feature, please make this repository public.
```

`actions/attest-build-provenance` stores its attestation in GitHub's attestation API, which is only
available to public repositories and organisation plans. `Gsoulja/leash` is a private, user-owned
repository, so the step fails on every push to `leash-mvp`, and `cosign sign` and the release never run.

**Fix (chosen by the product owner, 2026-09-25):** replace the GitHub attestation with
`cosign attest --type slsaprovenance1` on the pushed digest. The SLSA v1 predicate (same shape the
GitHub action produced) is stored in GHCR beside the signature and verified with
`cosign verify-attestation`. The `attestations: write` permission is dropped.

Known trade-off: keyless cosign (sign and attest) records the repository name and workflow identity in
the public Rekor transparency log. Accepted; a key-pair with `--tlog-upload=false` is the alternative if
that ever matters.

## Business Value
The `release` job is the last gate of LEASH-141; while it fails, no build is released or verifiable.

## Acceptance Criteria
- [x] The `release` job uses no `actions/attest*` action and needs no `attestations` permission.
- [x] Provenance is a `cosign attest --type slsaprovenance1` bound to `steps.push.outputs.digest`.
- [ ] A real Actions run on `leash-mvp` completes the `release` job, and
      `cosign verify-attestation --type slsaprovenance1 --certificate-identity-regexp 'https://github.com/Gsoulja/leash/.*' --certificate-oidc-issuer https://token.actions.githubusercontent.com ghcr.io/gsoulja/leash/leash-engine@<digest>` succeeds.

## Technical Approach
CI wiring only (`.github/workflows/ci.yml`), outside the hexagon. The predicate is built with `jq` from
the runner's `GITHUB_*` variables; expressions reach the script through `env`, never inline.

## Testing Requirements
`test_provenance_is_a_cosign_attestation_on_the_pushed_digest` in `tests/test_supply_chain.py` (written
first, failed on the old step). Run `uv run pytest tests/test_supply_chain.py -q` from `solution/engine/`,
then push and check the Actions run.

## Related Files
- `.github/workflows/ci.yml`
- `solution/engine/tests/test_supply_chain.py`
