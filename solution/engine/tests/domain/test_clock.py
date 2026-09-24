from datetime import timedelta, timezone
from pathlib import Path

import pytest
from mypy import api as mypy_api

from leash.domain.clock import SimTime, WallTime

WEEK = timedelta(days=7)


def test_seven_day_window_is_trailing_168_hours():
    now = SimTime.parse("2026-08-19T09:45:00Z")
    assert now.within(SimTime.parse("2026-08-12T09:45:01Z"), WEEK)  # 167:59:59 ago
    assert not now.within(SimTime.parse("2026-08-12T09:45:00Z"), WEEK)  # exactly 168 h ago
    assert now.within(now, WEEK)  # the same moment counts
    assert not now.within(SimTime.parse("2026-08-19T09:46:00Z"), WEEK)  # later is never "within"


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timezone"):
        SimTime.parse("2026-08-19T09:45:00")
    with pytest.raises(ValueError, match="timezone"):
        WallTime.parse("2026-08-19T09:45:00")


@pytest.mark.parametrize("cls", [SimTime, WallTime])
def test_parses_iso_utc_and_normalises_offsets(cls):
    a = cls.parse("2026-08-12T09:40:00Z")
    b = cls.parse("2026-08-12T11:40:00+02:00")
    assert a == b
    assert a.at.tzinfo == timezone.utc


def test_same_clock_subtracts_and_orders():
    a, b = SimTime.parse("2026-08-13T17:20:00Z"), SimTime.parse("2026-08-13T17:26:00Z")
    assert b - a == timedelta(minutes=6)
    assert a < b


@pytest.mark.parametrize(
    "op",
    [lambda s, w: s - w, lambda s, w: w - s, lambda s, w: s < w, lambda s, w: w >= s,
     lambda s, w: s == w, lambda s, w: s != w],
)
def test_mixing_clocks_raises_at_runtime(op):
    s, w = SimTime.parse("2026-08-12T09:40:00Z"), WallTime.parse("2026-08-12T09:40:00Z")
    with pytest.raises(TypeError, match="SimTime.*WallTime|WallTime.*SimTime"):
        op(s, w)


def test_mixing_clocks_is_a_mypy_error(tmp_path: Path):
    snippet = tmp_path / "mix.py"
    snippet.write_text(
        "from leash.domain.clock import SimTime, WallTime\n"
        "s = SimTime.parse('2026-08-12T09:40:00Z')\n"
        "w = WallTime.parse('2026-08-12T09:40:00Z')\n"
        "a = s - w\n"
        "b = s < w\n"
        "c = s.within(w, a)\n"
        "d = s == w\n"
        "e = s != w\n"
    )
    stdout, _, status = mypy_api.run([str(snippet), "--strict-equality", "--no-incremental"])
    assert status != 0
    errors = [line for line in stdout.splitlines() if ": error:" in line]
    assert {int(e.split(":")[1]) for e in errors} >= {4, 5, 6, 7, 8}, stdout


def test_local_time_is_europe_zurich():
    # 02:14 UTC in August is 04:14 in Zurich (summer time, UTC+2)
    local = SimTime.parse("2026-08-18T02:14:00Z").local()
    assert (local.hour, local.minute) == (4, 14)
    assert str(local.tzinfo) == "Europe/Zurich"
    # 23:30 UTC in January is 00:30 the next day in Zurich (winter time, UTC+1)
    winter = SimTime.parse("2026-01-10T23:30:00Z").local()
    assert (winter.day, winter.hour) == (11, 0)


@pytest.mark.parametrize("cls", [SimTime, WallTime])
@pytest.mark.parametrize("value", ["9999-12-31T23:59:59-23:59", "0001-01-01T00:00:00+23:59"])
def test_timestamp_outside_the_utc_range_is_a_value_error(cls, value):
    with pytest.raises(ValueError, match="out of range"):
        cls.parse(value)
