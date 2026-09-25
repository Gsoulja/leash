"""The sentence a customer approves, generated from the `Rule` object (DEC-045, LEASH-174).

The model reads the customer's words; this is how the resulting rule is read back to them. The
sentence must come from the rule and nothing else — never from model prose — so that what the
customer consents to and what the engine enforces cannot drift apart.

The compiler writes its own, richer note when it parsed the rule itself (it can quote the customer's
phrasing). This is the fallback for every rule it did not parse, which since DEC-045 includes every
rule read in German, French or Italian.
"""

from decimal import Decimal
from collections.abc import Sequence

from leash.domain import mandate as m
from leash.domain.mandate import Rule
from leash.domain.money import fmt_chf
from leash.policy.registry import REGISTRY, describe_field


def _words(value: object) -> str:
    return str(value).replace("_", " ")


def _listed(rule: Rule) -> str:
    values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    return " or ".join(_words(v) for v in values)


def _count(rule: Rule) -> int:
    """A whole number for a rule the registry types as a number; 0 if it is not one."""
    if not isinstance(rule.value, Decimal):
        return 0
    # Match the engine's integer thresholds, including strict and fractional bounds.
    if rule.operator in (">", ">="):
        return m._lower_int(rule.operator, rule.value)
    return m._upper_int(rule.operator, rule.value)


def _amount(rule: Rule) -> str:
    # `period_days` decides, not `scope`: a model-supplied rule carries no scope bookkeeping, and the
    # engine itself keys the per-order limit off period_days being absent.
    opening = "At most" if rule.operator == "<=" else "Under"
    if rule.period_days:
        return f"{opening} {fmt_chf(rule.value)} across any {rule.period_days} days."
    return f"{opening} {fmt_chf(rule.value)} per order, delivery included."


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _allow_or_deny(rule: Rule, allowed: str, denied: str) -> str:
    return denied if rule.operator in ("not_in", "!=") else allowed


UNENFORCEABLE = "A restriction I cannot enforce, so I would ask you about this purchase."


def describe_rule(rule: Rule) -> str:
    """One plain sentence for one rule. Never contains a field name, an ID or an operator.

    A rule the engine cannot enforce says so, whatever its field: it can never approve anything
    (DEC-005), and reading it back as a permission would tell the customer the opposite.
    """
    if not m.supported(rule):
        return UNENFORCEABLE
    field, n = rule.field, _count(rule)
    if field == m.F_BILLING_CHF:
        return _amount(rule)
    if field == m.F_PRIOR_PURCHASES:
        if n <= 0:
            return "No earlier purchases at the shop are required."
        return ("Only shops you have paid before." if n <= 1
                else f"Only shops you have paid at least {n} times before.")
    if field == m.F_RETURN_DAYS:
        return f"Returnable for at least {n} {_plural(n, 'day', 'days')}; if the shop doesn't say, I ask you."
    if field == m.F_MAX_QUANTITY:
        return "One item per order." if n == 1 else f"At most {n} items per order."
    if field == m.F_MAX_PURCHASES:
        return "One purchase in total." if n == 1 else f"At most {n} purchases in total."
    if field == m.F_UNREQUESTED_ITEMS:
        return ("Nothing extra: no add-ons, protection plans or vouchers next to what you asked for."
                if n == 0 else f"At most {n} extra {_plural(n, 'item', 'items')} beyond what you asked for.")
    if field == m.F_SESSION_RISK:
        return f"Checkout risk score must be {'below' if rule.operator == '<' else 'at most'} {rule.value}."
    if field == m.F_SPLIT_CHECK:
        return ("Two orders at the same shop within an hour that together pass a limit ask you first.")
    if field == m.F_ITEM_CATEGORY:
        return _allow_or_deny(rule, f"Only {_listed(rule)} in the basket.",
                              f"Never {_listed(rule)} in the basket.")
    if field == m.F_ITEM_ID:
        return _allow_or_deny(rule, f"Only the item you chose ({_listed(rule)}).",
                              f"Never the item {_listed(rule)}.")
    if field == m.F_MERCHANT_CATEGORY:
        return _allow_or_deny(rule, f"Only shops of the kind: {_listed(rule)}.",
                              f"Never shops of the kind: {_listed(rule)}.")
    if field == m.F_FULFILLMENT:
        return _allow_or_deny(rule, f"For {_listed(rule)} only.", f"Never by {_listed(rule)}.")
    if field == m.F_SIZE:
        return _allow_or_deny(rule, f"Size {_listed(rule)}, as stated by the shop.",
                              f"Never size {_listed(rule)}.")
    return UNENFORCEABLE


#: The headings the review is read under (LEASH-146). A customer checks one boundary at a time —
#: what may be bought, for how much, where, how often, and what happens when something is unclear —
#: so the order here is the order they are read in.
GROUPS = ("item", "price", "merchant", "frequency", "uncertainty")

