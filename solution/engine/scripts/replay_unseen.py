"""The decision engine alone, on the generated unseen pack. No model, no database, no network.

Why it exists: a replay driven by the assistant measures the reading and the engine together, so a
misread instruction hides whichever checks it never produced — in the first run of this pack the
rolling-window logic never fired at all, because the model had dropped the per-order limit.

These mandates are our own compilation of the generated instructions, not an answer key: they say what
each instruction means, and the engine still reaches every verdict itself. Regenerate the pack with
scripts/make_pack.py first.

    uv run python scripts/replay_unseen.py
"""
import sys
from decimal import Decimal as D
from pathlib import Path
ROOT = Path("/home/mxlk/Documents/leash")
sys.path[:0] = [str(ROOT / "solution/engine/src"), str(ROOT / "solution/engine")]
from leash.adapters.pack.loader import Pack
from leash.application.replay import format_rows, replay
from leash.domain import mandate as m
from leash.domain.mandate import CompiledMandate, Rule

def per_order(v): return Rule(m.F_BILLING_CHF, "<=", D(v), currency="CHF", scope="purchase")

MANDATES = {
  "SCEN0900": (("höchstens CHF 45 pro Bestellung, nur Lieferung"), (
      per_order("45"), Rule(m.F_FULFILLMENT, "in", ("delivery",)),
      Rule(m.F_ITEM_CATEGORY, "in", ("pharmacy",)))),
  "SCEN0901": (("CHF 40 per order and CHF 100 this week"), (
      per_order("40"), Rule(m.F_BILLING_CHF, "<=", D("100"), currency="CHF", scope="period", period_days=7),
      Rule(m.F_FULFILLMENT, "in", ("delivery",)), Rule(m.F_ITEM_CATEGORY, "in", ("pet_care",)))),
  "SCEN0902": (("the hardcover I chose, a bookshop I have used before, at most CHF 60"), (
      per_order("60"), Rule(m.F_ITEM_ID, "in", ("IT0903",)), Rule(m.F_PRIOR_PURCHASES, ">=", D("1")),
      Rule(m.F_MERCHANT_CATEGORY, "in", ("books",)), Rule(m.F_MAX_QUANTITY, "<=", D("1")))),
  "SCEN0903": (("the chair I chose, CHF 250 or less, nothing added"), (
      per_order("250"), Rule(m.F_ITEM_ID, "in", ("IT0904",)), Rule(m.F_UNREQUESTED_ITEMS, "=", D("0")),
      Rule(m.F_SPLIT_CHECK, "=", "on"), Rule(m.F_MAX_PURCHASES, "<=", D("1")))),
  "SCEN0904": (("travel adapters for delivery, up to CHF 35 per order"), (
      per_order("35"), Rule(m.F_FULFILLMENT, "in", ("delivery",)),
      Rule(m.F_ITEM_CATEGORY, "in", ("electronics",)))),
}

pack = Pack(ROOT / "solution/demo/unseen-pack")
for sid, (instruction, rules) in MANDATES.items():
    mandate = CompiledMandate(instruction=instruction, rules=rules, uncertainty="ask")
    print(f"\n=== {sid}  {instruction}")
    print(format_rows(replay(pack, sid, mandate)))
