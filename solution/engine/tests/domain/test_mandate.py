from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from leash.domain import mandate as m
from leash.domain.mandate import Bound, CompiledMandate, LooseningError, PeriodLimit, Rule

D = Decimal
INSTR = "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less."


def monitor() -> CompiledMandate:
    return CompiledMandate(
        instruction=INSTR,
        rules=(
            Rule(m.F_BILLING_CHF, "<=", D("400"), currency="CHF", scope="purchase"),
            Rule(m.F_ITEM_ID, "in", ("IT0017",)),
            Rule(m.F_PRIOR_PURCHASES, ">=", D("1")),
            Rule(m.F_UNREQUESTED_ITEMS, "=", D("0")),
            Rule(m.F_MAX_PURCHASES, "<=", D("1")),
        ),
        uncertainty="ask",
        notes=('"The monitor I chose" = catalogue item IT0017.',),
    )


def test_raising_limit_is_rejected():
    with pytest.raises(LooseningError, match="400"):
        monitor().tighten_max_per_order(D("450"))
    with pytest.raises(LooseningError):
        monitor().tighten_max_per_order(D("400"))  # not stricter either


def test_ask_to_approve_is_rejected():
    with pytest.raises(LooseningError):
        monitor().tighten_uncertainty("approve")
    decline = monitor().tighten_uncertainty("decline")
    assert decline.uncertainty == "decline"
    with pytest.raises(LooseningError):
        decline.tighten_uncertainty("ask")


def test_approve_to_ask_is_rejected_like_the_api():
    # The documented PATCH rule only allows moving to decline, even though ask is stricter than approve.
    approve = CompiledMandate(instruction="x", rules=(), uncertainty="approve")
    with pytest.raises(LooseningError):
        approve.tighten_uncertainty("ask")


def test_tightening_appends_and_never_replaces():
    before = monitor()
    after = before.tighten_max_per_order(D("350"))
    assert after.rules[: len(before.rules)] == before.rules
    assert after.rules[-1] == Rule(m.F_BILLING_CHF, "<=", D("350"), currency="CHF", scope="purchase")
    assert after.version == before.version + 1
    assert before.max_per_order == Bound(D("400"), inclusive=True)  # the original is unchanged


def test_strictest_rule_per_field_wins():
    mm = monitor().tighten(Rule(m.F_BILLING_CHF, "<", D("380"), currency="CHF", scope="purchase"))
    assert mm.max_per_order == Bound(D("380"), inclusive=False)
    mm = mm.tighten(Rule(m.F_PRIOR_PURCHASES, ">=", D("3")))
    assert mm.familiar_min == 3


def test_appending_a_rule_that_is_not_stricter_is_rejected():
    with pytest.raises(LooseningError):
        monitor().tighten(Rule(m.F_PRIOR_PURCHASES, ">=", D("0")))
    with pytest.raises(LooseningError):
        monitor().tighten(Rule(m.F_ITEM_ID, "in", ("IT0017", "IT0063")))  # widening the item list


def test_holds_every_compiled_constraint():
    mm = CompiledMandate(
        instruction="shoes",
        rules=(
            Rule(m.F_BILLING_CHF, "<=", D("200"), currency="CHF", scope="purchase"),
            Rule(m.F_BILLING_CHF, "<=", D("300"), currency="CHF", scope="period", period_days=7),
            Rule(m.F_MERCHANT_CATEGORY, "in", ("sporting_goods",)),
            Rule(m.F_PRIOR_PURCHASES, ">=", D("1")),
            Rule(m.F_ITEM_CATEGORY, "in", ("groceries", "household")),
            Rule(m.F_ITEM_ID, "in", ("IT0014",)),
            Rule(m.F_SIZE, "=", "43"),
            Rule(m.F_RETURN_DAYS, ">=", D("14")),
            Rule(m.F_UNREQUESTED_ITEMS, "=", D("0")),
            Rule(m.F_MAX_PURCHASES, "<=", D("1")),
            Rule(m.F_MAX_QUANTITY, "<=", D("1")),
            Rule(m.F_SESSION_RISK, "<", D("2")),
            Rule(m.F_SPLIT_CHECK, "=", "on"),
            Rule(m.F_FULFILLMENT, "in", ("delivery",)),
        ),
        uncertainty="ask",
        notes=("note",),
    )
    assert mm.max_per_order == Bound(D("200"), inclusive=True)
    assert mm.periods == (PeriodLimit(Bound(D("300"), inclusive=True), days=7),)
    assert mm.merchant_categories == frozenset({"sporting_goods"})
    assert mm.familiar_min == 1
    assert mm.item_categories == frozenset({"groceries", "household"})
    assert mm.target_item_ids == frozenset({"IT0014"})
    assert mm.sizes == frozenset({"43"})
    assert mm.min_return_days == 14
    assert mm.no_addons is True
    assert mm.max_purchases == 1
    assert mm.max_quantity == 1
    assert mm.session_risk_limit == Bound(D("2"), inclusive=False)
    assert mm.split_check is True
    assert mm.fulfillment == frozenset({"delivery"})
    assert (mm.uncertainty, mm.notes, mm.version) == ("ask", ("note",), 1)


