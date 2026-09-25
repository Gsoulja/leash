"""Anti-corruption layer: a live authorization event → a Purchase, the run's mandate and the context
(LEASH-051, DEC-003).

The event's own mandate is authoritative for its run: it is compiled from its hard_rules through the
field registry's serializer (policy/hard_rules), never from the instruction text. Nulls stay None, the
string tri-states become Terms, and every amount becomes an exact Decimal. Live and source IDs stay
separate. The structural schema check is injected (adapters/viseca_api/event_schema.py); the translator
still refuses any value it can't type. billing_amount_chf is checked against amount × the pack's fixed
rate: a mismatch is reported as an integrity alert (amount_mismatch), never silently corrected.
"""

import html
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from leash.application.decide_purchase import DecisionRequest
from leash.domain.checks import Check
from leash.domain.clock import SimTime, WallTime
from leash.domain.decide import Decision
from leash.domain.explain import explain
from leash.domain.mandate import CompiledMandate
from leash.domain.money import FX_TO_CHF, fmt_chf, money, to_chf
from leash.domain.purchase import LineItem, Merchant, Purchase, Term
from leash.policy.hard_rules import HardRulesError, mandate_from_api

INVALID_EVENT = "invalid_event"
_MAX_AMOUNT = Decimal("1e12")
_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", re.I)


class InvalidEvent(ValueError):
    """The event can't be read safely. `authorization_id` is set when a live ID was still readable."""

    def __init__(self, message: str, authorization_id: str | None = None) -> None:
        super().__init__(message)
        self.authorization_id = authorization_id


@dataclass(frozen=True)
class TranslatedEvent:
    purchase: Purchase
    mandate: CompiledMandate  # compiled from the event's hard_rules: authoritative for the run
    mandate_id: str
    request_id: str
    deadline_at: WallTime
    received_at: WallTime | None
    platform_period_spend_chf: Decimal | None
    integrity: tuple[str, ...]  # alerts to raise (e.g. amount_mismatch); the decision still proceeds


def _live_id(event: Mapping[str, Any]) -> str | None:
    authorization = event.get("authorization") if isinstance(event, Mapping) else None
    value = authorization.get("authorization_id") if isinstance(authorization, Mapping) else None
    return value if isinstance(value, str) and value else None


class _Reader:
    def __init__(self, live_id: str | None) -> None:
        self.live_id = live_id

    def fail(self, where: str, why: str) -> InvalidEvent:
        return InvalidEvent(f"{where}: {why}", self.live_id)

    def obj(self, node: Any, where: str) -> Mapping[str, Any]:
        if not isinstance(node, Mapping):
            raise self.fail(where, "must be an object")
        return node

    def text(self, node: Mapping[str, Any], key: str, where: str, *, optional: bool = False) -> str | None:
        if key not in node:
            raise self.fail(f"{where}/{key}", "is required")
        value = node[key]
        if value is None and optional:
            return None
        if not isinstance(value, str) or (not optional and not value):
            raise self.fail(f"{where}/{key}", "must be a string")
        return value

    def req(self, node: Mapping[str, Any], key: str, where: str) -> str:
        value = self.text(node, key, where)
        assert value is not None
        return value

    def amount(self, node: Mapping[str, Any], key: str, where: str, *, optional: bool = False) -> Decimal | None:
        if key not in node:
            raise self.fail(f"{where}/{key}", "is required")
        value = node[key]
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self.fail(f"{where}/{key}", "must be a number")
        try:
            exact = Decimal(str(value))
        except InvalidOperation as exc:
            raise self.fail(f"{where}/{key}", "must be a number") from exc
        if not exact.is_finite() or abs(exact) >= _MAX_AMOUNT:
            raise self.fail(f"{where}/{key}", "must be a finite amount")
        if exact != exact.quantize(Decimal("0.01")):
            raise self.fail(f"{where}/{key}", "must be whole cents (at most two decimals)")  # never rounded silently
        return money(exact)

    def money_(self, node: Mapping[str, Any], key: str, where: str) -> Decimal:
        value = self.amount(node, key, where)
        assert value is not None
        return value

    def whole(self, node: Mapping[str, Any], key: str, where: str, minimum: int) -> int:
        value = node.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise self.fail(f"{where}/{key}", f"must be a whole number of at least {minimum}")
        return value

    def term(self, node: Mapping[str, Any], key: str, where: str) -> Term:
        try:
            return Term.parse(self.req(node, key, where))
        except ValueError as exc:
            raise self.fail(f"{where}/{key}", str(exc)) from exc

    def _timestamp(self, node: Mapping[str, Any], key: str, where: str) -> str:
        value = self.req(node, key, where)
        if not _RFC3339.fullmatch(value):
            raise self.fail(f"{where}/{key}", "must be an RFC 3339 timestamp with a time zone")
        return value

    def sim_time(self, node: Mapping[str, Any], key: str, where: str) -> SimTime:
        value = self._timestamp(node, key, where)
        try:
            return SimTime.parse(value)
        except ValueError as exc:
            raise self.fail(f"{where}/{key}", f"not a timestamp ({exc})") from exc

    def wall_time(self, node: Mapping[str, Any], key: str, where: str) -> WallTime:
        value = self._timestamp(node, key, where)
        try:
            return WallTime.parse(value)
        except ValueError as exc:
            raise self.fail(f"{where}/{key}", f"not a timestamp ({exc})") from exc


