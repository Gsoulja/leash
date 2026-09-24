"""Event translator: the API's event → Purchase + the run's mandate (LEASH-051)."""

import asyncio
import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from fake_api.app import FakeViseca
from leash.adapters.pack.loader import Pack
from leash.adapters.viseca_api.client import VisecaClient
from leash.adapters.viseca_api.event_schema import load_event_validator
from leash.adapters.viseca_api.translate import InvalidEvent, invalid_event_response, translate
from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.purchase import Term

DATA = Path(__file__).resolve().parents[4] / "data"
EXAMPLE = json.loads((DATA / "scenario_fixtures" / "example_authorization_request.json").read_text())
VALIDATE = load_event_validator(DATA / "schemas" / "authorization_event.schema.json")


def event(**changes):
    e = copy.deepcopy(EXAMPLE)
    for path, value in changes.items():
        node = e
        *parents, last = path.split("__")
        for p in parents:
            node = node[p]
        node[last] = value
    return e


def test_example_event_translates():
    t = translate(EXAMPLE, validate=VALIDATE)
    p = t.purchase
    assert (p.authorization_id, p.source_authorization_id, p.card_id) == ("AU_EXAMPLE_0001", "AU_EXAMPLE_0001",
                                                                          "CA_EXAMPLE_0001")
    assert (p.merchant.merchant_id, p.merchant.name, p.merchant.category, p.merchant.mcc) == (
        "ME_EXAMPLE_0001", "Example Market", "groceries", "5411")
    assert p.merchant.recurring_capable is False
    assert p.amount == Decimal("20.00") and p.billing_amount_chf == Decimal("20.00") and p.delivery_fee == Decimal("2.00")
    assert [(i.item_id, i.quantity, i.unit_price, i.details) for i in p.items] == [
        ("IT_EXAMPLE_0001", 1, Decimal("18.00"), "Synthetic parser example")]
    assert t.mandate_id == "TM_EXAMPLE_0001" and t.mandate.uncertainty == "ask"
    assert t.deadline_at.at.isoformat() == "2026-08-12T09:00:08+00:00" and t.integrity == ()


def test_null_delivery_by_stays_none():
    t = translate(event(authorization__delivery_by=None, authorization__related_authorization_id=None), validate=VALIDATE)
    assert t.purchase.delivery_by is None and t.purchase.related_authorization_id is None
    assert t.platform_period_spend_chf == Decimal("0.00")
    t2 = translate(event(context__approved_spend_in_period_chf=None), validate=VALIDATE)
    assert t2.platform_period_spend_chf is None
    t3 = translate(event(authorization__delivery_by="2026-08-10"), validate=VALIDATE)
    assert t3.purchase.delivery_by == date(2026, 8, 10)


def test_tri_states_and_amounts_are_typed():
    t = translate(event(authorization__order_returnable="true", authorization__order_cancellable="not_applicable",
                        authorization__amount=19.99, authorization__billing_amount_chf=19.99), validate=VALIDATE)
    assert t.purchase.order_returnable is Term.TRUE and t.purchase.order_cancellable is Term.NOT_APPLICABLE
    assert isinstance(t.purchase.amount, Decimal) and t.purchase.amount == Decimal("19.99")


def test_live_and_source_ids_are_kept_separate():
    t = translate(event(authorization__authorization_id="AZ-live-1", authorization__source_authorization_id="AU0035"),
                  validate=VALIDATE)
    assert (t.purchase.authorization_id, t.purchase.source_authorization_id) == ("AZ-live-1", "AU0035")


def test_the_events_mandate_is_compiled_from_its_hard_rules():
    rules = [{"field": "authorization.billing_amount_chf", "operator": "<=", "value": 20, "currency": "CHF",
              "scope": "purchase"}, {"field": "leash.merchant.carbon_score.v1", "operator": "<=", "value": 3}]
    t = translate(event(mandate__hard_rules=rules, mandate__uncertainty_policy="decline"), validate=VALIDATE)
    assert t.mandate.rules[0] == Rule(m.F_BILLING_CHF, "<=", Decimal("20"), currency="CHF", scope="purchase")
    assert t.mandate.uncertainty == "decline"
    assert len(t.mandate.unsupported_rules()) == 1  # kept, enforced as unsupported (DEC-005)


@pytest.mark.parametrize("change, fragment", [
    ({"authorization__amount": "20.00"}, "amount"),
    ({"authorization__order_returnable": "maybe"}, "order_returnable"),
    ({"type": "something.else"}, "type"),
    ({"authorization__items": []}, "items"),
])
def test_invalid_events_are_rejected_with_a_clear_error(change, fragment):
    with pytest.raises(InvalidEvent) as exc:
        translate(event(**change), validate=VALIDATE)
    assert fragment in str(exc.value) and exc.value.authorization_id == "AU_EXAMPLE_0001"


def test_without_a_validator_the_translator_still_refuses_bad_types():
    with pytest.raises(InvalidEvent):
        translate(event(authorization__billing_amount_chf="lots"))
    with pytest.raises(InvalidEvent) as exc:
        translate({"type": "authorization.request"})
    assert exc.value.authorization_id is None


