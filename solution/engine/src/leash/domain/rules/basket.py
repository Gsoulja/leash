"""Basket contents: requested items only (item mode) or items within the purpose (purpose mode),
no unrequested add-ons, and at most the requested quantity. Add-ons are recognised by the item's
category or the shop's text, never by the merchant's category."""

from dataclasses import replace
from itertools import combinations

from ..checks import Check
from ..facts import Facts
from ..mandate import F_ITEM_CATEGORY, F_ITEM_ID, CompiledMandate, Rule
from ..money import FX_TO_CHF, fmt_chf, to_chf
from ..purchase import LineItem, Purchase
from ..snapshot import Snapshot

ADDON_CATEGORIES = frozenset({"subscriptions", "membership", "gift_card"})
UNKNOWN_CATEGORY = "unknown"


def _words(category: str) -> str:
    return category.replace("_", " ")


def _is_addon(item: LineItem, facts: Facts) -> bool:
    return item.category in ADDON_CATEGORIES or item.line_no in facts.addon_lines


def _line_total(item: LineItem) -> str:
    total = item.unit_price * item.quantity
    if item.currency in FX_TO_CHF:
        return fmt_chf(to_chf(total, item.currency))
    return f"{item.currency} {total:.2f}"


def _requested(items: tuple[LineItem, ...], targets: frozenset[str] | None, purpose: frozenset[str] | None,
               no_addons: bool, facts: Facts) -> list[LineItem]:
    """The lines that hold what the customer asked for.

    A line that matches what was asked (a requested item ID, or an item in the wanted categories) is
    never an add-on because of its category. With neither stated, an add-on-category line is an add-on
    only next to an ordinary line. The shop's text can mark a line as an add-on only while another,
    unmarked line remains, or — when it flags every such line of a multi-line basket — the first line is the purchase.
    So a lone line is never "added", and more flags never loosen the verdict.
    """
    if targets is not None:
        pool = [i for i in items if i.item_id in targets]
    elif purpose is not None:
        pool = [i for i in items if i.category in purpose]
    else:
        pool = [i for i in items if i.category not in ADDON_CATEGORIES] or list(items)
    if not no_addons:
        return pool
    unmarked = [i for i in pool if i.line_no not in facts.addon_lines]
    if unmarked:
        return unmarked
    # The shop's text flags every candidate line. A lone line is never "added" to nothing; with several, the
    # first line is taken as the purchase and the others as add-ons, so more flags can only tighten (LEASH-034).
    return sorted(pool, key=lambda i: i.line_no)[:1]


_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}
_NARROWING = frozenset({F_ITEM_ID, F_ITEM_CATEGORY})


def _narrows(rule: Rule) -> bool:
    return rule.field in _NARROWING and rule.operator in ("in", "=")


def basket_rule(purchase: Purchase, mandate: CompiledMandate, snapshot: Snapshot, facts: Facts) -> list[Check]:
    """The basket judged under the mandate and under every subset of its narrowing rules (item-ID and
    item-category "in" rules, which decide what counts as asked for); the most severe result wins. Adding any
    rule only adds subsets, so a tightened mandate can never judge a basket more leniently (LEASH-034)."""
    if mandate.target_item_ids is None and mandate.item_categories is None and not mandate.excluded_item_categories \
            and not mandate.excluded_item_ids and mandate.max_quantity is None and not mandate.no_addons:
        return []
    narrowing = [r for r in mandate.rules if _narrows(r)]
    others = tuple(r for r in mandate.rules if not _narrows(r))
    worst = _judge(purchase, mandate, facts, mandate.target_item_ids, mandate.item_categories, mandate)
    for size in range(len(narrowing)):  # every proper subset; the full set is `worst` already
        for subset in combinations(narrowing, size):
            variant = replace(mandate, rules=others + subset)
            check = _judge(purchase, variant, facts, variant.target_item_ids, variant.item_categories, mandate)
            if _SEVERITY[check[0].status] > _SEVERITY[worst[0].status]:
                worst = check
    return worst


def _judge(purchase: Purchase, mandate: CompiledMandate, facts: Facts, targets: frozenset[str] | None,
           purpose: frozenset[str] | None, stated: CompiledMandate) -> list[Check]:
    excluded, excluded_ids = mandate.excluded_item_categories, mandate.excluded_item_ids
    max_qty = mandate.max_quantity
    items = purchase.items
    names = " + ".join(f"{i.quantity}× {i.name}" if i.quantity > 1 else i.name for i in items)
    wanted_ids, wanted_kinds = stated.target_item_ids, stated.item_categories  # the wording is the full mandate's
    agreed = ("Only the requested item" if wanted_ids is not None else
              f"Only {' or '.join(_words(c) for c in sorted(wanted_kinds))}" if wanted_kinds is not None
              else "Allowed items")
    if mandate.no_addons:
        agreed += ", nothing extra"
    if max_qty is not None:
        agreed += f", at most {max_qty}"

    def fail(detail: str, code: str) -> list[Check]:
        return [Check("items", "Items", "fail", agreed, names, detail, code)]

    def added(item: LineItem) -> list[Check]:
        return fail(f'The agent added "{item.name}" ({_line_total(item)}) that you didn\'t ask for.',
                    "unrequested_addon")

    for item in items:
        if item.category in excluded:
            return fail(f'"{item.name}" is {_words(item.category)}, which you excluded.', "excluded_item")
        if item.item_id in excluded_ids:
            return fail(f'"{item.name}" is an item you excluded.', "excluded_item")
    if purpose is not None and not purpose:  # item-category rules with no category in common: nothing fits
        return fail("Your item rules together allow no category at all, so nothing can be bought.", "outside_purpose")
    unknown = [i for i in items if i.category == UNKNOWN_CATEGORY] if excluded else []
    requested = _requested(items, targets, purpose, mandate.no_addons, facts)
    wanted_lines = {i.line_no for i in requested}
    extras = [i for i in items if i.line_no not in wanted_lines]
    if targets is not None and extras:
        extra = extras[0]
        if requested and (_is_addon(extra, facts) or mandate.no_addons):
            return added(extra)
        return fail(f'"{extra.name}" is not the item you asked for.', "item_mismatch")
    if targets is None and mandate.no_addons and requested:  # "added" needs something it was added to
        addons = [i for i in extras if _is_addon(i, facts)]
        if purpose is not None:  # nothing extra: a line outside what was asked for is extra, whatever its kind
            addons = addons or extras
        if addons:
            return added(addons[0])
    if max_qty is not None:
        qty = sum(i.quantity for i in items)  # every line counts: a narrower "asked for" never lowers the count
        if qty > max_qty:
            return fail(f"{qty} items in this order; you asked for at most {max_qty}.", "quantity_exceeded")
    if purpose is not None:
        outside = [i for i in items if i.category not in purpose]
        if outside:
            wanted = " or ".join(_words(c) for c in sorted(purpose))
            return [Check("items", "Items", "warn", agreed, names,
                          f'"{outside[0].name}" ({_words(outside[0].category)}) is outside {wanted}.', "outside_purpose")]
    if unknown:  # an unknown category is never read as "not excluded"
        return [Check("items", "Items", "warn", agreed, names,
                      f'"{unknown[0].name}" has no category, so I can\'t tell whether you excluded it.',
                      "unknown_item_category")]
    what = ("the item you asked for" if wanted_ids is not None else
            "what you asked for" if wanted_kinds is not None else "allowed items")
    return [Check("items", "Items", "pass", agreed, names, f"The basket holds only {what}.")]
