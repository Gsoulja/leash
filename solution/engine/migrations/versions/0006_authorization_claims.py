"""Durable processing claims on received authorizations (LEASH-131): which worker owns the decision work and
until when. A redelivery takes over an expired claim, recorded as a 'reclaimed' decision event.

Revision ID: 0006
Revises: 0005

**Downgrade can be impossible.** It narrows `decision_events_kind_check` back to the kinds before
`'reclaimed'`, so on a database where any worker ever reclaimed an expired claim the constraint is
violated by an existing row and the downgrade fails. The offending row cannot be deleted either: the
table is append-only by trigger. In that state the only ways back are a restore from backup or a new
forward revision. `tests/adapters/test_migrations.py::test_a_reclaimed_event_blocks_the_downgrade_past_0006`
pins this, so it is a documented property rather than a surprise.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_KINDS = "'received','decided','sent','customer_resolved','timed_out','integrity_alert'"


def upgrade() -> None:
    op.execute("ALTER TABLE authorizations ADD COLUMN claim_owner text, ADD COLUMN claim_expires_at timestamptz")
    op.execute("ALTER TABLE decision_events DROP CONSTRAINT decision_events_kind_check")
    op.execute(f"ALTER TABLE decision_events ADD CONSTRAINT decision_events_kind_check CHECK (kind IN ({_KINDS},'reclaimed'))")


def downgrade() -> None:
    op.execute("ALTER TABLE decision_events DROP CONSTRAINT decision_events_kind_check")
    op.execute(f"ALTER TABLE decision_events ADD CONSTRAINT decision_events_kind_check CHECK (kind IN ({_KINDS}))")
    op.execute("ALTER TABLE authorizations DROP COLUMN IF EXISTS claim_expires_at, DROP COLUMN IF EXISTS claim_owner")
