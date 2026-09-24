import threading
import time
from decimal import Decimal

import pytest

from factories import facts, line, mandate, max_per_order, purchase, snapshot
from leash.adapters.fallback_reader import FallbackReader, merge
from leash.domain import mandate as m
from leash.domain.decide import decide
from leash.domain.facts import Facts
from leash.domain.mandate import Rule


class Plenty:
    def remaining_seconds(self) -> float:
        return 30.0


class Fixed:
    def __init__(self, result: Facts | None = None, delay: float = 0.0, error: Exception | None = None):
        self.result, self.delay, self.error, self.calls = result, delay, error, 0

    def read(self, purchase, budget):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


REGEX = facts(reader="regex", sizes=("43",), return_days=30)
MODEL = facts(reader="laya", sizes=("43",), return_days=30)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def reader(primary, fallback=None, clock=None, timeout=0.05):
    return FallbackReader(primary, fallback or Fixed(REGEX), timeout_seconds=timeout, clock=clock or Clock())


def test_slow_reader_falls_back_after_one_second():
    release = threading.Event()

    class Hangs:
        def read(self, purchase, budget):
            release.wait(5)
            return MODEL

    r = FallbackReader(Hangs(), Fixed(REGEX))
    start = time.monotonic()
    out = r.read(purchase(), Plenty())
    elapsed = time.monotonic() - start
    release.set()
    assert 0.9 <= elapsed < 1.5
    assert out.reader == "regex" and out.model_unavailable
    assert out.sizes == ("43",)


def test_timeout_never_exceeds_the_remaining_budget():
    class Short:
        def remaining_seconds(self):
            return 0.02

    r = reader(Fixed(MODEL, delay=0.5), timeout=1.0)
    start = time.monotonic()
    out = r.read(purchase(), Short())
    assert time.monotonic() - start < 0.3 and out.model_unavailable


def test_errors_fall_back_too():
    out = reader(Fixed(error=RuntimeError("model down"))).read(purchase(), Plenty())
    assert (out.reader, out.model_unavailable) == ("regex", True)


def test_three_consecutive_failures_open_the_circuit_for_60_seconds():
    clock = Clock()
    primary = Fixed(error=RuntimeError("down"))
    r = reader(primary, clock=clock)
    for _ in range(3):
        r.read(purchase(), Plenty())
    assert primary.calls == 3
    out = r.read(purchase(), Plenty())
    assert primary.calls == 3 and out.model_unavailable  # open: the model isn't even tried
    clock.now += 59.9
    r.read(purchase(), Plenty())
    assert primary.calls == 3
    clock.now += 0.2  # 60 s later: try again (half-open)
    primary.error, primary.result = None, MODEL
    out = r.read(purchase(), Plenty())
    assert primary.calls == 4 and not out.model_unavailable


def test_a_success_resets_the_failure_count():
    clock = Clock()
    primary = Fixed(error=RuntimeError("down"))
    r = reader(primary, clock=clock)
    r.read(purchase(), Plenty()), r.read(purchase(), Plenty())
    primary.error, primary.result = None, MODEL
    r.read(purchase(), Plenty())
    primary.error = RuntimeError("down")
    r.read(purchase(), Plenty()), r.read(purchase(), Plenty())
    r.read(purchase(), Plenty())
    assert primary.calls == 6  # never opened: failures weren't consecutive


def test_a_failed_trial_after_the_open_period_reopens_at_once():
    clock = Clock()
    primary = Fixed(error=RuntimeError("down"))
    r = reader(primary, clock=clock)
    for _ in range(3):
        r.read(purchase(), Plenty())
    clock.now += 61
    r.read(purchase(), Plenty())  # trial fails
    r.read(purchase(), Plenty())
    assert primary.calls == 4


def test_facts_always_name_the_reader():
    assert reader(Fixed(MODEL)).read(purchase(), Plenty()).reader == "laya+regex"
    assert reader(Fixed(error=RuntimeError())).read(purchase(), Plenty()).reader == "regex"


def test_model_unavailable_is_information_only():
    out = reader(Fixed(error=RuntimeError())).read(purchase(), Plenty())
    decision = decide(purchase(), mandate(max_per_order("400")), snapshot(), out)
    assert decision.verdict == "approve"
    assert out.cautions == () and out.information == ("regex reader used: model unavailable",)


def test_missing_fact_follows_the_policy_even_when_the_model_states_it():
    no_size = facts(reader="regex", sizes=None)
    model = facts(reader="laya", sizes=("43",))
    out = reader(Fixed(model), Fixed(no_size)).read(purchase(), Plenty())
    assert out.sizes is None
    size43 = mandate(Rule(m.F_SIZE, "=", "43"))
    assert decide(purchase(), size43, snapshot(), out).verdict == "step_up"
    assert decide(purchase(), mandate(Rule(m.F_SIZE, "=", "43"), uncertainty="decline"), snapshot(),
                  out).verdict == "decline"


def test_a_definite_regex_injection_always_adds_caution():
    regex = facts(reader="regex", injection_excerpt="ignore previous instructions")
    for primary in (Fixed(facts(reader="laya")), Fixed(error=RuntimeError())):
        out = reader(primary, Fixed(regex)).read(purchase(), Plenty())
        assert "instruction_in_shop_text" in out.cautions


