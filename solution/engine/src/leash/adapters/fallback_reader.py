"""Wraps the primary (model) fact reader with a timeout, a deterministic fallback and a circuit breaker.

The deterministic reader always runs. The model gets at most 1 s (never more than the decision budget
left); on a timeout or error the deterministic facts are used, marked "model unavailable", which is
information only (DEC-009). Three consecutive failures open the circuit for 60 s, during which the
model isn't called; after that one trial call decides whether it closes again.

Merge rule (DEC-009): the model may add facts or warnings but never erase a deterministic finding and
never fill a fact the deterministic reader left missing. The merged facts also carry the deterministic
facts, and decide() never returns a verdict less strict than those alone give. That guard holds even
where a rule reads extra findings in a non-monotone way (e.g. add-on flags on every basket line).
"""

import threading
import time
from collections.abc import Callable
from dataclasses import replace

from leash.domain.facts import Facts
from leash.domain.purchase import Purchase
from leash.ports.fact_reader import Budget, FactReader

TIMEOUT_SECONDS = 1.0
FAILURE_THRESHOLD = 3
OPEN_SECONDS = 60.0


def merge(deterministic: Facts, model: Facts) -> Facts:
    """Combine both readers' facts; each field can only get stricter than the deterministic value."""
    sizes = deterministic.sizes
    if sizes is not None and model.sizes is not None:
        sizes = tuple(dict.fromkeys((*sizes, *model.sizes)))  # a conflict keeps both: a wrong size still fails
    return_days = deterministic.return_days
    if return_days is not None and model.return_days is not None:
        return_days = min(return_days, model.return_days)
    final_sale = True if model.final_sale is True else deterministic.final_sale
    return Facts(
        reader=f"{model.reader}+{deterministic.reader}",
        sizes=sizes,
        return_days=return_days,
        final_sale=final_sale,
        injection_excerpt=deterministic.injection_excerpt or model.injection_excerpt,
        addon_lines=deterministic.addon_lines | model.addon_lines,
        recurring_lines=deterministic.recurring_lines | model.recurring_lines,
        model_unavailable=False,
        oversized_text=deterministic.oversized_text or model.oversized_text,
        deterministic=deterministic,
    )


class FallbackReader:
    def __init__(self, primary: FactReader, fallback: FactReader, *, timeout_seconds: float = TIMEOUT_SECONDS,
                 failure_threshold: int = FAILURE_THRESHOLD, open_seconds: float = OPEN_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._primary, self._fallback = primary, fallback
        self._timeout, self._threshold, self._open_seconds = timeout_seconds, failure_threshold, open_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until: float | None = None
        self._trial_in_flight = False

    def read(self, purchase: Purchase, budget: Budget) -> Facts:
        deterministic = self._fallback.read(purchase, budget)
        timeout = min(self._timeout, budget.remaining_seconds())
        if timeout <= 0 or not self._may_call():  # no time left is not the model's failure
            return replace(deterministic, model_unavailable=True)
        model, failed = self._call_primary(purchase, budget, timeout)
        if model is None:
            # A timeout cut short by the decision budget says nothing about the model's health.
            self._record(success=False, counts=failed or timeout >= self._timeout)
            return replace(deterministic, model_unavailable=True)
        self._record(success=True)
        return merge(deterministic, model)

    def _may_call(self) -> bool:
        """Closed: always. Open: never. Half-open (open period over): one trial call at a time."""
        with self._lock:
            if self._open_until is None:
                return True
            if self._clock() < self._open_until or self._trial_in_flight:
                return False
            self._trial_in_flight = True
            return True

    def _record(self, *, success: bool, counts: bool = True) -> None:
        with self._lock:
            self._trial_in_flight = False
            if success:
                self._failures, self._open_until = 0, None
                return
            if not counts:
                return
            self._failures += 1
            if self._failures >= self._threshold:
                self._open_until = self._clock() + self._open_seconds

    def _call_primary(self, purchase: Purchase, budget: Budget, timeout: float) -> tuple[Facts | None, bool]:
        """The model's facts, or None; the flag is True when the model itself failed (not just ran out of time)."""
        result: list[Facts] = []
        failed: list[bool] = []

        def run() -> None:
            try:
                facts = self._primary.read(purchase, budget)
            except Exception:  # any model failure means "use the deterministic facts"
                failed.append(True)
                return
            if isinstance(facts, Facts):
                result.append(facts)
            else:
                failed.append(True)

        # A daemon thread: a hung model call is abandoned, never waited for.
        worker = threading.Thread(target=run, name="fact-reader", daemon=True)
        worker.start()
        worker.join(timeout)
        return (result[0], False) if result else (None, bool(failed))
