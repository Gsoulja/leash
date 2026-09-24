"""The run's stored mandate snapshot as a MandateSource for the API and the resolve re-check (LEASH-127)."""

from decimal import Decimal

import pytest

from adapters.test_decision_transaction import db, with_pool  # noqa: F401 - fixture
from leash.adapters.postgres.mandates import StoredMandates
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from test_schema import sql


def test_each_run_gets_its_own_version_compiled_from_its_hard_rules(db):  # noqa: F811
    sql(db, "insert into mandate_versions values ('TM1', 2, '[{\"field\": \"authorization.billing_amount_chf\", "
            "\"operator\": \"<=\", \"value\": 50, \"currency\": \"CHF\", \"scope\": \"purchase\"}]', 'decline', "
            "'{}', now())",
        "insert into runs values ('RUN2', 'SCEN0001', 'TM1', 2, 'CA0001', now())")
    mandates = StoredMandates()

    async def body(pool):
        await mandates.refresh(pool)

    with_pool(db, body)
    assert mandates.for_run("RUN1").rules == () and mandates.for_run("RUN1").uncertainty == "ask"
    assert mandates.for_run("RUN2").rules == (Rule(m.F_BILLING_CHF, "<=", Decimal("50"), currency="CHF",
                                                   scope="purchase"),)
    assert mandates.for_run("RUN2").uncertainty == "decline"


def test_an_unknown_run_is_refused_never_given_an_empty_mandate(db):  # noqa: F811
    with pytest.raises(LookupError):
        StoredMandates().for_run("RUN-nope")
    with pytest.raises(LookupError):
        StoredMandates().for_run(None)


def test_one_unreadable_snapshot_leaves_only_its_run_unknown(db):  # noqa: F811
    sql(db, "insert into mandate_versions values ('TM1', 3, '[{\"field\": \"x\"}]', 'ask', '{}', now())",
        "insert into runs values ('RUN3', 'SCEN0001', 'TM1', 3, 'CA0001', now())")
    mandates = StoredMandates()
    with_pool(db, mandates.refresh)
    assert mandates.for_run("RUN1").uncertainty == "ask"
    with pytest.raises(LookupError):
        mandates.for_run("RUN3")


def test_an_approval_check_for_a_run_started_a_moment_ago_loads_it_instead_of_failing(db):  # noqa: F811
    from leash.adapters.http.query_api import approval_check
    from leash.adapters.postgres.repository import PostgresRepository

    mandates = StoredMandates()  # empty: RUN1 has not been loaded yet

    async def body(pool):
        from adapters.test_decision_transaction import NOW, buy
        from datetime import timedelta
        p = buy("A", "20.00")
        await PostgresRepository(pool).receive(p, run_id="RUN1", event={}, received_at=NOW,
                                               deadline_at=NOW + timedelta(seconds=8))
        row = await pool.fetchrow("select authorization_id, run_id, card_id, purchase from authorizations "
                                  "where authorization_id = 'A'")
        async with pool.acquire() as conn:
            return await approval_check(conn, pool, mandates, row)

    can_approve, _ = with_pool(db, body)
    assert can_approve is True and mandates.for_run("RUN1").rules == ()
