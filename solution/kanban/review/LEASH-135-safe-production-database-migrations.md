# LEASH-135: Safe production database migrations

**Status**: REVIEW
**Priority**: P0
**Type**: infra
**Estimated Effort**: M
**Milestone**: M7 — Production hardening
**Rule source**: Engineering
**Decisions**: DEC-040
**Parent**: LEASH-129
**Task ID**: 129-T6
**Blocked by**: none
**Blocks**: LEASH-139, LEASH-142, LEASH-143
**Updated**: 2026-09-24

## Description
Make every schema change safe on populated databases, beginning with migration `0002`, which adds a non-null column without a backfill.

## Business Value
Deployments must not fail, corrupt data or require dropping the production database.

## Acceptance Criteria
- [x] A database containing realistic `0001` rows upgrades to head without data loss.
- [x] Required columns use expand, backfill, validation and contract steps.
- [x] Long-running migrations have bounded locks and an operational rollback plan.
- [x] Application versions remain compatible during rolling deployment.
- [x] Migration checks run against both an empty and populated previous-version database.
- [x] Downgrade policy is documented; irreversible migrations require backup evidence.

## Technical Approach
Replace unsafe DDL with staged Alembic revisions and add upgrade fixtures representing every supported previous release.

### Dependencies
- Blocks LEASH-139.
- Blocks LEASH-142.
- Blocks LEASH-143.

## Testing Requirements
Write a failing migration test that inserts an authorization at revision `0001`, upgrades to head and verifies the row and reconstructed purchase.

## Related Files
- `solution/engine/migrations/versions/0002_purchase_column.py`
- `solution/engine/migrations/`
- `solution/engine/src/leash/adapters/postgres/migrate.py`

## Out of scope
- Changing the database technology.

## Implementation notes

The bug was real and reproduced first: at revision `0001`, inserting one authorization and upgrading to
head fails with `NotNullViolation: column "purchase" of relation "authorizations" contains null values`.
It passed until now only because every test started from an empty database.

- **`0002` is expand only.** `ADD COLUMN purchase jsonb`, nullable. Adding a nullable column is a
  catalogue change, so it holds ACCESS EXCLUSIVE for an instant and rewrites nothing.
- **`0008_purchase_backfill.py` is backfill → validate → contract.** Each missing `purchase` is rebuilt
  from the raw event the decision was made on, through `translate()` — the same pure translator the
  worker uses, so the result is byte-for-byte what the engine would have written. A row whose event
  cannot be translated raises with that row's ID and stops the migration: a guessed amount or basket
  would feed straight into spend, familiarity and duplicate checks. Then an explicit count of remaining
  nulls (so the operator gets a number, not a bare constraint violation), then `SET NOT NULL`.
- **Rolling deploy (AC4)** falls out of the split: `upgrade 0007` → roll out the app version that writes
  `purchase` → `upgrade head`. In between, an old instance that omits the column can still insert. A test
  pins that the column is `is_nullable = YES` at `0002` and `NO` at head.
- **Bounded locks (AC3) live in `migrations/env.py`**, not in each revision, so a new revision cannot
  forget them: `SET LOCAL lock_timeout` / `statement_timeout` inside the migration transaction, from
  `LEASH_MIGRATION_LOCK_TIMEOUT` (5s) and `LEASH_MIGRATION_STATEMENT_TIMEOUT` (300s). Both are validated
  against a Postgres interval pattern rather than interpolated raw — they reach SQL as text.
- **`migrations/env.py` added to `SHARED_FILES`.** It decides how every revision is applied, so a change
  there could change what a migration does with no revision file moving — a hole in the fingerprint.
- **`migrations/README.md`** carries the expand/backfill/validate/contract rules, the three-step rolling
  deploy, the timeout table, and the downgrade policy: every revision in this chain is reversible (a test
  walks the whole chain to `base` and back), a revision that would destroy unrebuildable data must say so
  in its own docstring and requires verified backup evidence — dump taken, restored elsewhere, row counts
  of every touched table checked, location and checker recorded — and reversing is a repair path, not a
  deploy step.

New file outside Related Files: `solution/engine/tests/adapters/test_migrations.py` (the check the
Testing Requirements ask for). `src/leash/policy/registry.py` and `tests/policy/test_registry.py` changed
for the `SHARED_FILES` addition and the LOCK re-pin.

Verification: `tests/adapters/test_migrations.py` 6 passed (3 of them verified failing before the change);
full suite 1485 passed; `mypy src` clean.

## Review log

### 2026-09-24 — independent agent review
AC1, AC2, AC3, AC4, AC5 `met`; **AC6 `not met`** — all findings now fixed.

