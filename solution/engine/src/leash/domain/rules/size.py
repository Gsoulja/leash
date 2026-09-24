"""Size: the size stated in the shop's text against the requested size. Not stated is missing, not a pass."""

from ..checks import Check
from ..facts import Facts
from ..mandate import CompiledMandate
from ..purchase import Purchase
from ..snapshot import Snapshot


def size_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    allowed, excluded = mandate.sizes, mandate.excluded_sizes
    if allowed is None and not excluded:
        return []
    agreed = "Size " + " or ".join(sorted(allowed)) if allowed is not None else "Not size " + ", ".join(sorted(excluded))
    if facts.sizes is None:
        return [Check("size", "Size", "warn", agreed, "Not stated", "The shop doesn't state a size.", "size_missing")]
    wrong = [s for s in facts.sizes if (allowed is not None and s not in allowed) or s in excluded]
    if wrong:
        wanted = " or ".join(sorted(allowed)) if allowed is not None else "another size"
        return [Check("size", "Size", "fail", agreed, f"Size {wrong[0]}",
                      f"Size {wrong[0]}, but you asked for size {wanted}.", "size_mismatch")]
    return [Check("size", "Size", "pass", agreed, f"Size {facts.sizes[0]}", f"Size {facts.sizes[0]}, as asked.")]
