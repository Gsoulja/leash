"""The customer's confirmed permission, as the engine interprets it.

A mandate is an append-only list of rules in the Viseca `hard_rules` shape plus an uncertainty
policy. All rules hold at once, so every effective constraint is the strictest rule for its field.
Changes can only tighten: rules are appended, never removed or replaced (DEC-006), and uncertainty
can only move to `decline`. A change that would not make the policy stricter raises LooseningError.

Field names here are the engine's vocabulary; LEASH-117 turns them into a versioned registry.
"""

import math
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal, get_args

Uncertainty = Literal["ask", "decline", "approve"]
Operator = Literal["<", "<=", "=", "!=", ">", ">=", "in", "not_in"]
RuleValue = Decimal | str | tuple[str, ...]

# Fields from the Viseca event
F_BILLING_CHF = "authorization.billing_amount_chf"
F_FULFILLMENT = "authorization.fulfillment_method"
F_MERCHANT_CATEGORY = "merchant.merchant_category"
F_ITEM_CATEGORY = "items.item_category"
F_ITEM_ID = "items.item_id"
# Our own fields (DEC-004)
F_PRIOR_PURCHASES = "leash.merchant.prior_purchases.v1"
F_SIZE = "leash.items.size.v1"
F_RETURN_DAYS = "leash.order.return_days.v1"
F_UNREQUESTED_ITEMS = "leash.items.unrequested_count.v1"
F_MAX_PURCHASES = "leash.purchase.max_count.v2"  # v1 counted only the requested item (retired, DEC-032)
F_MAX_QUANTITY = "leash.items.max_quantity.v1"
F_SESSION_RISK = "leash.session.risk_score.v1"
F_SPLIT_CHECK = "leash.orders.split_check.v1"

class LooseningError(ValueError):
    """The change would not make the permission stricter."""


@dataclass(frozen=True)
class Rule:
    field: str
    operator: Operator
    value: RuleValue
    currency: str | None = None
    scope: Literal["purchase", "period"] | None = None
    period_days: int | None = None

    def __post_init__(self) -> None:
        if not self.field:
            raise ValueError("a rule needs a field")
        if self.operator not in get_args(Operator):
            raise ValueError(f"unknown operator {self.operator!r}")
        if isinstance(self.value, (float, bool)) or not isinstance(self.value, (Decimal, str, tuple)):
            raise TypeError(f"rule value must be Decimal, str or tuple of str, got {type(self.value).__name__}")
        if isinstance(self.value, tuple) and not all(isinstance(v, str) for v in self.value):
            raise TypeError("list values may contain strings only")
        if isinstance(self.value, Decimal) and self.value.is_snan():
            raise ValueError("signalling NaN is not a rule value")
        if self.scope not in (None, "purchase", "period"):
            raise ValueError(f"unknown scope {self.scope!r}; expected 'purchase', 'period' or None")
        if self.period_days is not None and (isinstance(self.period_days, bool) or not isinstance(self.period_days, int)):
            raise TypeError("period_days must be a whole number")
        if self.scope == "period" and not self.period_days:
            raise ValueError("a period rule needs period_days")
        if self.period_days is not None and self.period_days < 1:
            raise ValueError("period_days must be at least 1")


@dataclass(frozen=True, order=True)
class Bound:
    """An upper limit; `inclusive` means the value itself is allowed (<=)."""

    value: Decimal
    inclusive: bool

    def stricter(self, other: "Bound") -> "Bound":
        if self.value != other.value:
            return self if self.value < other.value else other
        return self if not self.inclusive else other


@dataclass(frozen=True)
class PeriodLimit:
    limit: Bound
    days: int


def _strictest(bounds: list[Bound]) -> Bound | None:
    result: Bound | None = None
    for b in bounds:
        result = b if result is None else result.stricter(b)
    return result


# Operators and value kinds each known field supports. Anything else is "unsupported": kept, never
# half-applied, and never allowed to approve (DEC-005).
MAX_RULE_NUMBER = Decimal("1e9")
_SETS = frozenset({"in", "not_in", "=", "!="})
FIELD_SPEC: dict[str, tuple[frozenset[str], str]] = {
    F_BILLING_CHF: (frozenset({"<", "<="}), "number"),
    F_FULFILLMENT: (_SETS, "text"),
    F_MERCHANT_CATEGORY: (_SETS, "text"),
    F_ITEM_CATEGORY: (_SETS, "text"),
    F_ITEM_ID: (_SETS, "text"),
    F_SIZE: (_SETS, "text"),
    F_PRIOR_PURCHASES: (frozenset({">=", ">"}), "number"),
    F_RETURN_DAYS: (frozenset({">=", ">"}), "number"),
    F_UNREQUESTED_ITEMS: (frozenset({"<", "<=", "="}), "number"),
    F_MAX_PURCHASES: (frozenset({"<", "<="}), "number"),
    F_MAX_QUANTITY: (frozenset({"<", "<="}), "number"),
    F_SESSION_RISK: (frozenset({"<", "<="}), "number"),
    F_SPLIT_CHECK: (frozenset({"="}), "text"),
}


