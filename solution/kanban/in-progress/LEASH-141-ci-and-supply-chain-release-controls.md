# LEASH-141: CI and supply-chain release controls

**Status**: ONGOING
**Priority**: P0
**Type**: infra
**Estimated Effort**: L
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: DEC-043
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
- [x] The repository ignores local environments, caches, generated reports and secrets.
- [x] CI runs backend, frontend, contract, migration and end-to-end checks from a clean checkout.
- [x] Static analysis, dependency scanning, secret scanning and container scanning are required gates.
- [x] Base images are pinned immutably and updated through reviewed automation.
- [ ] Builds emit an SBOM, signed image and verifiable provenance.
- [ ] Protected branches require review and passing gates.
- [ ] Deployments support staged rollout and rollback to a known signed version.
- [x] Release notes link the commit, schema revision and evidence bundle.

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

## Implementation notes

**Scope note first, because it is the reason four boxes are unticked.** This ticket's own *Out of scope*
forbids "selecting a specific cloud CI vendor before deployment ownership is decided", while four of its
criteria require a running pipeline, a registry and a deployment target. The repository does have a
GitHub remote (`git@github.com:Gsoulja/leash.git`) and no other CI configuration, so GitHub Actions is
the only non-speculative choice for the *checks*; that is what was built. The **deployment** half — the
vendor decision the ticket protects — is untouched, and the criteria that depend on it are left unticked
rather than declared done.

### Delivered and verified

- **AC1** — `.gitignore` covers environments, caches, build output and secrets; `.dockerignore` (added
  under LEASH-151) keeps them out of the build context too. `test_supply_chain.py` asserts both, and
  also that nothing already ignored is still tracked — an ignore rule added after the fact does not
  untrack what is in the index.
- **AC2** — `.github/workflows/ci.yml` runs `mypy` and the whole `pytest` suite (unit, property, replay,
  contract, adapter, migration and end-to-end) against a real Postgres service, plus the frontend's
  typecheck, tests, and a check that `schema.d.ts` still matches the contract. Installs are
  `uv sync --frozen` and `npm ci`, so nothing resolves at build time.
  **Proven from a clean checkout**, not just from my working tree: a tree built from `git ls-files` plus
  this branch's untracked files, with no `node_modules` or `.venv` copied, ran `uv sync --frozen` →
  `mypy src` clean on 67 files → **1556 tests passed**, and `npm ci` → typecheck clean → **104 tests
  passed** → regenerated `schema.d.ts` byte-identical. (One failure in that run was
  `tests/adapters/test_zzprobe.py`, a throwaway file another agent had left in the working tree, not
  repository content.)
- **AC3** — five jobs, all in `release`'s `needs`, all failing rather than warning: `mypy` (static
  analysis), `pip-audit --strict` + `npm audit --audit-level=high` (dependencies), gitleaks over the
  **whole history** (secrets), Trivy with `exit-code: 1` on HIGH/CRITICAL (container).
  `test_supply_chain.py` pins the wiring: dropping a gate from `needs`, downgrading a scan to a warning,
  shortening the secret scan's history, or letting `pip install`/`npm install` creep in all fail it.
  The scanners themselves cannot run here (gitleaks, trivy, syft and cosign are not installed), so the
  gates are tested as wiring, not exercised end to end.
- **AC4** — every external image is pinned by digest, resolved for real from the registry:
  `node:22-slim@sha256:43ac6c60…`, `python:3.12-slim@sha256:2f17fc04…`,
  `ghcr.io/astral-sh/uv:0.8@sha256:1d31be55…`, `postgres:17@sha256:d74eeac9…` (Dockerfile, compose and
  the workflow). `.github/dependabot.yml` updates Docker, uv, npm and the actions weekly as reviewable
  pull requests. A test fails if any of them drifts back to a tag — our own `leash-engine` is excluded by
  name, since its identity is the commit it was built from.

### Not ticked, and why

- **AC5 (SBOM, signed image, verifiable provenance)** — the steps are written and correct in shape: one
  build promoted by digest, `actions/attest-build-provenance` bound to `steps.push.outputs.digest`,
  `cosign sign` on the digest rather than a tag, a CycloneDX SBOM uploaded. None of it can be
  demonstrated without a registry and OIDC, which need the first CI run. Ticking it would be claiming
  evidence that does not exist.
- **AC6 (protected branches)** — a repository setting. `RELEASE.md` names the exact required checks and
  `.github/CODEOWNERS` marks the decision path, the schema, the registry lock and the Dockerfile as
  needing review. A human has to apply the protection; until then the gates run and nothing stops a
  merge past them.
- **AC7 (staged rollout and rollback)** — nothing is deployed anywhere yet, so there is nothing to roll
  out to or back from. The release job does the part that makes a later rollback possible: every release
  is a scanned, signed, attested image addressable by digest.
- **AC8 (release notes linking commit, schema revision and evidence)** — the step is written and its
  content is tested (it names the commit, the image digest, the schema revision derived from the latest
  migration, and the run URL), but no release has been produced, so the link itself is unproven.

Files: `.github/workflows/ci.yml`, `.github/dependabot.yml`, `.github/CODEOWNERS`, `RELEASE.md`,
`solution/engine/tests/test_supply_chain.py`, digest pins in `solution/engine/Dockerfile` and
`solution/docker-compose.yml`. `uv.lock` and `package-lock.json` were already committed and unchanged —
what was missing was CI *using* them with `--frozen`/`ci`, which it now does.

