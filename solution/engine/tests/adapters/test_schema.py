"""The initial migration, applied to a throw-away Postgres database."""

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

ENGINE = Path(__file__).resolve().parents[2]
TABLES = {"merchants", "auth_history", "mandates", "mandate_versions", "runs", "authorizations",
          "decision_events", "outbox", "fact_reads", "model_releases"}


def alembic(url: str) -> Config:
    cfg = Config(str(ENGINE / "alembic.ini"))
    cfg.set_main_option("script_location", str(ENGINE / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def sql(url: str, *statements: str):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            out = None
            for s in statements:
                out = await conn.fetch(s)
            return out
        finally:
            await conn.close()
    return asyncio.run(go())


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    return test_database_url


def seed_authorization(url: str, **overrides) -> str:
    values = {"state": "'received'", "engine_verdict": "NULL"} | overrides
    sql(url,
        "insert into merchants values ('ME0022','PixelHarbor','electronics','5732','CH','Zurich','store_and_online',false)",
        "insert into mandates values ('TM1','Buy the monitor','active',now())",
        "insert into mandate_versions values ('TM1',1,'[]','ask','{}',now())",
        "insert into runs values ('RUN1','SCEN0004','TM1',1,'CA0039',now())",
        f"""insert into authorizations (authorization_id, source_authorization_id, run_id, card_id, merchant_id, sim_ts,
            billing_chf, item_fingerprint, state, engine_verdict, received_at, deadline_at, event, purchase)
            values ('AZ1','AU0035','RUN1','CA0039','ME0022','2026-08-12T09:40:00Z',289.00,'IT0017:1',
                    {values['state']}, {values['engine_verdict']}, now(), now() + interval '8 seconds', '{{}}', '{{}}')""")
    return "AZ1"


def test_decision_events_is_append_only(db):
    sql(db, "insert into decision_events (authorization_id, kind, payload) values ('AZ1','received','{}')")
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        sql(db, "update decision_events set kind = 'decided'")
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        sql(db, "delete from decision_events")


def test_state_check_rejects_unknown_value(db):
    with pytest.raises(asyncpg.CheckViolationError):
        seed_authorization(db, state="'maybe'")


def test_verdict_check_rejects_unknown_value(db):
    with pytest.raises(asyncpg.CheckViolationError):
        seed_authorization(db, engine_verdict="'perhaps'")
    with pytest.raises(asyncpg.CheckViolationError):
        sql(db, "insert into mandates values ('TM9','x','sometimes',now())")


def test_money_and_time_column_types(db):
    rows = sql(db, """select table_name, column_name, data_type, numeric_precision, numeric_scale
                      from information_schema.columns where table_schema = 'public'""")
    cols = {(r["table_name"], r["column_name"]): r for r in rows}
    for table, column in [("authorizations", "billing_chf"), ("auth_history", "billing_chf")]:
        c = cols[(table, column)]
        assert (c["data_type"], c["numeric_precision"], c["numeric_scale"]) == ("numeric", 12, 2)
    for table, column in [("authorizations", "sim_ts"), ("authorizations", "received_at"),
                          ("authorizations", "deadline_at"), ("authorizations", "ask_expires_at"),
                          ("auth_history", "ts"), ("decision_events", "at")]:
        assert cols[(table, column)]["data_type"] == "timestamp with time zone", (table, column)
    assert ("authorizations", "sim_ts") in cols and ("authorizations", "deadline_at") in cols


def test_familiarity_view_counts_approved_purchases_only(db):
    rows = [("TR1", "purchase", "approved"), ("TR2", "purchase", "approved"), ("TR3", "refund", "approved"),
            ("TR4", "cash_withdrawal", "approved"), ("TR5", "purchase", "declined")]
    sql(db, *[f"""insert into auth_history (authorization_id, card_id, merchant_id, ts, transaction_type, status,
                   billing_chf, device_id, country, initiator)
                   values ('{i}','CA0011','ME0028','2026-01-01T00:00:00Z','{t}','{s}',10.00,null,'CH','human')"""
              for i, t, s in rows],
        "refresh materialized view card_merchant_familiarity")
    count = sql(db, "select approved_purchases from card_merchant_familiarity where card_id='CA0011' and merchant_id='ME0028'")
    assert count[0]["approved_purchases"] == 2


def test_upgrade_and_downgrade_are_clean(test_database_url):
    cfg = alembic(test_database_url)
    command.upgrade(cfg, "head")
    tables = {r["tablename"] for r in sql(test_database_url, "select tablename from pg_tables where schemaname='public'")}
    assert TABLES <= tables
    command.downgrade(cfg, "base")
    left = {r["tablename"] for r in sql(test_database_url, "select tablename from pg_tables where schemaname='public'")}
    assert left <= {"alembic_version"}
    assert not sql(test_database_url, "select 1 from pg_matviews where schemaname='public'")
    command.upgrade(cfg, "head")  # and again, from scratch
