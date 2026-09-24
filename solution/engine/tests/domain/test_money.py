from decimal import Decimal

import pytest

from leash.domain.money import UnsupportedCurrency, fmt_chf, money, to_chf


def test_usd_converts_with_fixed_rate():
    assert to_chf(money("450.00"), "USD") == Decimal("391.50")


def test_eur_and_gbp_convert_with_fixed_rates():
    assert to_chf(money("199.00"), "EUR") == Decimal("189.05")
    assert to_chf(money("219.00"), "GBP") == Decimal("245.28")


def test_chf_converts_to_itself():
    assert to_chf(money("20.00"), "CHF") == Decimal("20.00")


def test_half_even_rounding():
    assert money("0.125") == Decimal("0.12")
    assert money("0.135") == Decimal("0.14")
    assert money("2.675") == Decimal("2.68")


def test_amounts_are_decimal_never_float():
    assert isinstance(money("12.3"), Decimal)
    assert isinstance(to_chf(money("1"), "EUR"), Decimal)
    with pytest.raises(TypeError):
        money(0.1)


def test_conversion_rounds_half_even_to_cents():
    # 0.35 × 0.95 = 0.3325 → 0.33; 0.05 × 0.87 = 0.0435 → 0.04
    assert to_chf(money("0.35"), "EUR") == Decimal("0.33")
    assert to_chf(money("0.05"), "USD") == Decimal("0.04")


def test_unsupported_currency_raises_clear_error():
    with pytest.raises(UnsupportedCurrency, match="JPY"):
        to_chf(money("10.00"), "JPY")


def test_swiss_display_format():
    assert fmt_chf(money("1142.7")) == "CHF 1'142.70"
    assert fmt_chf(money("20")) == "CHF 20.00"
    assert fmt_chf(money("1234567.891")) == "CHF 1'234'567.89"
    assert fmt_chf(money("-1142.70")) == "CHF -1'142.70"