def test_unconstrained_fields_are_none_or_off():
    mm = CompiledMandate(instruction="x", rules=(Rule(m.F_BILLING_CHF, "<=", D("20")),), uncertainty="ask")
    assert (mm.periods, mm.merchant_categories, mm.familiar_min, mm.target_item_ids) == ((), None, 0, None)
    assert (mm.sizes, mm.min_return_days, mm.no_addons, mm.max_purchases, mm.max_quantity) == (None, None, False, None, None)
    assert (mm.session_risk_limit, mm.split_check, mm.fulfillment) == (None, False, None)


def test_periods_keep_the_strictest_limit_per_window_length():
    mm = CompiledMandate(instruction="x", uncertainty="ask", rules=(
        Rule(m.F_BILLING_CHF, "<=", D("300"), scope="period", period_days=7),
        Rule(m.F_BILLING_CHF, "<=", D("1000"), scope="period", period_days=30),
        Rule(m.F_BILLING_CHF, "<=", D("250"), scope="period", period_days=7),
    ))
    assert mm.periods == (PeriodLimit(Bound(D("250"), True), 7), PeriodLimit(Bound(D("1000"), True), 30))


def test_set_rules_intersect_and_exclusions_accumulate():
    mm = CompiledMandate(instruction="x", uncertainty="ask", rules=(
        Rule(m.F_ITEM_CATEGORY, "in", ("groceries", "cosmetics")),
        Rule(m.F_ITEM_CATEGORY, "in", ("groceries",)),
        Rule(m.F_ITEM_CATEGORY, "not_in", ("gift_card",)),
    ))
    assert mm.item_categories == frozenset({"groceries"})
    assert mm.excluded_item_categories == frozenset({"gift_card"})


def test_unknown_fields_are_kept_not_dropped():
    odd = Rule("leash.something.new.v9", "=", "x")
    mm = CompiledMandate(instruction="x", rules=(odd,), uncertainty="ask")
    assert odd in mm.rules
    assert mm.unsupported_rules() == (odd,)


def test_is_immutable():
    mm = monitor()
    with pytest.raises(FrozenInstanceError):
        mm.uncertainty = "approve"  # type: ignore[misc]
    with pytest.raises(ValueError):
        CompiledMandate(instruction="x", rules=(), uncertainty="sometimes")  # type: ignore[arg-type]


def test_rule_validates_its_shape():
    with pytest.raises(ValueError):
        Rule(m.F_BILLING_CHF, "~=", D("1"))
    with pytest.raises(TypeError):
        Rule(m.F_BILLING_CHF, "<=", 400.0)  # money never as float
    with pytest.raises(ValueError):
        Rule(m.F_BILLING_CHF, "<=", D("300"), scope="period")  # period needs period_days


# ---- review round 1: the effective constraint must never be looser than a stored rule ----
def mandate(*rules: Rule) -> CompiledMandate:
    return CompiledMandate(instruction="x", rules=tuple(rules), uncertainty="ask")


def test_addon_ban_written_with_less_than_is_kept():
    assert mandate(Rule(m.F_UNREQUESTED_ITEMS, "<", D("1"))).no_addons is True
    assert mandate(Rule(m.F_UNREQUESTED_ITEMS, "<=", D("0"))).no_addons is True
    assert mandate().tighten(Rule(m.F_UNREQUESTED_ITEMS, "<", D("1"))).no_addons is True


def test_integer_thresholds_round_in_the_strict_direction():
    assert mandate(Rule(m.F_PRIOR_PURCHASES, ">=", D("0.5"))).familiar_min == 1
    assert mandate(Rule(m.F_PRIOR_PURCHASES, ">", D("2"))).familiar_min == 3
    assert mandate(Rule(m.F_RETURN_DAYS, ">=", D("13.5"))).min_return_days == 14
    assert mandate(Rule(m.F_MAX_PURCHASES, "<", D("1.5"))).max_purchases == 1
    assert mandate(Rule(m.F_MAX_QUANTITY, "<=", D("2.9"))).max_quantity == 2


