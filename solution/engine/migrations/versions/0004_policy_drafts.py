"""Local policy drafts, kept apart from the Viseca mandate draft (LEASH-061).

A local draft (LD-…) is the compiled instruction the customer is still shaping. Submitting posts it to
Viseca as a platform draft (platform_draft_id, platform_body: exactly what was posted). Confirming
stores the returned mandate_id; the mandate itself lives in mandates / mandate_versions.

Revision ID: 0004
Revises: 0003

**Downgrade loses data.** It drops `policy_drafts` whole, including every submitted `platform_body` —
the exact payload posted to Viseca, which is the evidence for what was submitted. Backup evidence
required (`migrations/README.md`).
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE policy_drafts (
  draft_id           text PRIMARY KEY,
  instruction        text NOT NULL,
  draft              jsonb NOT NULL,
  platform_draft_id  text UNIQUE,
  platform_body      jsonb,
  mandate_id         text UNIQUE REFERENCES mandates,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (mandate_id IS NULL OR platform_draft_id IS NOT NULL)
)""")
    # Confirm bookkeeping, each written in its own short transaction (no lock is held during the Viseca call):
    # confirm_started_at marks a call whose answer may be unknown; confirmed_mandate_id is Viseca's answer,
    # saved before the mandate rows, so a failed local write is finished on retry without asking Viseca again.
    op.execute("ALTER TABLE policy_drafts ADD COLUMN confirm_started_at timestamptz, "
               "ADD COLUMN confirmed_mandate_id text")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policy_drafts")