_GROUP = {
    m.F_BILLING_CHF: "price",
    # The split check guards the amount limit; the hour window is only how the evasion is spotted, so
    # a customer reads it next to the money it protects, not next to the order count.
    m.F_SPLIT_CHECK: "price",
    m.F_ITEM_ID: "item", m.F_ITEM_CATEGORY: "item", m.F_SIZE: "item",
    m.F_UNREQUESTED_ITEMS: "item", m.F_RETURN_DAYS: "item", m.F_FULFILLMENT: "item",
    m.F_MAX_QUANTITY: "item",
    m.F_MERCHANT_CATEGORY: "merchant", m.F_PRIOR_PURCHASES: "merchant",
    m.F_MAX_PURCHASES: "frequency",
    m.F_SESSION_RISK: "uncertainty",
}

_CHOICES = {
    m.F_MERCHANT_CATEGORY: "shop category", m.F_PRIOR_PURCHASES: "shop familiarity",
    m.F_ITEM_ID: "exact product", m.F_ITEM_CATEGORY: "product category", m.F_SIZE: "size",
    m.F_RETURN_DAYS: "return window", m.F_FULFILLMENT: "delivery or collection",
    m.F_MAX_QUANTITY: "item quantity", m.F_MAX_PURCHASES: "number of purchases",
    m.F_UNREQUESTED_ITEMS: "extra items", m.F_SESSION_RISK: "session risk threshold",
    m.F_SPLIT_CHECK: "split-order threshold", m.F_BILLING_CHF: "spending limit",
}


def group_of(field: str) -> str:
    """The heading a rule on this field is read under. Unknown fields read as uncertainty: an
    ungrouped line must still be shown, and a rule we cannot place is exactly one to ask about."""
    return _GROUP.get(field, "uncertainty")


def choice_label(field: str) -> str:
    """The field in the customer's words, for naming what they left open (DEC-045)."""
    return _CHOICES.get(field, describe_field(field))


def permission_review(rules: Sequence[Rule], uncertainty: str) -> dict[str, list[dict[str, str]]]:
    """Read the enforced rules back without claiming that warning rules are hard declines.

    Every line carries the heading it belongs under, so the review can be read boundary by boundary
    and nothing has to be re-derived from the sentence itself (LEASH-146).
    """
    follow: list[dict[str, str]] = []
    ask: list[dict[str, str]] = []

    def line(text: str, field: str) -> dict[str, str]:
        return {"text": text, "group": group_of(field)}

    for rule in rules:
        if rule.field == m.F_MAX_PURCHASES:
            text = f"Another order after {_count(rule)} approved purchase(s)."
        elif rule.field == m.F_SPLIT_CHECK:
            text = "Orders at the same shop within an hour that together exceed the spending limit."
        elif rule.field == m.F_SESSION_RISK:
            text = f"Checkout risk score {'at or above' if rule.operator == '<' else 'above'} {rule.value}."
        else:
            text = describe_rule(rule)
            if rule.field == m.F_RETURN_DAYS:
                text = f"Returnable for at least {_count(rule)} days."
            # A catalogue id is not something a customer can check, and it is an internal identifier
            # in the one place that must read as plain language. The exact ids stay in the platform
            # payload, which the review shows on request.
            # ponytail: the ids are dropped, not translated. Name the products here once the review is
            # given the catalogue it would need to look them up in.
            if rule.field == m.F_ITEM_ID and m.supported(rule):
                text = _allow_or_deny(rule, "Only the exact product you chose.",
                                      "Never the product you excluded.")
            follow.append(line(text, rule.field))
            continue
        if uncertainty == "decline":
            follow.append(line(f"Decline when triggered: {text}", rule.field))
        elif uncertainty == "approve" and rule.field == m.F_SESSION_RISK:
            follow.append(line(f"Session warning alone does not block approval: {text}", rule.field))
        else:
            ask.append(line(text, rule.field))
    if uncertainty == "ask":
        ask.append({"text": "Missing or unclear evidence needed to check the rules above.",
                    "group": "uncertainty"})
    else:
        follow.append({"text": f"When evidence is unclear: {uncertainty}; a missing fact is never "
                               "recorded as a match.", "group": "uncertainty"})
    intervention = "Suspected duplicates, off-purpose orders, merchant instructions or integrity problems."
    if uncertainty == "decline":
        follow.append({"text": f"Decline: {intervention}", "group": "uncertainty"})
    else:
        ask.append({"text": intervention, "group": "uncertainty"})
    fields = {r.field for r in rules}
    choose = [{"text": f"No explicit restriction on {choice_label(field)}; all other checks still apply.",
               "group": group_of(field)}
              for field in REGISTRY if field not in fields]
    return {"must_follow": _once(follow), "may_choose": _once(choose), "must_ask": _once(ask)}


def _once(lines: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """One boundary, read back once: a rule stated twice is still one thing the customer agreed to."""
    return list({line["text"]: line for line in lines}.values())