def translate(event: Mapping[str, Any], *, validate: Callable[[Mapping[str, Any]], None] | None = None
              ) -> TranslatedEvent:
    live_id = _live_id(event)
    if validate is not None:
        validate(event)
    r = _Reader(live_id)
    e = r.obj(event, "event")
    if e.get("type") != "authorization.request":
        raise r.fail("type", "must be authorization.request")
    a = r.obj(e.get("authorization"), "authorization")
    mer = r.obj(a.get("merchant"), "authorization/merchant")
    recurring = r.req(mer, "recurring_capable", "authorization/merchant")
    if recurring not in ("true", "false"):
        raise r.fail("authorization/merchant/recurring_capable", "must be \"true\" or \"false\"")
    items_node = a.get("items")
    if not isinstance(items_node, list) or not items_node:
        raise r.fail("authorization/items", "must hold at least one line")
    items = []
    for n, raw in enumerate(items_node):
        where = f"authorization/items/{n}"
        line = r.obj(raw, where)
        items.append(LineItem(line_no=r.whole(line, "line_no", where, 1), item_id=r.req(line, "item_id", where),
                              name=r.req(line, "item_name", where), category=r.req(line, "item_category", where),
                              quantity=r.whole(line, "quantity", where, 1),
                              unit_price=r.money_(line, "unit_price", where), currency=r.req(line, "currency", where),
                              details=r.text(line, "item_details", where, optional=True) or ""))
    delivery_by = r.text(a, "delivery_by", "authorization", optional=True)
    if delivery_by is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", delivery_by):
        raise r.fail("authorization/delivery_by", "must be a date (YYYY-MM-DD)")
    try:
        delivery_date = date.fromisoformat(delivery_by) if delivery_by else None
    except ValueError as exc:
        raise r.fail("authorization/delivery_by", "must be a date") from exc
    try:
        purchase = Purchase(
            authorization_id=r.req(a, "authorization_id", "authorization"),
            source_authorization_id=r.text(a, "source_authorization_id", "authorization", optional=True),
            card_id=r.req(a, "card_id", "authorization"),
            merchant=Merchant(merchant_id=r.req(mer, "merchant_id", "merchant"),
                              name=r.req(mer, "merchant_name", "merchant"),
                              category=r.req(mer, "merchant_category", "merchant"),
                              mcc=r.req(mer, "merchant_mcc", "merchant"),
                              country=r.req(mer, "merchant_country", "merchant"),
                              city=r.text(mer, "merchant_city", "merchant", optional=True) or "",
                              availability=r.req(mer, "availability", "merchant"),
                              recurring_capable=recurring == "true"),
            sim_time=r.sim_time(a, "timestamp", "authorization"),
            amount=r.money_(a, "amount", "authorization"), currency=r.req(a, "currency", "authorization"),
            billing_amount_chf=r.money_(a, "billing_amount_chf", "authorization"),
            items_subtotal=r.money_(a, "items_subtotal", "authorization"),
            delivery_fee=r.money_(a, "delivery_fee", "authorization"), channel=r.req(a, "channel", "authorization"),
            device_id=r.text(a, "customer_device_id", "authorization", optional=True),
            recent_attempts_10m=r.whole(a, "recent_attempt_count_10m", "authorization", 0),
            fulfillment=r.req(a, "fulfillment_method", "authorization"), delivery_by=delivery_date,
            order_returnable=r.term(a, "order_returnable", "authorization"),
            order_cancellable=r.term(a, "order_cancellable", "authorization"),
            related_authorization_id=r.text(a, "related_authorization_id", "authorization", optional=True),
            related_status=r.text(a, "related_authorization_status", "authorization", optional=True),
            description=r.text(a, "purchase_description", "authorization", optional=True) or "",
            items=tuple(sorted(items, key=lambda i: i.line_no)),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, InvalidEvent):
            raise
        raise r.fail("authorization", str(exc)) from exc

    mn = r.obj(e.get("mandate"), "mandate")
    try:
        mandate, _ = mandate_from_api({"instruction": r.req(mn, "instruction", "mandate"),
                                       "hard_rules": mn.get("hard_rules"),
                                       "uncertainty_policy": mn.get("uncertainty_policy")})
    except HardRulesError as exc:
        raise r.fail("mandate", str(exc)) from exc
    context = r.obj(e.get("context"), "context")
    runtime = r.obj(e.get("runtime"), "runtime")

    integrity: list[str] = []
    if purchase.currency in FX_TO_CHF:
        expected = to_chf(purchase.amount, purchase.currency)
        if expected != purchase.billing_amount_chf:
            integrity.append(f"amount_mismatch: {purchase.currency} {purchase.amount} is {fmt_chf(expected)} at the "
                             f"fixed rate, but billing_amount_chf says {fmt_chf(purchase.billing_amount_chf)}")
    else:
        integrity.append(f"amount_mismatch: no fixed rate for {purchase.currency}; billing_amount_chf can't be checked")
    return TranslatedEvent(
        purchase=purchase, mandate=mandate, mandate_id=r.req(mn, "mandate_id", "mandate"),
        request_id=r.req(e, "request_id", "event"), deadline_at=r.wall_time(e, "deadline_at", "event"),
        received_at=r.wall_time(runtime, "received_at", "runtime") if runtime.get("received_at") else None,
        platform_period_spend_chf=r.amount(context, "approved_spend_in_period_chf", "context", optional=True),
        integrity=tuple(integrity))