def _lower_int(op: str, value: Decimal) -> int:
    """Smallest integer allowed by `op value` (strict direction for fractions)."""
    return math.floor(value) + 1 if op == ">" else math.ceil(value)


def _upper_int(op: str, value: Decimal) -> int:
    """Largest integer allowed by `op value`."""
    return math.ceil(value) - 1 if op == "<" else math.floor(value)


def supported(rule: Rule) -> bool:
    """True only when the engine enforces the rule exactly as written; anything else is unsupported."""
    spec = FIELD_SPEC.get(rule.field)
    if spec is None or rule.operator not in spec[0]:
        return False
    if spec[1] == "number" and not (isinstance(rule.value, Decimal) and rule.value.is_finite()
                                    and rule.value.copy_abs() <= MAX_RULE_NUMBER):
        return False  # NaN, infinity or an absurd magnitude is never a limit we can enforce
    if spec[1] == "text" and isinstance(rule.value, Decimal):
        return False
    if rule.operator in ("=", "!=") and isinstance(rule.value, tuple):
        return False  # '=' compares with one value; a list is ambiguous
    if rule.field == F_BILLING_CHF:
        if rule.currency not in (None, "CHF"):
            return False  # billing_amount_chf is CHF; a limit in another currency needs conversion we don't do
        if rule.period_days is not None and rule.scope != "period":
            return False  # a period length without scope=period is ambiguous
    elif rule.currency is not None or rule.scope is not None or rule.period_days is not None:
        return False  # scope, period and currency only have a meaning on the billing amount
    if rule.field == F_UNREQUESTED_ITEMS and isinstance(rule.value, Decimal):
        allowed = rule.value if rule.operator == "=" else _upper_int(rule.operator, rule.value)
        if allowed != 0:
            return False  # we enforce "no unrequested items", not a count above zero
    if rule.field == F_SPLIT_CHECK and rule.value != "on":
        return False
    return True


