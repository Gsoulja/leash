"""The DecisionStore port on Postgres (LEASH-053): receive, decide, record_fallback, mark_sent."""

from datetime import timedelta

from adapters.test_decision_transaction import NOW, WEEK_300, buy, db, with_pool  # noqa: F401 - fixture
from factories import facts
from leash.adapters.postgres.unit_of_work import PostgresDecisionStore

STEP_UP = {"authorization_id": "A", "decision": "step_up", "reason_codes": ["decision_timeout"],
           "customer_message": "I ran out of time, so I'm asking you.", "evidence": []}


def test_fallback_on_a_received_purchase_records_a_waiting_step_up_with_its_outbox_row(db):  # noqa: F811
    async def body(pool):
        store = PostgresDecisionStore(pool, engine_version="t")
        p = buy("A", "20.00")
        assert await store.receive(p, run_id="RUN1", event={}, received_at=NOW,
                                   deadline_at=NOW + timedelta(seconds=8)) is None
        assert await store.record_fallback(p, run_id="RUN1", response=STEP_UP,
                                           ask_expires_at=NOW + timedelta(seconds=120)) is None
        row = await pool.fetchrow("select state, engine_verdict, ask_expires_at from authorizations "
                                  "where authorization_id = 'A'")
        outbox = await pool.fetch("select endpoint, sent_at from outbox where authorization_id = 'A'")
        events = await pool.fetch("select kind from decision_events where authorization_id = 'A' order by seq")
        repeat = await store.receive(p, run_id="RUN1", event={}, received_at=NOW,
                                     deadline_at=NOW + timedelta(seconds=8))
        return row, outbox, events, repeat

    row, outbox, events, repeat = with_pool(db, body)
    assert (row["state"], row["engine_verdict"]) == ("waiting", "step_up") and row["ask_expires_at"] is not None
    assert [(r["endpoint"], r["sent_at"]) for r in outbox] == [("decision", None)]
    assert [e["kind"] for e in events] == ["received", "decided"]
    assert repeat.engine_verdict == "step_up" and repeat.response["decision"] == "step_up"


def test_fallback_after_a_committed_decision_returns_that_decision_and_changes_nothing(db):  # noqa: F811
    async def body(pool):
        store = PostgresDecisionStore(pool, engine_version="t")
        p = buy("A", "20.00")
        await store.receive(p, run_id="RUN1", event={}, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))
        await store.decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
        saved = await store.record_fallback(p, run_id="RUN1", response=STEP_UP,
                                            ask_expires_at=NOW + timedelta(seconds=120))
        count = await pool.fetchval("select count(*) from outbox where authorization_id = 'A'")
        return saved, count

    saved, count = with_pool(db, body)
    assert saved.engine_verdict == "approve" and saved.response["decision"] == "approve" and count == 1


def test_mark_sent_closes_the_decision_row_so_the_outbox_never_resends_it(db):  # noqa: F811
    async def body(pool):
        store = PostgresDecisionStore(pool, engine_version="t")
        p = buy("A", "20.00")
        await store.receive(p, run_id="RUN1", event={}, received_at=NOW, deadline_at=NOW + timedelta(seconds=8))
        await store.decide(p, run_id="RUN1", mandate=WEEK_300, facts=facts(), platform_period_spend_chf=None)
        await store.mark_sent("A")
        return await pool.fetchval("select count(*) from outbox where authorization_id = 'A' and sent_at is null")

    assert with_pool(db, body) == 0


def test_a_run_first_seen_in_an_event_is_recorded_with_the_events_mandate(db):  # noqa: F811
    event = {"mandate": {"mandate_id": "TM9", "instruction": "Buy it", "uncertainty_policy": "decline",
                         "hard_rules": [{"field": "authorization.billing_amount_chf", "operator": "<=", "value": 50,
                                         "currency": "CHF", "scope": "purchase"}]}}

    async def body(pool):
        store = PostgresDecisionStore(pool, engine_version="t")
        for aid, run in (("A", "RUN9"), ("B", "RUN9"), ("C", "RUN10")):
            await store.receive(buy(aid, "20.00"), run_id=run, event=event, received_at=NOW,
                                deadline_at=NOW + timedelta(seconds=8))
        runs = await pool.fetch("select run_id, mandate_id, mandate_version from runs where run_id like 'RUN%' "
                                "and run_id <> 'RUN1' order by run_id")
        versions = await pool.fetch("select version, uncertainty_policy from mandate_versions where mandate_id = 'TM9'")
        return runs, versions

    runs, versions = with_pool(db, body)
    assert [tuple(r) for r in runs] == [("RUN10", "TM9", 1), ("RUN9", "TM9", 1)]
    assert [tuple(v) for v in versions] == [(1, "decline")]  # the same snapshot is stored once
