"""Hand-compiled mandates for the five public scenario instructions, as the customer would confirm them.

A stand-in for the instruction compiler (LEASH-065), used only by tests and offline replay. Each is a
list of hard_rules in the Viseca shape, using the registry's fields (DEC-004), so it travels through
the live event exactly like a compiled mandate would.
"""

import csv
from decimal import Decimal
from pathlib import Path

from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Rule

_CATALOGUE = Path(__file__).resolve().parents[4] / "data" / "scenario_catalogue.csv"
with _CATALOGUE.open(encoding="utf-8") as f:
    INSTRUCTIONS: dict[str, str] = {r["scenario_id"]: r["cardholder_instruction"] for r in csv.DictReader(f)}

D = Decimal


def _per_order(chf: str) -> Rule:
    return Rule(m.F_BILLING_CHF, "<=", D(chf), currency="CHF", scope="purchase")


MANDATES: dict[str, CompiledMandate] = {
    "SCEN0000": CompiledMandate(INSTRUCTIONS["SCEN0000"], uncertainty="ask", rules=(
        _per_order("20"),
        Rule(m.F_MERCHANT_CATEGORY, "in", ("groceries",)),
        Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)),
        Rule(m.F_PRIOR_PURCHASES, ">=", D("3")),        # "a shop I use regularly" (DEC-014)
        Rule(m.F_MAX_QUANTITY, "<=", D("1")),           # "one … item" (DEC-013)
        Rule(m.F_MAX_PURCHASES, "<=", D("1")),
    ), notes=('"Regularly" = at least 3 earlier purchases at that shop on this card.',
              '"Ordinary grocery item" = one item from the groceries category.')),
    "SCEN0001": CompiledMandate(INSTRUCTIONS["SCEN0001"], uncertainty="ask", rules=(
        _per_order("120"),
        Rule(m.F_BILLING_CHF, "<=", D("300"), currency="CHF", scope="period", period_days=7),
        Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)),
        Rule(m.F_FULFILLMENT, "in", ("delivery",)),     # "for delivery" (DEC-022)
        Rule(m.F_SPLIT_CHECK, "=", "on"),
    ), notes=('"Any seven days" = a rolling 7 × 24 h window on purchase time.',
              'Only paid orders count; an order waiting for you counts once you approve it.')),
    "SCEN0002": CompiledMandate(INSTRUCTIONS["SCEN0002"], uncertainty="ask", rules=(
        _per_order("200"),
        Rule(m.F_MERCHANT_CATEGORY, "in", ("sporting_goods",)),   # "specialist sports retailer"
        Rule(m.F_ITEM_ID, "in", ("IT0014",)),                    # road-running shoes
        Rule(m.F_SIZE, "=", "43"),
        Rule(m.F_RETURN_DAYS, ">=", D("14")),
        Rule(m.F_UNREQUESTED_ITEMS, "=", D("0")),
        Rule(m.F_MAX_PURCHASES, "<=", D("1")),           # "replace my shoes" = one pair (DEC-013)
        Rule(m.F_MAX_QUANTITY, "<=", D("1")),
    ), notes=('"Specialist sports retailer" = shop category sporting goods.',
              'Size and return window are read from the shop\'s text; if missing, I ask.')),
    "SCEN0003": CompiledMandate(INSTRUCTIONS["SCEN0003"], uncertainty="ask", rules=(
        _per_order("250"),
        Rule(m.F_ITEM_CATEGORY, "in", ("clothing",)),
        Rule(m.F_PRIOR_PURCHASES, ">=", D("1")),         # "shops I have used before" (DEC-015)
        Rule(m.F_SESSION_RISK, "<", D("2")),             # "someone other than me driving" (DEC-024)
    ), notes=('"Someone else driving" = new device, bursts, night-time or a first-time country; '
              'two or more risk points (a new device alone is two): I ask you.',)),
    "SCEN0004": CompiledMandate(INSTRUCTIONS["SCEN0004"], uncertainty="ask", rules=(
        _per_order("400"),
        Rule(m.F_ITEM_ID, "in", ("IT0017",)),            # "the 27-inch monitor I chose"
        Rule(m.F_PRIOR_PURCHASES, ">=", D("1")),         # "a seller I have bought from before"
        Rule(m.F_UNREQUESTED_ITEMS, "=", D("0")),        # "do not add anything I did not ask for"
        Rule(m.F_MAX_PURCHASES, "<=", D("1")),
        Rule(m.F_MAX_QUANTITY, "<=", D("1")),
        Rule(m.F_SPLIT_CHECK, "=", "on"),
    ), notes=('"The monitor I chose" = the 27-inch computer monitor (catalogue item IT0017).',)),
}
