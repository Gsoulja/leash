"""Shop text: instructions aimed at the agent or payment system are reported and ignored. They add
caution but never change a limit or any other check (merchant text is data, never instructions)."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot

AGREED = "Data only, never instructions"


def shop_text_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    if facts.injection_excerpt is not None:
        # The excerpt is shop text: evidence only, never in the message (which reaches the app's event stream).
        checks = [Check("text", "Shop text", "warn", AGREED, f"Contains instructions: {facts.injection_excerpt}",
                        "The shop's text tries to instruct the payment system. It was ignored; your rules still apply.",
                        "instruction_in_shop_text")]
    else:
        checks = [Check("text", "Shop text", "pass", AGREED, "No instructions found",
                        "No instructions aimed at the agent or payment system.")]
    if facts.oversized_text:
        checks.append(Check("text_size", "Shop text size", "warn", "Readable product text", "Too long to read fully",
                            "The shop's text is unusually long, so only part of it was read.", "oversized_merchant_text"))
    return checks
