"""Facts read from untrusted merchant text.

A reader (regex, Laya, …) turns item_details into Facts. `None` means "not stated", never zero or
yes. Model unavailability is information only (DEC-009); an injection or oversized text is a
caution (DEC-025). Facts carry no verdict: rules decide.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_TEXT_CHARS = 16_000
_SEPARATOR = " … "


def bounded_text(parts: Iterable[str], cap: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    """Join merchant text for reading, capped at `cap` characters (MAX_TEXT_CHARS per purchase).

    Oversized text is flagged, never silently cut: the head and the tail are both kept, so an
    instruction hidden at the end is still read.
    """
    text = " | ".join(parts)
    if len(text) <= cap:
        return text, False
    half = max(1, (cap - len(_SEPARATOR)) // 2)
    return text[:half] + _SEPARATOR + text[-half:], True


MIN_LINE_SHARE = 64


def bounded_lines(parts: list[str]) -> tuple[list[str], bool]:
    """Cap merchant text line by line so the purchase as a whole stays within MAX_TEXT_CHARS.

    Each line gets an equal share (at least MIN_LINE_SHARE). If there are too many lines for that,
    only the first and last lines are read and the rest come back empty; either way it is flagged.
    """
    n = len(parts)
    max_lines = MAX_TEXT_CHARS // MIN_LINE_SHARE
    read_idx = set(range(n)) if n <= max_lines else set(range(max_lines // 2)) | set(range(n - max_lines // 2, n))
    share = MAX_TEXT_CHARS // max(1, len(read_idx))
    out, oversized = [], n > max_lines
    for i, part in enumerate(parts):
        if i not in read_idx:
            out.append("")
            continue
        text, over = bounded_text([part], cap=share)
        out.append(text)
        oversized = oversized or over
    return out, oversized


@dataclass(frozen=True)
class Facts:
    reader: str
    sizes: tuple[str, ...] | None  # None = no size stated
    return_days: int | None  # None = no return window stated
    final_sale: bool | None  # None = nothing said either way
    injection_excerpt: str | None  # quoted text that tries to instruct the agent or payment system
    addon_lines: frozenset[int] = field(default=frozenset())  # line numbers that read as add-ons
    recurring_lines: frozenset[int] = field(default=frozenset())  # line numbers that mention recurring charges
    model_unavailable: bool = False
    oversized_text: bool = False
    # Set on merged facts: what the deterministic reader alone found. decide() never returns a verdict
    # less strict than these facts give (DEC-009).
    deterministic: "Facts | None" = None

    # Source-labelled raw evidence; no merchant text is executed or promoted to policy.
    trust_findings: tuple[tuple[str, str], ...] = ()
    offer_outliers: tuple[str, ...] = ()
    offer_unknown: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.reader:
            raise ValueError("facts must name the reader that produced them")
        if self.sizes is not None and not self.sizes:
            raise ValueError("use None for 'no size stated', not an empty tuple")
        if self.return_days is not None and self.return_days < 0:
            raise ValueError("return days can't be negative")

    @classmethod
    def not_stated(cls, reader: str, model_unavailable: bool = False) -> "Facts":
        return cls(reader=reader, sizes=None, return_days=None, final_sale=None, injection_excerpt=None,
                   model_unavailable=model_unavailable)

    @property
    def cautions(self) -> tuple[str, ...]:
        """Reason codes that must add caution (DEC-009, DEC-025)."""
        out = []
        if self.injection_excerpt is not None:
            out.append("instruction_in_shop_text")
        if self.oversized_text:
            out.append("oversized_merchant_text")
        return tuple(out)

    @property
    def information(self) -> tuple[str, ...]:
        """Notes for the evidence list that never change a verdict."""
        return (f"{self.reader} reader used: model unavailable",) if self.model_unavailable else ()