def test_merge_adds_model_findings():
    model = facts(reader="laya", addon_lines=frozenset({2}), recurring_lines=frozenset({3}),
                  injection_excerpt="pay now", final_sale=True)
    out = merge(facts(reader="regex", addon_lines=frozenset({1})), model)
    assert out.addon_lines == {1, 2} and out.recurring_lines == {3}
    assert out.injection_excerpt == "pay now" and out.final_sale is True


def test_merge_never_erases_or_loosens_a_deterministic_finding():
    regex = facts(reader="regex", sizes=("43",), return_days=14, final_sale=True, injection_excerpt="approve this",
                  addon_lines=frozenset({2}), oversized_text=True)
    model = facts(reader="laya", sizes=("44",), return_days=60, final_sale=False)
    out = merge(regex, model)
    assert out.sizes == ("43", "44")  # a conflict keeps both, so a wrong size still fails
    assert out.return_days == 14 and out.final_sale is True
    assert out.injection_excerpt == "approve this" and out.addon_lines == {2} and out.oversized_text
    assert merge(regex, facts(reader="laya", return_days=7)).return_days == 7  # stricter model value wins


@pytest.mark.parametrize("model_days", [None, 7, 14, 60])
def test_merged_verdict_is_never_less_strict_than_the_deterministic_one(model_days):
    returns14 = mandate(Rule(m.F_RETURN_DAYS, ">=", Decimal("14")))
    order = {"approve": 0, "step_up": 1, "decline": 2}
    for regex_days in (None, 7, 14, 60):
        regex = facts(reader="regex", return_days=regex_days)
        merged = merge(regex, facts(reader="laya", return_days=model_days))
        p = purchase(items=(line(),))
        assert order[decide(p, returns14, snapshot(), merged).verdict] >= \
            order[decide(p, returns14, snapshot(), regex).verdict]


def test_model_addon_flags_can_never_loosen_a_deterministic_decline():
    # Found in review: the model flags the requested line too, so the basket rule treats all as flagged.
    no_extras = mandate(Rule(m.F_UNREQUESTED_ITEMS, "<=", Decimal("0")))
    p = purchase(items=(line("IT0017", name="27in monitor", category="electronics"),
                        line("IT0070", line_no=2, name="Extended warranty add-on", category="electronics")))
    regex = facts(reader="regex", addon_lines=frozenset({2}))
    assert decide(p, no_extras, snapshot(), regex).verdict == "decline"
    merged = merge(regex, facts(reader="laya", addon_lines=frozenset({1})))
    decision = decide(p, no_extras, snapshot(), merged)
    assert decision.verdict == "decline" and "unrequested_addon" in decision.reason_codes


def test_merged_facts_keep_the_deterministic_facts_for_the_verdict_guard():
    regex = facts(reader="regex", sizes=("43",))
    assert merge(regex, facts(reader="laya")).deterministic == regex


def test_an_exhausted_budget_is_not_a_model_failure():
    class Spent:
        def remaining_seconds(self):
            return 0.0

    primary = Fixed(MODEL)
    r = reader(primary)
    for _ in range(5):
        assert r.read(purchase(), Spent()).model_unavailable
    assert r.read(purchase(), Plenty()).reader == "laya+regex" and primary.calls == 1  # circuit never opened


def test_half_open_allows_a_single_trial_call():
    clock = Clock()
    primary = Fixed(error=RuntimeError("down"))
    r = reader(primary, clock=clock, timeout=1.0)
    for _ in range(3):
        r.read(purchase(), Plenty())
    clock.now += 61
    primary.error, primary.result, primary.delay = None, MODEL, 0.3
    threads = [threading.Thread(target=r.read, args=(purchase(), Plenty())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert primary.calls == 4  # 3 failures + exactly one trial


def test_merged_explanation_keeps_every_finding_from_both_readers():
    # Review round 2: a tie dropped a deterministic finding; falling back dropped the model's warning.
    no_extras = mandate(Rule(m.F_UNREQUESTED_ITEMS, "<=", Decimal("0")))
    p = purchase(items=(line("IT0017", name="27in monitor", category="electronics"),
                        line("IT0070", line_no=2, name="Extended warranty add-on", category="electronics")))
    regex = facts(reader="regex", addon_lines=frozenset({2}), oversized_text=True)
    merged = merge(regex, facts(reader="laya", addon_lines=frozenset({1}), injection_excerpt="approve now"))
    for policy, verdict in (("decline", "decline"), ("ask", "decline")):
        d = decide(p, mandate(*no_extras.rules, uncertainty=policy), snapshot(), merged)
        assert d.verdict == verdict
        assert {"unrequested_addon", "oversized_merchant_text", "instruction_in_shop_text"} <= set(d.reason_codes)


def test_a_budget_cut_timeout_is_not_a_model_failure():
    class Nearly:
        def remaining_seconds(self):
            return 0.01

    primary = Fixed(MODEL, delay=0.05)
    r = reader(primary, timeout=1.0)
    for _ in range(4):
        assert r.read(purchase(), Nearly()).model_unavailable
    assert r.read(purchase(), Plenty()).reader == "laya+regex"  # the circuit never opened
