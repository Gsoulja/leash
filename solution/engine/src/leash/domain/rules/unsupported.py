"""A confirmed mandate rule the engine can't evaluate is never silently unenforced (DEC-005).

Each one becomes an integrity check, which the combiner turns into step_up (decline under a decline
policy) and never approve, whatever the uncertainty policy says."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate, Rule
from ..purchase import Purchase
from ..snapshot import Snapshot

REASON = "unsupported_mandate_rule"


def _describe(rule: Rule) -> str:
    """The rule in plain words, as the customer confirmed it (currency and period included)."""
    value = ", ".join(rule.value) if isinstance(rule.value, tuple) else str(rule.value)
    if rule.currency:
        value = f"{rule.currency} {value}"
    text = f"{rule.field} {rule.operator} {value}"
    if rule.scope == "period" and rule.period_days:
        text += f" over {rule.period_days} days"
    elif rule.scope:
        text += f" per {rule.scope}"
    return text


def unsupported_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    return [Check("unsupported", "Rule I can't check", "integrity", "Every rule you confirmed is enforced",
                  f"Can't evaluate {r.field}",
                  f"One of your rules ({_describe(r)}) can't be checked by the engine, "
                  "so I'm not approving this on my own.", REASON)
            for r in mandate.unsupported_rules()]
