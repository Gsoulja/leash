"""Outbox retry bookkeeping, so backoff survives a restart (LEASH-054).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE outbox ADD COLUMN last_attempt_at timestamptz, ADD COLUMN last_error text")


def downgrade() -> None:
    op.execute("ALTER TABLE outbox DROP COLUMN IF EXISTS last_error, DROP COLUMN IF EXISTS last_attempt_at")
