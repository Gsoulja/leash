# LEASH-141: CI and supply-chain release controls

**Status**: BACKLOG
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: none
**Parent**: LEASH-129
**Task ID**: 129-T12
**Blocked by**: none
**Blocks**: LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Create a reproducible, policy-gated build and deployment pipeline with dependency and container provenance.

## Business Value
Production must run exactly the reviewed source and reject releases with failing safety or security evidence.

## Acceptance Criteria
- [ ] The repository ignores local environments, caches, generated reports and secrets.
- [ ] CI runs backend, frontend, contract, migration and end-to-end checks from a clean checkout.
- [ ] Static analysis, dependency scanning, secret scanning and container scanning are required gates.
- [ ] Base images are pinned immutably and updated through reviewed automation.
- [ ] Builds emit an SBOM, signed image and verifiable provenance.
- [ ] Protected branches require review and passing gates.
- [ ] Deployments support staged rollout and rollback to a known signed version.
- [ ] Release notes link the commit, schema revision and evidence bundle.

## Technical Approach
Add repository-level ignore rules and a CI/CD workflow that builds once, promotes immutable artifacts and enforces policy before deployment.

### Dependencies
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Prove the pipeline from a clean checkout and demonstrate that a failing safety test, leaked test secret or vulnerable image blocks release.

## Related Files
- `.gitignore`
- `solution/engine/Dockerfile`
- `solution/engine/uv.lock`
- `solution/app/package-lock.json`

## Out of scope
- Selecting a specific cloud CI vendor before deployment ownership is decided.
