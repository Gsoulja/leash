from decimal import Decimal
from pathlib import Path

import pytest

from leash.adapters.pack.catalogue import PRICE_NOTE, Catalogue

DATA = Path(__file__).resolve().parents[4] / "data"


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    return Catalogue(DATA)


def test_search_monitor_returns_it0017(catalogue):
    found = catalogue.search(name="monitor")
    it0017 = next(c for c in found.candidates if c.item_id == "IT0017")
    assert it0017.name == "27-inch computer monitor"
    assert it0017.category == "electronics"
    assert (it0017.price_context_chf.min_chf, it0017.price_context_chf.typical_chf,
            it0017.price_context_chf.max_chf) == (Decimal("140.00"), Decimal("270.00"), Decimal("650.00"))
    assert [s.shop_id for s in it0017.shops] == ["ME0022", "ME0023", "ME0024", "ME0059"]


def test_search_by_category_returns_items_with_ids_and_shops(catalogue):
    found = catalogue.search(category="electronics")
    assert {c.item_id for c in found.candidates} >= {"IT0017", "IT0046"}
    assert all(c.category == "electronics" and c.shops for c in found.candidates)


def test_ambiguous_reference_never_selects(catalogue):
    found = catalogue.search(name="monitor")  # IT0017 and IT0046 both read as a monitor
    assert {c.item_id for c in found.candidates} == {"IT0017", "IT0046"}
    assert found.resolved is None
    assert found.clarification and "monitor" in found.clarification


def test_running_shoes_stays_ambiguous_across_hyphenated_names(catalogue):
    found = catalogue.search(name="running shoes")
    assert {c.item_id for c in found.candidates} == {"IT0014", "IT0053", "IT0063"}
    assert found.resolved is None


def test_one_unambiguous_candidate_resolves(catalogue):
    found = catalogue.search(name="27-inch monitor")
    assert found.resolved is not None and found.resolved.item_id == "IT0017"
    assert found.clarification is None


def test_absent_reference_returns_a_clarification_and_no_candidates(catalogue):
    found = catalogue.search(name="flying carpet")
    assert found.candidates == ()
    assert found.resolved is None
    assert found.clarification and "flying carpet" in found.clarification


def test_unknown_category_returns_a_clarification(catalogue):
    found = catalogue.search(category="spaceships")
    assert found.candidates == ()
    assert found.clarification and "spaceships" in found.clarification


def test_price_range_is_context_only_and_never_a_purchase_price(catalogue):
    it0017 = catalogue.search(name="27-inch monitor").resolved
    assert it0017.price_context_chf.note == PRICE_NOTE
    assert not any(hasattr(it0017, f) for f in ("price", "amount", "unit_price", "billing_amount_chf"))


def test_shops_are_joined_by_id_so_lookalike_names_stay_separate(catalogue):
    shops = {s.shop_id: s.name for s in catalogue.search(name="27-inch monitor").resolved.shops}
    assert shops["ME0022"] == "PixelHarbor" and shops["ME0059"] == "PixelHarbour"


def test_item_categories_without_a_shop_kind_report_no_shops(catalogue):
    gift_cards = catalogue.search(category="gift_card")
    assert gift_cards.candidates and all(c.shops == () for c in gift_cards.candidates)