def test_an_invalid_event_with_a_readable_id_gets_a_safe_step_up():
    body = invalid_event_response("AU_EXAMPLE_0001", "amount must be a number", engine_version="leash-test")
    assert body["decision"] == "step_up" and body["reason_codes"] == ["invalid_event"]
    assert body["authorization_id"] == "AU_EXAMPLE_0001" and body["engine_version"] == "leash-test"


def test_billing_amount_is_checked_against_the_rate():
    ok = translate(event(authorization__currency="EUR", authorization__amount=100.0,
                         authorization__billing_amount_chf=95.0), validate=VALIDATE)
    assert ok.integrity == ()
    bad = translate(event(authorization__currency="EUR", authorization__amount=100.0,
                          authorization__billing_amount_chf=50.0), validate=VALIDATE)
    assert len(bad.integrity) == 1 and "amount_mismatch" in bad.integrity[0] and "CHF 95.00" in bad.integrity[0]


def test_every_pack_event_from_the_fake_platform_translates_back_to_its_purchase():
    pack = Pack(DATA)
    fake = FakeViseca(pack, api_key="k")
    client = VisecaClient("k", "http://fake", transport=httpx.ASGITransport(app=fake.app))

    async def go():
        events = []
        for scenario in sorted({a.scenario_id for a in pack.attempts()}):
            draft = await client.create_mandate({"instruction": "t", "hard_rules": [], "uncertainty_policy": "ask",
                                                 "guidance": [], "open_questions": []})
            mid = (await client.confirm_mandate(draft["draft_id"]))["mandate_id"]
            await client.start_run(scenario, mid)
            while (envelope := await client.next_decision_request(wait=0)) is not None:
                aid = envelope["data"]["authorization"]["authorization_id"]
                events.append(envelope["data"])
                await client.post_decision(aid, {"authorization_id": aid, "decision": "decline"})
        return events

    events = asyncio.run(go())
    assert len(events) == 45
    for e in events:
        t = translate(e, validate=VALIDATE)
        original = pack.attempt(t.purchase.source_authorization_id).purchase
        p = t.purchase
        assert p.authorization_id != original.authorization_id
        for field in ("card_id", "merchant", "sim_time", "amount", "currency", "billing_amount_chf", "items_subtotal",
                      "delivery_fee", "channel", "device_id", "recent_attempts_10m", "fulfillment", "delivery_by",
                      "order_returnable", "order_cancellable", "related_status", "description", "items"):
            assert getattr(p, field) == getattr(original, field), (field, e["authorization"]["source_authorization_id"])
        assert t.integrity == ()


@pytest.mark.parametrize("path, value", [
    ("authorization__amount", 1e30), ("authorization__billing_amount_chf", float("nan")),
    ("authorization__amount", float("inf")), ("context__approved_spend_in_period_chf", float("inf")),
    ("authorization__amount", 19.995), ("authorization__delivery_fee", 0.004),
])
def test_numbers_that_arent_exact_cents_are_invalid_events(path, value):
    with pytest.raises(InvalidEvent) as exc:
        translate(event(**{path: value}), validate=VALIDATE)
    assert exc.value.authorization_id == "AU_EXAMPLE_0001"


def test_line_amounts_are_checked_too():
    e = event()
    e["authorization"]["items"][0]["unit_price"] = 1e30
    with pytest.raises(InvalidEvent):
        translate(e, validate=VALIDATE)


@pytest.mark.parametrize("path, value", [
    ("deadline_at", "2026-08-12 08:59:59Z"), ("deadline_at", "20260812T085959Z"),
    ("authorization__timestamp", "2026-08-12T08:59:59"), ("authorization__delivery_by", "2026-W33-1"),
])
def test_timestamps_and_dates_must_be_rfc3339(path, value):
    with pytest.raises(InvalidEvent):
        translate(event(**{path: value}))


def test_the_invalid_event_evidence_is_escaped():
    body = invalid_event_response("AZ-1", 'merchant_mcc: "<img src=x onerror=alert(1)>" is not valid',
                                  engine_version="t")
    assert all("<" not in line for line in body["evidence"])


@pytest.mark.parametrize("path", ["authorization__timestamp", "deadline_at", "runtime__received_at"])
@pytest.mark.parametrize("value", ["9999-12-31T23:59:59-23:59", "0001-01-01T00:00:00+23:59"])
@pytest.mark.parametrize("validate", [None, VALIDATE])
def test_a_timestamp_outside_the_utc_range_is_an_invalid_event(path, value, validate):
    with pytest.raises(InvalidEvent) as exc:
        translate(event(**{path: value}), validate=validate)
    assert exc.value.authorization_id == "AU_EXAMPLE_0001"


def test_an_envelope_without_an_event_object_is_invalid():
    from leash.adapters.viseca_api.translate import request_from_envelope

    for envelope in ({"run_id": "R1"}, {"run_id": "R1", "data": "nope"}):
        with pytest.raises(InvalidEvent, match="envelope/data"):
            request_from_envelope(envelope)
    request, _ = request_from_envelope({"run_id": "R1", "data": event()}, validate=VALIDATE)
    assert request.run_id == "R1" and request.purchase.authorization_id == "AU_EXAMPLE_0001"
