"""Resolves a customer's words for an item ("the monitor I chose") against the supplied catalogue, so a
permission conversation can name an exact item ID instead of inventing one.

Evidence lookup only: it never recommends, never buys and never picks a product on the customer's behalf.
A reference that reads as more than one catalogue row comes back as candidates plus a question; a reference
that reads as none comes back as a question alone. Only a single candidate is "resolved".

Shops are the merchants whose `merchant_category` equals the item's `item_category`, joined by ID (names can
be lookalikes: ME0022 "PixelHarbor" and ME0059 "PixelHarbour" are different shops). Three item categories —
`gift_card`, `membership`, `cosmetics` — describe the basket, not the shop, so they list no shops.

Catalogue prices are context for the conversation. The purchase price comes from the checkout, never here.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from pathlib import Path

from leash.adapters.pack.loader import Pack, _rows
from leash.policy.compiler import _tokens  # the same reading of a name the draft compiler uses: one matcher, not two

PRICE_NOTE = "catalogue range, context only; the checkout supplies the purchase price"


@dataclass(frozen=True)
class PriceRange:
    min_chf: Decimal
    typical_chf: Decimal
    max_chf: Decimal
    note: str = PRICE_NOTE


@dataclass(frozen=True)
class Shop:
    shop_id: str
    name: str


@dataclass(frozen=True)
class Candidate:
    item_id: str
    name: str
    category: str
    price_context_chf: PriceRange
    shops: tuple[Shop, ...]


@dataclass(frozen=True)
class Resolution:
    reference: str
    candidates: tuple[Candidate, ...]
    clarification: str | None

    @property
    def resolved(self) -> Candidate | None:
        """The one candidate, or None. Several candidates are a question for the customer, not a choice."""
        return self.candidates[0] if len(self.candidates) == 1 else None


class Catalogue:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    @cached_property
    def _shops(self) -> dict[str, tuple[Shop, ...]]:
        by_category: dict[str, list[Shop]] = {}
        for merchant_id, m in sorted(Pack(self.data_dir).merchants().items()):
            by_category.setdefault(m.category, []).append(Shop(merchant_id, m.name))
        return {category: tuple(shops) for category, shops in by_category.items()}

    @cached_property
    def _items(self) -> list[Candidate]:
        return [
            Candidate(
                item_id=r["item_id"], name=r["item_name"], category=r["item_category"],
                price_context_chf=PriceRange(Decimal(r["unit_price_min_chf"]), Decimal(r["unit_price_typical_chf"]),
                                             Decimal(r["unit_price_max_chf"])),
                shops=self._shops.get(r["item_category"], ()),
            )
            for r in _rows(self.data_dir / "items.csv")
        ]

    def search(self, *, name: str | None = None, category: str | None = None) -> Resolution:
        """Candidates whose name covers every word of `name` and whose category is `category`."""
        reference = ", ".join(part for part in (name, category) if part)
        wanted = _tokens(name or "")
        found = tuple(
            item for item in self._items
            if (category is None or item.category == category) and wanted <= _tokens(item.name)
        )
        return Resolution(reference, found, _clarification(reference, found))


def _clarification(reference: str, found: tuple[Candidate, ...]) -> str | None:
    if not found:
        return (f'I can\'t find "{reference}" in the catalogue. Could you name it another way, or give me the '
                f"item ID?")
    if len(found) > 1:
        names = ", ".join(f"{c.name} ({c.item_id})" for c in found)
        return f'"{reference}" could be more than one catalogue item: {names}. Which one do you mean?'
    return None
