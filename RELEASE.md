# Release controls (LEASH-141)

What runs, what blocks, and the two settings a person has to apply in GitHub because a file in the
repository cannot apply them to itself.

## The pipeline

`.github/workflows/ci.yml`. One build, promoted — never rebuilt per stage, because a rebuild is a
different artifact and the thing that was scanned would not be the thing that ships.

| Job | What it proves |
| --- | --- |
| `backend` | `mypy src` and the whole `pytest` suite against a real Postgres: unit, property, replay, **contract**, adapter, **migration** and **end-to-end** |
| `frontend` | `npm run typecheck`, `npm test`, and that `schema.d.ts` still matches `contracts/policy-api.yaml` |
| `secrets` | gitleaks over the **whole history** — a secret committed and later removed is still leaked |
| `dependencies` | `pip-audit --strict` and `npm audit --audit-level=high` |
| `image` | builds once, scans with Trivy (`exit-code: 1` for HIGH/CRITICAL), emits a CycloneDX SBOM |
| `release` | needs **all five**; pushes, attests provenance to the pushed digest, signs it with cosign, and writes release notes |

Every install is from a lockfile (`uv sync --frozen`, `npm ci`), so CI resolves nothing at build time.

`solution/engine/tests/test_supply_chain.py` reads this configuration and fails if a control is lost: a
gate dropped from `release`'s `needs`, a scan downgraded to a warning, a base image drifting back to a
tag, `pip install` or `npm install` creeping in, or an ignore rule disappearing. It does not run the
scanners — that needs the CI runner — but it proves the wiring they hang from, which is what a refactor
breaks.

## Pinning

Base images are pinned by digest in `solution/engine/Dockerfile`, `solution/docker-compose.yml` and the
workflow's Postgres service. Every action is pinned to a **commit SHA** with the version in a trailing
comment — a tag can move, and a tag that does not exist fails only at runtime (`trivy-action@0.28.0` was
exactly that: the real tag is `v0.28.0`). `.github/dependabot.yml` updates Docker, uv, npm and the
actions weekly as pull requests a person reads.

Two pins Dependabot cannot reach, and what covers them instead:

- **`solution/docker-compose.yml`** — a second `docker` entry for `/solution` keeps it in scope.
- **the workflow's `services.db.image`** — Dependabot's `github-actions` ecosystem updates `uses:` refs,
  not service containers. `test_every_copy_of_an_image_digest_agrees` fails if that digest ever differs
  from the compose one, so updating one and forgetting the other is caught here rather than in
  production.

`gitleaks-action@v2` is free for user-owned repositories. Moving this repository into an organisation
requires a `GITLEAKS_LICENSE` secret, or the secret-scanning gate stops working.

## What a person still has to do

These are repository and environment settings, not files:

1. **Branch protection on `leash-mvp`.** Require a pull request with at least one approving review,
   require `CODEOWNERS` review, and require these checks to pass before merging:
   `backend tests and types`, `frontend tests and types`, `secret scan`, `dependency scan`,
   `build and scan the image`. Without this, the gates run but nothing stops a merge past them.
2. **A deployment target.** Staged rollout and rollback to a known signed version need somewhere to roll
   out *to*, and an owner for it. Until that exists, the release job publishes a signed, attested image
   by digest and stops there — which is the part that makes a later rollback possible, because every
   release is addressable by a digest that was scanned and signed.

## Verifying a release

```bash
cosign verify ghcr.io/<owner>/leash/leash-engine@<digest> \
  --certificate-identity-regexp 'https://github.com/<owner>/leash/.github/workflows/ci.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
gh attestation verify oci://ghcr.io/<owner>/leash/leash-engine@<digest> --repo <owner>/leash
```

The release notes name the commit, the image digest, the schema revision and the run that produced the
evidence; the SBOM is attached to the release.
