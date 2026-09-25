"""LEASH-130: what the engine decided and what the platform accepted are two different facts.

`authorizations.state` used to carry both. A decision the platform terminally refused still read as
`approved`, so it counted toward spend, familiarity, duplicates and the purchase count, and the app
showed it as paid. These tests hold the two apart: acceptance is recorded with the send, a terminal
refusal leaves the purchase `not_sent`, and nothing refused is ever counted or shown as delivered.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from alembic import command

from leash.adapters.postgres.repository import PostgresRepository
from leash.adapters.viseca_api.client import VisecaApiError
from leash.adapters.viseca_api.outbox_sender import OutboxSender
from leash.application.reconcile import Reconciler
from leash.domain.states import IllegalTransition, delivery_transition
from test_schema import alembic, sql

DATA = Path(__file__).resolve().parents[4] / "data"
T0 = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(test_database_url):
    command.upgrade(alembic(test_database_url), "head")
    return test_database_url


def add_authorization(url, aid, *, state="approved", chf="20.00", card="CA0001", run=None,
                      merchant="ME0022", sim="2026-08-12T09:40:00Z"):
    purchase = {"authorization_id": aid, "source_authorization_id": None, "card_id": card,
                "merchant": {"merchant_id": merchant, "name": "PixelHarbor", "category": "electronics",
                             "mcc": "5732", "country": "CH", "city": "Zurich", "availability": "online",
                             "recurring_capable": False},
                "sim_time": sim, "amount": chf, "currency": "CHF", "billing_amount_chf": chf,
                "items_subtotal": chf, "delivery_fee": "0.00", "channel": "online", "device_id": None,
                "recent_attempts_10m": 0, "fulfillment": "delivery", "delivery_by": None,
                "order_returnable": "unknown", "order_cancellable": "unknown",
                "related_authorization_id": None, "related_status": None, "description": "",
                "items": [{"line_no": 1, "item_id": "IT0017", "name": "monitor", "category": "electronics",
                           "quantity": 1, "unit_price": chf, "currency": "CHF", "details": ""}]}
    sql(url, "insert into authorizations (authorization_id, card_id, merchant_id, sim_ts, billing_chf,"
             " item_fingerprint, state, engine_verdict, received_at, deadline_at, event, purchase)"
             f" values ('{aid}', '{card}', '{merchant}', '{sim}', {chf}, '[]'::jsonb, '{state}',"
             f" 'approve', now(), now(), '{{}}'::jsonb, '{json.dumps(purchase)}'::jsonb)")
    sql(url, "insert into decision_events (authorization_id, kind, payload) values "
             f"('{aid}', 'received', '{{}}'::jsonb), ('{aid}', 'decided', '{{\"verdict\": \"approve\"}}'::jsonb)")


def add_outbox(url, aid, body=None):
    body = body or {"authorization_id": aid, "decision": "approve"}
    sql(url, f"insert into outbox (authorization_id, endpoint, body, created_at) "
             f"values ('{aid}', 'decision', '{json.dumps(body)}', '{T0.isoformat()}')")


def read(url, aid, columns="state, delivery, platform_outcome"):
    async def go():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchrow(f"select {columns} from authorizations where authorization_id = $1", aid)
        finally:
            await conn.close()
    return asyncio.run(go())


def with_pool(url, work):
    async def go():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            return await work(pool)
        finally:
            await pool.close()
    return asyncio.run(go())


class FakeClient:
    def __init__(self, fail=None):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail or {}

    async def post_decision(self, aid, body, timeout=None):
        self.calls.append((aid, body))
        error = self.fail.get(aid)
        if error:
            raise error
        return {"data": {}}

    async def resolve(self, aid, body):
        return {"data": {}}


# --- AC1: three facts, three columns -----------------------------------------------------------

def test_the_verdict_the_delivery_and_the_platform_outcome_are_separate(db):
    add_authorization(db, "AZ-1")
    row = read(db, "AZ-1", "engine_verdict, state, delivery, platform_outcome")
    assert (row["engine_verdict"], row["state"]) == ("approve", "approved")
    assert (row["delivery"], row["platform_outcome"]) == ("pending", None), \
        "a decision starts undelivered: nothing has been accepted yet"


def test_a_delivery_outcome_is_recorded_once_and_never_revised():
    assert delivery_transition("pending", "accepted", "platform") == "accepted"
    assert delivery_transition("pending", "refused", "platform") == "refused"
    for already in ("accepted", "refused"):
        with pytest.raises(IllegalTransition):
            delivery_transition(already, "accepted", "platform")
    with pytest.raises(IllegalTransition):
        delivery_transition("pending", "accepted", "engine")  # only the platform can accept


# --- AC2: acceptance lands with the send, in one transaction -----------------------------------

def test_a_successful_post_records_acceptance_with_the_outbox_close(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    client = FakeClient()
    with_pool(db, lambda pool: OutboxSender(pool, client, clock=lambda: T0, grace_seconds=0).send_pending())
    row = read(db, "AZ-1")
    assert (row["state"], row["delivery"], row["platform_outcome"]) == ("approved", "accepted", "accepted")
    closed = asyncio.run(_scalar(db, "select sent_at is not null and last_error is null from outbox"))
    assert closed is True


def test_the_immediate_send_path_records_acceptance_too(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    assert read(db, "AZ-1")["delivery"] == "accepted"


def test_a_second_pass_changes_nothing(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    later = T0 + timedelta(minutes=5)
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: later).mark_sent("AZ-1"))
    row = read(db, "AZ-1", "delivery, delivered_at")
    assert row["delivery"] == "accepted" and row["delivered_at"] == T0


# --- AC3 and AC4: a terminal refusal is not an approval ----------------------------------------

def refuse(url, aid, status=422, code="deadline_passed"):
    error = VisecaApiError(status, "POST", f"/v1/authorizations/{aid}/decision", {"code": code, "message": "too late"})
    client = FakeClient(fail={aid: error})
    with_pool(url, lambda pool: OutboxSender(pool, client, clock=lambda: T0, grace_seconds=0).send_pending())
    return client


def test_a_terminal_refusal_leaves_the_purchase_not_sent(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    refuse(db, "AZ-1")
    row = read(db, "AZ-1")
    assert row["state"] == "not_sent", "an answer the platform will never accept is not an approval"
    assert row["delivery"] == "refused" and "deadline_passed" in row["platform_outcome"]


def test_a_retryable_failure_leaves_the_delivery_pending(db):
    """A 503 is not a refusal: the answer may still land, so the reservation stays."""
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    error = VisecaApiError(503, "POST", "/x", {"code": "unavailable", "message": "later"})
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(fail={"AZ-1": error}), clock=lambda: T0,
                                            grace_seconds=0).send_pending())
    row = read(db, "AZ-1")
    assert (row["state"], row["delivery"]) == ("approved", "pending")


def test_a_refused_decision_counts_toward_nothing(db):
    """Spend, familiarity, duplicates and the purchase count all read the same prior list."""
    add_authorization(db, "AZ-kept", chf="30.00")
    add_authorization(db, "AZ-refused", chf="70.00")
    add_outbox(db, "AZ-refused")
    refuse(db, "AZ-refused")

    async def snapshot(pool):
        return await PostgresRepository(pool).snapshot("CA0001", run_id=None, platform_period_spend_chf=None)

    prior = with_pool(db, snapshot).prior
    ids = [p.purchase.authorization_id for p in prior]
    assert ids == ["AZ-kept"], "a refused decision must not appear in the ledger at all"
    assert sum(p.purchase.billing_amount_chf for p in prior if p.state == "approved") == Decimal("30.00")


# --- AC6: a body that was never accepted is not "sent to Viseca" -------------------------------

def test_sent_to_viseca_is_empty_for_a_refused_delivery(db):
    """Through the endpoint the app actually calls — re-typing the query here would pass whatever
    `query_api` did."""
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    refuse(db, "AZ-1")
    seen = _payment(db, "AZ-1")
    assert seen["sent_to_viseca"] is None, "the outbox closes a refused row too; that is not a delivery"
    assert seen["delivery"] == "refused" and seen["final_state"] == "not_sent"


def test_sent_to_viseca_shows_the_body_of_an_accepted_delivery(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    seen = _payment(db, "AZ-1")
    assert seen["sent_to_viseca"] == {"authorization_id": "AZ-1", "decision": "approve"}
    assert seen["delivery"] == "accepted"


def _payment(url: str, aid: str) -> dict:
    """GET /api/payments/{id}, through the app the customer's screen actually calls."""
    from fastapi.testclient import TestClient

    from leash.adapters.http.query_api import create_query_app

    class _NoMandates:
        def for_run(self, run_id):  # the payment view needs no mandate
            raise LookupError(run_id)

    with TestClient(create_query_app(url, _NoMandates(), clock=lambda: datetime.now(timezone.utc))) as http:
        return http.get(f"/api/payments/{aid}").json()


