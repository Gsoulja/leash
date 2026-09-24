"""Two clocks that must never mix.

SimTime is simulated purchase time: spending windows, velocity and familiarity use it.
WallTime is the real clock: response deadlines and the customer's answer window use it.
They are separate types so that mixing them is a mypy error and raises at runtime.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Self
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {value!r}")
    try:
        return dt.astimezone(timezone.utc)
    except OverflowError as exc:  # e.g. 9999-12-31T23:59:59-23:59 has no UTC instant
        raise ValueError(f"timestamp out of range in UTC: {value!r}") from exc


@dataclass(frozen=True, eq=False)
class _Instant:
    at: datetime

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            raise ValueError(f"{type(self).__name__} needs a timezone-aware datetime")
        object.__setattr__(self, "at", self.at.astimezone(timezone.utc))

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(_parse_utc(value))

    def _same_clock(self, other: object) -> datetime:
        if type(other) is type(self):
            return other.at
        if isinstance(other, _Instant):
            raise TypeError(f"cannot mix {type(self).__name__} with {type(other).__name__}")
        raise TypeError(f"cannot compare {type(self).__name__} with {type(other).__name__}")

    if not TYPE_CHECKING:
        # Defined for the runtime only: mypy skips --strict-equality for classes with a custom
        # __eq__, so hiding it lets mypy report `SimTime == WallTime` while runtime still raises.
        def __eq__(self, other: object) -> bool:
            if not isinstance(other, _Instant):
                return NotImplemented
            return self.at == self._same_clock(other)

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.at))

    def __lt__(self, other: Self) -> bool:
        return self.at < self._same_clock(other)

    def __le__(self, other: Self) -> bool:
        return self.at <= self._same_clock(other)

    def __gt__(self, other: Self) -> bool:
        return self.at > self._same_clock(other)

    def __ge__(self, other: Self) -> bool:
        return self.at >= self._same_clock(other)

    def __sub__(self, other: Self) -> timedelta:
        return self.at - self._same_clock(other)


@dataclass(frozen=True, eq=False)
class SimTime(_Instant):
    """Simulated scenario time (`authorization.timestamp`)."""

    def within(self, earlier: "SimTime", window: timedelta) -> bool:
        """True when `earlier` falls in the trailing window (self - window, self]."""
        return timedelta(0) <= self - earlier < window

    def local(self) -> datetime:
        return self.at.astimezone(ZURICH)


@dataclass(frozen=True, eq=False)
class WallTime(_Instant):
    """Real clock (`deadline_at`, `received_at`)."""

    @classmethod
    def now(cls) -> "WallTime":
        return cls(datetime.now(timezone.utc))
