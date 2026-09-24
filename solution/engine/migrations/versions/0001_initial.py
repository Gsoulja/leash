"""Initial schema: reference data, mandates, runs, decisions, append-only log, outbox, reader cache.

Money is NUMERIC(12,2). Every time is timestamptz; simulated purchase time (sim_ts) and real-clock
times (received_at, deadline_at, ask_expires_at) are separate columns (CLAUDE.md: two clocks).

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = """
-- reference data, loaded from the challenge pack (LEASH-042)
CREATE TABLE merchants (
  merchant_id        text PRIMARY KEY,
  name               text NOT NULL,
  category           text NOT NULL,
  mcc                char(4) NOT NULL,
  country            char(2) NOT NULL,
  city               text,
  availability       text NOT NULL,
  recurring_capable  boolean NOT NULL
);

CREATE TABLE auth_history (
  authorization_id  text PRIMARY KEY,
  card_id           text NOT NULL,
  merchant_id       text,
  ts                timestamptz NOT NULL,
  transaction_type  text NOT NULL CHECK (transaction_type IN ('purchase','refund','cash_withdrawal')),
  status            text NOT NULL CHECK (status IN ('approved','declined')),
  billing_chf       numeric(12,2) NOT NULL,
  device_id         text,
  country           char(2),
  initiator         text NOT NULL CHECK (initiator IN ('human','agent','merchant'))
);
CREATE INDEX auth_history_card ON auth_history (card_id, merchant_id);

-- familiarity baseline: approved purchases only (DEC-011)
CREATE MATERIALIZED VIEW card_merchant_familiarity AS
  SELECT card_id, merchant_id, count(*)::int AS approved_purchases
  FROM auth_history
  WHERE transaction_type = 'purchase' AND status = 'approved' AND merchant_id IS NOT NULL
  GROUP BY card_id, merchant_id;
CREATE UNIQUE INDEX card_merchant_familiarity_key ON card_merchant_familiarity (card_id, merchant_id);

-- policy
CREATE TABLE mandates (
  mandate_id   text PRIMARY KEY,
  instruction  text NOT NULL,
  status       text NOT NULL CHECK (status IN ('draft','active','revoked','expired')),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mandate_versions (
  mandate_id          text NOT NULL REFERENCES mandates,
  version             int  NOT NULL CHECK (version >= 1),
  hard_rules          jsonb NOT NULL,
  uncertainty_policy  text NOT NULL CHECK (uncertainty_policy IN ('ask','decline','approve')),
  compiled            jsonb NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (mandate_id, version)
);

CREATE TABLE runs (
  run_id           text PRIMARY KEY,
  scenario_id      text NOT NULL,
  mandate_id       text NOT NULL,
  mandate_version  int  NOT NULL,            -- the snapshot this run uses (DEC-003)
  card_id          text NOT NULL,
  started_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (mandate_id, mandate_version) REFERENCES mandate_versions
);

-- decisions: current state per purchase (projection of decision_events)
CREATE TABLE authorizations (
  authorization_id         text PRIMARY KEY,   -- live ID: idempotency key
  source_authorization_id  text,
  run_id                   text REFERENCES runs,
  card_id                  text NOT NULL,
  merchant_id              text NOT NULL,
  sim_ts                   timestamptz NOT NULL,   -- simulated purchase time
  billing_chf              numeric(12,2) NOT NULL,
  item_fingerprint         text NOT NULL,
  state                    text NOT NULL CHECK (state IN ('received','approved','declined','waiting','timed_out','not_sent')),
  engine_verdict           text CHECK (engine_verdict IN ('approve','decline','step_up')),
  resolved_by              text CHECK (resolved_by IN ('engine','customer','platform')),
  received_at              timestamptz NOT NULL,   -- real clock
  deadline_at              timestamptz NOT NULL,   -- real clock
  ask_expires_at           timestamptz,            -- real clock, from bootstrap's human window
  event                    jsonb NOT NULL,
  checks                   jsonb,
  model_release            text
);
CREATE INDEX authorizations_window ON authorizations (card_id, sim_ts) WHERE state = 'approved';
CREATE INDEX authorizations_recent ON authorizations (card_id, merchant_id, sim_ts);
CREATE INDEX authorizations_waiting ON authorizations (ask_expires_at) WHERE state = 'waiting';

-- append-only audit log (source of truth for replay)
CREATE TABLE decision_events (
  seq               bigserial PRIMARY KEY,
  authorization_id  text NOT NULL,
  kind              text NOT NULL CHECK (kind IN ('received','decided','sent','customer_resolved','timed_out','integrity_alert')),
  payload           jsonb NOT NULL,
  at                timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION forbid_decision_event_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'decision_events is append-only';
END $$;
CREATE TRIGGER decision_events_append_only
  BEFORE UPDATE OR DELETE ON decision_events
  FOR EACH ROW EXECUTE FUNCTION forbid_decision_event_change();
CREATE TRIGGER decision_events_no_truncate
  BEFORE TRUNCATE ON decision_events
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_decision_event_change();

-- outbox: decisions and resolutions to (re)send to the Viseca API (DEC-007)
CREATE TABLE outbox (
  id                bigserial PRIMARY KEY,
  authorization_id  text NOT NULL,
  endpoint          text NOT NULL CHECK (endpoint IN ('decision','resolve')),
  body              jsonb NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  sent_at           timestamptz,
  attempts          int NOT NULL DEFAULT 0
);
CREATE INDEX outbox_unsent ON outbox (id) WHERE sent_at IS NULL;

-- shop-text reader cache and model releases (LEASH-081/082)
CREATE TABLE fact_reads (
  text_hash      bytea NOT NULL,
  question_bank  text NOT NULL,
  model_release  text NOT NULL,
  answers        jsonb NOT NULL,
  PRIMARY KEY (text_hash, question_bank, model_release)
);

CREATE TABLE model_releases (
  release_id       text PRIMARY KEY,
  question_bank    text NOT NULL,
  temperatures     jsonb NOT NULL,
  ask_costs        jsonb NOT NULL,
  dataset_version  text NOT NULL,
  gate_report      jsonb NOT NULL,
  status           text NOT NULL CHECK (status IN ('shadow','active','retired'))
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS model_releases;
DROP TABLE IF EXISTS fact_reads;
DROP TABLE IF EXISTS outbox;
DROP TABLE IF EXISTS decision_events;
DROP FUNCTION IF EXISTS forbid_decision_event_change();
DROP TABLE IF EXISTS authorizations;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS mandate_versions;
DROP TABLE IF EXISTS mandates;
DROP MATERIALIZED VIEW IF EXISTS card_merchant_familiarity;
DROP TABLE IF EXISTS auth_history;
DROP TABLE IF EXISTS merchants;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