# --- AC7: reconciliation repairs or alerts, never overwrites ------------------------------------

class FakePlatform:
    def __init__(self, rows):
        self.rows = rows

    async def list_authorizations(self):
        return {"data": {"authorizations": self.rows}}


def reconcile(url, rows):
    return with_pool(url, lambda pool: Reconciler(pool, FakePlatform(rows), clock=lambda: T0).run_once())


def test_reconciliation_fills_in_a_delivery_the_platform_has_decided(db):
    add_authorization(db, "AZ-1")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "approved"}])
    assert found.repaired and not found.alerts
    assert read(db, "AZ-1")["delivery"] == "accepted"


def test_platform_waiting_for_customer_agrees_with_our_step_up(db):
    add_authorization(db, "AZ-1", state="waiting")
    rows = [{"authorization_id": "AZ-1", "status": "waiting_for_customer"}]
    first = reconcile(db, rows)
    assert first.repaired and not first.alerts
    assert tuple(read(db, "AZ-1").values()) == ("waiting", "accepted", "waiting_for_customer")
    again = reconcile(db, rows)
    assert not again.repaired and not again.alerts


def test_reconciliation_records_a_platform_refusal_as_not_sent(db):
    add_authorization(db, "AZ-1")
    reconcile(db, [{"authorization_id": "AZ-1", "status": "deadline_passed"}])
    row = read(db, "AZ-1")
    assert (row["state"], row["delivery"]) == ("not_sent", "refused")


