"""Mandates to and from the Viseca API's shape: hard_rules, uncertainty_policy, guidance, open_questions.

Every enforceable permission is a hard_rule (DEC-004); guidance is explanation only (the mandate's notes).
Rule values keep their exact meaning: amounts are written as JSON numbers (whole numbers as integers, as in
the docs) and read back through their text into Decimal. The API body carries no mandate version, so a
parsed mandate starts at version 1; versions are tracked by the mandate service (LEASH-061). Fields the registry doesn't know are kept, so the
engine enforces them as unsupported (never approve, DEC-005). Tightening only appends (DEC-006):
check_append_only refuses a change that removes or replaces an existing rule.

The rule format is checked here by hand (it mirrors data/schemas/authorization_event.schema.json
`mandate_rule`; tests/policy/test_hard_rules.py keeps the two in step).
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, cast, get_args

from leash.domain.mandate import CompiledMandate, Rule, Uncertainty

OPERATORS = frozenset({"<", "<=", "=", "!=", ">", ">=", "in", "not_in"})
CURRENCIES = frozenset({"CHF", "EUR", "GBP", "USD"})
SCOPES = frozenset({"purchase", "period"})
_KEYS = frozenset({"field", "operator", "value", "currency", "scope", "period_days"})


class HardRulesError(ValueError):
    """The API body doesn't follow the rule format."""


class AppendOnlyError(ValueError):
    """A change removes or replaces an existing rule (mandates only tighten by appending, DEC-006)."""


def _number(value: Decimal) -> int | float:
    if not value.is_finite():
        raise HardRulesError(f"{value} can't be written as a JSON number")
    if value == value.to_integral_value():
        return int(value)
    as_float = float(value)
    if Decimal(repr(as_float)) != value:
        raise HardRulesError(f"{value} can't be written as a JSON number without changing it")
    return as_float


def rule_to_api(rule: Rule) -> dict[str, Any]:
    value = rule.value
    body: dict[str, Any] = {"field": rule.field, "operator": rule.operator,
                            "value": _number(value) if isinstance(value, Decimal) else
                            list(value) if isinstance(value, tuple) else value}
    for key in ("currency", "scope", "period_days"):
        if getattr(rule, key) is not None:
            body[key] = getattr(rule, key)
    _check_rule(body)  # never emit anything the API's rule format can't hold (e.g. an unknown currency)
    return body


def _check_rule(body: Mapping[str, Any]) -> None:
    if not isinstance(body, Mapping):
        raise HardRulesError("a hard rule must be an object")
    extra = set(body) - _KEYS
    if extra or not {"field", "operator", "value"} <= set(body):
        raise HardRulesError("hard rule keys must be field, operator, value (+ currency, scope, period_days): "
                             f"{sorted(body)}")
    if not isinstance(body["field"], str) or not body["field"]:
        raise HardRulesError("field must be a non-empty string")
    for key in ("operator", "currency", "scope"):
        if body.get(key) is not None and not isinstance(body[key], str):
            raise HardRulesError(f"{key} must be a string")
    if body["operator"] not in OPERATORS:
        raise HardRulesError(f"unknown operator {body['operator']!r}")
    value = body["value"]
    if isinstance(value, bool) or not (isinstance(value, (int, float, str)) or
                                       (isinstance(value, list) and all(isinstance(v, str) for v in value))):
        raise HardRulesError("value must be a number, a string or a list of strings")
    if body.get("currency") is not None and body["currency"] not in CURRENCIES:
        raise HardRulesError(f"unknown currency {body['currency']!r}")
    if body.get("scope") is not None and body["scope"] not in SCOPES:
        raise HardRulesError(f"unknown scope {body['scope']!r}")
    days = body.get("period_days")
    whole = isinstance(days, int) or (isinstance(days, float) and days.is_integer())
    if days is not None and (isinstance(days, bool) or not whole or days < 1):
        raise HardRulesError("period_days must be a whole number of at least 1")


def rule_from_api(body: Mapping[str, Any]) -> Rule:
    _check_rule(body)
    value = body["value"]
    if isinstance(value, (int, float)):
        try:
            parsed: Any = Decimal(str(value))
        except InvalidOperation as exc:
            raise HardRulesError(f"not a number: {value!r}") from exc
        if not parsed.is_finite():
            raise HardRulesError(f"not a finite number: {value!r}")
    elif isinstance(value, list):
        parsed = tuple(value)
    else:
        parsed = value
    try:
        days = body.get("period_days")
        return Rule(body["field"], body["operator"], parsed, currency=body.get("currency"),
                    scope=body.get("scope"), period_days=int(days) if days is not None else None)
    except (TypeError, ValueError) as exc:
        raise HardRulesError(str(exc)) from exc


def mandate_to_api(mandate: CompiledMandate, *, open_questions: Iterable[str] = ()) -> dict[str, Any]:
    if not mandate.instruction:
        raise HardRulesError("a mandate needs the customer's instruction")
    return {"instruction": mandate.instruction, "hard_rules": [rule_to_api(r) for r in mandate.rules],
            "uncertainty_policy": mandate.uncertainty, "guidance": list(mandate.notes),
            "open_questions": list(open_questions)}


def mandate_from_api(body: Mapping[str, Any]) -> tuple[CompiledMandate, tuple[str, ...]]:
    policy = body.get("uncertainty_policy")
    if not isinstance(policy, str) or policy not in get_args(Uncertainty):
        raise HardRulesError(f"uncertainty_policy must be ask, decline or approve, not {policy!r}")
    rules = body.get("hard_rules")
    if not isinstance(rules, list):
        raise HardRulesError("hard_rules must be a list")
    instruction = body.get("instruction")
    if not isinstance(instruction, str) or not instruction:
        raise HardRulesError("instruction must be a non-empty string")
    guidance = tuple(str(g) for g in body.get("guidance") or ())
    questions = tuple(str(q) for q in body.get("open_questions") or ())
    uncertainty = cast(Uncertainty, policy)  # checked against the allowed values above
    return CompiledMandate(instruction, tuple(rule_from_api(r) for r in rules), uncertainty, notes=guidance), questions


def check_append_only(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]) -> None:
    """Raise unless `after` keeps every rule of `before`, unchanged and in order, and only adds new ones."""
    def canonical(rule: Mapping[str, Any]) -> str:  # explicit nulls don't count; True is never 1
        return json.dumps({k: v for k, v in rule.items() if v is not None}, sort_keys=True)

    if len(after) < len(before) or [canonical(r) for r in after[:len(before)]] != [canonical(r) for r in before]:
        raise AppendOnlyError("existing hard rules must stay unchanged; a tighter rule is added, never swapped in")
