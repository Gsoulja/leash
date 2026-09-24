"""Deterministic fact reader: plain patterns over merchant text.

Always available, fast, and the baseline any model must beat (LEASH-076). It reads sizes, return
windows, final sale, add-on and recurring phrasing, and instructions aimed at an AI agent or payment
system. Text is capped per purchase (DEC-025); oversized text is flagged and its tail is still read.
"""

import re

from leash.domain.facts import Facts, bounded_lines
from leash.domain.purchase import Purchase
from leash.ports.fact_reader import Budget

NAME = "regex"

_SIZE = re.compile(r"\b(?:size|gr(?:ö|oe|o)sse|größe|taille|taglia)\s+(\d{1,2}(?:[.,]5)?|XXXS|XXS|XS|S|M|L|XL|XXL|XXXL)(?!\w|[.,]\d)", re.I)
_RETURN_DAYS = (
    re.compile(r"\breturn(?:s|able)?\b[^.;|]{0,40}?\bwithin\s+(\d{1,3})\s+days?\b", re.I),
    re.compile(r"\b(\d{1,3})[- ]days?\s+return", re.I),
    re.compile(r"\br(?:ü|ue)ckgabe\b[^.;|]{0,30}?\b(\d{1,3})\s+tag", re.I),
    re.compile(r"\bretours?\b[^.;|]{0,30}?\b(\d{1,3})\s+jours?\b", re.I),
    re.compile(r"\breso\b[^.;|]{0,30}?\b(\d{1,3})\s+giorni\b", re.I),
)
_FINAL_SALE = re.compile(r"\bfinal[- ]sale\b|\bno returns\b|\bnon-returnable\b", re.I)
_ADDON = re.compile(r"\badd-on\b|\bprotection plan\b|\bextended (?:warranty|cover|protection)\b|\bsubscription\b|\bmembership (?:fee|plan|upgrade|tier)\b", re.I)
_RECURRING = re.compile(r"\bbilled (?:monthly|weekly|yearly|annually|every)\b|(?<!non-)(?<!not )\brecurring\b|\bsubscription\b(?![^.;|]{0,20}\bone-off\b)", re.I)
_TARGET = r"(?:payment|purchase|transaction|charge)"
_INJECTION = (
    re.compile(r"\bignore\s+(?:all\s+|any\s+)?(?:previous\s+|prior\s+|earlier\s+)?(?:instructions\b|(?:spending|payment|purchase|budget)\s+(?:instructions|rules|limits)\b)", re.I),
    re.compile(r"\bdisregard\s+(?:all\s+|any\s+)?(?:previous\s+|prior\s+)?(?:instructions\b|(?:spending|payment|budget)\s+(?:rules|limits)\b)", re.I),
    re.compile(r"\bnote\s+(?:for|to)\s+(?:automated|ai)\s+(?:\w+\s+)?agents?\b", re.I),
    re.compile(r"\bcardholder\s+(?:has\s+)?pre-?authori[sz]ed\s+(?:our|this|the|us|up\s+to|payments?|purchases?)\b|\bpre-?authori[sz]ed\s+(?:our|this|the)\s+(?:store|shop|merchant|seller)\b", re.I),
    re.compile(r"(?:^|[.;:!?]\s*)system\s*:\s*(?:ignore|approve|authori[sz]e|override|disregard|you\s+must)\s", re.I),
    re.compile(r"\[\s*system\s*\]", re.I),
    re.compile(rf"\b(?:approve|authori[sz]e)\s+this\s+{_TARGET}\b|\bapprove\s+the\s+{_TARGET}\s+(?:immediately|now|without|automatically)\b", re.I),
    re.compile(r"\b(?:ai|automated)\s+(?:shopping\s+|purchasing\s+)?agents?\s*:", re.I),
    re.compile(r"\b(?:skip|bypass|override)\s+(?:the\s+)?(?:spending|budget|per-order|payment)\s+(?:limit|check)s?\b", re.I),
    re.compile(r"\b(?:limits?|checks?)\s+do(?:es)?\s+not\s+apply\b", re.I),
    re.compile(r"\bwithout\s+further\s+checks\b", re.I),
    re.compile(r"\bcardholder\s+is\s+unavailable\b", re.I),
    re.compile(r"\bignorier\w*\s+(?:alle\s+)?(?:vorherigen\s+)?anweisungen\b", re.I),
    re.compile(r"\bignore[rz]?\s+(?:toutes\s+)?les\s+instructions\b", re.I),
    re.compile(r"\bignora\s+(?:tutte\s+)?le\s+istruzioni\b", re.I),
)


def _excerpt(text: str, match: re.Match[str]) -> str:
    start, end = max(0, match.start() - 20), min(len(text), match.end() + 80)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


class RegexReader:
    def read(self, purchase: Purchase, budget: Budget) -> Facts:
        capped, oversized = bounded_lines([item.details for item in purchase.items])
        lines = list(zip((item.line_no for item in purchase.items), capped, strict=True))
        text = " | ".join(capped)

        sizes = tuple(dict.fromkeys(m.group(1).upper() for _, t in lines for m in _SIZE.finditer(t)))
        days = [int(m.group(1)) for _, t in lines for pattern in _RETURN_DAYS for m in pattern.finditer(t)]
        final_sale = True if _FINAL_SALE.search(text) else (False if days else None)

        injection = None
        for pattern in _INJECTION:
            match = pattern.search(text)
            if match:
                injection = _excerpt(text, match)
                break

        return Facts(
            reader=NAME,
            sizes=sizes or None,
            return_days=min(days) if days and not final_sale else None,
            final_sale=final_sale,
            injection_excerpt=injection,
            addon_lines=frozenset(no for no, t in lines if _ADDON.search(t)),
            recurring_lines=frozenset(no for no, t in lines if _RECURRING.search(t)),
            oversized_text=oversized,
        )
