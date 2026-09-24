"""Durable local draft revisions (LEASH-101).

A customer who corrects an unconfirmed draft gets a new revision rather than an edit in place: the
earlier proposal is marked superseded, never deleted, and each revision keeps the transcript of the
answers it was built from and the context bundle it was drafted against (LEASH-154's evidence,
moved here because only a draft revision has something to attach it to).

Submission and confirmation may name the revision the customer actually reviewed; a stale one is
refused, so an answer given after a review can never be confirmed as though it had been reviewed.

Revision ID: 0007
Revises: 0006

**Downgrade loses data.** It drops `draft_revisions`, which holds every superseded proposal, its
transcript and the context bundle it was drafted against — the evidence for a confirmed mandate. Backup
evidence required (`migrations/README.md`).
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE policy_drafts ADD COLUMN revision int NOT NULL DEFAULT 1")
    op.execute("""
CREATE TABLE draft_revisions (
  draft_id    text NOT NULL REFERENCES policy_drafts ON DELETE CASCADE,
  revision    int  NOT NULL CHECK (revision >= 1),
  draft       jsonb NOT NULL,
  answers     jsonb NOT NULL DEFAULT '[]',
  context     jsonb NOT NULL DEFAULT '{}',
  superseded  boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (draft_id, revision)
)""")
    # The stored view is what GET returns, and PolicyDraft now requires `revision`: an existing
    # draft would answer with a body that fails its own schema, so stamp it as revision 1 too.
    op.execute("UPDATE policy_drafts SET draft = jsonb_set(draft, '{revision}', '1'::jsonb, true)")
    # Every existing draft becomes its own revision 1, so nothing loses its history at upgrade.
    op.execute("INSERT INTO draft_revisions (draft_id, revision, draft, answers) "
               "SELECT draft_id, 1, draft, answers FROM policy_drafts")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS draft_revisions")
    op.execute("ALTER TABLE policy_drafts DROP COLUMN IF EXISTS revision")
