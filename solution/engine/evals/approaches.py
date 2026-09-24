"""The approaches a benchmark run compares.

An "approach" is one way of answering the same 45 purchases: a fact reader, a set of compiled
mandates, or both. Adding one is adding an entry to APPROACHES — there is no plugin machinery.

`safety_gate` marks an approach that must never be less strict than the reference. It holds for any
reader that *adds* facts on top of the regex reader — DEC-009: a model may add caution, never remove
it. It does not hold for two kinds of approach:

  * one that deliberately changes the customer's uncertainty policy, where a looser answer is the point;
  * one that reads *less* than the reference. Losing a fact correctly turns a decline into a step_up
    (you cannot know the size is wrong if you never read the size), and a step_up is not permission.
    That is "missing is not permission" working, not a defect, so `blind` is measured but not gated.
"""

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from fixtures.mandates import MANDATES

from leash.adapters.regex_reader import RegexReader
from leash.domain.facts import Facts
from leash.domain.mandate import CompiledMandate
from leash.domain.purchase import Purchase
from leash.ports.fact_reader import Budget, FactReader


class BlindReader:
    """Establishes nothing. The control: it shows what reading merchant text actually buys us,
    and it is what every reader must beat on friction without ever beating it on strictness."""

    def read(self, purchase: Purchase, budget: Budget) -> Facts:
        return Facts(reader="blind", sizes=None, return_days=None, final_sale=None, injection_excerpt=None)


@dataclass(frozen=True)
class Approach:
    name: str
    description: str
    reader: Callable[[], FactReader] = RegexReader
    mandates: Mapping[str, CompiledMandate] = dataclasses.field(default_factory=lambda: MANDATES)
    safety_gate: bool = True  # False where being looser than the reference is correct, not a defect


def _policy(uncertainty: str) -> Mapping[str, CompiledMandate]:
    return {s: dataclasses.replace(mand, uncertainty=uncertainty) for s, mand in MANDATES.items()}


REFERENCE = "regex"

APPROACHES: dict[str, Approach] = {
    "regex": Approach("regex", "Deterministic regex reader, hand-compiled mandates (the reference)"),
    "blind": Approach("blind", "No merchant text read at all: the floor every reader must improve on",
                      reader=BlindReader, safety_gate=False),
    "policy-decline": Approach("policy-decline", "Uncertainty policy set to decline instead of ask",
                               mandates=_policy("decline"), safety_gate=False),
    "policy-approve": Approach("policy-approve", "Uncertainty policy set to approve instead of ask",
                               mandates=_policy("approve"), safety_gate=False),
}
