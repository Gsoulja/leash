"""Fulfilment method (DEC-022): 'for delivery' compiles to a fulfilment rule; any other method fails it.
A missing or unknown method is not permission: it follows the uncertainty policy."""

from ..checks import Check
from ..facts import Facts
from ..mandate import F_FULFILLMENT, CompiledMandate, supported
from ..purchase import Purchase
from ..snapshot import Snapshot

UNKNOWN = frozenset({"", "unknown"})


def _norm(value: object) -> frozenset[str]:
    values = value if isinstance(value, tuple) else (value,)
    return frozenset(str(v).strip().lower() for v in values)


def _limits(mandate: CompiledMandate) -> tuple[frozenset[str] | None, frozenset[str]]:
    """Allowed and excluded methods, each rule normalised before rules are combined (strictest wins)."""
    allowed: frozenset[str] | None = None
    excluded: frozenset[str] = frozenset()
    for rule in mandate.rules:
        if rule.field != F_FULFILLMENT or not supported(rule):
            continue
        if rule.operator in ("in", "="):
            allowed = _norm(rule.value) if allowed is None else allowed & _norm(rule.value)
        elif rule.operator in ("not_in", "!="):
            excluded |= _norm(rule.value)
    return (None if allowed is None else frozenset(a for a in allowed if a)), frozenset(e for e in excluded if e)


def fulfilment_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    # Both sides compared the same way: trimmed and lower-case (a "Pickup" exclusion still excludes pickup).
    allowed, excluded = _limits(mandate)
    if allowed is None and not excluded:
        return []
    method = (purchase.fulfillment or "").strip().lower()
    wanted = " or ".join(sorted(allowed)) if allowed else None
    agreed = (f"Only {wanted}" if wanted else "No method allowed" if allowed is not None else "Any method") + \
        (f", never {' or '.join(sorted(excluded))}" if excluded else "")
    if method in UNKNOWN:
        return [Check("fulfilment", "Fulfilment", "warn", agreed, "Not stated",
                      "The order doesn't say how it will be fulfilled.", "fulfilment_unknown")]
    if method in excluded:
        detail = f"This order is for {method}, which you excluded."
    elif allowed is not None and not allowed:
        detail = f"Your rules allow no fulfilment method, so this {method} order can't pass."
    elif allowed is not None and method not in allowed:
        detail = f"This order is for {method}, but you asked for {wanted}."
    else:
        return [Check("fulfilment", "Fulfilment", "pass", agreed, method.capitalize(), f"{method.capitalize()}, as agreed.")]
    return [Check("fulfilment", "Fulfilment", "fail", agreed, method.capitalize(), detail, "fulfilment_not_allowed")]