@dataclass(frozen=True)
class CompiledMandate:
    instruction: str
    rules: tuple[Rule, ...]
    uncertainty: Uncertainty
    notes: tuple[str, ...] = field(default=())
    version: int = 1

    def __post_init__(self) -> None:
        if self.uncertainty not in get_args(Uncertainty):
            raise ValueError(f"unknown uncertainty policy {self.uncertainty!r}")

    # ----- effective constraints: strictest supported rule per field -----
    def _rules(self, field_name: str, *ops: str) -> list[Rule]:
        return [r for r in self.rules if r.field == field_name and supported(r) and (not ops or r.operator in ops)]

    def _numbers(self, field_name: str, *ops: str) -> list[tuple[str, Decimal]]:
        return [(r.operator, r.value) for r in self._rules(field_name, *ops) if isinstance(r.value, Decimal)]

    def _billing(self, *, period_days: int | None) -> Bound | None:
        bounds = [Bound(r.value, inclusive=r.operator == "<=") for r in self._rules(F_BILLING_CHF)
                  if isinstance(r.value, Decimal) and r.period_days == period_days]
        return _strictest(bounds)

    def _lower(self, field_name: str) -> int | None:
        values = [_lower_int(op, v) for op, v in self._numbers(field_name)]
        return max(values) if values else None

    def _upper(self, field_name: str) -> int | None:
        values = [_upper_int(op, v) for op, v in self._numbers(field_name)]
        return min(values) if values else None

    def _allowed(self, field_name: str) -> frozenset[str] | None:
        sets = [frozenset(r.value) if isinstance(r.value, tuple) else frozenset({str(r.value)})
                for r in self._rules(field_name, "in", "=")]
        if not sets:
            return None
        allowed = sets[0]
        for s in sets[1:]:
            allowed &= s
        return allowed

    def _excluded(self, field_name: str) -> frozenset[str]:
        out: set[str] = set()
        for r in self._rules(field_name, "not_in", "!="):
            out |= set(r.value) if isinstance(r.value, tuple) else {str(r.value)}
        return frozenset(out)

    @property
    def max_per_order(self) -> Bound | None:
        return self._billing(period_days=None)

    @property
    def periods(self) -> tuple[PeriodLimit, ...]:
        days = sorted({r.period_days for r in self._rules(F_BILLING_CHF) if r.period_days})
        return tuple(PeriodLimit(b, d) for d in days if (b := self._billing(period_days=d)) is not None)

    @property
    def merchant_categories(self) -> frozenset[str] | None:
        return self._allowed(F_MERCHANT_CATEGORY)

    @property
    def excluded_merchant_categories(self) -> frozenset[str]:
        return self._excluded(F_MERCHANT_CATEGORY)

    @property
    def familiar_min(self) -> int:
        return self._lower(F_PRIOR_PURCHASES) or 0

    @property
    def item_categories(self) -> frozenset[str] | None:
        return self._allowed(F_ITEM_CATEGORY)

    @property
    def excluded_item_categories(self) -> frozenset[str]:
        return self._excluded(F_ITEM_CATEGORY)

    @property
    def target_item_ids(self) -> frozenset[str] | None:
        return self._allowed(F_ITEM_ID)

    @property
    def excluded_item_ids(self) -> frozenset[str]:
        return self._excluded(F_ITEM_ID)

    @property
    def sizes(self) -> frozenset[str] | None:
        return self._allowed(F_SIZE)

    @property
    def excluded_sizes(self) -> frozenset[str]:
        return self._excluded(F_SIZE)

    @property
    def min_return_days(self) -> int | None:
        return self._lower(F_RETURN_DAYS)

    @property
    def no_addons(self) -> bool:
        limit = self._upper(F_UNREQUESTED_ITEMS)
        return limit is not None and limit <= 0

    @property
    def max_purchases(self) -> int | None:
        return self._upper(F_MAX_PURCHASES)

    @property
    def max_quantity(self) -> int | None:
        return self._upper(F_MAX_QUANTITY)

    @property
    def session_risk_limit(self) -> Bound | None:
        return _strictest([Bound(v, inclusive=op == "<=") for op, v in self._numbers(F_SESSION_RISK)])

    @property
    def split_check(self) -> bool:
        return bool(self._rules(F_SPLIT_CHECK))

    @property
    def fulfillment(self) -> frozenset[str] | None:
        return self._allowed(F_FULFILLMENT)

    @property
    def excluded_fulfillment(self) -> frozenset[str]:
        return self._excluded(F_FULFILLMENT)

    def unsupported_rules(self) -> tuple[Rule, ...]:
        """Rules the engine can't evaluate: unknown field, operator or value kind (DEC-005)."""
        return tuple(r for r in self.rules if not supported(r))

    # ----- changes: tighten only -----
    def _snapshot(self) -> tuple[object, ...]:
        return (self.max_per_order, self.periods, self.merchant_categories, self.excluded_merchant_categories,
                self.familiar_min, self.item_categories, self.excluded_item_categories, self.target_item_ids,
                self.excluded_item_ids, self.sizes, self.excluded_sizes, self.min_return_days, self.no_addons,
                self.max_purchases, self.max_quantity, self.session_risk_limit, self.split_check, self.fulfillment,
                self.excluded_fulfillment, frozenset(self.unsupported_rules()))

    def tighten(self, *new_rules: Rule) -> "CompiledMandate":
        """Append rules. Refused if the result would be no stricter than before."""
        if not new_rules:
            raise LooseningError("nothing to add")
        duplicates = [r for r in new_rules if r in self.rules]
        if duplicates:
            raise LooseningError(f"already part of the permission: {duplicates[0].field} {duplicates[0].operator} {duplicates[0].value}")
        after = replace(self, rules=self.rules + tuple(new_rules), version=self.version + 1)
        if after._snapshot() == self._snapshot():
            raise LooseningError("these rules are not stricter than the current permission; "
                                 "create a new permission to loosen it")
        return after

    def tighten_max_per_order(self, new_max: Decimal) -> "CompiledMandate":
        if not new_max.is_finite():
            raise ValueError("the new limit must be a finite amount")
        current = self.max_per_order
        if current is not None and new_max >= current.value:
            raise LooseningError(f"the per-order limit is CHF {current.value}; it can only go down")
        return self.tighten(Rule(F_BILLING_CHF, "<=", new_max, currency="CHF", scope="purchase"))

    def tighten_uncertainty(self, new: Uncertainty) -> "CompiledMandate":
        # Mirrors the documented PATCH rule: approve or ask may move to decline, nothing else.
        if new != "decline" or self.uncertainty == "decline":
            raise LooseningError(f"uncertainty can only move to 'decline' (now {self.uncertainty!r})")
        return replace(self, uncertainty="decline", version=self.version + 1)
