"""The customer's answers to a local draft's questions (LEASH-123), in the order given.

Revision ID: 0005
Revises: 0004

**Downgrade loses data.** It drops `policy_drafts.answers`, and the customer's answers to a draft's
questions exist nowhere else — re-upgrading leaves them `[]`. Backup evidence required
(`migrations/README.md`).
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE policy_drafts ADD COLUMN answers jsonb NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE policy_drafts DROP COLUMN IF EXISTS answers")
