import re
from decimal import Decimal
from pathlib import Path

import pytest

from fixtures.mandates import INSTRUCTIONS, MANDATES
from leash.policy.registry import check_rules

ENGINE = Path(__file__).resolve().parents[2]


def numbers(text: str) -> dict[str, Decimal]:
    out = {}
    if m := re.search(r"CHF (\d+) or less|up to CHF (\d+)|no more than CHF (\d+)|order at or below CHF (\d+)", text):
        out["max"] = Decimal(next(g for g in m.groups() if g))
    if m := re.search(r"any seven days at or below CHF (\d+)", text):
        out["period"] = Decimal(m.group(1))
    if m := re.search(r"size (\d+)", text):
        out["size"] = Decimal(m.group(1))
    if m := re.search(r"within (\d+) days", text):
        out["return_days"] = Decimal(m.group(1))
    return out


def test_one_fixture_per_scenario_with_the_exact_instruction():
    assert set(MANDATES) == {"SCEN0000", "SCEN0001", "SCEN0002", "SCEN0003", "SCEN0004"}
    for sid, mm in MANDATES.items():
        assert mm.instruction == INSTRUCTIONS[sid]


@pytest.mark.parametrize("sid", ["SCEN0000", "SCEN0001", "SCEN0002", "SCEN0003", "SCEN0004"])
def test_every_fixture_is_at_least_as_strict_as_its_instruction_numbers(sid):
    mm, want = MANDATES[sid], numbers(INSTRUCTIONS[sid])
    assert mm.max_per_order is not None and mm.max_per_order.value <= want["max"]
    if "period" in want:
        assert [p.days for p in mm.periods] == [7] and mm.periods[0].limit.value <= want["period"]
    if "size" in want:
        assert mm.sizes == frozenset({str(want["size"])})
    if "return_days" in want:
        assert mm.min_return_days is not None and mm.min_return_days >= want["return_days"]
    assert mm.uncertainty == "ask"  # every instruction says "Ask me when uncertain"


@pytest.mark.parametrize("sid", ["SCEN0000", "SCEN0001", "SCEN0002", "SCEN0003", "SCEN0004"])
def test_fixtures_are_hard_rules_the_registry_accepts(sid):
    check_rules(MANDATES[sid].rules)
    assert MANDATES[sid].unsupported_rules() == ()


def test_full_policy_meaning():
    s0, s1, s2, s3, s4 = (MANDATES[f"SCEN000{i}"] for i in range(5))
    # SCEN0000: one ordinary grocery item from a shop used regularly (DEC-013, DEC-014)
    assert (s0.merchant_categories, s0.item_categories) == (frozenset({"groceries"}),) * 2
    assert (s0.familiar_min, s0.max_quantity, s0.max_purchases) == (3, 1, 1)
    # SCEN0001: household groceries for delivery, split orders watched (DEC-022)
    assert s1.item_categories == frozenset({"groceries"}) and s1.fulfillment == frozenset({"delivery"})
    assert s1.split_check and s1.familiar_min == 0
    # SCEN0002: road-running shoes from a specialist, returnable, nothing extra, one pair
    assert s2.merchant_categories == frozenset({"sporting_goods"}) and s2.target_item_ids == frozenset({"IT0014"})
    assert s2.no_addons and (s2.max_purchases, s2.max_quantity) == (1, 1) and s2.familiar_min == 0
    # SCEN0003: clothing from shops used before, session watched (DEC-024)
    assert s3.item_categories == frozenset({"clothing"}) and s3.familiar_min == 1
    assert s3.session_risk_limit is not None and s3.session_risk_limit.value == 2 and not s3.session_risk_limit.inclusive
    # SCEN0004: the chosen monitor from a known seller, nothing extra, once
    assert s4.target_item_ids == frozenset({"IT0017"}) and s4.familiar_min == 1
    assert s4.no_addons and (s4.max_purchases, s4.max_quantity) == (1, 1) and s4.split_check


def test_production_code_never_imports_fixtures():
    for path in (ENGINE / "src").rglob("*.py"):
        assert "fixtures" not in path.read_text(), path
