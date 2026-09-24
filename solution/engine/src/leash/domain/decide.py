"""The decision core: a pure function from facts to a verdict with its evidence.

`decide()` runs every rule and keeps every check (nothing short-circuits, so explanations list all
reasons). `combine()` picks the most restrictive outcome: decline > step_up > approve. Warnings follow
the customer's uncertainty policy, except those that are not ordinary uncertainty: repeat, split, off-purpose
and already-bought orders (DEC-030) and an instruction in shop text (DEC-029) are never approved automatically:
step_up, or decline under a decline policy. Being at least as strict as an ordinary warning keeps the verdict
monotone when a rule swaps one warning for another. Integrity problems (a rule the engine can't enforce) never
approve.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .checks import Check, Verdict
from .facts import Facts
from .mandate import CompiledMandate, Uncertainty
from .purchase import Purchase
from .rules.basket import basket_rule
from .rules.duplicates import duplicates_rule
from .rules.familiar import familiar_rule
from .rules.fulfilment import fulfilment_rule
from .rules.period import period_rule
from .rules.price import price_rule
from .rules.returns import returns_rule
from .rules.session import session_rule
from .rules.shop_text import shop_text_rule
from .rules.shop_type import shop_type_rule
from .rules.single import single_rule
from .rules.size import size_rule
from .rules.unsupported import unsupported_rule
from .snapshot import Snapshot

RuleFn = Callable[[Purchase, CompiledMandate, Snapshot, Facts], list[Check]]

DEFAULT_RULES: tuple[RuleFn, ...] = (unsupported_rule, price_rule, period_rule, shop_type_rule, familiar_rule, fulfilment_rule,
                                     basket_rule, duplicates_rule, single_rule, session_rule, size_rule, returns_rule,
                                     shop_text_rule)

_ON_WARNING: dict[str, Verdict] = {"ask": "step_up", "decline": "decline", "approve": "approve"}
_STRICTNESS: dict[Verdict, int] = {"approve": 0, "step_up": 1, "decline": 2}
# Warnings that are never approved automatically: repeat, split, off-purpose and already-bought orders
# (DEC-023, DEC-030) and a shop trying to steer the agent (DEC-029). Treated like an integrity problem.
NEVER_APPROVE = frozenset({"possible_duplicate", "possible_split", "outside_purpose", "already_purchased",
                           "instruction_in_shop_text"})


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    checks: tuple[Check, ...]
    reason_codes: tuple[str, ...]
    alerts: tuple[str, ...] = ()  # operational alerts (info checks with a code), e.g. spend_counter_mismatch


def _verdict_of(check: Check, uncertainty: Uncertainty) -> Verdict:
    if check.status == "fail":
        return "decline"
    if check.status == "integrity" or (check.status == "warn" and check.reason_code in NEVER_APPROVE):
        return "decline" if uncertainty == "decline" else "step_up"
    if check.status == "warn":
        return _ON_WARNING[uncertainty]
    return "approve"


def combine(checks: Iterable[Check], uncertainty: Uncertainty) -> Verdict:
    return max((_verdict_of(c, uncertainty) for c in checks), key=_STRICTNESS.__getitem__, default="approve")


_FINDINGS = ("fail", "warn", "integrity")


def decide(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts,
           rules: Sequence[RuleFn] = DEFAULT_RULES) -> Decision:
    checks = _checks(purchase, mandate, snapshot, facts, rules)
    if facts.deterministic is not None:
        # Model output may never loosen or hide a deterministic finding (DEC-009): decide on the merged
        # facts' checks plus every finding the deterministic facts alone produce. The verdict is then never
        # less strict than the deterministic one, and the explanation keeps both readers' findings.
        base = decide(purchase, mandate, snapshot, facts.deterministic, rules).checks
        base_findings = [c for c in base if c.status in _FINDINGS]
        flagged = {c.key for c in base_findings}
        present = {(c.key, c.status, c.reason_code) for c in checks}
        checks = tuple(c for c in checks if c.status in _FINDINGS or c.key not in flagged) + tuple(
            c for c in base_findings if (c.key, c.status, c.reason_code) not in present)
    codes = tuple(dict.fromkeys(c.reason_code for c in checks if c.reason_code and c.status in _FINDINGS))
    alerts = tuple(dict.fromkeys(c.reason_code for c in checks if c.reason_code and c.status == "info"))
    return Decision(combine(checks, mandate.uncertainty), checks, codes, alerts)


def _checks(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts,
            rules: Sequence[RuleFn]) -> tuple[Check, ...]:
    return tuple(check for rule in rules for check in rule(purchase, mandate, snapshot, facts))
