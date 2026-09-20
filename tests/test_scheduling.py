"""Time-window invariants: UTC storage, zone retention, and interval logic."""

from datetime import UTC, datetime, timedelta

import pytest

from health_assistant.domain.errors import (
    InvalidTimeRangeError,
    NaiveDatetimeError,
    UnknownTimeZoneError,
)
from health_assistant.domain.scheduling import TimeWindow, require_utc
from tests.support import at, window


def test_naive_datetimes_are_rejected() -> None:
    naive = datetime(2026, 1, 5, 12, 0)  # noqa: DTZ001 - naive input is the subject under test
    with pytest.raises(NaiveDatetimeError):
        require_utc(naive, "start")


def test_non_utc_input_is_normalized_to_utc() -> None:
    eastern = datetime(2026, 1, 5, 7, 0, tzinfo=UTC).astimezone(UTC)
    assert require_utc(eastern, "start").tzinfo is UTC


def test_window_end_must_follow_start() -> None:
    start = at(hours=1)
    with pytest.raises(InvalidTimeRangeError):
        TimeWindow(start=start, end=start, time_zone="America/Toronto")


def test_unknown_time_zone_is_rejected() -> None:
    with pytest.raises(UnknownTimeZoneError):
        TimeWindow(start=at(hours=1), end=at(hours=2), time_zone="Mars/Olympus_Mons")


def test_overlap_is_half_open() -> None:
    first = TimeWindow(start=at(hours=1), end=at(hours=2), time_zone="UTC")
    touching = TimeWindow(start=at(hours=2), end=at(hours=3), time_zone="UTC")
    crossing = TimeWindow(start=at(hours=1.5), end=at(hours=2.5), time_zone="UTC")

    assert not first.overlaps(touching)
    assert first.overlaps(crossing)
    assert crossing.overlaps(first)


def test_originating_zone_is_retained_for_local_rendering() -> None:
    subject = window(start_hours=24, time_zone="America/Toronto")
    assert subject.time_zone == "America/Toronto"
    assert subject.local_start().utcoffset() == timedelta(hours=-5)
