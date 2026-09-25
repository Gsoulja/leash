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
    messages = {
        "instruction_in_shop_text": "The shop text tries to steer the agent. Your rules still apply.",
        "off_platform_payment": "The shop asks for payment outside this checkout. This needs your attention.",
        "shop_check_uncertain": "The shop safety check was inconclusive. Please review the checkout.",
    }
    for index, (code, evidence) in enumerate(facts.trust_findings):
        checks.append(Check(f"trust_{index}", "Shop safety", "integrity", AGREED, evidence,
                            messages.get(code, "The shop safety check needs your attention."), code))
    if facts.recurring_lines and (mandate.no_addons or
                                 bool(mandate.excluded_item_categories & {"subscriptions", "membership"})):
        checks.append(Check("recurring", "Recurring terms", "integrity", "No unauthorized extras",
                            f"Recurring terms on lines {sorted(facts.recurring_lines)}",
                            "The shop mentions recurring charges that may conflict with your permission.",
                            "unverified_recurring_terms"))
    for index, evidence in enumerate(facts.offer_outliers):
        checks.append(Check(f"offer_{index}", "Offer price", "warn", "Synthetic catalogue range", evidence,
                            "The unit price is outside the reference range. This does not prove fraud.",
                            "offer_price_outlier"))
    if facts.offer_unknown:
        checks.append(Check("offer_reference", "Offer price", "info", "Reference price when available",
                            f"No comparable reference for lines {list(facts.offer_unknown)}",
                            "Price plausibility could not be checked for every item."))
    return checks