def test_a_real_disagreement_raises_an_alert_and_changes_nothing(db):
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "declined"}])
    assert found.alerts and not found.repaired
    assert read(db, "AZ-1")["state"] == "approved", "a disagreement is never resolved by overwriting"
    alerts = asyncio.run(_scalar(db, "select count(*) from decision_events where kind = 'integrity_alert'"))
    assert alerts == 1


def test_an_authorization_we_do_not_know_is_reported_not_invented(db):
    found = reconcile(db, [{"authorization_id": "AZ-someone-else", "status": "approved"}])
    assert found.unknown_to_us == ["AZ-someone-else"] and not found.repaired and not found.alerts


def test_a_platform_word_we_do_not_understand_is_an_alert_not_a_pass(db):
    add_authorization(db, "AZ-1")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "quantum"}])
    assert found.alerts and read(db, "AZ-1")["delivery"] == "pending"


def test_reconciliation_never_makes_a_purchase_less_restrictive(db):
    """The platform reporting an approval for a purchase we declined is a disagreement, not new
    information to adopt. The only state change the reconciler may cause is toward `not_sent`."""
    add_authorization(db, "AZ-1", state="declined")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "approved"}])
    assert found.alerts and not found.repaired
    row = read(db, "AZ-1")
    assert (row["state"], row["delivery"]) == ("declined", "pending")


