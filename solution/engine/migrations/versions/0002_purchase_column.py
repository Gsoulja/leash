"""Store each authorization's purchase in the repository's own form, so snapshots can rebuild earlier
purchases without re-parsing the raw event (LEASH-043).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE authorizations ADD COLUMN purchase jsonb NOT NULL")
    op.execute("CREATE INDEX authorizations_run_card ON authorizations (run_id, card_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS authorizations_run_card")
    op.execute("ALTER TABLE authorizations DROP COLUMN IF EXISTS purchase")
