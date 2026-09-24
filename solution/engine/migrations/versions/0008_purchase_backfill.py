"""Backfill, validate and require `authorizations.purchase` (LEASH-135).

The contract half of `0002`'s expand. Rows written before `0002` have no stored purchase, so each one
is rebuilt from the raw event it was decided on — the same translator the worker uses, so the result is
what the engine would have written at the time. A row whose event cannot be translated stops the
migration: a purchase that cannot be rebuilt is not invented, because a guessed amount or basket would
feed straight into spend, familiarity and duplicate checks.

Deploy order on a populated database: upgrade to `0007` (the column is optional), roll out the
application version that writes `purchase`, then upgrade to `0008`. Reversing this revision only drops
the NOT NULL; it never drops the backfilled data. See `migrations/README.md`.

Revision ID: 0008
Revises: 0007
"""

import json

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

#: How many rows are rebuilt per round trip. It bounds memory only. Nothing bounds how long the whole
#: backfill holds its row locks: the revision runs in one transaction, and `env.py`'s statement_timeout
#: bounds a single statement, not a loop of them. On a table large enough for that to matter, run this
#: revision in a maintenance window — see `migrations/README.md`.
BATCH = 500


def remaining_without_purchase(conn: object) -> int:
    """Rows the backfill did not fill. Separate so it can be tested without a half-applied migration."""
    return int(conn.exec_driver_sql(  # type: ignore[attr-defined]
        "select count(*) from authorizations where purchase is null").scalar())


def upgrade() -> None:
    # Imported here, not at module import time: a migration must not depend on the application package
    # merely to be listed. `translate` is pure (no I/O, no clock) and is the one path from a platform
    # event into a Purchase, so the rebuilt row matches what the engine itself would have stored.
    from leash.adapters.postgres.repository import purchase_to_json
    from leash.adapters.viseca_api.translate import translate

    conn = op.get_bind()
    while True:
        rows = conn.exec_driver_sql(
            "select authorization_id, event from authorizations where purchase is null limit %(n)s",
            {"n": BATCH}).fetchall()
        if not rows:
            break
        for authorization_id, event in rows:
            data = event if isinstance(event, dict) else json.loads(event)
            try:
                purchase = translate(data).purchase
            except Exception as exc:  # noqa: BLE001 — any failure to rebuild must stop the migration
                raise RuntimeError(
                    f"cannot rebuild the purchase for {authorization_id} from its stored event: {exc}. "
                    "Nothing was guessed. Repair or remove that row, then run the migration again "
                    "(see migrations/README.md)") from exc
            conn.exec_driver_sql(
                "update authorizations set purchase = %(p)s::jsonb where authorization_id = %(a)s",
                {"p": json.dumps(purchase_to_json(purchase), default=str), "a": authorization_id})

    # Validate before contracting. The loop above only exits when the count is already zero, so this is
    # defence in depth rather than the normal path — it catches a row inserted by another session while
    # the backfill ran, and gives the operator a number instead of a bare constraint violation.
    left = remaining_without_purchase(conn)
    if left:
        raise RuntimeError(f"{left} authorizations still have no purchase; refusing to require the column")
    op.execute("ALTER TABLE authorizations ALTER COLUMN purchase SET NOT NULL")


def downgrade() -> None:
    # The backfilled data stays: only the requirement is lifted, so an older application version that
    # does not write `purchase` can run again.
    op.execute("ALTER TABLE authorizations ALTER COLUMN purchase DROP NOT NULL")