def test_a_pending_delivery_the_platform_agrees_with_is_accepted(db):
    """Our decline, acknowledged: the delivery landed even though the purchase did not."""
    add_authorization(db, "AZ-1", state="declined")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "declined"}])
    assert found.repaired and read(db, "AZ-1")["delivery"] == "accepted"
    assert read(db, "AZ-1")["state"] == "declined"


# --- AC8: a local approval reserves; only the platform's acceptance is accepted -----------------

def test_an_approval_awaiting_acknowledgement_still_holds_its_spend(db):
    """Counting only acknowledged spend would let two concurrent purchases both pass while their
    acknowledgements were outstanding. The reservation is what stops that."""
    add_authorization(db, "AZ-1", chf="60.00")

    async def snapshot(pool):
        return await PostgresRepository(pool).snapshot("CA0001", run_id=None, platform_period_spend_chf=None)

    prior = with_pool(db, snapshot).prior
    assert [p.purchase.authorization_id for p in prior] == ["AZ-1"]
    assert read(db, "AZ-1")["delivery"] == "pending", "reserved before it is acknowledged"


def test_a_refusal_releases_the_reservation(db):
    add_authorization(db, "AZ-1", chf="60.00")
    add_outbox(db, "AZ-1")
    refuse(db, "AZ-1")

    async def snapshot(pool):
        return await PostgresRepository(pool).snapshot("CA0001", run_id=None, platform_period_spend_chf=None)

    assert with_pool(db, snapshot).prior == (), "the spend a refused decision held must be released"


# --- the migration's own backfill ---------------------------------------------------------------

def test_the_migration_reads_delivery_out_of_the_outbox(test_database_url):
    """Rows written before 0009 have no delivery column; the outbox already knows what happened."""
    command.upgrade(alembic(test_database_url), "0008")
    for aid, state in (("AZ-accepted", "approved"), ("AZ-refused", "approved"), ("AZ-pending", "approved")):
        add_authorization(test_database_url, aid, state=state)
        add_outbox(test_database_url, aid)
    sql(test_database_url, "update outbox set sent_at = now() where authorization_id = 'AZ-accepted'")
    sql(test_database_url, "update outbox set sent_at = now(), last_error = 'HTTP 422 deadline_passed' "
                           "where authorization_id = 'AZ-refused'")
    command.upgrade(alembic(test_database_url), "head")
    assert read(test_database_url, "AZ-accepted")["delivery"] == "accepted"
    assert read(test_database_url, "AZ-refused")["delivery"] == "refused"
    assert read(test_database_url, "AZ-pending")["delivery"] == "pending"
    # and the refusal releases the spend, as it does for every row written after 0009: recording the
    # refusal while leaving `state = 'approved'` would reintroduce the bug for every older row
    assert read(test_database_url, "AZ-refused")["state"] == "not_sent"
    assert read(test_database_url, "AZ-accepted")["state"] == "approved"

    async def prior(pool):
        return await PostgresRepository(pool).snapshot("CA0001", run_id=None, platform_period_spend_chf=None)

    kept = [p.purchase.authorization_id for p in with_pool(test_database_url, prior).prior]
    assert "AZ-refused" not in kept, "a backfilled refusal must not count toward spend either"


# --- round 2: the gaps the independent review found ---------------------------------------------

def test_a_row_still_being_decided_is_left_alone(db):
    """`received` means the worker owns it. An acknowledgement written here would be for a decision
    that does not exist — and because a delivery outcome is recorded once, it would make the real one
    unrecordable, so a later genuine refusal would be silently dropped."""
    add_authorization(db, "AZ-1", state="received")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "pending"}])
    assert found.in_flight == ["AZ-1"] and not found.repaired and not found.alerts
    row = read(db, "AZ-1")
    assert (row["state"], row["delivery"]) == ("received", "pending")


def test_a_refusal_the_platform_reports_for_an_undecided_row_is_not_applied_either(db):
    """The same row, the other direction: taking it to `not_sent` would collide with the decision the
    worker is about to commit."""
    add_authorization(db, "AZ-1", state="received")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "deadline_passed"}])
    assert found.in_flight == ["AZ-1"]
    assert read(db, "AZ-1")["state"] == "received"


