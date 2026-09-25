# LEASH-197: Secret scan fails with 403 on pull requests

**Status**: REVIEW
**Priority**: P0
**Type**: bug
**Estimated Effort**: S
**Milestone**: M7 — Production hardening
**Rule source**: Team (observed in a GitHub Actions run for pull request #8 on 2026-09-25)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T7
**Blocked by**: none
**Blocks**: LEASH-141
**Updated**: 2026-09-25

## Description
On `pull_request` events the `secrets` job dies before gitleaks scans anything:

```
RequestError [HttpError]: Resource not accessible by integration   (403)
GET https://api.github.com/repos/Gsoulja/leash/pulls/8/commits
x-accepted-github-permissions: pull_requests=read
```

gitleaks-action lists the pull request's commits through the API to decide what to scan. The workflow
grants the token only `contents: read`, so the call is refused. Push events don't make that call, which is
why the job passed on pushes.

**Fix:** job-level `permissions` on `secrets` with `contents: read` and `pull-requests: read`. A job's
permissions replace the workflow's, so `contents: read` is repeated. Every other job keeps `contents: read`.

## Business Value
`secrets` is one of the gates `release` needs (LEASH-141); a failing check also blocks merging pull requests.

## Acceptance Criteria
- [x] The `secrets` job's token has `contents: read` and `pull-requests: read`, and nothing more.
- [ ] A real Actions run on a pull request completes the gitleaks step (fails only on findings, never on a 403).

## Technical Approach
CI wiring only (`.github/workflows/ci.yml`), outside the hexagon.

## Testing Requirements
`test_the_secret_scan_may_list_a_pull_requests_commits` in `tests/test_supply_chain.py` (written first,
failed on the old workflow). Run `uv run pytest tests/test_supply_chain.py -q` from `solution/engine/`, then
push and check the pull request's Actions run.

## Related Files
- `.github/workflows/ci.yml`
- `solution/engine/tests/test_supply_chain.py`