Verified independently, not taken on trust: four awkward rows at `0001` (USD 450.00 → CHF 391.50 with
line items out of order, quantity 3 and injection text; a related/refund row with nulls throughout; EUR
12345.67; a null `delivery_by`) all round-tripped exactly — `purchase_from_json(stored) ==
translate(event).purchase`, stored JSON byte-identical to `purchase_to_json(expected)`, **zero floats**
anywhere in any stored purchase, `sim_ts` (simulated) untouched and separate from the real-clock columns,
and all 17 pre-existing columns identical after the upgrade. 1201 rows backfilled in 0.5 s across the
batch loop. `translate` proved strict enough to reject a partially-populated event rather than produce
something wrong (it refused a `related_authorization_status` outside its allowed set). The lock bound was
measured by holding `ACCESS EXCLUSIVE` from a second connection: 2 s setting → failed after 2.0 s, 1 ms
statement timeout → cancelled, and the rollback left `alembic_version` at `0001` with the data intact.
All 13 LOCK values recomputed: 0 mismatches, and `migrations/env.py` is genuinely hashed (changing
`DEFAULT_LOCK_TIMEOUT` moved every fingerprint).

**AC6 — two claims in `migrations/README.md` were false, both reproduced.** Fixed by making the
documentation true rather than by softening it:

- *"Every revision in this chain is reversible"* — false on a populated database, the only kind this
  ticket says matters. `0006`'s downgrade narrows `decision_events_kind_check` back to the kinds before
  `'reclaimed'`, so any database where a worker ever reclaimed a claim is blocked, and the offending row
  cannot be deleted because the table is append-only. The cited evidence walked the chain on an *empty*
  database and could never have caught it. The README now carries a per-revision reversibility table, each
  revision states its own downgrade cost in its docstring, and
  `test_a_reclaimed_event_blocks_the_downgrade_past_0006` pins the failure as a documented property.
- *"A revision that would destroy data the application cannot rebuild must say so in its own docstring"* —
  contradicted by the chain it documents. `0005` silently drops the customer's draft answers (reproduced:
  `[{"q": "a"}]` → gone, `[]` after re-upgrading), `0004` drops every submitted `platform_body`, `0007`
  drops the draft transcripts and retained context, `0001` drops the audit log. All five now say so.

Other findings, fixed:
- **A zero timeout disabled the bound it was there to guarantee.** The interval regex accepted `0` and
  `0ms`, which Postgres reads as *no timeout*. Now refused with that reason.
- **The AC3 test was a string grep over `env.py`** and passed with both `SET LOCAL` statements deleted.
  Replaced by `test_a_blocked_migration_fails_fast_instead_of_waiting`, which holds a conflicting lock and
  measures the migration giving up — and runs the upgrade in a thread with a wall-clock join, because
  without the bound it does not fail, it hangs. Re-running the reviewer's own mutation now fails it in
  15.6 s with "the migration was still waiting for the lock; env.py is not bounding it".
- **The validation count had no test** and deleting it changed nothing. Extracted as
  `remaining_without_purchase` and tested directly; neutering it now fails that test.
- **`0008`'s comment claimed `statement_timeout` bounds the backfill's lock duration** — it bounds one
  statement, not a loop of them (the reviewer completed a 1201-row backfill with a 200 ms statement
  timeout). Corrected, with a pointer to running it in a maintenance window.
- **The refusal assertion was loose** (`"purchase" in str(exc).lower()` would have accepted a bare
  `NotNullViolation`). It now requires the row ID and the words "cannot rebuild", and asserts the
  migration left `alembic_version` at `0001`.
- **The populated fixture keyed a row `AZ-legacy` against an event saying `AU_EXAMPLE_0001`** — unrealistic
  in exactly the field that identifies the row. It now keys the row the way `receive` does.
- **"`migrations/versions/*` is hashed whole, so any edit moves every field"** — false for `.py` files:
  `code_hash` is an AST dump with docstrings stripped, so comment-only edits deliberately move nothing.
  Corrected in the README and in the re-pin note.
- The offline `--sql` path sets no bounds and cannot generate `0008` at all; `env.py` now says so.

Left as noted, not acted on: `0008` does not cross-check the row key against the event's own
`authorization_id` (harmless — `receive` always keys on `purchase.authorization_id`), and the batch loop
has no progress guard (unreachable while the update matches on the primary key).

Verification after round 2: 9 migration tests (the three new ones verified failing against the reviewer's
own mutations), `tests/policy` + migrations 26 passed, `mypy src` clean on 66 files.