def test_a_refusal_whose_release_never_happened_is_repaired(db):
    """The shape an older backfill could leave: refused, but still counting as approved."""
    add_authorization(db, "AZ-1", chf="70.00")
    sql(db, "update authorizations set delivery = 'refused', platform_outcome = 'deadline_passed' "
            "where authorization_id = 'AZ-1'")
    found = reconcile(db, [{"authorization_id": "AZ-1", "status": "deadline_passed"}])
    assert found.repaired and not found.alerts
    assert read(db, "AZ-1")["state"] == "not_sent"

    async def snapshot(pool):
        return await PostgresRepository(pool).snapshot("CA0001", run_id=None, platform_period_spend_chf=None)

    assert with_pool(db, snapshot).prior == (), "the repair must release the spend it was holding"


def test_the_same_disagreement_is_recorded_once_not_every_pass(db):
    """An append-only log nobody can read is as bad as no log."""
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    rows = [{"authorization_id": "AZ-1", "status": "declined"}]
    for _ in range(3):
        assert reconcile(db, rows).alerts
    alerts = asyncio.run(_scalar(db, "select count(*) from decision_events where kind = 'integrity_alert'"))
    assert alerts == 1


def test_a_successful_send_clears_an_earlier_retryable_error(db):
    """`sent_to_viseca` reads `last_error is null` as "the platform took this body". A stale error from
    an attempt that failed and was retried would hide a decision Viseca did accept."""
    add_authorization(db, "AZ-1")
    add_outbox(db, "AZ-1")
    error = VisecaApiError(503, "POST", "/x", {"code": "unavailable", "message": "later"})
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(fail={"AZ-1": error}), clock=lambda: T0,
                                            grace_seconds=0).send_pending())
    assert asyncio.run(_scalar(db, "select last_error from outbox where authorization_id = 'AZ-1'")) is not None
    with_pool(db, lambda pool: OutboxSender(pool, FakeClient(), clock=lambda: T0).mark_sent("AZ-1"))
    assert _payment(db, "AZ-1")["sent_to_viseca"] is not None, "an accepted decision must read as sent"
    assert read(db, "AZ-1")["delivery"] == "accepted"


def test_the_platform_spend_recheck_ignores_a_refusal_recorded_after_the_purchase_arrived(db):
    """Ordering matters: `platform_spend_now` only sums approvals recorded *after* the purchase came in,
    so a refusal recorded before it would pass this check without the state change doing any work."""
    add_authorization(db, "AZ-now", chf="10.00")
    sql(db, "update authorizations set event = '{\"context\": {\"approved_spend_in_period_chf\": \"0.00\"}}'::jsonb "
            "where authorization_id = 'AZ-now'")
    add_authorization(db, "AZ-later", chf="70.00")  # arrives, and is approved, after AZ-now
    add_outbox(db, "AZ-later")

    async def recheck(pool):
        async with pool.acquire() as conn:
            return await PostgresRepository.platform_spend_now(conn, "AZ-now")

    assert with_pool(db, recheck) == Decimal("70.00"), "a live approval counts against the re-check"
    refuse(db, "AZ-later")
    assert with_pool(db, recheck) == Decimal("0.00"), "a refused one does not"


async def _scalar_conn(url, query):
    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(query)
    finally:
        await conn.close()


def _scalar(url, query):
    return _scalar_conn(url, query)


def test_live_pending_step_up_and_external_resolution_stay_truthful(db):
    add_authorization(db, "AZ-live", state="waiting")
    found = reconcile(db, [{"authorization_id": "AZ-live", "status": "pending_step_up"}])
    assert not found.alerts and read(db, "AZ-live")["delivery"] == "accepted"
    found = reconcile(db, [{"authorization_id": "AZ-live", "status": "approved"}])
    row = read(db, "AZ-live")
    assert found.alerts and row["state"] == "waiting"
    assert row["platform_outcome"] == "conflict:approved"