def test_operators_a_field_does_not_support_are_never_half_applied():
    odd = (Rule(m.F_PRIOR_PURCHASES, "=", D("1")), Rule(m.F_BILLING_CHF, ">", D("5")),
           Rule(m.F_SIZE, "=", D("43")), Rule(m.F_BILLING_CHF, "<=", D("300"), period_days=7))
    mm = mandate(Rule(m.F_PRIOR_PURCHASES, ">=", D("3")), *odd)
    assert mm.familiar_min == 3
    assert set(mm.unsupported_rules()) == set(odd)
    assert mm.max_per_order is None and mm.sizes is None


def test_genuinely_stricter_rules_are_accepted():
    assert mandate().tighten(Rule(m.F_MERCHANT_CATEGORY, "not_in", ("gift_card",))).excluded_merchant_categories == frozenset({"gift_card"})
    assert mandate().tighten(Rule(m.F_FULFILLMENT, "!=", "pickup")).excluded_fulfillment == frozenset({"pickup"})
    assert mandate().tighten(Rule(m.F_ITEM_CATEGORY, "not_in", ("cosmetics",))).excluded_item_categories == frozenset({"cosmetics"})


def test_an_exact_duplicate_is_not_a_tightening():
    odd = Rule("leash.something.new.v9", "=", "x")
    with pytest.raises(LooseningError):
        mandate(odd).tighten(odd)
    with pytest.raises(LooseningError):
        monitor().tighten(monitor().rules[0])


# ---- review round 2: never silently looser, never silently ignored ----
@pytest.mark.parametrize("rule", [
    Rule(m.F_UNREQUESTED_ITEMS, "<=", D("2")),                                   # N1: a limit we don't enforce
    Rule(m.F_BILLING_CHF, "<=", D("100"), currency="EUR"),                       # N2: not CHF
    Rule(m.F_BILLING_CHF, "<=", D("300"), currency="USD", scope="period", period_days=7),
    Rule(m.F_PRIOR_PURCHASES, ">=", D("3"), scope="period", period_days=30),     # N3: windowed familiarity
    Rule(m.F_SESSION_RISK, "<", D("2"), scope="period", period_days=1),
    Rule(m.F_RETURN_DAYS, ">=", D("14"), currency="CHF"),
    Rule(m.F_BILLING_CHF, "<=", D("NaN")),                                       # not a finite number
    Rule(m.F_MAX_QUANTITY, "<=", D("Infinity")),
    Rule(m.F_FULFILLMENT, "=", ("delivery", "pickup")),                          # '=' needs one value
])
def test_ambiguous_rules_are_unsupported_not_misread(rule):
    mm = mandate(rule)
    assert mm.unsupported_rules() == (rule,)
    assert (mm.max_per_order, mm.periods, mm.familiar_min, mm.min_return_days) == (None, (), 0, None)
    assert (mm.no_addons, mm.max_quantity, mm.session_risk_limit, mm.fulfillment) == (False, None, None, None)


def test_chf_currency_on_billing_is_fine():
    assert mandate(Rule(m.F_BILLING_CHF, "<=", D("100"), currency="CHF")).max_per_order == Bound(D("100"), True)


# ---- review round 3 ----
@pytest.mark.parametrize("scope", ["lifetime", "day", "total", "PERIOD", "Purchase", ""])
def test_unknown_scope_is_rejected(scope):
    with pytest.raises(ValueError, match="scope"):
        Rule(m.F_BILLING_CHF, "<=", D("100"), scope=scope)  # type: ignore[arg-type]


@pytest.mark.parametrize("days", [1.5, True, D("7.5")])
def test_period_days_must_be_a_whole_number(days):
    with pytest.raises(TypeError):
        Rule(m.F_BILLING_CHF, "<=", D("300"), scope="period", period_days=days)  # type: ignore[arg-type]


def test_signalling_nan_is_rejected():
    with pytest.raises(ValueError):
        Rule(m.F_BILLING_CHF, "<=", D("sNaN"))


def test_tighten_max_needs_a_finite_amount():
    with pytest.raises(ValueError):
        monitor().tighten_max_per_order(D("NaN"))


def test_absurd_magnitudes_are_unsupported_not_hanging():
    rule = Rule(m.F_UNREQUESTED_ITEMS, "<", D("1E+100000000"))
    assert mandate(rule).unsupported_rules() == (rule,)
    big = Rule(m.F_BILLING_CHF, "<=", D("1E+100000000"))
    assert mandate(big).unsupported_rules() == (big,)