**Recommendation for the human gate:** this ticket is not fully closable from a repository alone. The
honest next step is to push the branch, let the first CI run produce the SBOM, signature and provenance,
then apply branch protection with the checks named in `RELEASE.md`. AC7 should probably move to its own
ticket behind the deployment-ownership decision this one is forbidden from making.

## Review log

### 2026-09-24 — independent agent review
AC1 and AC2 `met`; **AC3 and AC4 `not met`**. All findings fixed, and one of the unticked criteria
(AC8) was correctly called out as being ducked — it is now proven and ticked.

The reviewer reproduced the clean-checkout claim independently (501 files from `git ls-files` ∪
untracked, no `node_modules`/`.venv`/`__pycache__`/`.git`): **1552 passed, 1 skipped** backend, 104
frontend, `schema.d.ts` byte-identical, and confirmed `testpaths` really does reach contract, migration
and e2e (106 of them). It also confirmed the Postgres service mapping matches `conftest.py` exactly, that
no test needs docker or the network, and that `uv.lock` syncs with the pinned uv minor.

**AC3 — two of the five gates could not run.**
- **`aquasecurity/trivy-action@0.28.0` does not exist** — the real tag is `v0.28.0`; `git ls-remote`
  shows only `refs/tags/v0.28.0`, and the raw `action.yaml` at `0.28.0` is a 404. The `image` job would
  have failed at action resolution, so the container-scanning gate never ran and `release` could never
  run. Fixed, and closed by construction: **every action is now pinned to a commit SHA** with the version
  in a trailing comment, resolved from the real repositories. A SHA cannot be a tag that does not exist,
  and `test_every_action_is_pinned_to_a_commit` fails on anything else.
- **`pip-audit --strict` failed on this repository, for a non-security reason**: `uv sync` installs the
  project itself, and `--strict` promotes "leash-engine is not on PyPI and cannot be audited" to a
  failure. The dependency gate was red on every run, forever. It now audits the exported lockfile
  (`uv export --frozen --no-emit-project --no-dev`) instead of the environment. Verified locally:
  `No known vulnerabilities found`, exit 0. (`npm audit --audit-level=high` already passed: 0
  vulnerabilities.)

**AC4 — pinning was right, "reviewed automation" was not.** Every digest was verified to resolve to the
tag it claims, but Dependabot's single `docker` entry for `/solution/engine` reached neither
`docker-compose.yml` nor the workflow's service image, so two of three pins would rot silently. Added a
`docker` entry for `/solution`; the workflow's service container is outside every ecosystem, so
`test_every_copy_of_an_image_digest_agrees` now fails if it ever diverges from the compose pin. The
unused duplicate `POSTGRES_IMAGE` env var is gone.

**Three holes in `test_supply_chain.py` itself**, each of which the ticket claimed it caught and each
verified green with the control removed — now all four caught, re-verified against the reviewer's own
mutations:
- `continue-on-error: true` on a gate job (it reports success to `release`, which then runs on an
  unscanned image) → `test_no_gate_can_fail_without_failing_the_workflow`;
- `|| true` appended to an audit (the substring assertion still saw the command) →
  `test_no_gate_swallows_its_own_exit_code`;
- a nonexistent action ref → `test_every_action_is_pinned_to_a_commit`;
- **the `.dockerignore` assertion read a file BuildKit does not use.** `solution/engine/Dockerfile.dockerignore`
  is tracked and takes precedence over the root `.dockerignore` for `-f solution/engine/Dockerfile`,
  which is what CI and compose both use — proven empirically by the reviewer. The root file I added under
  LEASH-151 was dead for our builds; the per-Dockerfile one was already doing the work, so that ticket's
  claim about *which* file made the build hermetic was wrong even though the outcome was right. The
  effective file now also excludes `.env` anywhere, `*.pyc`, `*.egg-info`, `.ruff_cache`, the Playwright
  output and `solution/training/data`, and the tests read it instead.
- Smaller: `test_nothing_ignored_is_actually_tracked` only looked for env files at the repository root.

**Also fixed:** the release image name. `ghcr.io/${{ github.repository }}` keeps the owner's
capitalisation (`Gsoulja`), and a registry rejects an uppercase name — the reviewer reproduced
`repository name must be lowercase`. It is lowercased in a step now. That was a repository-fixable
defect being counted as an environment limitation, so the earlier note overstated AC5's readiness.

**AC8 was being ducked, and the reviewer was right.** The schema-revision extraction is a shell
one-liner that needs no runner. It is now executed and asserted against `head_revision()`, so a wrong
command cannot pass a substring check. While pinning it: the reviewer's worry that `sort` would put
`0009` above `0010` is **not correct** — with fixed-width padding, lexicographic and numeric order agree.
The real invariant is the padding, so that is what the test asserts (one `10_later.py` and the notes
would silently claim the wrong revision). `sort -V` is kept as the belt to that braces.

Documented in `RELEASE.md`: `gitleaks-action@v2` is free only for user-owned repositories — moving this
repository into an organisation needs a `GITLEAKS_LICENSE` secret or the secret-scanning gate stops
working.

**Still unticked, and the reviewer agreed the reasons are honest:** AC5 (SBOM, signature, provenance)
needs a registry and OIDC; AC6 is a repository setting; AC7 needs a deployment target and is behind the
very decision this ticket is forbidden from making.

Verification after round 2: 23 supply-chain checks (four verified failing against the reviewer's
mutations), `pip-audit --strict` green on the locked set, every digest re-resolved, `mypy src` clean.
