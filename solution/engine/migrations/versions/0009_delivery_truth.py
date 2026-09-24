"""Separate the engine's verdict from what the payment platform actually accepted (LEASH-130).

`authorizations.state` carried both: a purchase read as `approved` whether or not our answer ever
reached Viseca. That is the wrong default for money — a decision the platform terminally refused
(`deadline_passed`) would still have counted toward spend, familiarity, duplicates and the purchase
count, and the app would still have shown it as paid.

Three columns, so the three facts stay apart: the engine's verdict (`engine_verdict`, already here),
whether our answer was delivered (`delivery`), and what the platform said about it (`platform_outcome`).
`delivery` is added with a default, which in Postgres 11+ is a catalogue-only change, so it can be NOT
NULL from the start without rewriting the table (see `migrations/README.md`).

`decision_events` gains the `delivered` kind, so acceptance and refusal are in the audit log rather than
only in the projection.

**Downgrade can be impossible**, for the same reason as `0006`: it narrows `decision_events_kind_check`
back to the kinds before `'delivered'`, and on a database that recorded any delivery an existing row
violates it — a row that cannot be deleted, because the table is append-only by trigger. The only ways
back are a restore from backup or a new forward revision.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_KINDS = ("'received','decided','sent','customer_resolved','timed_out','integrity_alert','reclaimed'")


def upgrade() -> None:
    op.execute("""
        ALTER TABLE authorizations
          ADD COLUMN delivery text NOT NULL DEFAULT 'pending'
            CHECK (delivery IN ('pending','accepted','refused')),
          ADD COLUMN platform_outcome text,
          ADD COLUMN delivered_at timestamptz
    """)
    # Backfill from the outbox, which already knows: a row closed without an error was delivered, a row
    # closed with one was refused, and an open row is still pending. Nothing is guessed — an
    # authorization with no outbox row at all stays 'pending'.
    op.execute("""
        UPDATE authorizations a SET delivery = 'accepted', delivered_at = o.sent_at,
                                    platform_outcome = 'accepted'
        FROM outbox o
        WHERE o.authorization_id = a.authorization_id AND o.endpoint = 'decision'
          AND o.sent_at IS NOT NULL AND o.last_error IS NULL
    """)
    # A refused delivery also moves the purchase out of its decided state, exactly as `record_delivery`
    # does from now on. Recording the refusal without this would leave `state = 'approved'` on a decision
    # the platform never accepted — which is the whole bug this revision exists to fix, reintroduced by
    # the backfill for every row that predates it.
    op.execute("""
        UPDATE authorizations a SET delivery = 'refused', delivered_at = o.sent_at,
                                    platform_outcome = o.last_error,
                                    state = CASE WHEN a.state IN ('approved','declined','waiting','received')
                                                 THEN 'not_sent' ELSE a.state END
        FROM outbox o
        WHERE o.authorization_id = a.authorization_id AND o.endpoint = 'decision'
          AND o.sent_at IS NOT NULL AND o.last_error IS NOT NULL
    """)
    op.execute("ALTER TABLE decision_events DROP CONSTRAINT decision_events_kind_check")
    op.execute(f"ALTER TABLE decision_events ADD CONSTRAINT decision_events_kind_check "
               f"CHECK (kind IN ({_KINDS},'delivered'))")
    # Reading the ledger means reading accepted spend as well as reserved spend.
    op.execute("CREATE INDEX authorizations_delivery ON authorizations (card_id, delivery) "
               "WHERE state = 'approved'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS authorizations_delivery")
    op.execute("ALTER TABLE decision_events DROP CONSTRAINT decision_events_kind_check")
    op.execute(f"ALTER TABLE decision_events ADD CONSTRAINT decision_events_kind_check CHECK (kind IN ({_KINDS}))")
    op.execute("ALTER TABLE authorizations DROP COLUMN IF EXISTS delivered_at, "
               "DROP COLUMN IF EXISTS platform_outcome, DROP COLUMN IF EXISTS delivery")
