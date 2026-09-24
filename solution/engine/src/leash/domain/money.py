"""Money as exact decimals. Never use float for amounts: CHF 300.00 must equal 300.00."""

from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")

# Fixed synthetic rates from data/fx_rates.csv (rate_date 2026-08-01, source synthetic_fixed).
FX_TO_CHF: dict[str, Decimal] = {
    "CHF": Decimal("1.000000"),
    "EUR": Decimal("0.950000"),
    "GBP": Decimal("1.120000"),
    "USD": Decimal("0.870000"),
}


class UnsupportedCurrency(ValueError):
    """The currency has no fixed rate in the challenge pack."""


def money(value: str | int | Decimal) -> Decimal:
    """Parse an amount and round it to cents with the pack's half-even rule."""
    if isinstance(value, float):
        raise TypeError("pass amounts as str, int or Decimal, never float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)


def to_chf(amount: Decimal, currency: str) -> Decimal:
    """Convert with the row's own currency, never the merchant's country."""
    try:
        rate = FX_TO_CHF[currency]
    except KeyError:
        raise UnsupportedCurrency(
            f"no fixed rate for currency {currency!r}; supported: {', '.join(FX_TO_CHF)}"
        ) from None
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_EVEN)


def fmt_chf(amount: Decimal) -> str:
    """Swiss display format with apostrophe thousands separators: CHF 1'142.70."""
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount).quantize(CENT, rounding=ROUND_HALF_EVEN):f}".split(".")
    grouped = f"{int(whole):,}".replace(",", "'")
    return f"CHF {sign}{grouped}.{cents}"
