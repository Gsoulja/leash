"""Rolling period limit: final approvals in this run over any window of simulated time that contains
the purchase (DEC-010). Cross-checked with the platform's counter: on a mismatch the higher total is used and an
operational alert is raised. The platform doesn't say which window its counter covers, so it applies to every
period rule; otherwise appending a second period rule would drop it and loosen the first. Waiting purchases are
paused, not spent."""

from datetime import timedelta

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..money import fmt_chf
from ..purchase import Purchase
from ..snapshot import Snapshot


def period_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    checks: list[Check] = []
    platform = snapshot.platform_period_spend_chf
    alert: Check | None = None
    for period in mandate.periods:
        window = timedelta(days=period.days)
        ours = snapshot.approved_spend_in_window(purchase.sim_time, window)
        paid = ours
        if platform is not None and platform != ours:
            paid = max(ours, platform)
            alert = alert or Check("period_counter", "Spend cross-check", "info", fmt_chf(ours), fmt_chf(platform),
                                   f"Our ledger says {fmt_chf(ours)}, the platform says {fmt_chf(platform)}; "
                                   "the higher value was used.", "spend_counter_mismatch")
        # "Any N days": every window that contains this purchase must stay within the limit, including
        # windows ending at an approval dated after it (purchases can be decided out of simulated order).
        later_ends = [p.purchase.sim_time for p in snapshot.prior if p.state == "approved"
                      and p.purchase.sim_time > purchase.sim_time and p.purchase.sim_time.within(purchase.sim_time, window)]
        paid = max([paid, *(snapshot.approved_spend_in_window(end, window) for end in later_ends)])
        total = paid + purchase.billing_amount_chf
        limit = period.limit
        ok = total <= limit.value if limit.inclusive else total < limit.value
        label = f"{period.days}-day total"
        agreed = f"{'≤' if limit.inclusive else '<'} {fmt_chf(limit.value)} in any {period.days} days"
        actual = f"{fmt_chf(paid)} paid + {fmt_chf(purchase.billing_amount_chf)} = {fmt_chf(total)}"
        if ok:
            checks.append(Check("period", label, "pass", agreed, actual,
                                f"{fmt_chf(total)} in the last {period.days} days, within {fmt_chf(limit.value)}."))
        else:
            checks.append(Check("period", label, "fail", agreed, actual,
                                f"This would bring the last {period.days} days to {fmt_chf(total)}, "
                                f"over your {fmt_chf(limit.value)} limit.", "over_period_limit"))
    return checks + ([alert] if alert else [])
