"""Single purchase (DEC-013): 'buy the monitor I chose' is one successful purchase. After the allowed
number of approved purchases in this run, a further one asks the customer.

max_count.v2 (DEC-032) counts every approved purchase in the run, whatever the item: an item rule can
only narrow what is allowed, never what is counted, so tightening can't lift the count. Waiting,
declined and timed-out purchases don't count.
"""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot


def single_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    allowed, targets = mandate.max_purchases, mandate.target_item_ids
    if allowed is None:
        return []
    bought = [p.purchase for p in snapshot.prior
              if p.state == "approved" and p.purchase.authorization_id != purchase.authorization_id]
    if len(bought) < allowed:
        return []
    agreed = "Buy it once" if allowed == 1 else f"At most {allowed} purchases"
    if not bought:  # a limit of zero: the mandate allows no purchase of this at all
        return [Check("once", "Already bought", "warn", "No purchases", "0 approved",
                      "Your rule allows no purchases of this.", "already_purchased")]
    last = bought[-1]
    item = next((i for i in last.items if targets is None or i.item_id in targets), last.items[0])
    when = last.sim_time.local().strftime("%d %b %H:%M")
    return [Check("once", "Already bought", "warn", agreed, f"{len(bought)} approved",
                  f'You already bought "{item.name}" ({when}).', "already_purchased")]