def invalid_event_response(authorization_id: str, error: str, *, engine_version: str) -> dict[str, Any]:
    """The safe answer for an event that can't be read but whose live ID can (never approve)."""
    check = Check("event", "Purchase message", "integrity", "A readable purchase message", "Unreadable",
                  "I couldn't read this purchase request safely, so I'm asking you.", INVALID_EVENT)
    decision = Decision("step_up", (check,), (INVALID_EVENT,))
    body = explain(decision, authorization_id=authorization_id, engine_version=engine_version)
    body["evidence"] = [*body["evidence"],
                        {"check": "event", "label": "Parse error", "status": "integrity", "agreed": "A readable event",
                         "actual": html.escape(error)[:300], "reason_code": INVALID_EVENT}]
    return body


def request_from_envelope(envelope: Mapping[str, Any], *,
                          validate: Callable[[Mapping[str, Any]], None] | None = None
                          ) -> tuple[DecisionRequest, TranslatedEvent]:
    """A polled envelope → the request DecidePurchase handles. The one path from the platform into the engine,
    shared by the worker and the offline slice (LEASH-121); the run ID comes from the envelope."""
    data = envelope.get("data") if isinstance(envelope, Mapping) else None
    if not isinstance(data, Mapping):
        raise InvalidEvent("envelope/data: must be an object")
    translated = translate(data, validate=validate)
    run_id = envelope.get("run_id")
    request = DecisionRequest(purchase=translated.purchase, mandate=translated.mandate,
                              run_id=run_id if isinstance(run_id, str) else None, event=data,
                              deadline_at=translated.deadline_at,
                              platform_period_spend_chf=translated.platform_period_spend_chf)
    return request, translated
