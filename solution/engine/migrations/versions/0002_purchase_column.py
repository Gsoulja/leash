"""Store each authorization's purchase in the repository's own form, so snapshots can rebuild earlier
purchases without re-parsing the raw event (LEASH-043).

**Expand only** (LEASH-135). The column started life as `jsonb NOT NULL`, which Postgres refuses the
moment the table holds one row — so this migration failed on every populated database and passed only
in tests that began empty. It is now nullable here and made required in `0008`, after the backfill.
That split is also what a rolling deploy needs: between the two revisions an application version that
does not yet write `purchase` can still insert.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: adding a nullable column is a catalogue-only change, so it takes no table rewrite and
    # holds ACCESS EXCLUSIVE for an instant. `0008` backfills and then requires it.
    op.execute("ALTER TABLE authorizations ADD COLUMN purchase jsonb")
    # CREATE INDEX blocks writes to the table while it runs; env.py bounds how long that can last.
    op.execute("CREATE INDEX authorizations_run_card ON authorizations (run_id, card_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS authorizations_run_card")
    op.execute("ALTER TABLE authorizations DROP COLUMN IF EXISTS purchase")
