# LEASH-176: Worker refuses to start against the live platform — data version `saw26-hackaton-api` != `saw26`

**Status**: BACKLOG
**Priority**: P0
**Type**: bug
**Estimated Effort**: S
**Milestone**: M5 — Hosted API and release
**Rule source**: Found running `solution/run-local.sh --live` against the hosted sandbox (2026-09-24)
**Decisions**: none
**Parent**: LEASH-174
**Task ID**: 174-T2
**Blocked by**: none
**Blocks**: LEASH-114, LEASH-128
**Gate**: DECISION — confirm with Viseca whether `saw26-hackaton-api` is the live data version going forward, or a temporary label.
**Updated**: 2026-09-24

## Description
`solution/run-local.sh --live` builds and starts `db`, `migrate`, `api` and `worker` against the real Viseca platform. `db`, `migrate` and `api` come up healthy; `worker` is reported `unhealthy` by `docker compose ... --wait` and never becomes ready.

**Confirmed general, not a local-machine issue.** The worker's own startup code is the cause, so this reproduces on any machine pointed at the live platform, not just this one:

- `solution/engine/src/leash/config.py:29` hardcodes `EXPECTED_DATA_VERSION = "saw26"`.
- `check_compatibility()` (`config.py:198-204`) does an exact string comparison: `if data_version != EXPECTED_DATA_VERSION: raise IncompatibleApi(...)`.
- `load_runtime()` (`config.py:239-248`) calls this right after reading `/v1/bootstrap`, and only the **worker** calls `load_runtime` at startup (`adapters/viseca_api/worker.py:233-235`) — the `api` service never does, which is exactly why `api` reports healthy while `worker` does not.
- The live platform's `/v1/bootstrap` currently reports `data_version` as `saw26-hackaton-api`, not `saw26`. The exact-match check raises `IncompatibleApi`, which propagates out of `_work`/`_serve` uncaught, so the worker process exits and the container's health check never passes.

This matches a note already left in the (untracked, local-only) `solution/run-local.sh` script itself, written from an earlier `--live` attempt — so the mismatch has been observed at least twice and was never turned into a tracked ticket or a decision-log entry.

## Business Value
Nothing that requires the worker (deciding real purchases, the live rehearsal LEASH-114, the release-readiness gate LEASH-128) can run against the hosted platform until this is resolved. This blocks the event-day path entirely, not just local development.

## Acceptance Criteria
- [ ] Confirm with Viseca (open question) whether `saw26-hackaton-api` is the stable data version identifier for the hosted sandbox going forward, a temporary/environment-specific suffix, or a platform-side labelling bug — record the answer in `solution/docs/decisions.md`.
- [ ] Until confirmed, the worker starts successfully against the live platform without weakening the safety intent of the check: an unrecognized major version or a value with no relation to `saw26` must still refuse to start (this is not "accept anything").
- [ ] `check_compatibility` is covered by a test asserting today's live value (`saw26-hackaton-api`) is accepted and an unrelated value (e.g. `"other-pack"`) is still rejected.
- [ ] Re-run `solution/run-local.sh --live` (or the equivalent CI/manual check) and confirm `worker` reaches healthy.

## Technical Approach
`solution/engine/src/leash/config.py`, `check_compatibility()` and `EXPECTED_DATA_VERSION`. Likely a prefix or pattern match (`data_version == EXPECTED_DATA_VERSION or data_version.startswith(EXPECTED_DATA_VERSION + "-")`) rather than widening to a fuzzy match — exact rule depends on Viseca's answer to the decision gate above.

### Dependencies
- Blocks LEASH-114 (live rehearsal needs a running worker).
- Blocks LEASH-128 (release-readiness gate needs live evidence).

## Testing Requirements
Write first: `test_check_compatibility_accepts_current_live_data_version`, `test_check_compatibility_still_rejects_an_unrelated_data_version`. Run `uv run pytest solution/engine/tests -k check_compatibility -x -q`.

## Related Files
- `solution/engine/src/leash/config.py`
- `solution/engine/src/leash/adapters/viseca_api/worker.py`
- `solution/run-local.sh` (untracked local script; carries the original observation in a comment)

## Out of scope
- Changing what the `api` service checks at startup — it does not call `load_runtime` today and this ticket does not add that.
- The unrelated live PATCH issue tracked separately in LEASH-157.
