"""Session integrity (DEC-024), scored as leash.session.risk_score.v1: signals that someone other than
the customer may be driving the agent. Points: new device 2, 2+ other attempts in 10 min 2 (1 attempt 1),
night-time in Zurich (00:00–05:59) 1, first-time country 2. At or over the limit the customer is asked.
A missing device ID counts as a new device."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot

NIGHT_END_HOUR = 6


def session_points(purchase: Purchase, snapshot: Snapshot) -> list[tuple[str, int]]:
    """Each signal that fired, with its points."""
    points: list[tuple[str, int]] = []
    if purchase.device_id is None:
        points.append(("no device ID", 2))
    elif not snapshot.known_device(purchase.device_id):
        points.append((f"new device {purchase.device_id}", 2))
    n = purchase.recent_attempts_10m
    if n > 0:
        points.append((f"{n} other attempt{'s' if n != 1 else ''} in 10 minutes", 2 if n >= 2 else 1))
    local = purchase.sim_time.local()
    if local.hour < NIGHT_END_HOUR:
        points.append((f"{local.strftime('%H:%M')} at night in Zurich", 1))
    if not snapshot.known_country(purchase.merchant.country):
        points.append((f"first purchase in {purchase.merchant.country}", 2))
    return points


def session_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    limit = mandate.session_risk_limit
    if limit is None:
        return []
    signals = session_points(purchase, snapshot)
    score = sum(p for _, p in signals)
    ok = score <= limit.value if limit.inclusive else score < limit.value
    bound = f"{limit.value.normalize():f}"
    agreed = f"{'At most' if limit.inclusive else 'Under'} {bound} risk point{'' if bound == '1' else 's'}"
    actual = f"{score} point{'s' if score != 1 else ''}"
    listed = ", ".join(f"{text} ({p})" for text, p in signals)
    if ok:
        detail = "Usual device and pace." if not signals else f"Low session risk: {listed}."
        return [Check("session", "Session", "pass", agreed, actual, detail)]
    return [Check("session", "Session", "warn", agreed, actual,
                  f"This may not be you driving the agent: {listed}.", "session_risk")]
